"""Tests for the sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from united_utilities import MeterReadings

from custom_components.united_utilities.const import DOMAIN

from .conftest import ACCOUNT_NUMBER


@pytest.fixture
async def loaded(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    entity_registry_enabled_by_default: None,
) -> MockConfigEntry:
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


@pytest.mark.parametrize(
    ("entity_id", "state", "unit"),
    [
        ("sensor.united_utilities_meter_reading", "1975", "m³"),
        ("sensor.united_utilities_last_reading_date", "2026-11-21", None),
        ("sensor.united_utilities_next_reading_date", "2027-04-09", None),
        ("sensor.united_utilities_account_balance", "80.58", "GBP"),
        ("sensor.united_utilities_next_payment", "51.78", "GBP"),
        ("sensor.united_utilities_next_payment_date", "2026-11-23", None),
    ],
)
async def test_sensor_states(
    hass: HomeAssistant, loaded: MockConfigEntry, entity_id: str, state: str, unit: str | None
) -> None:
    current = hass.states.get(entity_id)
    assert current is not None
    assert current.state == state
    assert current.attributes.get("unit_of_measurement") == unit


async def test_meter_reading_attributes(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    state = hass.states.get("sensor.united_utilities_meter_reading")
    assert state is not None
    assert state.attributes["reading_date"] == "2026-11-21"
    assert state.attributes["read_by"] == "customer"
    assert state.attributes["state_class"] == "total_increasing"
    assert "serial_number" not in state.attributes


async def test_unique_ids_use_account_number(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    registry = er.async_get(hass)
    entry = registry.async_get("sensor.united_utilities_account_balance")
    assert entry is not None
    assert entry.unique_id == f"{ACCOUNT_NUMBER}_balance"


async def test_one_service_device_without_account_number(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), loaded.entry_id)
    assert len(devices) == 1
    device = devices[0]
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.name == "United Utilities"
    assert device.identifiers == {(DOMAIN, ACCOUNT_NUMBER)}
    assert ACCOUNT_NUMBER not in (device.name or "")


async def test_no_readings_is_unknown(hass: HomeAssistant, loaded: MockConfigEntry, mock_client: MagicMock) -> None:
    mock_client.meter_readings.return_value = MeterReadings.from_json({"readings": []})
    await loaded.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("sensor.united_utilities_meter_reading")
    assert state is not None
    assert state.state == "unknown"
    assert hass.states.get("sensor.united_utilities_last_reading_date").state == "unknown"  # type: ignore[union-attr]


async def test_last_reading_date_is_diagnostic_and_off_by_default(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entry = er.async_get(hass).async_get("sensor.united_utilities_last_reading_date")
    assert entry is not None
    assert entry.entity_category is EntityCategory.DIAGNOSTIC
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get("sensor.united_utilities_last_reading_date") is None
