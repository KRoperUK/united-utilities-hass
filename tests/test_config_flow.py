"""Tests for the United Utilities config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from united_utilities import AccountLockedError, AuthError, ClientError

from custom_components.united_utilities.const import CONF_AUTH_FAILED, DOMAIN, NAME

from .conftest import ACCOUNT_NUMBER, CUSTOMER_ID, ENTRY_DATA, PIN, POSTCODE

USER_INPUT = {"account_number": ACCOUNT_NUMBER, "postcode": POSTCODE, "pin": PIN}


async def _start(hass: HomeAssistant) -> Any:
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def _submit(hass: HomeAssistant, user_input: dict[str, str]) -> Any:
    result = await _start(hass)
    with patch("custom_components.united_utilities.async_setup_entry", return_value=True):
        return await hass.config_entries.flow.async_configure(result["flow_id"], user_input=user_input)


async def test_form_is_shown(hass: HomeAssistant) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_customer_id_is_looked_up_and_postcode_not_stored(
    hass: HomeAssistant, mock_client: MagicMock, mock_lookup: AsyncMock
) -> None:
    result = await _submit(hass, {**USER_INPUT, "account_number": f" {ACCOUNT_NUMBER} ", "postcode": f" {POSTCODE} "})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == ENTRY_DATA  # customer ID from the lookup; no postcode
    assert result["result"].unique_id == ACCOUNT_NUMBER
    assert mock_lookup.await_args.args == (ACCOUNT_NUMBER, POSTCODE)
    mock_client.login.assert_awaited_once()  # never retried
    mock_client.logout.assert_awaited_once()


@pytest.mark.parametrize(
    ("exc", "errors"),
    [
        (AuthError("no match"), {"base": "no_match"}),
        (AccountLockedError("locked", code="423"), {"base": "account_locked"}),
        (ClientError("register first", code="not_registered"), {"base": "not_registered"}),
        (ClientError("boom", code="500"), {"base": "cannot_connect"}),
        (TimeoutError(), {"base": "cannot_connect"}),
        (RuntimeError("surprise"), {"base": "unknown"}),
    ],
)
async def test_lookup_errors_stop_before_login(
    hass: HomeAssistant, mock_client: MagicMock, mock_lookup: AsyncMock, exc: Exception, errors: dict[str, str]
) -> None:
    mock_lookup.side_effect = exc
    result = await _submit(hass, USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors
    assert mock_lookup.await_count == 1
    mock_client.login.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "exc", "errors"),
    [
        ("login", AuthError("bad pin", attempts_remaining=2), {"pin": "invalid_auth"}),
        ("login", AccountLockedError("locked", code="423"), {"base": "account_locked"}),
        ("account_details", ClientError("forbidden", code="403"), {"account_number": "invalid_account"}),
        ("account_details", ClientError("boom", code="500"), {"base": "cannot_connect"}),
    ],
)
async def test_login_errors_are_shown_and_not_retried(
    hass: HomeAssistant, mock_client: MagicMock, method: str, exc: Exception, errors: dict[str, str]
) -> None:
    getattr(mock_client, method).side_effect = exc
    result = await _submit(hass, USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors
    assert mock_client.login.await_count == 1


async def test_failed_logout_does_not_block_setup(hass: HomeAssistant, mock_client: MagicMock) -> None:
    mock_client.logout.side_effect = TimeoutError()
    result = await _submit(hass, USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_account_aborts_before_any_request(
    hass: HomeAssistant, mock_client: MagicMock, mock_lookup: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await _submit(hass, USER_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_lookup.assert_not_awaited()
    mock_client.login.assert_not_awaited()


async def test_reauth_relooks_up_customer_id_and_clears_flag(
    hass: HomeAssistant, mock_client: MagicMock, mock_lookup: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, data={**ENTRY_DATA, CONF_AUTH_FAILED: True})
    mock_lookup.return_value = "25000000"  # app was re-registered: new customer ID

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch("custom_components.united_utilities.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"postcode": f"{POSTCODE} ", "pin": "111111"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_lookup.await_args.args == (ACCOUNT_NUMBER, POSTCODE)  # account fixed by the entry
    assert mock_config_entry.data == {"customer_id": "25000000", "pin": "111111", "account_number": ACCOUNT_NUMBER}


async def test_reauth_bad_pin_shows_error(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_client.login.side_effect = AuthError("bad pin", attempts_remaining=1)

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"postcode": POSTCODE, "pin": "999999"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"pin": "invalid_auth"}
    assert mock_config_entry.data["customer_id"] == CUSTOMER_ID


async def test_reauth_unlinked_account_error_shows_on_form(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The reauth form has no account number field, so the error moves to the form itself."""
    mock_config_entry.add_to_hass(hass)
    mock_client.account_details.side_effect = ClientError("forbidden", code="403")

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"postcode": POSTCODE, "pin": PIN}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_account"}


async def test_reconfigure_updates_pin_and_customer_id(
    hass: HomeAssistant, mock_client: MagicMock, mock_lookup: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_lookup.return_value = "25000000"

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    with patch("custom_components.united_utilities.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"postcode": f" {POSTCODE}", "pin": " 111111 "}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_lookup.await_args.args == (ACCOUNT_NUMBER, POSTCODE)
    assert mock_config_entry.data == {"customer_id": "25000000", "pin": "111111", "account_number": ACCOUNT_NUMBER}
    assert mock_client.login.await_count == 1


async def test_reconfigure_bad_pin_keeps_entry(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_client.login.side_effect = AuthError("bad pin", attempts_remaining=2)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"postcode": POSTCODE, "pin": "999999"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"pin": "invalid_auth"}
    assert mock_config_entry.data == ENTRY_DATA
    assert mock_client.login.await_count == 1  # never retried
