"""Fixtures for the United Utilities integration tests.

All data is synthetic. The client library is mocked at the class level, so no
test ever reaches the real API (where wrong PINs count toward a lockout).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from united_utilities import AccountDetails, MeterReadings, PaymentInfo

from custom_components.united_utilities.const import CONF_ACCOUNT_NUMBER, CONF_CUSTOMER_ID, DOMAIN, NAME

CUSTOMER_ID = "24000000"
PIN = "000000"
ACCOUNT_NUMBER = "4000000000"
POSTCODE = "M1 1AA"

ENTRY_DATA: dict[str, Any] = {CONF_CUSTOMER_ID: CUSTOMER_ID, "pin": PIN, CONF_ACCOUNT_NUMBER: ACCOUNT_NUMBER}

DETAILS = AccountDetails.from_json(
    {
        "nextPaymentDate": "23112026",
        "nextPaymentDue": 51.78,
        "accountHistory": [{"amount": 76.51, "date": "21112026", "type": "BI", "billCancelled": False}],
        "isOnMeter": True,
        "paymentPlan": "DD",
        "isActive": True,
        "hasMissedPayment": False,
        "accountBalance": 80.58,
    }
)
METER = MeterReadings.from_json(
    {
        "details": {"meterLocation": "IN", "serialNumber": "00A000000", "lastRoutineRead": "1975"},
        "readings": [
            {"date": "21112026", "value": "1975", "readingType": "C"},
            {"date": "08102026", "value": "1965", "readingType": "R"},
        ],
        "nextReadingDate": "09042027",
    }
)
PAYMENT = PaymentInfo.from_json({"currentBalance": 80.58, "minimumPayment": 0.0, "courtDebt": False})


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> Any:
    """Let Home Assistant load integrations from ``custom_components/``."""
    yield


def _make_client() -> MagicMock:
    client = MagicMock()
    client.logged_in = False

    async def _login() -> None:
        client.logged_in = True

    async def _logout() -> None:
        client.logged_in = False

    client.login = AsyncMock(side_effect=_login)
    client.logout = AsyncMock(side_effect=_logout)
    client.account_details = AsyncMock(return_value=DETAILS)
    client.meter_readings = AsyncMock(return_value=METER)
    client.payment_info = AsyncMock(return_value=PAYMENT)
    return client


@pytest.fixture
def mock_lookup() -> Generator[AsyncMock]:
    """The customer-ID lookup the config flow runs before logging in."""
    lookup = AsyncMock(return_value=CUSTOMER_ID)
    with patch("custom_components.united_utilities.config_flow.lookup_customer_id", lookup):
        yield lookup


@pytest.fixture
def mock_client(mock_lookup: AsyncMock) -> Generator[MagicMock]:
    """One mock client, used by both setup and the config flow."""
    client = _make_client()
    with (
        patch("custom_components.united_utilities.UnitedUtilitiesClient", return_value=client),
        patch("custom_components.united_utilities.config_flow.UnitedUtilitiesClient", return_value=client),
    ):
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A configured water account."""
    return MockConfigEntry(domain=DOMAIN, title=NAME, data=dict(ENTRY_DATA), unique_id=ACCOUNT_NUMBER)
