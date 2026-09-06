"""Constants for the WaterOn (SmarterHomes) integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "wateron"
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
]

API_BASE = "https://api.wateron.cc"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_POLL_INTERVAL = 300  # seconds
MIN_POLL_INTERVAL = 60

LOGGER = logging.getLogger(__package__)