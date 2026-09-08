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
API_BASE_V2 = "https://appapi.wateron.in/v2.0"
API_BASE_MAIN = "https://mainappapi.wateron.in/api/v1.0"
API_BASE_MAIN_V1 = "https://mainappapi.wateron.in/api/v1.1"

CONF_ACCOUNT_TYPE = "account_type"
CONF_MOBILE = "mobile"
CONF_ISD = "isd"
CONF_OTP = "otp"
CONF_TOKEN = "token"

ACCOUNT_COMMITTEE = "committee"
ACCOUNT_RESIDENT = "resident"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_POLL_INTERVAL = 300  # seconds
MIN_POLL_INTERVAL = 60

LOGGER = logging.getLogger(__package__)