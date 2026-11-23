"""Diagnostics must never leak credentials or account identifiers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.united_utilities.diagnostics import async_get_config_entry_diagnostics

from .conftest import ACCOUNT_NUMBER, CUSTOMER_ID, PIN


async def test_diagnostics_are_allowlisted(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    dumped = json.dumps(result)

    for secret in (CUSTOMER_ID, PIN, ACCOUNT_NUMBER, "00A000000"):
        assert secret not in dumped
    assert result["has_data"] is True
    assert result["meter"]["reading_count"] == 2
    assert result["meter"]["latest_reading_date"] == "2026-11-21"
    assert result["account"]["payment_plan"] == "DD"
