"""Client pour la Fronius Solar API (v1)."""

import logging
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_PATH = "/solar_api/v1"


class FroniusClientError(Exception):
    """Erreur de communication avec l'onduleur Fronius."""


class FroniusClient:
    """Client HTTP pour interroger un onduleur ou Datamanager Fronius (Solar API v1)."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def _get(self, path: str, timeout: float | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            r = self._session.get(url, timeout=timeout or self.timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise FroniusClientError(f"Request failed: {e}") from e
        except ValueError as e:
            raise FroniusClientError(f"Invalid JSON: {e}") from e

    def _body_data(self, path: str, timeout: float | None = None) -> dict[str, Any]:
        data = self._get(path, timeout=timeout)
        head = data.get("Head", {})
        if head.get("Status", {}).get("Code", 0) != 0:
            reason = head.get("Status", {}).get("Reason", "Unknown")
            raise FroniusClientError(f"API error: {reason}")
        return data.get("Body", {}).get("Data", {})

    def get_power_flow(self) -> dict[str, Any] | None:
        """GetPowerFlowRealtimeData.fcgi — flux de puissance site et onduleurs."""
        try:
            return self._body_data(f"{BASE_PATH}/GetPowerFlowRealtimeData.fcgi")
        except FroniusClientError as e:
            logger.warning("PowerFlow unreachable: %s", e)
            return None

    def get_inverter_realtime_system(self) -> dict[str, Any] | None:
        """GetInverterRealtimeData.cgi?Scope=System — données temps réel système."""
        try:
            return self._body_data(
                f"{BASE_PATH}/GetInverterRealtimeData.cgi?Scope=System"
            )
        except FroniusClientError as e:
            logger.warning("Inverter realtime (system) unreachable: %s", e)
            return None

    def get_inverter_realtime_device(self, device_id: int) -> dict[str, Any] | None:
        """GetInverterRealtimeData.cgi?Scope=Device — données par onduleur (IDC, UDC, FAC…)."""
        try:
            return self._body_data(
                f"{BASE_PATH}/GetInverterRealtimeData.cgi"
                f"?Scope=Device&DeviceId={device_id}"
                f"&DataCollection=CommonInverterData"
            )
        except FroniusClientError as e:
            logger.warning(
                "Inverter realtime (device %s) unreachable: %s", device_id, e
            )
            return None

    def get_archive_data(self) -> dict[str, Any] | None:
        """GetArchiveData.cgi — données archive (Current/Voltage DC String par onduleur)."""
        now = datetime.now(tz=timezone.utc)
        # Round down to 5-minute boundary
        truncated = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
        start = truncated.isoformat()
        end_dt = truncated.replace(minute=truncated.minute + 5)
        end = end_dt.isoformat()
        try:
            return self._body_data(
                f"{BASE_PATH}/GetArchiveData.cgi?Scope=System"
                f"&Channel=Voltage_DC_String_1"
                f"&Channel=Current_DC_String_1"
                f"&Channel=Voltage_DC_String_2"
                f"&Channel=Current_DC_String_2"
                f"&HumanReadable=false"
                f"&StartDate={start}"
                f"&EndDate={end}",
                timeout=30.0,
            )
        except FroniusClientError as e:
            logger.warning("Archive data unreachable: %s", e)
            return None

    def get_meter_realtime_system(self) -> dict[str, Any] | None:
        """GetMeterRealtimeData.cgi?Scope=System — données compteur si présent."""
        try:
            return self._body_data(f"{BASE_PATH}/GetMeterRealtimeData.cgi?Scope=System")
        except FroniusClientError as e:
            logger.warning("Meter realtime unreachable: %s", e)
            return None
