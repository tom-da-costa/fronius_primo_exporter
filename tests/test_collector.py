from unittest.mock import MagicMock

from collector import FroniusCollector


def _make_collector(pf=None, inv=None, meter=None):
    client = MagicMock()
    client.get_power_flow.return_value = pf
    client.get_inverter_realtime_system.return_value = inv
    client.get_meter_realtime_system.return_value = meter
    return FroniusCollector(client, prefix="fronius_")


def _collect_names(collector):
    metrics = list(collector.collect())
    return {m.name for m in metrics if m is not None}


def test_collector_yields_metrics():
    collector = _make_collector(
        pf={
            "Site": {"P_PV": 100, "P_Grid": -50, "P_Load": 50, "P_Akku": 0},
            "Inverters": {"1": {"P": 100}},
        }
    )
    names = _collect_names(collector)
    assert "fronius_scrape_duration_seconds" in names
    assert any("scrape_errors" in n for n in names)
    assert "fronius_site_power_photovoltaic" in names


def test_scrape_errors_increment_on_none():
    collector = _make_collector(pf=None, inv=None)
    list(collector.collect())
    assert collector._scrape_errors == 2


def test_power_flow_all_site_metrics():
    collector = _make_collector(
        pf={
            "Site": {
                "P_PV": 1200,
                "P_Grid": -800,
                "P_Load": 400,
                "P_Akku": 0,
                "E_Day": 5000,
                "E_Year": 200000,
                "E_Total": 1000000,
                "rel_Autonomy": 75,
                "rel_SelfConsumption": 80,
            },
            "Inverters": {"1": {"P": 1200, "SOC": 85}},
        }
    )
    names = _collect_names(collector)
    for expected in (
        "fronius_site_power_photovoltaic",
        "fronius_site_power_grid",
        "fronius_site_power_load",
        "fronius_site_power_accu",
        "fronius_site_energy_day_wh",
        "fronius_site_energy_year_wh",
        "fronius_site_energy_total_wh",
        "fronius_site_autonomy_ratio",
        "fronius_site_self_consumption_ratio",
        "fronius_site_energy_consumption",
        "fronius_inverter_power",
        "fronius_inverter_soc",
    ):
        assert expected in names, f"{expected} missing"


def test_inverter_soc_emitted_when_present():
    collector = _make_collector(
        pf={
            "Site": {"P_PV": 100},
            "Inverters": {"1": {"P": 100, "SOC": 50}},
        }
    )
    metrics = list(collector.collect())
    soc = [m for m in metrics if m.name == "fronius_inverter_soc"]
    assert len(soc) == 1
    assert soc[0].samples[0].value == 0.5


def test_inverter_realtime_families():
    collector = _make_collector(
        inv={
            "PAC": {"Values": {"1": 1500}},
            "FAC": {"Values": {"1": 50.01}},
            "DAY_ENERGY": {"Values": {"1": 3000}},
            "YEAR_ENERGY": {"Values": {"1": 150000}},
            "TOTAL_ENERGY": {"Values": {"1": 900000}},
            "IDC": {"Values": {"1": 5.2}},
            "UDC": {"Values": {"1": 320.5}},
            "IDC_2": {"Values": {"1": 4.8}},
            "UDC_2": {"Values": {"1": 310.0}},
        }
    )
    names = _collect_names(collector)
    for expected in (
        "fronius_inverter_ac_power",
        "fronius_inverter_ac_frequency_hz",
        "fronius_inverter_energy_day_wh",
        "fronius_inverter_energy_year_wh",
        "fronius_inverter_energy_total_wh",
        "fronius_inverter_dc_current",
        "fronius_inverter_dc_voltage",
        "fronius_site_realtime_data_ac_frequency",
        "fronius_site_mppt_current_dc",
        "fronius_site_mppt_voltage",
    ):
        assert expected in names, f"{expected} missing"


def test_site_ac_frequency_value():
    collector = _make_collector(inv={"FAC": {"Values": {"1": 49.98}}})
    metrics = list(collector.collect())
    freq = [m for m in metrics if m.name == "fronius_site_realtime_data_ac_frequency"]
    assert len(freq) == 1
    assert freq[0].samples[0].value == 49.98


def test_site_ac_frequency_zero_when_absent():
    collector = _make_collector(inv={"PAC": {"Values": {"1": 0}}})
    metrics = list(collector.collect())
    freq = [m for m in metrics if m.name == "fronius_site_realtime_data_ac_frequency"]
    assert len(freq) == 1
    assert freq[0].samples[0].value == 0.0


def test_mppt_labels():
    collector = _make_collector(
        inv={
            "IDC": {"Values": {"1": 5.0}},
            "UDC": {"Values": {"1": 300.0}},
            "IDC_2": {"Values": {"1": 4.0}},
            "UDC_2": {"Values": {"1": 290.0}},
        }
    )
    metrics = list(collector.collect())
    mppt_i = [m for m in metrics if m.name == "fronius_site_mppt_current_dc"]
    assert len(mppt_i) == 1
    labels_set = {(s.labels["inverter"], s.labels["mppt"]) for s in mppt_i[0].samples}
    assert ("1", "1") in labels_set
    assert ("1", "2") in labels_set


def test_meter_families():
    collector = _make_collector(
        meter={
            "0": {
                "EnergyReal_WAC_Sum_Produced": 12000,
                "EnergyReal_WAC_Sum_Consumed": 8000,
            }
        }
    )
    names = _collect_names(collector)
    assert "fronius_meter_energy_produced_wh" in names
    assert "fronius_meter_energy_consumed_wh" in names

    metrics = list(collector.collect())
    prod = [m for m in metrics if m.name == "fronius_meter_energy_produced_wh"]
    assert prod[0].samples[0].value == 12000


def test_meter_smartmeter_keys():
    collector = _make_collector(
        meter={
            "0": {
                "SMARTMETER_ENERGYACTIVE_PRODUCED_SUM_F64": 5000,
                "SMARTMETER_ENERGYACTIVE_CONSUMED_SUM_F64": 3000,
            }
        }
    )
    metrics = list(collector.collect())
    cons = [m for m in metrics if m.name == "fronius_meter_energy_consumed_wh"]
    assert cons[0].samples[0].value == 3000


def test_energy_consumption_values():
    collector = _make_collector(
        pf={
            "Site": {"E_Day": 5000, "E_Year": 200000, "E_Total": 1000000},
            "Inverters": {},
        }
    )
    metrics = list(collector.collect())
    ec = [m for m in metrics if m.name == "fronius_site_energy_consumption"]
    assert len(ec) == 1
    values = {s.labels["time_frame"]: s.value for s in ec[0].samples}
    assert values["day"] == 5000
    assert values["year"] == 200000
    assert values["total"] == 1000000


def test_prefix_without_trailing_underscore():
    collector = FroniusCollector(MagicMock(), prefix="test")
    assert collector._prefix == "test_"
