"""Region metadata aligned with EVCC BMW implementation."""

from dataclasses import dataclass
from typing import List

from bimmer_connected.const import APP_VERSIONS, SERVER_URLS_MYBMW, USER_AGENTS, Regions


EVCC_SCOPE = (
    "openid profile email offline_access smacc vehicle_data perseus dlm svds cesim vsapi remote_services fupo "
    "authenticate_user"
)


@dataclass(frozen=True)
class RegionConfig:
    """Static configuration matching EVCC’s BMW region parameters."""

    auth_uri: str
    coco_api_uri: str
    client_id: str
    state: str
    token_authorization: str
    x_user_agent_region: str


REGION_CONFIG = {
    Regions.NORTH_AMERICA: RegionConfig(
        auth_uri="https://login.bmwusa.com/gcdm",
        coco_api_uri="https://cocoapi.bmwgroup.us",
        client_id="54394a4b-b6c1-45fe-b7b2-8fd3aa9253aa",
        state="rgastJbZsMtup49-Lp0FMQ",
        token_authorization="Basic NTQzOTRhNGItYjZjMS00NWZlLWI3YjItOGZkM2FhOTI1M2FhOmQ5MmYzMWMwLWY1NzktNDRmNS1hNzdkLTk2NmY4ZjAwZTM1MQ==",
        x_user_agent_region="na",
    ),
    Regions.REST_OF_WORLD: RegionConfig(
        auth_uri="https://customer.bmwgroup.com/gcdm",
        coco_api_uri="https://cocoapi.bmwgroup.com",
        client_id="31c357a0-7a1d-4590-aa99-33b97244d048",
        state="cEG9eLAIi6Nv-aaCAniziE_B6FPoobva3qr5gukilYw",
        token_authorization="Basic MzFjMzU3YTAtN2ExZC00NTkwLWFhOTktMzNiOTcyNDRkMDQ4OmMwZTMzOTNkLTcwYTItNGY2Zi05ZDNjLTg1MzBhZjY0ZDU1Mg==",
        x_user_agent_region="row",
    ),
}


def valid_regions() -> List[str]:
    """Get list of valid regions as strings."""
    return [region.name.lower() for region in Regions]


def get_region_from_name(name: str) -> Regions:
    """Get a region for a string.

    This function is not case-sensitive.
    """
    for region in Regions:
        if name.lower() == region.name.lower():
            return region
    raise ValueError(f"Unknown region {name}. Valid regions are: {','.join(valid_regions())}")


def get_server_url(region: Regions) -> str:
    """Get the url of the server for the region."""
    return REGION_CONFIG[region].coco_api_uri


def get_user_agent(region: Regions) -> str:
    """Get the Dart user agent for the region."""
    return USER_AGENTS[region]


def get_app_version(region: Regions) -> str:
    """Get the app version & build number for the region."""
    return APP_VERSIONS[region]


def get_region_config(region: Regions) -> RegionConfig:
    """Return EVCC-aligned configuration for a region."""

    try:
        return REGION_CONFIG[region]
    except KeyError as exc:  # pragma: no cover - defensive guard for unsupported regions
        raise ValueError(f"Unsupported region: {region}") from exc
