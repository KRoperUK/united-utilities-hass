"""Tests for setup, polling, auth handling and unload."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from united_utilities import AuthError, ClientError, NotLoggedInError

from custom_components.united_utilities.const import CONF_AUTH_FAILED

from .conftest import DETAILS, ENTRY_DATA


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _reauth_flows(hass: HomeAssistant) -> list[object]:
    return [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == SOURCE_REAUTH]


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_client.login.assert_awaited_once()

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    mock_client.logout.assert_awaited_once()


async def test_rejected_pin_opens_reauth_and_sets_flag(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_client.login.side_effect = AuthError("bad pin", attempts_remaining=2)
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert mock_config_entry.data[CONF_AUTH_FAILED] is True
    assert _reauth_flows(hass)
    assert mock_client.login.await_count == 1
    assert mock_config_entry.error_reason_translation_key == "pin_rejected"
    # HA drops the trailing full stop from translated exception messages.
    assert mock_config_entry.reason == (
        "United Utilities rejected the PIN (attempts left before lockout: 2). Reauthenticate with your current app PIN"
    )


async def test_flag_skips_login_entirely(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A restart must not spend another lockout strike on a PIN known to be wrong."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, data={**ENTRY_DATA, CONF_AUTH_FAILED: True})
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert _reauth_flows(hass)
    mock_client.login.assert_not_awaited()
    assert mock_config_entry.error_reason_translation_key == "pin_previously_rejected"


async def test_unknown_attempts_remaining_is_spelled_out(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_client.login.side_effect = AuthError("bad pin")
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.error_reason_translation_placeholders == {"attempts_remaining": "unknown"}


async def test_connection_error_retries_later(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_client.account_details.side_effect = ClientError("boom", code="500")
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert CONF_AUTH_FAILED not in mock_config_entry.data
    # The rendered message, since HA 2026.8 doesn't pass the translation key on for not-ready entries.
    assert mock_config_entry.reason == "Error communicating with United Utilities: boom"


async def test_timeout_without_message_names_the_error(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_client.account_details.side_effect = TimeoutError()
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.reason == "Error communicating with United Utilities: TimeoutError"


async def test_expired_token_relogs_in_once(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    # Next poll: the stored token is rejected once, then the fresh one works.
    mock_client.account_details.side_effect = [NotLoggedInError("expired"), DETAILS]
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert mock_client.login.await_count == 2


async def test_pin_rejected_on_relogin_stops_polling(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    mock_client.account_details.side_effect = NotLoggedInError("expired")
    mock_client.login.side_effect = AuthError("pin changed", attempts_remaining=2)
    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert mock_config_entry.data[CONF_AUTH_FAILED] is True
    assert _reauth_flows(hass)
    assert mock_client.login.await_count == 2  # setup + the single relogin attempt


async def test_unload_survives_failed_logout(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    mock_client.logout.side_effect = ClientError("forbidden", code="403")

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
