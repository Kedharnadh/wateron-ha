"""Sensors for the WaterOn (SmarterHomes) integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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

from .const import ACCOUNT_RESIDENT, DOMAIN
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


@dataclass(frozen=True)
class WaterOnResidentSensorDescription(SensorEntityDescription):
    """Describe a resident bill sensor keyed per apartment."""

    value_fn: Callable[[dict[str, Any], dict[str, Any]], Any] | None = None


PAID_VALUES_TRUE = {"yes", "y", "true", "1", "paid"}
PAID_VALUES_FALSE = {"no", "n", "false", "0", "pending"}


def _bill_amount(bill: dict[str, Any]) -> float | None:
    amount = bill.get("amount")
    if amount is None or amount == "":
        return None
    try:
        return float(amount)
    except (TypeError, ValueError):
        return None


def _bill_paid(bill: dict[str, Any]) -> str | None:
    paid = str(bill.get("paid") or "").strip().lower()
    if not paid:
        return None
    if paid in PAID_VALUES_TRUE:
        return "Paid"
    if paid in PAID_VALUES_FALSE:
        return "Pending"
    return str(bill.get("paid"))


def _bill_date(bill: dict[str, Any], _: dict[str, Any]) -> date | None:
    raw = bill.get("date")
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


RESIDENT_BILL_SENSORS: tuple[WaterOnResidentSensorDescription, ...] = (
    WaterOnResidentSensorDescription(
        key="amount",
        name="Bill amount",
        translation_key="bill_amount",
        icon="mdi:currency-inr",
        value_fn=_bill_amount,
    ),
    WaterOnResidentSensorDescription(
        key="date",
        name="Bill date",
        translation_key="bill_date",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar",
        value_fn=_bill_date,
    ),
    WaterOnResidentSensorDescription(
        key="paid",
        name="Bill paid",
        translation_key="bill_paid",
        icon="mdi:check-circle",
        value_fn=lambda bill, _: _bill_paid(bill),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterOn sensors from a config entry."""
    coordinator: WaterOnDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    if coordinator.data.get("account_type") != ACCOUNT_RESIDENT:
        entities.extend(
            WaterOnSocietySensor(coordinator, entry, description)
            for description in SOCIETY_SENSORS
        )

    for apartment in coordinator.data.get("apartments", []):
        entities.append(WaterOnApartmentSensor(coordinator, entry, apartment))
        if coordinator.data.get("account_type") == ACCOUNT_RESIDENT:
            entities.extend(
                WaterOnResidentBillSensor(coordinator, entry, apartment, description)
                for description in RESIDENT_BILL_SENSORS
            )

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
        unit = apartment.get("unit_abbrev") or UnitOfVolume.LITERS
        self._attr_native_unit_of_measurement = (
            unit if unit in (UnitOfVolume.LITERS, "KL", "kl") else UnitOfVolume.LITERS
        )
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


class WaterOnResidentBillSensor(WaterOnEntity, SensorEntity):
    """Resident per-apartment bill sensor (amount, date, paid status)."""

    def __init__(
        self,
        coordinator: WaterOnDataUpdateCoordinator,
        entry: ConfigEntry,
        apartment: dict[str, Any],
        description: WaterOnResidentSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._apt_id = apartment.get("id", "unknown")
        self._flat = apartment.get("flat", self._apt_id)
        self._attr_unique_id = (
            f"wateron_{coordinator.society_id}_bill_"
            f"{self._apt_id}_{description.key}"
        )
        self._attr_name = (
            f"{self._flat} {description.name.lower()}"
        )
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
    def native_value(self) -> Any:
        value_fn = self.entity_description.value_fn
        if value_fn is None:
            return None
        bill = self.coordinator.data.get("bills", {}).get(self._apt_id, {})
        return value_fn(bill, self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        bill = self.coordinator.data.get("bills", {}).get(self._apt_id, {})
        return {
            "flat": self._flat,
            "bill_cycle_id": bill.get("billCycleId"),
            "online_bill": bill.get("onlineBill"),
            "block_app": bill.get("blockApp"),
            "client_id": bill.get("clientId"),
            "last_update": self.coordinator.data.get("last_update"),
        }