"""Valve control switches for the WaterOn (SmarterHomes) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up WaterOn valve switches from a config entry."""
    coordinator: WaterOnDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[WaterOnValveSwitch] = []
    seen: set[str] = set()

    for valve in coordinator.data.get("valves", []):
        meter_id = valve.get("meterId", "")
        if meter_id and meter_id not in seen:
            seen.add(meter_id)
            entities.append(WaterOnValveSwitch(coordinator, entry, valve))

    # Fallback: create a switch per apartment meter if valve status is not
    # returned by the API (e.g. wireless meters without valve control).
    if not entities:
        for apartment in coordinator.data.get("apartments", []):
            meter_id = apartment.get("meterId", "")
            if meter_id and meter_id not in seen:
                seen.add(meter_id)
                entities.append(
                    WaterOnValveSwitch(
                        coordinator,
                        entry,
                        {
                            "meterId": meter_id,
                            "aptNo": apartment.get("flat", ""),
                            "valveStatus": "",
                            "status": None,
                            "actionReason": "",
                        },
                    )
                )

    if entities:
        async_add_entities(entities)


class WaterOnValveSwitch(CoordinatorEntity[WaterOnDataUpdateCoordinator], SwitchEntity):
    """A switch that opens/closes a WaterOn smart valve."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WaterOnDataUpdateCoordinator,
        entry: ConfigEntry,
        valve: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._attr_config_entry_id = entry.entry_id
        self._meter_id = valve.get("meterId", "")
        self._apt_no = valve.get("aptNo") or "Meter"
        self._attr_unique_id = (
            f"wateron_{coordinator.society_id}_valve_{self._meter_id}"
        )
        self._attr_name = f"{self._apt_no} valve"
        self._attr_icon = "mdi:water-valve"
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
        """True = valve open, False = valve closed, None = unknown."""
        for valve in self.coordinator.data.get("valves", []):
            if valve.get("meterId") == self._meter_id:
                status = valve.get("valveStatus", "")
                if status:
                    return status.lower() in ("open", "on", "1", "true")
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        for valve in self.coordinator.data.get("valves", []):
            if valve.get("meterId") == self._meter_id:
                return {
                    "meter_id": self._meter_id,
                    "apt_no": self._apt_no,
                    "action_reason": valve.get("actionReason", ""),
                    "status": valve.get("status"),
                    "last_update": self.coordinator.data.get("last_update"),
                }
        return {"meter_id": self._meter_id, "apt_no": self._apt_no}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Open the valve."""
        await self.coordinator.async_valve_action(int(self._meter_id), "open")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Close the valve."""
        await self.coordinator.async_valve_action(int(self._meter_id), "close")