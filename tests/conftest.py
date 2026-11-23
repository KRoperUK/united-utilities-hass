"""Fixtures for the United Utilities integration tests.

All data is synthetic. The client library is mocked at the class level, so no
test ever reaches the real API (where wrong PINs count toward a lockout).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from united_utilities import (
    AccountDetails,
    Bill,
    BillReading,
    ChargeLine,
    MeterReadings,
    PaymentInfo,
    StatementItem,
)

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

# Newest first, as the API returns them: an itemised bill, then a payment-plan update.
STATEMENT = [
    StatementItem.from_json({"itemType": "PA", "date": "23112026", "amount": 51.78}),
    StatementItem.from_json({"itemType": "BI", "date": "21112026", "amount": 76.70, "documentId": "DOC-NEW"}),
    StatementItem.from_json({"itemType": "BI", "date": "08102026", "amount": 0.0, "documentId": "DOC-PLAN"}),
]


def _lines(service: str, usage: tuple[float, float, float], standing: tuple[float, float, float]) -> list[ChargeLine]:
    return [
        ChargeLine(service=service, kind="usage", quantity=usage[0], rate=usage[1], amount=usage[2]),
        ChargeLine(service=service, kind="standing", quantity=standing[0], rate=standing[1], amount=standing[2]),
    ]


GOOD_BILL = Bill(
    period_start=date(2026, 10, 9),
    period_end=date(2026, 11, 21),
    previous_reading=BillReading(1000, date(2026, 10, 8), "united_utilities"),
    current_reading=BillReading(1012, date(2026, 11, 21), "customer"),
    usage_m3=12,
    charges=[
        *_lines("water", (12, 3.0, 36.0), (44, 30.0, 3.62)),
        *_lines("wastewater", (12, 2.0, 24.0), (44, 150.0, 18.08)),
    ],
    discount=5.0,
    total=76.70,
)
PLAN_UPDATE = Bill()
BAD_BILL = Bill(
    charges=GOOD_BILL.charges,
    total=99.99,
    problems=("charge lines add up to £76.70 but the bill total is £99.99",),
)
BILLS_BY_PDF: dict[bytes, Bill] = {b"%PDF-DOC-NEW": GOOD_BILL, b"%PDF-DOC-PLAN": PLAN_UPDATE}


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
    client.statement = AsyncMock(return_value=STATEMENT)

    async def _bill_pdf(document_id: str) -> bytes:
        return f"%PDF-{document_id}".encode()

    client.bill_pdf = AsyncMock(side_effect=_bill_pdf)
    return client


@pytest.fixture
def bills() -> Generator[dict[bytes, Bill]]:
    """What ``parse_bill`` returns for each fake PDF. Tests can swap entries."""
    by_pdf = dict(BILLS_BY_PDF)
    with patch("custom_components.united_utilities.coordinator.parse_bill", side_effect=lambda pdf: by_pdf[pdf]):
        yield by_pdf


@pytest.fixture
def mock_lookup() -> Generator[AsyncMock]:
    """The customer-ID lookup the config flow runs before logging in."""
    lookup = AsyncMock(return_value=CUSTOMER_ID)
    with patch("custom_components.united_utilities.config_flow.lookup_customer_id", lookup):
        yield lookup


@pytest.fixture
def mock_client(mock_lookup: AsyncMock, bills: dict[bytes, Bill]) -> Generator[MagicMock]:
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
