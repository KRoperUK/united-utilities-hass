"""Sensor platform for the United Utilities integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, NAME
from .coordinator import UnitedUtilitiesConfigEntry, UnitedUtilitiesCoordinator, UnitedUtilitiesData

# Read-only entities fed by one coordinator; nothing to serialise.
PARALLEL_UPDATES = 0

# The API tags each reading "C" (read by the customer) or "R" (read by United Utilities).
_READING_SOURCE = {"C": "customer", "R": "united_utilities"}


@dataclass(frozen=True, kw_only=True)
class UnitedUtilitiesSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor and how to read its value from a poll."""

    value_fn: Callable[[UnitedUtilitiesData], float | int | date | None]
    attributes_fn: Callable[[UnitedUtilitiesData], dict[str, Any]] | None = None


def _latest_reading_attributes(data: UnitedUtilitiesData) -> dict[str, Any]:
    latest = data.meter.latest
    if latest is None:
        return {}
    return {
        "reading_date": latest.date.isoformat() if latest.date else None,
        "read_by": _READING_SOURCE.get(latest.reading_type or "", latest.reading_type),
    }


SENSORS: tuple[UnitedUtilitiesSensorEntityDescription, ...] = (
    UnitedUtilitiesSensorEntityDescription(
        key="meter_reading",
        translation_key="meter_reading",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        value_fn=lambda d: d.meter.latest.value if d.meter.latest else None,
        attributes_fn=_latest_reading_attributes,
    ),
    UnitedUtilitiesSensorEntityDescription(
        key="last_reading_date",
        translation_key="last_reading_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: d.meter.latest.date if d.meter.latest else None,
    ),
    UnitedUtilitiesSensorEntityDescription(
        key="next_reading_date",
        translation_key="next_reading_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: d.meter.next_reading_date,
    ),
    UnitedUtilitiesSensorEntityDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="GBP",
        suggested_display_precision=2,
        value_fn=lambda d: d.details.account_balance,
    ),
    UnitedUtilitiesSensorEntityDescription(
        key="next_payment",
        translation_key="next_payment",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="GBP",
        suggested_display_precision=2,
        value_fn=lambda d: d.details.next_payment_due,
    ),
    UnitedUtilitiesSensorEntityDescription(
        key="next_payment_date",
        translation_key="next_payment_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: d.details.next_payment_date,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnitedUtilitiesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up United Utilities sensors."""
    coordinator = entry.runtime_data
    async_add_entities(UnitedUtilitiesSensor(coordinator, entry, description) for description in SENSORS)


class UnitedUtilitiesSensor(CoordinatorEntity[UnitedUtilitiesCoordinator], SensorEntity):
    """A single value from the water account."""

    _attr_has_entity_name = True
    entity_description: UnitedUtilitiesSensorEntityDescription

    def __init__(
        self,
        coordinator: UnitedUtilitiesCoordinator,
        entry: UnitedUtilitiesConfigEntry,
        description: UnitedUtilitiesSensorEntityDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        account_key = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{account_key}_{description.key}"
        # Device name deliberately omits the account number: it ends up in logs and screenshots.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_key)},
            name=NAME,
            manufacturer=MANUFACTURER,
            model="Water account",
            configuration_url="https://myaccount.unitedutilities.com/",
        )

    @property
    def native_value(self) -> float | int | date | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, if this sensor has any."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
