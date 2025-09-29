"""URLs for different services and error code mapping."""

from enum import Enum


class CarBrands(str, Enum):
    """Car brands supported by the MyBMW API."""

    @classmethod
    def _missing_(cls, value):
        value = next(iter(value.split("_")))
        for member in cls:
            if member.value == value.lower():
                return member
        raise ValueError(f"'{value}' is not a valid {cls.__name__}")

    BMW = "bmw"
    MINI = "mini"
    TOYOTA = "toyota"


class Regions(str, Enum):
    """Regions of the world with separate servers."""

    NORTH_AMERICA = "na"
    REST_OF_WORLD = "row"


SERVER_URLS_MYBMW = {
    Regions.NORTH_AMERICA: "cocoapi.bmwgroup.us",
    Regions.REST_OF_WORLD: "cocoapi.bmwgroup.com",
}

HCAPTCHA_SITE_KEYS = {
    Regions.NORTH_AMERICA: "dc24de9a-9844-438b-b542-60067ff4dbe9",
    "_": "10000000-ffff-ffff-ffff-000000000001",
}

APP_VERSIONS = {
    Regions.NORTH_AMERICA: "4.9.2(36892)",
    Regions.REST_OF_WORLD: "4.9.2(36892)",
}

HTTPX_TIMEOUT = 30.0

USER_AGENTS = {
    Regions.NORTH_AMERICA: "Dart/3.3 (dart:io)",
    Regions.REST_OF_WORLD: "Dart/3.3 (dart:io)",
}
X_USER_AGENT = "android({build_string});{brand};{app_version};{region}"


VEHICLES_URL = "/eadrax-vcs/v4/vehicles"
VEHICLE_PROFILE_URL = "/eadrax-vcs/v5/vehicle-data/profile"
VEHICLE_STATE_URL = "/eadrax-vcs/v4/vehicles/state"

REMOTE_SERVICE_V3_BASE_URL = "/eadrax-vrccs/v3/presentation/remote-commands"
REMOTE_SERVICE_URL = REMOTE_SERVICE_V3_BASE_URL + "/{vin}/{service_type}"

VEHICLE_CHARGING_BASE_URL = "/eadrax-crccs/v1/vehicles/{vin}"

VEHICLE_IMAGE_URL = "/eadrax-ics/v5/presentation/vehicles/images"
VEHICLE_POI_URL = "/eadrax-dcs/v2/user/{gcid}/send-to-car"

VEHICLE_CHARGING_STATISTICS_URL = "/eadrax-chs/v2/charging-statistics"
VEHICLE_CHARGING_SESSIONS_URL = "/eadrax-chs/v2/charging-sessions"

SERVICE_CHARGING_STATISTICS_URL = "CHARGING_STATISTICS"
SERVICE_CHARGING_SESSIONS_URL = "CHARGING_SESSIONS"
SERVICE_CHARGING_PROFILE = "CHARGING_PROFILE"


ATTR_STATE = "state"
ATTR_CAPABILITIES = "capabilities"
ATTR_ATTRIBUTES = "attributes"
ATTR_CHARGING_SETTINGS = "charging_settings"

DEFAULT_POI_NAME = "Sent with ♥ by bimmer_connected"
