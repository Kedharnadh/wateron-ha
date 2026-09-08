"""The WaterOn (SmarterHomes) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WaterOnAPI, WaterOnAuthError, WaterOnConnectionError
from .api_resident import (
    WaterOnResidentAPI,
    WaterOnResidentAuthError,
    WaterOnResidentConnectionError,
)
from .const import (
    ACCOUNT_RESIDENT,
    CONF_ISD,
    CONF_MOBILE,
    CONF_POLL_INTERVAL,
    CONF_TOKEN,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LOGGER,
    PLATFORMS,
)
from .coordinator import (
    WaterOnDataUpdateCoordinator,
    WaterOnResidentDataUpdateCoordinator,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WaterOn from a config entry."""
    session = async_get_clientsession(hass)
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    if entry.data.get("account_type") == ACCOUNT_RESIDENT:
        api = WaterOnResidentAPI(
            session=session,
            mobile=str(entry.data[CONF_MOBILE]),
            isd=str(entry.data[CONF_ISD]),
            token=entry.data.get(CONF_TOKEN),
        )
        try:
            await api.async_profile()
        except WaterOnResidentAuthError:
            LOGGER.info("Saved token expired, attempting refresh")
            try:
                await api.async_refresh_token()
                await api.async_profile()
            except (WaterOnResidentAuthError, WaterOnResidentConnectionError):
                LOGGER.error("Authentication failed for entry %s", entry.entry_id)
                return False
        except WaterOnResidentConnectionError:
            LOGGER.error("Could not reach the WaterOn API for entry %s", entry.entry_id)
            return False

        coordinator = WaterOnResidentDataUpdateCoordinator(
            hass, api, entry, poll_interval
        )
    else:
        api = WaterOnAPI(
            session=session,
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )
        try:
            await api.async_login()
        except WaterOnAuthError:
            LOGGER.error("Authentication failed for entry %s", entry.entry_id)
            return False
        except WaterOnConnectionError:
            LOGGER.error("Could not reach the WaterOn API for entry %s", entry.entry_id)
            return False

        coordinator = WaterOnDataUpdateCoordinator(hass, api, poll_interval)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)