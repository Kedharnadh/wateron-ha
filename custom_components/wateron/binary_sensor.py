"""Alert binary sensors for the WaterOn (SmarterHomes) integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WaterOnDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterOn alert binary sensors from a config entry."""
    coordinator: WaterOnDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[WaterOnAlertSensor] = []
    seen: set[tuple[str, str]] = set()

    for alert in coordinator.data.get("alerts", []):
        is_burst = str(alert.get("alertType", "")) == "Q"
        key = (alert.get("meterId", ""), is_burst and "burst" or "leak")
        if key in seen:
            continue
        seen.add(key)
        entities.append(WaterOnAlertSensor(coordinator, entry, alert, is_burst))

    if entities:
        async_add_entities(entities)


class WaterOnAlertSensor(
    CoordinatorEntity[WaterOnDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor indicating an active leak/burst alert for a meter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WaterOnDataUpdateCoordinator,
        entry: ConfigEntry,
        alert: dict[str, Any],
        is_burst: bool,
    ) -> None:
        super().__init__(coordinator)
        self._attr_config_entry_id = entry.entry_id
        self._meter_id = alert.get("meterId", "")
        self._apt_no = alert.get("aptNo") or "Meter"
        self._is_burst = is_burst
        self._attr_unique_id = (
            f"wateron_{coordinator.society_id}_alert_"
            f"{self._meter_id}_{'burst' if is_burst else 'leak'}"
        )
        self._attr_name = f"{self._apt_no} {'burst' if is_burst else 'leakage'}"
        self._attr_device_class = (
            BinarySensorDeviceClass.PROBLEM
        )
        self._attr_icon = "mdi:pipe-burst" if is_burst else "mdi:pipe-leak"
        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, f"{coordinator.society_id}_apt_{self._apt_no}")
            },
            "name": f"WaterOn {self._apt_no}",
            "manufacturer": "SmarterHomes Technologies",
            "model": "WaterOn Smart Water Meter",
            "via_device": (DOMAIN, coordinator.society_id),
        }

    @property
    def is_on(self) -> bool | None:
        """True while this meter reports an active alert."""
        for alert in self.coordinator.data.get("alerts", []):
            is_burst = str(alert.get("alertType", "")) == "Q"
            if (
                alert.get("meterId") == self._meter_id
                and is_burst == self._is_burst
            ):
                return True
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "meter_id": self._meter_id,
            "apt_no": self._apt_no,
            "last_update": self.coordinator.data.get("last_update"),
        }
        for alert in self.coordinator.data.get("alerts", []):
            if (
                alert.get("meterId") == self._meter_id
                and (str(alert.get("alertType", "")) == "Q") == self._is_burst
            ):
                attrs["location"] = alert.get("location", "")
                attrs["time"] = alert.get("time", "")
                attrs["quantity"] = alert.get("quantity")
                raw_date = alert.get("date")
                if isinstance(raw_date, (int, float)):
                    try:
                        attrs["started_at"] = datetime.fromtimestamp(
                            raw_date / 1000
                        ).isoformat()
                    except (OverflowError, OSError, ValueError):
                        attrs["started_at"] = raw_date
                return attrs
        return attrs