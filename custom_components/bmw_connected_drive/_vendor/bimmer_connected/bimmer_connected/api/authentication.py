"""Authentication management for BMW APIs aligned with EVCC."""

import asyncio
import datetime
import logging
import ssl
from typing import AsyncGenerator, Generator, Optional, Union
from uuid import uuid4

import httpx

from bimmer_connected.api.regions import (
    EVCC_SCOPE,
    get_app_version,
    get_region_config,
    get_server_url,
    get_user_agent,
)
from bimmer_connected.api.utils import (
    create_s256_code_challenge,
    generate_token,
    get_x_user_agent_buildstring,
    handle_httpstatuserror,
)
from bimmer_connected.const import HTTPX_TIMEOUT, X_USER_AGENT, Regions
from bimmer_connected.models import MyBMWAPIError, MyBMWCaptchaMissingError

_REDIRECT_URI = "com.bmw.connected://oauth"
EXPIRES_AT_OFFSET = datetime.timedelta(seconds=HTTPX_TIMEOUT * 2)

_LOGGER = logging.getLogger(__name__)


class MyBMWAuthentication(httpx.Auth):
    """Authentication and Retry Handler using EVCC’s OAuth flow."""

    def __init__(
        self,
        username: str,
        password: str,
        region: Regions,
        access_token: Optional[str] = None,
        expires_at: Optional[datetime.datetime] = None,
        refresh_token: Optional[str] = None,
        gcid: Optional[str] = None,
        hcaptcha_token: Optional[str] = None,
        verify: Union[ssl.SSLContext, str, bool] = True,
    ):
        self.username: str = username
        self.password: str = password
        self.region: Regions = region
        self.region_config = get_region_config(region)
        self.access_token: Optional[str] = access_token
        self.expires_at: Optional[datetime.datetime] = expires_at
        self.refresh_token: Optional[str] = refresh_token
        self.session_id: str = str(uuid4())
        self._lock: Optional[asyncio.Lock] = None
        self.gcid: Optional[str] = gcid
        self.hcaptcha_token: Optional[str] = hcaptcha_token
        # Use external SSL context. Required in Home Assistant due to event loop blocking when httpx loads
        # SSL certificates from disk. If not given, uses httpx defaults.
        self.verify: Union[ssl.SSLContext, str, bool] = verify

    @property
    def login_lock(self) -> asyncio.Lock:
        """Make sure that there is a lock in the current event loop."""
        if not self._lock:
            self._lock = asyncio.Lock()
        return self._lock

    def sync_auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        raise RuntimeError("Cannot use an async authentication class with httpx.Client")

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        # Get an access token on first call
        async with self.login_lock:
            if not self.access_token or (self.expires_at and self.expires_at <= datetime.datetime.now(datetime.timezone.utc)):
                await self.login()
        request.headers["authorization"] = f"Bearer {self.access_token}"
        request.headers["bmw-session-id"] = self.session_id

        response: httpx.Response = yield request

        if response.is_success:
            return

        await response.aread()

        if response.status_code == 401:
            async with self.login_lock:
                _LOGGER.debug("Received unauthorized response, refreshing token.")
                await self.login()
            request.headers["authorization"] = f"Bearer {self.access_token}"
            request.headers["bmw-session-id"] = self.session_id
            response = yield request

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as ex:
            await handle_httpstatuserror(ex, module="API", log_handler=_LOGGER)

    async def login(self) -> None:
        """Get a valid OAuth token using EVCC-compatible flow."""
        token_data = {}

        if self.refresh_token:
            token_data = await self._refresh_evcc()

        if not token_data:
            token_data = await self._login_evcc()

        expires_at = token_data["expires_at"] - EXPIRES_AT_OFFSET
        self.access_token = token_data["access_token"]
        self.expires_at = expires_at
        self.refresh_token = token_data["refresh_token"]
        self.gcid = token_data.get("gcid")

    async def _login_evcc(self) -> dict:
        """Perform EVCC-style login for ROW / NA regions."""
        if not self.hcaptcha_token:
            raise MyBMWCaptchaMissingError(
                "Missing hCaptcha token for login. See https://bimmer-connected.readthedocs.io/en/stable/captcha.html"
            )

        code_verifier = generate_token(86)
        code_challenge = create_s256_code_challenge(code_verifier)

        oauth_base_values = {
            "client_id": self.region_config.client_id,
            "response_type": "code",
            "scope": EVCC_SCOPE,
            "redirect_uri": _REDIRECT_URI,
            "state": self.region_config.state,
            "nonce": "login_nonce",
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
        }

        data_with_credentials = {
            **oauth_base_values,
            "grant_type": "authorization_code",
            "username": self.username,
            "password": self.password,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "hcaptchatoken": self.hcaptcha_token,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(HTTPX_TIMEOUT), verify=self.verify, follow_redirects=False) as client:
            auth_url = f"{self.region_config.auth_uri}/oauth/authenticate"
            token_url = f"{self.region_config.auth_uri}/oauth/token"

            response = await client.post(auth_url, data=data_with_credentials, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as ex:
                await handle_httpstatuserror(ex, module="AUTH", log_handler=_LOGGER)

            payload = response.json()
            redirect_to = payload.get("redirect_to")
            if not redirect_to:
                raise MyBMWAPIError("authorization redirect missing in authenticate response")

            authorization = httpx.URL(redirect_to).params.get("authorization")
            if not authorization:
                raise MyBMWAPIError("authorization code missing in authenticate redirect")

            # The captcha token is single use – clear after first call.
            self.hcaptcha_token = None

            response = await client.post(
                auth_url,
                data={**oauth_base_values, "authorization": authorization},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as ex:
                await handle_httpstatuserror(ex, module="AUTH", log_handler=_LOGGER)

            location = response.headers.get("Location") or response.headers.get("location")
            if not location:
                raise MyBMWAPIError("authorization code redirect missing")

            code = httpx.URL(location).params.get("code")
            if not code:
                raise MyBMWAPIError("authorization code not found in redirect")

            now = datetime.datetime.now(datetime.timezone.utc)
            response = await client.post(
                token_url,
                data={
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": _REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": self.region_config.token_authorization,
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as ex:
                await handle_httpstatuserror(ex, module="AUTH", log_handler=_LOGGER)

            token_json = response.json()

        expires_in = int(token_json.get("expires_in", 0))
        expires_at = now + datetime.timedelta(seconds=expires_in)
        return {
            "access_token": token_json.get("access_token"),
            "refresh_token": token_json.get("refresh_token"),
            "gcid": token_json.get("gcid"),
            "expires_at": expires_at,
        }

    async def _refresh_evcc(self) -> dict:
        """Refresh an access token using EVCC token endpoint."""
        if not self.refresh_token:
            return {}

        async with httpx.AsyncClient(timeout=httpx.Timeout(HTTPX_TIMEOUT), verify=self.verify) as client:
            token_url = f"{self.region_config.auth_uri}/oauth/token"
            response = await client.post(
                token_url,
                data={
                    "redirect_uri": _REDIRECT_URI,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": self.region_config.token_authorization,
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as ex:
                await handle_httpstatuserror(ex, module="AUTH", log_handler=_LOGGER, dont_raise=True)
                return {}

            token_json = response.json()

        expires_in = int(token_json.get("expires_in", 0))
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)
        return {
            "access_token": token_json.get("access_token"),
            "refresh_token": token_json.get("refresh_token"),
            "gcid": token_json.get("gcid"),
            "expires_at": expires_at,
        }


class MyBMWLoginClient(httpx.AsyncClient):
    """Async HTTP client used for the main API once authenticated."""

    def __init__(self, *args, **kwargs):
        # Increase timeout
        kwargs["timeout"] = httpx.Timeout(HTTPX_TIMEOUT)

        # Set default values
        region = kwargs.pop("region")
        kwargs["base_url"] = get_server_url(region)
        kwargs["headers"] = {
            "user-agent": get_user_agent(region),
            "x-user-agent": X_USER_AGENT.format(
                build_string=get_x_user_agent_buildstring(),
                brand="bmw",
                app_version=get_app_version(region),
                region=get_region_config(region).x_user_agent_region,
            ),
            "X-User-Agent": X_USER_AGENT.format(
                build_string="SP1A.210812.016.C1",
                brand="bmw",
                app_version="99.0.0(99999)",
                region=get_region_config(region).x_user_agent_region,
            ),
        }

        super().__init__(*args, **kwargs)


class MyBMWLoginRetry(httpx.Auth):
    """Compatibility stub for legacy retry auth handler."""

    def sync_auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        raise RuntimeError("Cannot use an async authentication class with httpx.Client")

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        yield request
