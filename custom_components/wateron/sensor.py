"""Sensors for the WaterOn (SmarterHomes) integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WaterOnDataUpdateCoordinator


@dataclass(frozen=True)
class WaterOnSensorDescription(SensorEntityDescription):
    """Describe a society-level WaterOn sensor."""

    value_fn: Callable[[dict[str, Any]], Any] | None = None


SOCIETY_SENSORS: tuple[WaterOnSensorDescription, ...] = (
    WaterOnSensorDescription(
        key="totalConsumption",
        name="Total consumption",
        translation_key="total_consumption",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        icon="mdi:water",
    ),
    WaterOnSensorDescription(
        key="highestConsumption",
        name="Highest single-day consumption",
        translation_key="highest_consumption",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        icon="mdi:water-alert",
    ),
    WaterOnSensorDescription(
        key="lowestConsumption",
        name="Lowest single-day consumption",
        translation_key="lowest_consumption",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        icon="mdi:water-check",
    ),
    WaterOnSensorDescription(
        key="totalBillAmount",
        name="Total billed amount",
        translation_key="total_billed",
        icon="mdi:currency-inr",
        value_fn=lambda s: s.get("totalBillAmount", 0),
    ),
    WaterOnSensorDescription(
        key="totalCollectedAmount",
        name="Total collected amount",
        translation_key="total_collected",
        icon="mdi:currency-inr",
        value_fn=lambda s: s.get("totalCollectedAmount", 0),
    ),
    WaterOnSensorDescription(
        key="totalPaidCount",
        name="Apartments paid",
        translation_key="total_paid",
        icon="mdi:check-circle",
        value_fn=lambda s: s.get("totalPaidCount", 0),
    ),
    WaterOnSensorDescription(
        key="totalUnpaidCount",
        name="Apartments unpaid",
        translation_key="total_unpaid",
        icon="mdi:alert-circle",
        value_fn=lambda s: s.get("totalUnpaidCount", 0),
    ),
    WaterOnSensorDescription(
        key="last_update",
        name="Last update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda s: s.get("last_update"),
    ),
)

# Sensor description for per-apartment consumption meters.
APARTMENT_SENSOR = SensorEntityDescription(
    key="consumption",
    name="Water consumption",
    translation_key="apartment_consumption",
    device_class=SensorDeviceClass.WATER,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfVolume.LITERS,
    icon="mdi:water",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterOn sensors from a config entry."""
    coordinator: WaterOnDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        WaterOnSocietySensor(coordinator, entry, description)
        for description in SOCIETY_SENSORS
    ]

    for apartment in coordinator.data.get("apartments", []):
        entities.append(WaterOnApartmentSensor(coordinator, entry, apartment))

    async_add_entities(entities)


class WaterOnEntity(CoordinatorEntity[WaterOnDataUpdateCoordinator]):
    """Base entity with device info."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WaterOnDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_config_entry_id = entry.entry_id


class WaterOnSocietySensor(WaterOnEntity, SensorEntity):
    """Society-wide WaterOn sensor."""

    def __init__(
        self,
        coordinator: WaterOnDataUpdateCoordinator,
        entry: ConfigEntry,
        description: WaterOnSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = (
            f"wateron_{coordinator.society_id}_{description.key}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.society_id)},
            "name": f"WaterOn ({coordinator.society_id})",
            "manufacturer": "SmarterHomes Technologies",
            "model": "WaterOn Smart Water Meter",
        }

    @property
    def native_value(self) -> Any:
        society = self.coordinator.data.get("society", {})
        sensor = self.entity_description
        if sensor.value_fn is not None:
            value = sensor.value_fn(society)
            if sensor.device_class == SensorDeviceClass.TIMESTAMP:
                return self._parse_timestamp(value)
            return value
        return society.get(sensor.key)

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        attrs = {}
        if self.entity_description.key != "last_update":
            attrs["month"] = f"{data.get('year')}-{data.get('month'):02d}"
            attrs["data_points"] = data.get("society", {}).get("dataPoints", 0)
            attrs["last_update"] = data.get("last_update")
        return attrs


class WaterOnApartmentSensor(WaterOnEntity, SensorEntity):
    """Per-apartment WaterOn consumption sensor."""

    def __init__(
        self,
        coordinator: WaterOnDataUpdateCoordinator,
        entry: ConfigEntry,
        apartment: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = APARTMENT_SENSOR
        self._apt_id = apartment.get("id", "unknown")
        self._flat = apartment.get("flat", self._apt_id)
        self._attr_unique_id = (
            f"wateron_{coordinator.society_id}_apt_{self._apt_id}"
        )
        self._attr_name = f"{self._flat} water consumption"
        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, f"{coordinator.society_id}_apt_{self._apt_id}")
            },
            "name": f"WaterOn {self._flat}",
            "manufacturer": "SmarterHomes Technologies",
            "model": "WaterOn Smart Water Meter",
            "via_device": (DOMAIN, coordinator.society_id),
        }

    @property
    def native_value(self) -> float | None:
        for apartment in self.coordinator.data.get("apartments", []):
            if apartment.get("id") == self._apt_id:
                return apartment.get("consumption")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "flat": self._flat,
            "month": (
                f"{self.coordinator.data.get('year')}-"
                f"{self.coordinator.data.get('month'):02d}"
            ),
            "last_update": self.coordinator.data.get("last_update"),
        }