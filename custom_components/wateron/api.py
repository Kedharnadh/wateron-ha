"""Asynchronous client for the WaterOn (SmarterHomes) API.

Reverse-engineered from the fm.wateron.cc React portal (v1.3.5).
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_BASE, LOGGER

LOGIN_PATH = "/identityservice/user/login"
PROFILE_PATH = "/societydataservice/society/profile"
AGGREGATE_PATH = "/watersourceservice/society/aggregateconsumption"
METERS_PATH = "/watersourceservice/society/getmeterwiseconsumption"
SUMMARY_PATH = "/watersourceservice/society/consumptionsummary"
ALERT_PATH = "/identityservice/society/alert"
VALVE_PATH = "/apartmentinfoservice/society/valve"
VALVE_STATUS_PATH = "/apartmentinfoservice/society/valvestatus"
VALVE_HISTORY_PATH = "/apartmentinfoservice/society/valvehistory"


class WaterOnAuthError(Exception):
    """Raised when authentication fails or a token is rejected (HTTP 401)."""


class WaterOnConnectionError(Exception):
    """Raised when the API cannot be reached."""


class WaterOnAPI:
    """Minimal async client for the WaterOn API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        api_base: str = API_BASE,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._api_base = api_base
        self._token: str | None = None
        self.society_id: str | None = None
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "type": "Web",
        }

    @property
    def is_authenticated(self) -> bool:
        return bool(self._token)

    async def async_login(self) -> None:
        """Authenticate and store access token + society id."""
        url = f"{self._api_base}{LOGIN_PATH}"
        try:
            resp = await self._session.post(
                url,
                json={"username": self._username, "password": self._password},
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=30),
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise WaterOnConnectionError(f"Cannot reach {url}: {err}") from err

        if resp.status == 401:
            raise WaterOnAuthError("Invalid username or password")

        try:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError) as err:
            raise WaterOnConnectionError(f"Bad response from login: {err}") from err

        self._token = data.get("access_token")
        self.society_id = data.get("society_id")

        if not self._token:
            raise WaterOnAuthError("Login response missing access_token")

        self._headers["Authorization"] = f"Bearer {self._token}"
        LOGGER.debug("Authenticated, society_id=%s", self.society_id)

    async def async_post(self, path: str, body: dict[str, Any]) -> dict | None:
        """POST JSON to the API, raising WaterOnAuthError on 401."""
        url = f"{self._api_base}{path}"
        try:
            resp = await self._session.post(
                url,
                json=body,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=30),
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise WaterOnConnectionError(f"Cannot reach {url}: {err}") from err

        if resp.status == 401:
            raise WaterOnAuthError("Token rejected (HTTP 401)")

        try:
            resp.raise_for_status()
            return await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError) as err:
            raise WaterOnConnectionError(f"Bad response from {url}: {err}") from err

    async def async_profile(self) -> dict | None:
        return await self.async_post(
            PROFILE_PATH, {"societyId": self.society_id}
        )

    async def async_aggregate(self, month: str, year: str) -> dict | None:
        return await self.async_post(
            AGGREGATE_PATH,
            {"societyId": self.society_id, "month": month, "year": year},
        )

    async def async_meters(self, month: str, year: str) -> dict | None:
        return await self.async_post(
            METERS_PATH,
            {"societyId": self.society_id, "month": month, "year": year},
        )

    async def async_summary(self) -> dict | None:
        return await self.async_post(
            SUMMARY_PATH, {"societyId": self.society_id}
        )

    async def async_alerts(self, alert_type: str = "current", **kwargs: Any) -> dict | None:
        """Fetch alerts. type = 'current' or 'history'.

        History supports: limit (default 50), page, aptNumber.
        """
        body: dict[str, Any] = {"societyId": self.society_id, "type": alert_type}
        if alert_type == "history":
            body.setdefault("limit", kwargs.get("limit", 50))
            body.setdefault("page", kwargs.get("page", 1))
            body.setdefault("aptNumber", kwargs.get("aptNumber", ""))
        return await self.async_post(ALERT_PATH, body)

    async def async_valve_action(self, meter_id: int, action: str) -> dict | None:
        """Open ('open') or close ('close') a meter's smart valve."""
        return await self.async_post(
            VALVE_PATH,
            {
                "meterId": meter_id,
                "action": action,
                "username": self._username,
                "adminFlag": True,
                "userInterface": "admin",
                "actionReason": "admin",
            },
        )

    async def async_valve_status(self) -> dict | None:
        """Return per-meter valve status rows."""
        return await self.async_post(VALVE_STATUS_PATH, {"aptId": 0})

    async def async_valve_history(self, apt_id: int | str = 0) -> dict | None:
        return await self.async_post(
            VALVE_HISTORY_PATH, {"aptId": apt_id}
        )