"""Diagnostics for the United Utilities integration.

Diagnostics get pasted into public issues, so this builds a summary from an
allowlist instead of dumping payloads: a redaction list fails open the moment a
reverse-engineered API adds a field.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from homeassistant.core import HomeAssistant

from .const import VERSION
from .coordinator import UnitedUtilitiesConfigEntry


def _library_version() -> str:
    try:
        return version("united-utilities")
    except PackageNotFoundError:  # pragma: no cover - always installed at runtime
        return "unknown"


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: UnitedUtilitiesConfigEntry) -> dict[str, Any]:
    """Return a non-identifying summary of the entry and its last poll."""
    coordinator = entry.runtime_data
    data = coordinator.data
    summary: dict[str, Any] = {
        "integration_version": VERSION,
        "library_version": _library_version(),
        "last_update_success": coordinator.last_update_success,
        "logged_in": coordinator.client.logged_in,
        "has_data": data is not None,
    }
    if data is not None:
        latest = data.meter.latest
        summary["account"] = {
            "is_active": data.details.is_active,
            "is_on_meter": data.details.is_on_meter,
            "payment_plan": data.details.payment_plan,
            "has_missed_payment": data.details.has_missed_payment,
            "history_items": len(data.details.account_history),
        }
        summary["meter"] = {
            "has_details": data.meter.details is not None,
            "reading_count": len(data.meter.readings),
            "latest_reading_date": latest.date.isoformat() if latest and latest.date else None,
            "latest_reading_type": latest.reading_type if latest else None,
            "next_reading_date": data.meter.next_reading_date.isoformat() if data.meter.next_reading_date else None,
        }
        # Shape and cross-check results only: enough to debug a template change, no amounts
        # that would identify a household.
        bill = data.latest_bill.bill if data.latest_bill else None
        summary["latest_bill"] = (
            None
            if bill is None
            else {
                "bill_date": data.latest_bill.date.isoformat() if data.latest_bill and data.latest_bill.date else None,
                "itemised": bill.itemised,
                "trustworthy": bill.trustworthy,
                "charge_lines": len(bill.charges),
                "tariff_periods": len({(c.period_start, c.period_end) for c in bill.charges}),
                "has_readings": bill.previous_reading is not None and bill.current_reading is not None,
                "has_discount": bill.discount is not None,
                "problems": list(bill.problems),
            }
        )
    return summary
