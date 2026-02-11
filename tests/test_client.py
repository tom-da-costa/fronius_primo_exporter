from unittest.mock import MagicMock, patch

import pytest
import requests

from client import FroniusClient, FroniusClientError


def test_client_strips_trailing_slash():
    c = FroniusClient(base_url="http://host/", timeout=1.0)
    assert c.base_url == "http://host"


def test_client_raises_on_request_error():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("500")
    with patch.object(c._session, "get", return_value=resp):
        with pytest.raises(FroniusClientError):
            c._get("/solar_api/v1/GetPowerFlowRealtimeData.fcgi")


def test_get_success():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"key": "value"}
    with patch.object(c._session, "get", return_value=resp):
        result = c._get("/path")
    assert result == {"key": "value"}


def test_get_invalid_json():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.side_effect = ValueError("bad json")
    with patch.object(c._session, "get", return_value=resp):
        with pytest.raises(FroniusClientError, match="Invalid JSON"):
            c._get("/path")


def test_body_data_success():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    api_response = {
        "Head": {"Status": {"Code": 0}},
        "Body": {"Data": {"P_PV": 1200}},
    }
    with patch.object(c, "_get", return_value=api_response):
        result = c._body_data("/path")
    assert result == {"P_PV": 1200}


def test_body_data_api_error():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    api_response = {
        "Head": {"Status": {"Code": 255, "Reason": "device not found"}},
        "Body": {"Data": {}},
    }
    with patch.object(c, "_get", return_value=api_response):
        with pytest.raises(FroniusClientError, match="API error"):
            c._body_data("/path")


def test_get_power_flow_success():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    expected = {"Site": {"P_PV": 100}}
    with patch.object(c, "_body_data", return_value=expected):
        result = c.get_power_flow()
    assert result == expected


def test_get_power_flow_returns_none_on_error():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    with patch.object(c, "_body_data", side_effect=FroniusClientError("fail")):
        result = c.get_power_flow()
    assert result is None


def test_get_inverter_realtime_system_success():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    expected = {"PAC": {"Values": {"1": 1500}}}
    with patch.object(c, "_body_data", return_value=expected):
        result = c.get_inverter_realtime_system()
    assert result == expected


def test_get_inverter_realtime_system_returns_none_on_error():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    with patch.object(c, "_body_data", side_effect=FroniusClientError("fail")):
        result = c.get_inverter_realtime_system()
    assert result is None


def test_get_meter_realtime_system_success():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    expected = {"0": {"EnergyReal_WAC_Sum_Produced": 5000}}
    with patch.object(c, "_body_data", return_value=expected):
        result = c.get_meter_realtime_system()
    assert result == expected


def test_get_meter_realtime_system_returns_none_on_error():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    with patch.object(c, "_body_data", side_effect=FroniusClientError("fail")):
        result = c.get_meter_realtime_system()
    assert result is None


def test_get_inverter_realtime_device_success():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    expected = {"FAC": 50.0, "IDC": 5.0, "UDC": 320.0}
    with patch.object(c, "_body_data", return_value=expected):
        result = c.get_inverter_realtime_device(1)
    assert result == expected


def test_get_inverter_realtime_device_returns_none_on_error():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    with patch.object(c, "_body_data", side_effect=FroniusClientError("fail")):
        result = c.get_inverter_realtime_device(1)
    assert result is None


def test_get_archive_data_success():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    expected = {
        "inverter/1": {
            "Data": {
                "Current_DC_String_1": {"Unit": "A", "Values": {"0": 13.0}},
            }
        }
    }
    with patch.object(c, "_body_data", return_value=expected):
        result = c.get_archive_data()
    assert result == expected


def test_get_archive_data_returns_none_on_error():
    c = FroniusClient(base_url="http://host", timeout=1.0)
    with patch.object(c, "_body_data", side_effect=FroniusClientError("fail")):
        result = c.get_archive_data()
    assert result is None
