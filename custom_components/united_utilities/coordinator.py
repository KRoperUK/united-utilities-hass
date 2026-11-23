"""Data update coordinator for the United Utilities integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from united_utilities import (
    AccountDetails,
    AuthError,
    Bill,
    ClientError,
    MeterReadings,
    NotLoggedInError,
    PaymentInfo,
    UnitedUtilitiesClient,
    parse_bill,
)

from .const import CONF_AUTH_FAILED, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Payment-plan updates are issued as bills with no charges, so look a few bills
# back for the latest itemised one. Each bill is downloaded at most once per run.
MAX_BILLS_TO_CHECK = 3
ISSUE_BILL_UNREADABLE = "bill_unreadable"
ISSUE_TRACKER_URL = "https://github.com/KRoperUK/united-utilities-hass/issues"

type UnitedUtilitiesConfigEntry = ConfigEntry[UnitedUtilitiesCoordinator]


@dataclass(frozen=True)
class LatestBill:
    """The newest bill that has charges, or that failed its consistency checks."""

    date: date | None
    bill: Bill


@dataclass(frozen=True)
class UnitedUtilitiesData:
    """One poll's worth of account data."""

    details: AccountDetails
    meter: MeterReadings
    payment: PaymentInfo
    latest_bill: LatestBill | None = None


class UnitedUtilitiesCoordinator(DataUpdateCoordinator[UnitedUtilitiesData]):
    """Polls one water account.

    The session token is kept between polls. A rejected token triggers exactly
    one fresh login; a rejected PIN stops polling and opens a reauth flow,
    because each wrong PIN counts toward the service's 3-strike lockout.

    Bill PDFs are parsed for tariffs. A bill that fails the library's consistency
    checks is never used for prices: it raises a repair issue instead.
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
        # Parsed bills by document ID. Bills never change, so each is downloaded once.
        self._bills: dict[str, Bill] = {}
        self._latest_bill: LatestBill | None = None
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
        details = await self.client.account_details()
        meter = await self.client.meter_readings()
        payment = await self.client.payment_info()
        await self._refresh_latest_bill()
        return UnitedUtilitiesData(details=details, meter=meter, payment=payment, latest_bill=self._latest_bill)

    async def _refresh_latest_bill(self) -> None:
        """Find the newest itemised bill. A failure here keeps the previous bill, never fails the poll."""
        try:
            items = [i for i in await self.client.statement() if i.item_type == "BI" and i.document_id]
            for item in items[:MAX_BILLS_TO_CHECK]:
                document_id = item.document_id
                assert document_id is not None  # filtered above; narrows the type
                bill = self._bills.get(document_id)
                if bill is None:
                    pdf = await self.client.bill_pdf(document_id)
                    # pypdf is synchronous and CPU-bound.
                    bill = await self.hass.async_add_executor_job(parse_bill, pdf)
                    self._bills[document_id] = bill
                if bill.itemised or bill.problems:
                    self._set_latest_bill(LatestBill(item.date, bill))
                    return
        except NotLoggedInError:
            raise  # let the caller do its single re-login
        except (ClientError, TimeoutError) as err:
            _LOGGER.debug("Couldn't fetch bills this poll; keeping the previous bill: %s", err)

    def _set_latest_bill(self, latest: LatestBill) -> None:
        previous = self._latest_bill
        self._latest_bill = latest
        issue_id = f"{ISSUE_BILL_UNREADABLE}_{self.config_entry.entry_id}"
        if not latest.bill.problems:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        if previous is None or previous.bill is not latest.bill:
            # Problems contain amounts and volumes only, never personal details.
            _LOGGER.warning(
                "The United Utilities bill dated %s failed its consistency checks, so its prices won't be used: %s",
                latest.date,
                "; ".join(latest.bill.problems),
            )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_BILL_UNREADABLE,
            translation_placeholders={
                "bill_date": latest.date.isoformat() if latest.date else "unknown",
                "problems": "; ".join(latest.bill.problems),
                # hassfest rejects URLs inside translation strings, so it's passed in.
                "issue_tracker": ISSUE_TRACKER_URL,
            },
        )

    def _mark_auth_failed(self) -> None:
        entry = self.config_entry
        if not entry.data.get(CONF_AUTH_FAILED):
            self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_AUTH_FAILED: True})
