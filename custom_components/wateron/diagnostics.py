"""Diagnostics support for the WaterOn (SmarterHomes) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"token", "password", "username", "mobile", "isd"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "config_entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "coordinator_data": coordinator.data,
    }
