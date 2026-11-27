"""The United Utilities integration.

Read-only: exposes balance, payments and meter readings from the United
Utilities mobile app API via the ``united-utilities`` client library.
"""

from __future__ import annotations

import contextlib

from homeassistant.const import CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from united_utilities import ClientError, UnitedUtilitiesClient

from .const import CONF_ACCOUNT_NUMBER, CONF_AUTH_FAILED, CONF_CUSTOMER_ID, DOMAIN, PLATFORMS
from .coordinator import UnitedUtilitiesConfigEntry, UnitedUtilitiesCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: UnitedUtilitiesConfigEntry) -> bool:
    """Set up United Utilities from a config entry."""
    if entry.data.get(CONF_AUTH_FAILED):
        # Don't spend another lockout strike on a PIN already known to be wrong.
        raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="pin_previously_rejected")

    client = UnitedUtilitiesClient(
        entry.data[CONF_CUSTOMER_ID],
        entry.data[CONF_PIN],
        entry.data[CONF_ACCOUNT_NUMBER],
        session=async_get_clientsession(hass),
    )
    coordinator = UnitedUtilitiesCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UnitedUtilitiesConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # Best effort: the token expires on its own.
        with contextlib.suppress(ClientError, TimeoutError):
            await entry.runtime_data.client.logout()
    return unloaded
