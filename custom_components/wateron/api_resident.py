"""Asynchronous client for the WaterOn (SmarterHomes) individual-flat API.

Reverse-engineered from the 'WaterOn' Android app (com.wateron.smartrhomes),
which targets resident endpoints on appapi.wateron.in / mainappapi.wateron.in.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import (
    API_BASE_MAIN,
    API_BASE_MAIN_V1,
    API_BASE_V2,
    LOGGER,
)

REGISTER_PATH = "/register"
VERIFY_OTP_PATH = "/verifyOtp"
PROFILE_PATH = "/profile"
AUTH_PATH = "/auth"
DASHBOARD_PATH = "/dashboard/confinedwithinvoice/apt/{apt_id}"
DAILY_PATH = "/getreading/daily"
ALERTS_ACTIVE_PATH = "/alerts/active/{apt_id}"
ALERTS_HISTORY_PATH = "/alerts/history"
VALVE_STATUS_PATH = "/meter/{meter_id}/valve/status"
VALVE_ACTION_PATH = "/meter/{meter_id}/valve/action/{action}"

TIMEOUT = aiohttp.ClientTimeout(total=30)

# The getreading/daily endpoint rejects an empty FCM token. Home Assistant has
# no Firebase registration, so a static placeholder is sent instead.
_FCM_TOKEN_PLACEHOLDER = "homeassistant-wateron"

MAX_RETRIES = 3
RETRY_BACKOFF = 1.0  # seconds, doubled each attempt


class WaterOnResidentAuthError(Exception):
    """Raised when an OTP/token is rejected (HTTP 401)."""


class WaterOnResidentConnectionError(Exception):
    """Raised when the API cannot be reached."""


class WaterOnResidentAPI:
    """Minimal async client for the WaterOn individual-flat API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        mobile: str,
        isd: str,
        token: str | None = None,
    ) -> None:
        self._session = session
        self._mobile = mobile
        self._isd = isd
        self._token = token
        self._msin = f"({isd}){mobile}"

    @property
    def is_authenticated(self) -> bool:
        return bool(self._token)

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def mobile(self) -> str:
        return self._mobile

    @property
    def isd(self) -> str:
        return self._isd

    @property
    def msin(self) -> str:
        return self._msin

    def _auth_headers(self, bearer: str | None = None) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "X-AUTH-TOKEN": f"Bearer {bearer or self._token}",
            "X-MSIN": self._msin,
        }

    async def async_send_otp(self) -> None:
        """Request a login OTP for the registered mobile number."""
        url = f"{API_BASE_MAIN}{REGISTER_PATH}"
        data = await self._async_post_form(
            url, {"mobile": self._mobile, "isd": self._isd}
        )
        message = data.get("message", "") if isinstance(data, dict) else ""
        if not isinstance(data, dict) or message.strip().lower() != "valid user":
            raise WaterOnResidentAuthError("Unable to send OTP for this mobile number")
        LOGGER.debug("OTP sent to %s%s", self._isd, self._mobile)

    async def async_verify_otp(self, otp: str) -> str:
        """Verify the OTP and store the returned auth token."""
        url = f"{API_BASE_MAIN}{VERIFY_OTP_PATH}"
        data = await self._async_post_form(
            url,
            {"mobile": self._mobile, "isd": self._isd, "otp": otp},
        )
        if not isinstance(data, dict) or data.get("status_code") != 200:
            raise WaterOnResidentAuthError("Invalid OTP")
        self._token = data.get("token")
        if not self._token:
            raise WaterOnResidentAuthError("OTP verification response missing token")
        LOGGER.debug("OTP verified for %s%s", self._isd, self._mobile)
        return self._token

    async def async_refresh_token(self) -> str | None:
        """Fetch a fresh auth token via GET /v2.0/auth/ (used on 401)."""
        url = f"{API_BASE_V2}{AUTH_PATH}"
        data = await self._async_get(url, bearer="req4auth")
        if isinstance(data, dict):
            token = data.get("auth-token") or data.get("token")
            if token:
                self._token = token
                return token
        return None

    async def async_profile(self) -> dict[str, Any] | None:
        """Return the resident profile with apartments, meters and slabs."""
        url = f"{API_BASE_MAIN}{PROFILE_PATH}"
        return await self._async_post_form(
            url,
            {
                "mobile": self._mobile,
                "isd": self._isd,
                "token": self._token or "",
            },
        )

    async def async_dashboard(self, apt_id: int | str) -> dict[str, Any] | None:
        """Return bill and alert data for a single apartment."""
        url = f"{API_BASE_V2}{DASHBOARD_PATH.format(apt_id=apt_id)}"
        return await self._async_get(url)

    async def async_daily(
        self, meter_ids: list[int], fdate: str, tdate: str
    ) -> dict[str, Any] | None:
        """Return per-day consumption for the given meters between two dates."""
        url = f"{API_BASE_MAIN_V1}{DAILY_PATH}"
        return await self._async_post_form(
            url,
            {
                "meterId": ",".join(str(m) for m in meter_ids),
                "token": self._token or "",
                "tdate": tdate,
                "fdate": fdate,
                "mobile": self._mobile,
                "isd": self._isd,
                "fcmToken": _FCM_TOKEN_PLACEHOLDER,
            },
        )

    async def async_valve_status(self, meter_id: int | str) -> dict[str, Any] | None:
        """Return the current valve state for a meter."""
        url = f"{API_BASE_V2}{VALVE_STATUS_PATH.format(meter_id=meter_id)}"
        return await self._async_get(url)

    async def async_valve_action(
        self, meter_id: int | str, action: str
    ) -> dict[str, Any] | None:
        """Open ('open') or close ('close') a meter's smart valve."""
        url = f"{API_BASE_V2}{VALVE_ACTION_PATH.format(meter_id=meter_id, action=action)}"
        try:
            resp = await self._session.post(url, headers=self._auth_headers())
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise WaterOnResidentConnectionError(f"Cannot reach {url}: {err}") from err
        if resp.status == 401:
            raise WaterOnResidentAuthError("Token rejected (HTTP 401)")
        try:
            resp.raise_for_status()
            return await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError, asyncio.TimeoutError) as err:
            raise WaterOnResidentConnectionError(f"Bad response from {url}: {err}") from err

    async def async_active_alerts(self, apt_id: int | str) -> list[Any] | None:
        """Return active alerts for an apartment."""
        url = f"{API_BASE_V2}{ALERTS_ACTIVE_PATH.format(apt_id=apt_id)}"
        return await self._async_get(url)

    async def async_alert_history(
        self, apt_id: int | str, limit: int = 300
    ) -> dict[str, Any] | None:
        """Return the alert history (leakage/burst list) for an apartment."""
        url = f"{API_BASE_MAIN}{ALERTS_HISTORY_PATH}"
        return await self._async_post_form(
            url,
            {
                "token": self._token or "",
                "mobile": self._mobile,
                "isd": self._isd,
                "aptId": str(apt_id),
                "start": "0",
                "limit": str(limit),
                "fcmToken": _FCM_TOKEN_PLACEHOLDER,
            },
        )

    async def _async_get(
        self, url: str, bearer: str | None = None
    ) -> Any | None:
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._session.get(
                    url, headers=self._auth_headers(bearer), timeout=TIMEOUT
                )
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_err = err
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF * (2 ** attempt))
                    continue
                raise WaterOnResidentConnectionError(f"Cannot reach {url}: {err}") from err
            if resp.status == 401:
                raise WaterOnResidentAuthError("Token rejected (HTTP 401)")
            try:
                resp.raise_for_status()
                return await resp.json(content_type=None)
            except (aiohttp.ClientError, ValueError, asyncio.TimeoutError) as err:
                raise WaterOnResidentConnectionError(f"Bad response from {url}: {err}") from err
        raise WaterOnResidentConnectionError(f"Cannot reach {url}: {last_err}")

    async def _async_post_form(
        self, url: str, params: dict[str, Any]
    ) -> Any | None:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._session.post(
                    url, data=params, headers=headers, timeout=TIMEOUT
                )
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_err = err
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF * (2 ** attempt))
                    continue
                raise WaterOnResidentConnectionError(f"Cannot reach {url}: {err}") from err
            if resp.status == 401:
                raise WaterOnResidentAuthError("Token rejected (HTTP 401)")
            try:
                resp.raise_for_status()
                return await resp.json(content_type=None)
            except (aiohttp.ClientError, ValueError, asyncio.TimeoutError) as err:
                raise WaterOnResidentConnectionError(f"Bad response from {url}: {err}") from err
        raise WaterOnResidentConnectionError(f"Cannot reach {url}: {last_err}")