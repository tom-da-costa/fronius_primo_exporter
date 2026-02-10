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
