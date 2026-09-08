"""Config flows for the WaterOn (SmarterHomes) integration."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WaterOnAPI, WaterOnAuthError, WaterOnConnectionError
from .api_resident import (
    WaterOnResidentAPI,
    WaterOnResidentAuthError,
    WaterOnResidentConnectionError,
)
from .const import (
    ACCOUNT_COMMITTEE,
    ACCOUNT_RESIDENT,
    CONF_ACCOUNT_TYPE,
    CONF_ISD,
    CONF_MOBILE,
    CONF_OTP,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_USERNAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_POLL_INTERVAL,
)

ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT_TYPE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(
                        value=ACCOUNT_COMMITTEE,
                        label="Society committee member (fm.wateron.cc)",
                    ),
                    selector.SelectOptionDict(
                        value=ACCOUNT_RESIDENT,
                        label="Individual flat resident (WaterOn app)",
                    ),
                ],
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
    }
)

COMMITTEE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

RESIDENT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ISD, default="91"): str,
        vol.Required(CONF_MOBILE): str,
    }
)

OTP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_OTP): str,
    }
)


class WaterOnConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WaterOn."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Ask which account type (committee or resident) to configure."""
        if user_input is not None:
            if user_input[CONF_ACCOUNT_TYPE] == ACCOUNT_COMMITTEE:
                return await self.async_step_committee()
            return await self.async_step_resident()

        return self.async_show_form(
            step_id="user",
            data_schema=ACCOUNT_SCHEMA,
        )

    async def async_step_committee(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Configure a society committee account (fm.wateron.cc)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = WaterOnAPI(
                session=async_get_clientsession(self.hass),
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )
            try:
                await api.async_login()
            except WaterOnAuthError:
                errors["base"] = "invalid_auth"
            except WaterOnConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected WaterOn login error")
                errors["base"] = "unknown"
            else:
                data = {CONF_ACCOUNT_TYPE: ACCOUNT_COMMITTEE, **user_input}
                title = f"WaterOn ({api.society_id})"
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="committee",
            data_schema=COMMITTEE_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_resident(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect the resident mobile number and request an OTP."""
        errors: dict[str, str] = {}

        if user_input is not None:
            isd = user_input[CONF_ISD].strip().lstrip("+")
            mobile = user_input[CONF_MOBILE].strip()

            for entry in self._async_current_entries():
                if (
                    entry.data.get(CONF_ACCOUNT_TYPE) == ACCOUNT_RESIDENT
                    and entry.data.get(CONF_MOBILE) == mobile
                    and str(entry.data.get(CONF_ISD, "")).lstrip("+") == isd
                ):
                    return self.async_abort(reason="already_configured")

            self._api = WaterOnResidentAPI(
                session=async_get_clientsession(self.hass),
                mobile=mobile,
                isd=isd,
            )
            try:
                await self._api.async_send_otp()
            except WaterOnResidentAuthError:
                errors["base"] = "invalid_auth"
            except WaterOnResidentConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected WaterOn OTP request error")
                errors["base"] = "unknown"
            else:
                return await self.async_step_otp()

        return self.async_show_form(
            step_id="resident",
            data_schema=RESIDENT_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Verify the OTP and create the config entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                token = await self._api.async_verify_otp(user_input[CONF_OTP])
                profile = await self._api.async_profile()
            except WaterOnResidentAuthError as err:
                LOGGER.debug("WaterOn OTP verification rejected: %s", err)
                errors["base"] = "invalid_otp"
            except (WaterOnResidentConnectionError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected WaterOn OTP verification error")
                errors["base"] = "unknown"
            else:
                society = ""
                payload = profile.get("payload") if isinstance(profile, dict) else None
                apt_list = (
                    payload.get("apartment") if isinstance(payload, dict) else None
                )
                if isinstance(apt_list, list) and apt_list:
                    first = apt_list[0]
                    if isinstance(first, dict):
                        society = first.get("society", "")

                data = {
                    CONF_ACCOUNT_TYPE: ACCOUNT_RESIDENT,
                    CONF_ISD: self._api.isd,
                    CONF_MOBILE: self._api.mobile,
                    CONF_TOKEN: token,
                }
                title = f"WaterOn ({self._api.mobile})" + (
                    f" - {society}" if society else ""
                )
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="otp",
            data_schema=OTP_SCHEMA,
            errors=errors,
            description_placeholders={
                CONF_MOBILE: f"({self._api.isd}) {self._api.mobile}"
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WaterOnOptionsFlow(config_entry)


class WaterOnOptionsFlow(OptionsFlow):
    """Handle WaterOn options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL, default=current
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_POLL_INTERVAL, max=86400),
                    )
                }
            ),
        )