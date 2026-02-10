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
            yield from self._inverter_realtime_families(p, inv)
        if meter:
            yield from self._meter_families(p, meter)

    def _power_flow_families(
        self, p: str, site: dict[str, Any], inverters: dict[str, Any]
    ) -> Iterator[Metric]:
        gf = GaugeMetricFamily(
            p + "site_power_photovoltaic_watts",
            "Puissance PV site (W)",
            labels=[],
        )
        gf.add_metric([], safe_float(site.get("P_PV")))
        yield gf

        for name, key, help_suffix in (
            (
                "site_power_grid_watts",
                "P_Grid",
                "Puissance réseau (W), positif = export",
            ),
            ("site_power_load_watts", "P_Load", "Puissance charge site (W)"),
            (
                "site_power_accu_watts",
                "P_Akku",
                "Puissance accumulateur (W) si présent",
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

        inv_power = GaugeMetricFamily(
            p + "inverter_power_watts",
            "Puissance AC de l'onduleur (W)",
            labels=["inverter_id"],
        )
        inv_soc = GaugeMetricFamily(
            p + "inverter_soc_ratio",
            "State of charge batterie (0–1) si présente",
            labels=["inverter_id"],
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
        self, p: str, data: dict[str, Any]
    ) -> Iterator[Metric]:
        key_to_metric = [
            ("PAC", p + "inverter_ac_power_watts", "Puissance AC (W)", "device_id"),
            ("FAC", p + "inverter_ac_frequency_hz", "Fréquence AC (Hz)", "device_id"),
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

        idc_fam = GaugeMetricFamily(
            p + "inverter_dc_current_amps",
            "Courant DC MPPT (A)",
            labels=["device_id", "mppt"],
        )
        udc_fam = GaugeMetricFamily(
            p + "inverter_dc_voltage_volts",
            "Tension DC MPPT (V)",
            labels=["device_id", "mppt"],
        )
        for key, fam, mppt_label in (
            ("IDC", idc_fam, "1"),
            ("UDC", udc_fam, "1"),
        ):
            obj = data.get(key)
            if obj and isinstance(obj, dict):
                for device_id, val in (obj.get("Values") or {}).items():
                    fam.add_metric([str(device_id), mppt_label], safe_float(val))
        for i in range(1, 5):
            for key, fam in ((f"IDC_{i}", idc_fam), (f"UDC_{i}", udc_fam)):
                obj = data.get(key)
                if obj and isinstance(obj, dict):
                    for device_id, val in (obj.get("Values") or {}).items():
                        fam.add_metric([str(device_id), str(i)], safe_float(val))
        yield idc_fam
        yield udc_fam

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
