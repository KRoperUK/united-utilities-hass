"""Base entity for the United Utilities integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, NAME
from .coordinator import UnitedUtilitiesCoordinator


class UnitedUtilitiesEntity(CoordinatorEntity[UnitedUtilitiesCoordinator]):
    """An entity on the water account's device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UnitedUtilitiesCoordinator, key: str) -> None:
        """Attach the entity to the account's device."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        account_key = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{account_key}_{key}"
        # Device name deliberately omits the account number: it ends up in logs and screenshots.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_key)},
            entry_type=DeviceEntryType.SERVICE,
            name=NAME,
            manufacturer=MANUFACTURER,
            model="Water account",
            configuration_url="https://myaccount.unitedutilities.com/",
        )
