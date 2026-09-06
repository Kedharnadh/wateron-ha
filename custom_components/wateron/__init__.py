"""The WaterOn (SmarterHomes) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WaterOnAPI, WaterOnAuthError, WaterOnConnectionError
from .const import (
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_USERNAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LOGGER,
    PLATFORMS,
)
from .coordinator import WaterOnDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WaterOn from a config entry."""
    session = async_get_clientsession(hass)
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

    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
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