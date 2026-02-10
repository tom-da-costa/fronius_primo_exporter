from unittest.mock import MagicMock

from collector import FroniusCollector


def test_collector_yields_metrics():
    client = MagicMock()
    client.get_power_flow.return_value = {
        "Site": {"P_PV": 100, "P_Grid": -50, "P_Load": 50, "P_Akku": 0},
        "Inverters": {"1": {"P": 100}},
    }
    client.get_inverter_realtime_system.return_value = None
    client.get_meter_realtime_system.return_value = None

    collector = FroniusCollector(client, prefix="fronius_")
    metrics = list(collector.collect())

    assert len(metrics) >= 2  # scrape_duration, scrape_errors + power flow
    names = [m.name for m in metrics if m is not None]
    assert "fronius_scrape_duration_seconds" in names
    assert any("scrape_errors" in n for n in names)
    assert "fronius_site_power_photovoltaic_watts" in names
