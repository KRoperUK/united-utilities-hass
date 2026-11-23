"""Config flow for the United Utilities integration."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PIN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
from united_utilities import AccountLockedError, AuthError, ClientError, UnitedUtilitiesClient, lookup_customer_id

from .const import CONF_ACCOUNT_NUMBER, CONF_AUTH_FAILED, CONF_CUSTOMER_ID, CONF_POSTCODE, DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)

_PIN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _schema(suggested: Mapping[str, Any] | None, *, include_account: bool) -> Any:
    """Form schema, pre-filled with ``suggested`` values (never the PIN).

    Typed ``Any`` on purpose: HA 2026.9+ swaps voluptuous for probatio (aliased as
    ``voluptuous`` at runtime), so the stubs disagree with ``async_show_form``'s
    signature, while HA 2026.8 (our floor) still ships real voluptuous.
    """
    suggested = suggested or {}

    def field(key: str) -> vol.Required:
        return vol.Required(key, description={"suggested_value": suggested.get(key)})

    fields: dict[Any, Any] = {}
    if include_account:
        fields[field(CONF_ACCOUNT_NUMBER)] = str
    fields[field(CONF_POSTCODE)] = str
    fields[vol.Required(CONF_PIN)] = _PIN_SELECTOR
    return vol.Schema(fields)


class _FormError(Exception):
    """Validation failed in a way the form can explain."""

    def __init__(self, field: str, error: str) -> None:
        super().__init__(error)
        self.errors = {field: error}


class UnitedUtilitiesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup and reauthentication for a water account."""

    VERSION = 1

    async def _validate(self, account_number: str, postcode: str, pin: str) -> str:
        """Find the app customer ID, log in once and read the account. Returns the customer ID.

        Nothing here is retried: wrong PINs and wrong postcodes both count toward a lockout.
        """
        session = async_get_clientsession(self.hass)
        try:
            customer_id = await lookup_customer_id(account_number, postcode, session=session)
        except AccountLockedError as err:
            raise _FormError("base", "account_locked") from err
        except AuthError as err:
            raise _FormError("base", "no_match") from err
        except ClientError as err:
            if err.code == "not_registered":
                raise _FormError("base", "not_registered") from err
            raise

        client = UnitedUtilitiesClient(customer_id, pin, account_number, session=session)
        try:
            await client.login()
        except AccountLockedError as err:
            raise _FormError("base", "account_locked") from err
        except AuthError as err:
            raise _FormError(CONF_PIN, "invalid_auth") from err
        try:
            await client.account_details()
        except ClientError as err:
            if err.code == "403":
                raise _FormError(CONF_ACCOUNT_NUMBER, "invalid_account") from err
            raise
        finally:
            with contextlib.suppress(ClientError, TimeoutError):
                await client.logout()
        return customer_id

    async def _try_validate(self, account_number: str, postcode: str, pin: str) -> tuple[str | None, dict[str, str]]:
        """Run validation and map failures onto form errors."""
        try:
            return await self._validate(account_number, postcode, pin), {}
        except _FormError as err:
            return None, err.errors
        except ClientError, TimeoutError:
            return None, {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001 - a flow must never show a traceback
            _LOGGER.exception("Unexpected error validating United Utilities credentials")
            return None, {"base": "unknown"}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect account number, postcode and PIN."""
        errors: dict[str, str] = {}
        if user_input is not None:
            account_number = user_input[CONF_ACCOUNT_NUMBER].strip()
            pin = user_input[CONF_PIN].strip()

            await self.async_set_unique_id(account_number)
            self._abort_if_unique_id_configured()

            customer_id, errors = await self._try_validate(account_number, user_input[CONF_POSTCODE], pin)
            if customer_id is not None:
                # The postcode is only needed for the lookup, so it isn't stored.
                return self.async_create_entry(
                    title=NAME,
                    data={CONF_CUSTOMER_ID: customer_id, CONF_PIN: pin, CONF_ACCOUNT_NUMBER: account_number},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input, include_account=True),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after the PIN was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect the postcode and current PIN for the existing account.

        The customer ID is looked up again because re-registering the app issues a new one.
        """
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input[CONF_PIN].strip()
            customer_id, errors = await self._try_validate(
                entry.data[CONF_ACCOUNT_NUMBER], user_input[CONF_POSTCODE], pin
            )
            if customer_id is not None:
                data = {k: v for k, v in entry.data.items() if k != CONF_AUTH_FAILED}
                data.update({CONF_CUSTOMER_ID: customer_id, CONF_PIN: pin})
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_schema(user_input, include_account=False),
            errors=errors,
        )
