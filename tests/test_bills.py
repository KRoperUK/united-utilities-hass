"""Bill-derived sensors, bill caching, and the repair issue for bills that fail their checks."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from united_utilities import Bill, ClientError, NotLoggedInError, StatementItem

from custom_components.united_utilities.const import DOMAIN
from custom_components.united_utilities.coordinator import ISSUE_BILL_UNREADABLE
from custom_components.united_utilities.diagnostics import async_get_config_entry_diagnostics

from .conftest import BAD_BILL, GOOD_BILL, STATEMENT

PRICE = "sensor.united_utilities_water_price"
STANDING = "sensor.united_utilities_standing_charge"
LAST_BILL = "sensor.united_utilities_last_bill"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{ISSUE_BILL_UNREADABLE}_{entry.entry_id}")


async def test_bill_sensors_from_trustworthy_bill(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)

    price = hass.states.get(PRICE)
    assert price is not None
    assert price.state == "5.0"
    assert price.attributes["unit_of_measurement"] == "GBP/m³"
    assert price.attributes["water_per_m3"] == 3.0
    assert price.attributes["wastewater_per_m3"] == 2.0
    assert price.attributes["from_bill_dated"] == "2026-11-21"

    standing = hass.states.get(STANDING)
    assert standing is not None
    assert float(standing.state) == pytest.approx(180 / 365, abs=1e-4)
    assert standing.attributes["per_year"] == 180.0

    last = hass.states.get(LAST_BILL)
    assert last is not None
    assert last.state == "76.7"
    assert last.attributes["period_start"] == "2026-10-09"
    assert last.attributes["water_usage"] == 36.0
    assert last.attributes["wastewater_standing_charge"] == 18.08
    assert last.attributes["discount"] == 5.0
    assert _issue(hass, mock_config_entry) is None


async def test_each_bill_is_downloaded_once(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    assert mock_client.bill_pdf.await_count == 1  # newest bill was itemised: no need to look further

    await mock_config_entry.runtime_data.async_refresh()
    assert mock_client.bill_pdf.await_count == 1  # cached


async def test_skips_payment_plan_updates_to_find_itemised_bill(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry, bills: dict[bytes, Bill]
) -> None:
    newer_plan = StatementItem.from_json({"itemType": "BI", "date": "01122026", "documentId": "DOC-PLAN"})
    mock_client.statement.return_value = [newer_plan, *STATEMENT[:2]]
    await _setup(hass, mock_config_entry)

    assert [c.args[0] for c in mock_client.bill_pdf.await_args_list] == ["DOC-PLAN", "DOC-NEW"]
    assert hass.states.get(LAST_BILL).attributes["bill_date"] == "2026-11-21"  # type: ignore[union-attr]


async def test_untrustworthy_bill_raises_repair_issue_and_withholds_prices(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry, bills: dict[bytes, Bill]
) -> None:
    bills[b"%PDF-DOC-NEW"] = BAD_BILL
    await _setup(hass, mock_config_entry)

    for entity_id in (PRICE, STANDING, LAST_BILL):
        assert hass.states.get(entity_id).state == "unavailable"  # type: ignore[union-attr]
    # The account sensors are unaffected.
    assert hass.states.get("sensor.united_utilities_account_balance").state == "80.58"  # type: ignore[union-attr]

    issue = _issue(hass, mock_config_entry)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == ISSUE_BILL_UNREADABLE
    assert issue.translation_placeholders == {
        "bill_date": "2026-11-21",
        "problems": "charge lines add up to £76.70 but the bill total is £99.99",
        "issue_tracker": "https://github.com/KRoperUK/united-utilities-hass/issues",
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert diagnostics["latest_bill"]["trustworthy"] is False
    assert diagnostics["latest_bill"]["problems"] == list(BAD_BILL.problems)


async def test_issue_clears_when_a_good_bill_arrives(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry, bills: dict[bytes, Bill]
) -> None:
    bills[b"%PDF-DOC-NEW"] = BAD_BILL
    await _setup(hass, mock_config_entry)
    assert _issue(hass, mock_config_entry) is not None

    newer = StatementItem.from_json({"itemType": "BI", "date": "02012027", "documentId": "DOC-NEWER"})
    mock_client.statement.return_value = [newer, *STATEMENT]
    bills[b"%PDF-DOC-NEWER"] = GOOD_BILL
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert _issue(hass, mock_config_entry) is None
    assert hass.states.get(PRICE).state == "5.0"  # type: ignore[union-attr]


async def test_no_itemised_bill_leaves_bill_sensors_unavailable_without_issue(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_client.statement.return_value = [STATEMENT[2]]  # only a payment-plan update
    await _setup(hass, mock_config_entry)

    assert hass.states.get(PRICE).state == "unavailable"  # type: ignore[union-attr]
    assert _issue(hass, mock_config_entry) is None


async def test_bill_download_failure_keeps_previous_bill_and_poll_succeeds(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    mock_client.statement.side_effect = ClientError("boom", code="500")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success
    assert hass.states.get(PRICE).state == "5.0"  # type: ignore[union-attr]


async def test_expired_token_during_bill_fetch_relogs_in_once(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    mock_client.statement.side_effect = [NotLoggedInError("expired"), STATEMENT]
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert mock_client.login.await_count == 2
