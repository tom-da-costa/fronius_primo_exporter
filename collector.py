"""
Collecteur Prometheus pour les métriques Fronius.

À chaque scrape (/metrics), interroge la Fronius Solar API et expose
les données en métriques (power flow, inverter realtime, meter si présent).
"""

import logging
import threading
import time
from typing import Any, Iterator

from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    Metric,
)

from client import FroniusClient
from metrics import safe_float

logger = logging.getLogger(__name__)


class FroniusCollector:
    """Collecteur custom : appelle l'API Fronius à chaque collect() et yield les métriques."""

    def __init__(self, client: FroniusClient, prefix: str = "fronius_") -> None:
        self._client = client
        self._prefix = prefix if prefix.endswith("_") else prefix + "_"
        self._lock = threading.Lock()
        self._scrape_errors = 0
        self._last_scrape_duration_sec = 0.0

    def collect(self) -> Iterator[Metric]:
        with self._lock:
            start = time.perf_counter()

        pf = self._client.get_power_flow()
        inv = self._client.get_inverter_realtime_system()
        meter = self._client.get_meter_realtime_system()
        archive = self._client.get_archive_data()

        # Discover inverter IDs from PowerFlow and fetch per-device data
        inverter_ids: list[str] = []
        if pf:
            inverter_ids = [
                str(k)
                for k, v in (pf.get("Inverters") or {}).items()
                if isinstance(v, dict)
            ]
        inv_devices: dict[str, dict[str, Any]] = {}
        for dev_id in inverter_ids:
            dev_data = self._client.get_inverter_realtime_device(int(dev_id))
            if dev_data:
                inv_devices[dev_id] = dev_data

        with self._lock:
            self._last_scrape_duration_sec = time.perf_counter() - start
            if pf is None:
                self._scrape_errors += 1
            if inv is None:
                self._scrape_errors += 1

        p = self._prefix

        # Scrape meta
        g_duration = GaugeMetricFamily(
            p + "scrape_duration_seconds",
            "Durée du dernier scrape en secondes",
        )
        g_duration.add_metric([], self._last_scrape_duration_sec)
        yield g_duration
        c_errors = CounterMetricFamily(
            p + "scrape_errors_total",
            "Nombre d'erreurs de scrape",
        )
        c_errors.add_metric([], self._scrape_errors)
        yield c_errors

        # Power flow
        if pf:
            site = pf.get("Site") or {}
            invs = pf.get("Inverters") or {}
            yield from self._power_flow_families(p, site, invs)
        if inv:
            yield from self._inverter_realtime_families(p, inv, inv_devices)
        if archive:
            yield from self._archive_families(p, archive)
        if meter:
            yield from self._meter_families(p, meter)

    def _power_flow_families(
        self, p: str, site: dict[str, Any], inverters: dict[str, Any]
    ) -> Iterator[Metric]:
        gf = GaugeMetricFamily(
            p + "site_power_photovoltaic",
            "Power flow of the site photovoltaic in Watt",
            labels=[],
        )
        gf.add_metric([], safe_float(site.get("P_PV")))
        yield gf

        for name, key, help_suffix in (
            (
                "site_power_grid",
                "P_Grid",
                "Site power supplied to or provided from the grid in Watt",
            ),
            ("site_power_load", "P_Load", "Site power load in Watt"),
            (
                "site_power_accu",
                "P_Akku",
                "Site power supplied to or provided from the accumulator(s) in Watt",
            ),
            ("site_energy_day_wh", "E_Day", "Énergie du jour (Wh)"),
            ("site_energy_year_wh", "E_Year", "Énergie de l'année (Wh)"),
            ("site_energy_total_wh", "E_Total", "Énergie totale (Wh)"),
        ):
            g = GaugeMetricFamily(p + name, help_suffix, labels=[])
            g.add_metric([], safe_float(site.get(key)))
            yield g

        g = GaugeMetricFamily(
            p + "site_autonomy_ratio", "Autonomie relative (0–1)", labels=[]
        )
        g.add_metric([], safe_float(site.get("rel_Autonomy"), 0) / 100.0)
        yield g

        pv = safe_float(site.get("P_PV"))
        g = GaugeMetricFamily(
            p + "site_self_consumption_ratio",
            "Autoconsommation relative (0–1)",
            labels=[],
        )
        g.add_metric(
            [],
            (safe_float(site.get("rel_SelfConsumption"), 0) / 100.0)
            if pv != 0
            else 1.0,
        )
        yield g

        energy_consumption = GaugeMetricFamily(
            p + "site_energy_consumption",
            "Energy consumption in kWh",
            labels=["time_frame"],
        )
        energy_consumption.add_metric(["day"], safe_float(site.get("E_Day")))
        energy_consumption.add_metric(["year"], safe_float(site.get("E_Year")))
        energy_consumption.add_metric(["total"], safe_float(site.get("E_Total")))
        yield energy_consumption

        inv_power = GaugeMetricFamily(
            p + "inverter_power",
            "Power flow of the inverter in Watt",
            labels=["inverter"],
        )
        inv_soc = GaugeMetricFamily(
            p + "inverter_soc",
            "State of charge of the battery attached to the inverter in percent",
            labels=["inverter"],
        )
        for inv_id, inv_data in inverters.items():
            if isinstance(inv_data, dict):
                inv_power.add_metric([str(inv_id)], safe_float(inv_data.get("P")))
                if inv_data.get("SOC") is not None:
                    inv_soc.add_metric(
                        [str(inv_id)], safe_float(inv_data.get("SOC"), 0) / 100.0
                    )
        yield inv_power
        yield inv_soc

    def _inverter_realtime_families(
        self,
        p: str,
        data: dict[str, Any],
        devices: dict[str, dict[str, Any]] | None = None,
    ) -> Iterator[Metric]:
        devices = devices or {}

        # --- System-scope metrics (PAC, DAY_ENERGY, YEAR_ENERGY, TOTAL_ENERGY) ---
        key_to_metric = [
            ("PAC", p + "inverter_ac_power", "Puissance AC (W)", "device_id"),
            (
                "DAY_ENERGY",
                p + "inverter_energy_day_wh",
                "Énergie jour (Wh)",
                "device_id",
            ),
            (
                "YEAR_ENERGY",
                p + "inverter_energy_year_wh",
                "Énergie année (Wh)",
                "device_id",
            ),
            (
                "TOTAL_ENERGY",
                p + "inverter_energy_total_wh",
                "Énergie totale (Wh)",
                "device_id",
            ),
        ]
        for key, name, help_text, label in key_to_metric:
            obj = data.get(key)
            if not obj or not isinstance(obj, dict):
                continue
            g = GaugeMetricFamily(name, help_text, labels=[label])
            for device_id, val in (obj.get("Values") or {}).items():
                g.add_metric([str(device_id)], safe_float(val))
            yield g

        # --- Device-scope metrics (FAC, IDC, UDC) from per-device calls ---
        # Site-level AC frequency (single gauge, first device value)
        ac_freq = GaugeMetricFamily(
            p + "site_realtime_data_ac_frequency",
            "Site real time data AC frequency in Hz",
        )
        fac_val = 0.0
        for dev_data in devices.values():
            v = dev_data.get("FAC")
            if v is not None:
                fac_val = safe_float(v)
                break
        ac_freq.add_metric([], fac_val)
        yield ac_freq

        idc_fam = GaugeMetricFamily(
            p + "inverter_dc_current",
            "Courant DC MPPT (A)",
            labels=["device_id", "mppt"],
        )
        udc_fam = GaugeMetricFamily(
            p + "inverter_dc_voltage",
            "Tension DC MPPT (V)",
            labels=["device_id", "mppt"],
        )

        for dev_id, dev_data in devices.items():
            # MPPT 1 (IDC / UDC)
            for key, fam in (("IDC", idc_fam), ("UDC", udc_fam)):
                v = dev_data.get(key)
                if v is not None:
                    fam.add_metric([dev_id, "1"], safe_float(v))
            # MPPT 2..4 (IDC_2 / UDC_2, etc.)
            for i in range(2, 5):
                for key, fam in (
                    (f"IDC_{i}", idc_fam),
                    (f"UDC_{i}", udc_fam),
                ):
                    v = dev_data.get(key)
                    if v is not None:
                        fam.add_metric([dev_id, str(i)], safe_float(v))

        yield idc_fam
        yield udc_fam

    def _archive_families(self, p: str, data: dict[str, Any]) -> Iterator[Metric]:
        """Parse GetArchiveData response for per-string current/voltage."""
        mppt_current = GaugeMetricFamily(
            p + "site_mppt_current_dc",
            "Site mppt current DC in A",
            labels=["inverter", "mppt"],
        )
        mppt_voltage = GaugeMetricFamily(
            p + "site_mppt_voltage",
            "Site mppt voltage in V",
            labels=["inverter", "mppt"],
        )
        for raw_key, inverter_data in data.items():
            if not isinstance(inverter_data, dict):
                continue
            inv_id = raw_key.removeprefix("inverter/")
            channels = inverter_data.get("Data") or {}
            for mppt_idx, cur_key, vol_key in (
                ("1", "Current_DC_String_1", "Voltage_DC_String_1"),
                ("2", "Current_DC_String_2", "Voltage_DC_String_2"),
            ):
                cur_ch = channels.get(cur_key)
                if cur_ch and isinstance(cur_ch, dict):
                    vals = cur_ch.get("Values") or {}
                    if vals:
                        mppt_current.add_metric(
                            [inv_id, mppt_idx],
                            safe_float(next(iter(vals.values()))),
                        )
                vol_ch = channels.get(vol_key)
                if vol_ch and isinstance(vol_ch, dict):
                    vals = vol_ch.get("Values") or {}
                    if vals:
                        mppt_voltage.add_metric(
                            [inv_id, mppt_idx],
                            safe_float(next(iter(vals.values()))),
                        )
        yield mppt_current
        yield mppt_voltage

    def _meter_families(self, p: str, data: dict[str, Any]) -> Iterator[Metric]:
        produced = GaugeMetricFamily(
            p + "meter_energy_produced_wh",
            "Énergie produite (Wh)",
            labels=["device_id"],
        )
        consumed = GaugeMetricFamily(
            p + "meter_energy_consumed_wh",
            "Énergie consommée (Wh)",
            labels=["device_id"],
        )
        for device_id, meter in data.items():
            if not isinstance(meter, dict):
                continue
            prod = safe_float(
                meter.get("EnergyReal_WAC_Sum_Produced")
                or meter.get("SMARTMETER_ENERGYACTIVE_PRODUCED_SUM_F64")
            )
            cons = safe_float(
                meter.get("EnergyReal_WAC_Sum_Consumed")
                or meter.get("SMARTMETER_ENERGYACTIVE_CONSUMED_SUM_F64")
            )
            produced.add_metric([str(device_id)], prod)
            consumed.add_metric([str(device_id)], cons)
        yield produced
        yield consumed
