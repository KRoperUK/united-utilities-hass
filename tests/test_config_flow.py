"""Tests for the United Utilities config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from united_utilities import AuthError, ClientError

from custom_components.united_utilities.const import CONF_AUTH_FAILED, DOMAIN, NAME

from .conftest import ACCOUNT_NUMBER, CUSTOMER_ID, ENTRY_DATA, PIN


async def _start(hass: HomeAssistant) -> Any:
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_form_is_shown(hass: HomeAssistant) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_valid_credentials_create_entry(hass: HomeAssistant, mock_client: MagicMock) -> None:
    with patch("custom_components.united_utilities.async_setup_entry", return_value=True):
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"customer_id": f" {CUSTOMER_ID} ", "pin": PIN, "account_number": ACCOUNT_NUMBER},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == ENTRY_DATA  # whitespace stripped
    assert result["result"].unique_id == ACCOUNT_NUMBER
    mock_client.login.assert_awaited_once()  # never retried
    mock_client.logout.assert_awaited_once()


@pytest.mark.parametrize(
    ("failure", "field", "error"),
    [
        (("login", AuthError("bad pin", attempts_remaining=2)), "base", "invalid_auth"),
        (("account_details", ClientError("forbidden", code="403")), "account_number", "invalid_account"),
        (("account_details", ClientError("boom", code="500")), "base", "cannot_connect"),
        (("login", TimeoutError()), "base", "cannot_connect"),
        (("login", RuntimeError("surprise")), "base", "unknown"),
    ],
)
async def test_errors_are_shown_and_not_retried(
    hass: HomeAssistant, mock_client: MagicMock, failure: tuple[str, Exception], field: str, error: str
) -> None:
    method, exc = failure
    getattr(mock_client, method).side_effect = exc

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=dict(ENTRY_DATA))

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {field: error}
    assert mock_client.login.await_count == 1


async def test_duplicate_account_aborts_before_logging_in(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=dict(ENTRY_DATA))

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client.login.assert_not_awaited()


async def test_reauth_updates_credentials_and_clears_flag(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, data={**ENTRY_DATA, CONF_AUTH_FAILED: True})

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"customer_id": CUSTOMER_ID, "pin": "111111"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data["pin"] == "111111"
    assert CONF_AUTH_FAILED not in mock_config_entry.data


async def test_reauth_bad_pin_shows_error(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_client.login.side_effect = AuthError("bad pin", attempts_remaining=1)

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"customer_id": CUSTOMER_ID, "pin": "999999"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_for_another_account_aborts(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_client.account_details.side_effect = ClientError("forbidden", code="403")

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"customer_id": "25000000", "pin": PIN}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert mock_config_entry.data["customer_id"] == CUSTOMER_ID


async def test_failed_logout_does_not_block_setup(hass: HomeAssistant, mock_client: MagicMock) -> None:
    mock_client.logout.side_effect = TimeoutError()
    with patch("custom_components.united_utilities.async_setup_entry", return_value=True):
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=dict(ENTRY_DATA))

    assert result["type"] is FlowResultType.CREATE_ENTRY
