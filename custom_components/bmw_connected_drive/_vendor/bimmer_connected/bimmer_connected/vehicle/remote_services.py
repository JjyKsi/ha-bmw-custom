"""Trigger remote services on a vehicle using EVCC-compatible endpoints."""

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from bimmer_connected.api.client import MyBMWClient
from bimmer_connected.const import REMOTE_SERVICE_URL, VEHICLE_CHARGING_BASE_URL
from bimmer_connected.models import MyBMWRemoteServiceError, StrEnum
from bimmer_connected.utils import MyBMWJSONEncoder
from bimmer_connected.vehicle.fuel_and_battery import ChargingState

if TYPE_CHECKING:
    from bimmer_connected.vehicle import MyBMWVehicle

_LOGGER = logging.getLogger(__name__)

class ExecutionState(StrEnum):
    """Enumeration of possible states of the execution of a remote service."""

    INITIATED = "INITIATED"
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    EXECUTED = "EXECUTED"
    ERROR = "ERROR"
    IGNORED = "IGNORED"
    UNKNOWN = "UNKNOWN"


class Services(StrEnum):
    """Enumeration of possible services to be executed."""

    LIGHT_FLASH = "light-flash"
    VEHICLE_FINDER = "vehicle-finder"
    DOOR_LOCK = "door-lock"
    DOOR_UNLOCK = "door-unlock"
    HORN = "horn-blow"
    AIR_CONDITIONING = "climate-now"
    CHARGE_START = "start-charging"
    CHARGE_STOP = "stop-charging"
    CHARGING_SETTINGS = "CHARGING_SETTINGS"
    CHARGING_PROFILE = "CHARGING_PROFILE"
    SEND_POI = "SEND_POI"


# Non-default remote services URLs
SERVICE_URLS = {
    Services.CHARGE_START: VEHICLE_CHARGING_BASE_URL + "/{service_type}",
    Services.CHARGE_STOP: VEHICLE_CHARGING_BASE_URL + "/{service_type}",
}

class RemoteServiceStatus:
    """Wraps the status of the execution of a remote service."""

    def __init__(self, response: dict, event_id: Optional[str] = None):
        """Construct a new object from a dict."""
        status = None
        if "eventStatus" in response:
            status = response.get("eventStatus")

        self.state = ExecutionState(status or "UNKNOWN")
        self.details = response
        self.event_id = event_id


class RemoteServices:
    """Trigger remote services on a vehicle."""

    def __init__(self, vehicle: "MyBMWVehicle"):
        self._account = vehicle.account
        self._vehicle = vehicle

    async def trigger_remote_service(
        self, service_id: Services, params: Optional[Dict] = None, data: Any = None, refresh: bool = False
    ) -> RemoteServiceStatus:
        """Trigger a remote service and wait for the result."""

        url_template = SERVICE_URLS.get(service_id, REMOTE_SERVICE_URL)
        url = url_template.format(vin=self._vehicle.vin, service_type=service_id.value, gcid=self._account.gcid)

        headers = {"accept": "application/json", "content-type": "application/json"}

        async with MyBMWClient(self._account.config, brand=self._vehicle.brand) as client:
            response = await client.post(
                url,
                headers=headers,
                params=params,
                content=json.dumps(data or {}, cls=MyBMWJSONEncoder),
            )
            response.raise_for_status()

        if refresh:
            await self._account.get_vehicles()

        return RemoteServiceStatus({"eventStatus": ExecutionState.EXECUTED.value})

    async def _unsupported(self, service: Services) -> RemoteServiceStatus:
        raise MyBMWRemoteServiceError(
            f"Remote service '{service.value}' is not available in EVCC-aligned mode."
        )

    async def trigger_remote_light_flash(self) -> RemoteServiceStatus:
        """Trigger the vehicle to flash its headlights."""
        if not self._vehicle.is_remote_lights_enabled:
            raise ValueError(f"Vehicle does not support remote service '{Services.LIGHT_FLASH.value}'.")
        return await self.trigger_remote_service(Services.LIGHT_FLASH)

    async def trigger_remote_door_lock(self) -> RemoteServiceStatus:
        """Trigger the vehicle to lock its doors."""
        if not self._vehicle.is_remote_lock_enabled:
            raise ValueError(f"Vehicle does not support remote service '{Services.DOOR_LOCK.value}'.")
        return await self.trigger_remote_service(Services.DOOR_LOCK, refresh=True)

    async def trigger_remote_door_unlock(self) -> RemoteServiceStatus:
        """Trigger the vehicle to unlock its doors."""
        if not self._vehicle.is_remote_unlock_enabled:
            raise ValueError(f"Vehicle does not support remote service '{Services.DOOR_UNLOCK.value}'.")
        return await self.trigger_remote_service(Services.DOOR_UNLOCK, refresh=True)

    async def trigger_remote_horn(self) -> RemoteServiceStatus:
        """Trigger the vehicle to sound its horn."""
        if not self._vehicle.is_remote_horn_enabled:
            raise ValueError(f"Vehicle does not support remote service '{Services.HORN.value}'.")
        return await self.trigger_remote_service(Services.HORN)

    async def trigger_charge_start(self) -> RemoteServiceStatus:
        """Trigger the vehicle to start charging."""
        if not self._vehicle.is_remote_charge_start_enabled:
            raise ValueError(f"Vehicle does not support remote service '{Services.CHARGE_START.value}'.")

        if not self._vehicle.fuel_and_battery.is_charger_connected:
            _LOGGER.warning("Charger not connected, cannot start charging.")
            return RemoteServiceStatus({"eventStatus": "IGNORED"})

        return await self.trigger_remote_service(Services.CHARGE_START, refresh=True)

    async def trigger_charge_stop(self) -> RemoteServiceStatus:
        """Trigger the vehicle to stop charging."""
        if not self._vehicle.is_remote_charge_stop_enabled:
            raise ValueError(f"Vehicle does not support remote service '{Services.CHARGE_STOP.value}'.")

        if not self._vehicle.fuel_and_battery.is_charger_connected:
            _LOGGER.warning("Charger not connected, cannot stop charging.")
            return RemoteServiceStatus({"eventStatus": "IGNORED"})
        if self._vehicle.fuel_and_battery.charging_status != ChargingState.CHARGING:
            _LOGGER.warning("Vehicle not charging, cannot stop charging.")
            return RemoteServiceStatus({"eventStatus": "IGNORED"})

        return await self.trigger_remote_service(Services.CHARGE_STOP, refresh=True)

    async def trigger_remote_air_conditioning(self) -> RemoteServiceStatus:
        """Trigger the air conditioning to start."""
        return await self._unsupported(Services.AIR_CONDITIONING)

    async def trigger_remote_air_conditioning_stop(self) -> RemoteServiceStatus:
        """Trigger the air conditioning to stop."""
        return await self._unsupported(Services.AIR_CONDITIONING)

    async def trigger_charging_settings_update(
        self, target_soc: Optional[int] = None, ac_limit: Optional[int] = None
    ) -> RemoteServiceStatus:
        """Update the charging settings on the vehicle."""
        return await self._unsupported(Services.CHARGING_SETTINGS)

    async def trigger_charging_profile_update(
        self, charging_mode: Optional[Any] = None, precondition_climate: Optional[bool] = None
    ) -> RemoteServiceStatus:
        """Update the charging profile on the vehicle."""

        return await self._unsupported(Services.CHARGING_PROFILE)

    async def trigger_send_poi(self, poi: Union[Dict, Any]) -> RemoteServiceStatus:
        """Send a PointOfInterest to the vehicle.

        :param poi: A PointOfInterest containing at least 'lat' and 'lon' and optionally
            'name', 'street', 'city', 'postalCode', 'country'
        """
        return await self._unsupported(Services.SEND_POI)

    async def trigger_remote_vehicle_finder(self) -> RemoteServiceStatus:
        """Trigger the vehicle finder."""
        # Even if the API reports this as False, calling the service still works
        # if not self._vehicle.is_vehicle_tracking_enabled:
        #     raise ValueError(f"Vehicle does not support remote service '{Services.VEHICLE_FINDER.value}'.")

        return await self._unsupported(Services.VEHICLE_FINDER)
