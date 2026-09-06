"""Config flows for the WaterOn (SmarterHomes) integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WaterOnAPI, WaterOnAuthError, WaterOnConnectionError
from .const import (
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_USERNAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_POLL_INTERVAL,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class WaterOnConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WaterOn."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
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
                title = f"WaterOn ({api.society_id})"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
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