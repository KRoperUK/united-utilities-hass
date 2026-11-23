"""Constants for the United Utilities integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "united_utilities"
NAME = "United Utilities"
MANUFACTURER = "United Utilities"
VERSION = "0.3.0"  # x-release-please-version

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONF_CUSTOMER_ID = "customer_id"
CONF_ACCOUNT_NUMBER = "account_number"
# Only used in the config flow to look up the customer ID; never stored.
CONF_POSTCODE = "postcode"
# Set when the PIN was rejected. While present, setup refuses to try the PIN
# again: the service locks the account after three bad attempts, and every Home
# Assistant restart would otherwise spend one. Cleared by a successful reauth.
CONF_AUTH_FAILED = "auth_failed"

# Bills and meter reads change every few weeks at most.
SCAN_INTERVAL = timedelta(hours=6)
