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
from united_utilities import Bill

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
    #: Extra availability check on top of the coordinator's.
    available_fn: Callable[[UnitedUtilitiesData], bool] | None = None


def _trusted_bill(data: UnitedUtilitiesData) -> Bill | None:
    """The latest bill, only if it passed every consistency check."""
    latest = data.latest_bill
    return latest.bill if latest and latest.bill.trustworthy else None


def _standing_per_day(data: UnitedUtilitiesData) -> float | None:
    bill = _trusted_bill(data)
    per_year = bill.standing_charge_per_year if bill else None
    return round(per_year / 365, 4) if per_year is not None else None


def _standing_attributes(data: UnitedUtilitiesData) -> dict[str, Any]:
    bill = _trusted_bill(data)
    return {"per_year": bill.standing_charge_per_year} if bill else {}


def _tariff_rate(bill: Bill, service: str, kind: str) -> float | None:
    """The latest tariff's rate for one service, e.g. fresh water usage in £/m³."""
    lines = [c for c in bill.charges if c.service == service and c.kind == kind]
    if not lines:
        return None
    latest_end = max((c.period_end for c in lines if c.period_end), default=None)
    return next(c.rate for c in lines if c.period_end == latest_end)


def _price_attributes(data: UnitedUtilitiesData) -> dict[str, Any]:
    bill = _trusted_bill(data)
    if bill is None:
        return {}
    return {
        "water_per_m3": _tariff_rate(bill, "water", "usage"),
        "wastewater_per_m3": _tariff_rate(bill, "wastewater", "usage"),
        "from_bill_dated": data.latest_bill.date.isoformat() if data.latest_bill and data.latest_bill.date else None,
    }


def _bill_attributes(data: UnitedUtilitiesData) -> dict[str, Any]:
    bill = _trusted_bill(data)
    if bill is None:
        return {}

    def spent(service: str, kind: str) -> float:
        return round(sum(c.amount for c in bill.charges if c.service == service and c.kind == kind), 2)

    return {
        "bill_date": data.latest_bill.date.isoformat() if data.latest_bill and data.latest_bill.date else None,
        "period_start": bill.period_start.isoformat() if bill.period_start else None,
        "period_end": bill.period_end.isoformat() if bill.period_end else None,
        "usage_m3": bill.usage_m3,
        "water_usage": spent("water", "usage"),
        "water_standing_charge": spent("water", "standing"),
        "wastewater_usage": spent("wastewater", "usage"),
        "wastewater_standing_charge": spent("wastewater", "standing"),
        "discount": bill.discount,
    }


def _bill_available(data: UnitedUtilitiesData) -> bool:
    return _trusted_bill(data) is not None


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
    # From the latest itemised bill PDF. Unavailable when that bill failed its consistency
    # checks (a repair issue explains why) or no itemised bill has been found yet.
    UnitedUtilitiesSensorEntityDescription(
        key="water_price",
        translation_key="water_price",
        # Currency per volume: what the Energy dashboard expects for a water price entity.
        native_unit_of_measurement=f"GBP/{UnitOfVolume.CUBIC_METERS}",
        suggested_display_precision=3,
        value_fn=lambda d: bill.price_per_m3 if (bill := _trusted_bill(d)) else None,
        attributes_fn=_price_attributes,
        available_fn=_bill_available,
    ),
    UnitedUtilitiesSensorEntityDescription(
        key="standing_charge",
        translation_key="standing_charge",
        native_unit_of_measurement="GBP/d",
        suggested_display_precision=3,
        value_fn=_standing_per_day,
        attributes_fn=_standing_attributes,
        available_fn=_bill_available,
    ),
    UnitedUtilitiesSensorEntityDescription(
        key="last_bill",
        translation_key="last_bill",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="GBP",
        suggested_display_precision=2,
        value_fn=lambda d: bill.total if (bill := _trusted_bill(d)) else None,
        attributes_fn=_bill_attributes,
        available_fn=_bill_available,
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
    def available(self) -> bool:
        """Available when the last poll succeeded and this sensor's data is usable."""
        if not super().available:
            return False
        check = self.entity_description.available_fn
        return check is None or check(self.coordinator.data)

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
