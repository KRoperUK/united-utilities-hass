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
from united_utilities import AuthError, ClientError, UnitedUtilitiesClient

from .const import CONF_ACCOUNT_NUMBER, CONF_AUTH_FAILED, CONF_CUSTOMER_ID, DOMAIN, NAME

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

    fields: dict[Any, Any] = {field(CONF_CUSTOMER_ID): str, vol.Required(CONF_PIN): _PIN_SELECTOR}
    if include_account:
        fields[field(CONF_ACCOUNT_NUMBER)] = str
    return vol.Schema(fields)


class _InvalidAccount(Exception):
    """Login worked but the account number isn't on this login."""


class UnitedUtilitiesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup and reauthentication for a water account."""

    VERSION = 1

    async def _validate(self, customer_id: str, pin: str, account_number: str) -> None:
        """Log in once and read the account. Never retries: wrong PINs count toward a lockout."""
        client = UnitedUtilitiesClient(customer_id, pin, account_number, session=async_get_clientsession(self.hass))
        await client.login()
        try:
            await client.account_details()
        except ClientError as err:
            if err.code == "403":
                raise _InvalidAccount from err
            raise
        finally:
            with contextlib.suppress(ClientError, TimeoutError):
                await client.logout()

    async def _try_validate(self, customer_id: str, pin: str, account_number: str) -> dict[str, str]:
        """Run validation and map failures onto form errors."""
        try:
            await self._validate(customer_id, pin, account_number)
        except AuthError:
            return {"base": "invalid_auth"}
        except _InvalidAccount:
            return {CONF_ACCOUNT_NUMBER: "invalid_account"}
        except ClientError, TimeoutError:
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001 - a flow must never show a traceback
            _LOGGER.exception("Unexpected error validating United Utilities credentials")
            return {"base": "unknown"}
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect customer ID, PIN and account number."""
        errors: dict[str, str] = {}
        if user_input is not None:
            customer_id = user_input[CONF_CUSTOMER_ID].strip()
            pin = user_input[CONF_PIN].strip()
            account_number = user_input[CONF_ACCOUNT_NUMBER].strip()

            await self.async_set_unique_id(account_number)
            self._abort_if_unique_id_configured()

            errors = await self._try_validate(customer_id, pin, account_number)
            if not errors:
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
        """Collect a new customer ID / PIN for the existing account."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            customer_id = user_input[CONF_CUSTOMER_ID].strip()
            pin = user_input[CONF_PIN].strip()
            errors = await self._try_validate(customer_id, pin, entry.data[CONF_ACCOUNT_NUMBER])
            if errors.get(CONF_ACCOUNT_NUMBER):
                # The account number is fixed for this entry, so these credentials belong elsewhere.
                return self.async_abort(reason="wrong_account")
            if not errors:
                data = {k: v for k, v in entry.data.items() if k != CONF_AUTH_FAILED}
                data.update({CONF_CUSTOMER_ID: customer_id, CONF_PIN: pin})
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_schema(entry.data, include_account=False),
            errors=errors,
        )
