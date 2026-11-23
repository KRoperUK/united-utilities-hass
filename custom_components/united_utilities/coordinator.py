"""Data update coordinator for the United Utilities integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from united_utilities import (
    AccountDetails,
    AuthError,
    ClientError,
    MeterReadings,
    NotLoggedInError,
    PaymentInfo,
    UnitedUtilitiesClient,
)

from .const import CONF_AUTH_FAILED, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type UnitedUtilitiesConfigEntry = ConfigEntry[UnitedUtilitiesCoordinator]


@dataclass(frozen=True)
class UnitedUtilitiesData:
    """One poll's worth of account data."""

    details: AccountDetails
    meter: MeterReadings
    payment: PaymentInfo


class UnitedUtilitiesCoordinator(DataUpdateCoordinator[UnitedUtilitiesData]):
    """Polls one water account.

    The session token is kept between polls. A rejected token triggers exactly
    one fresh login; a rejected PIN stops polling and opens a reauth flow,
    because each wrong PIN counts toward the service's 3-strike lockout.
    """

    config_entry: UnitedUtilitiesConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: UnitedUtilitiesConfigEntry,
        client: UnitedUtilitiesClient,
    ) -> None:
        """Set up the coordinator."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> UnitedUtilitiesData:
        """Fetch account data, logging in when needed."""
        try:
            if not self.client.logged_in:
                await self.client.login()
            try:
                return await self._fetch()
            except NotLoggedInError:
                # Token expired between polls: one fresh login, never a loop.
                await self.client.login()
                return await self._fetch()
        except AuthError as err:
            self._mark_auth_failed()
            raise ConfigEntryAuthFailed(
                f"United Utilities rejected the PIN (attempts remaining: {err.attempts_remaining})"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error communicating with United Utilities: {err}") from err

    async def _fetch(self) -> UnitedUtilitiesData:
        return UnitedUtilitiesData(
            details=await self.client.account_details(),
            meter=await self.client.meter_readings(),
            payment=await self.client.payment_info(),
        )

    def _mark_auth_failed(self) -> None:
        entry = self.config_entry
        if not entry.data.get(CONF_AUTH_FAILED):
            self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_AUTH_FAILED: True})
