"""Config flow for Alexa Shopping List Sync."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD

from .alexa_client import AlexaClient
from .const import (
    CONF_COOKIES,
    CONF_EMAIL,
    CONF_OTP_SECRET,
    CONF_URL,
    DEFAULT_URL,
    DOMAIN,
)
from .exceptions import AlexaAuthError, AlexaCaptchaRequired, AlexaMfaRequired

_LOGGER = logging.getLogger(__name__)


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_URL, default=DEFAULT_URL): str,
    }
)


class AlexaShoppingListConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: AlexaClient | None = None
        self._email: str | None = None
        self._password: str | None = None
        self._url: str = DEFAULT_URL
        self._captcha_url: str | None = None
        self._reauth_id: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            self._url = user_input.get(CONF_URL, DEFAULT_URL)

            await self.async_set_unique_id(f"{self._email}@{self._url}".lower())
            if not self._reauth_id:
                self._abort_if_unique_id_configured()

            return await self._try_login(errors)

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    async def async_step_mfa(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            return await self._try_login(errors, otp=user_input[CONF_OTP_SECRET])
        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema({vol.Required(CONF_OTP_SECRET): str}),
            errors=errors,
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            return await self._try_login(errors, captcha=user_input["captcha"])
        return self.async_show_form(
            step_id="captcha",
            data_schema=vol.Schema({vol.Required("captcha"): str}),
            description_placeholders={"captcha_url": self._captcha_url or ""},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._reauth_id = self.context["entry_id"]
        self._email = entry_data.get(CONF_EMAIL)
        self._url = entry_data.get(CONF_URL, DEFAULT_URL)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._password = user_input[CONF_PASSWORD]
            return await self._try_login(errors)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    async def _try_login(
        self,
        errors: dict[str, str],
        *,
        otp: str | None = None,
        captcha: str | None = None,
    ) -> ConfigFlowResult:
        assert self._email and self._password
        if self._client is None:
            self._client = AlexaClient(self._url, self._email, self._password)

        try:
            state = await self._client.login(otp=otp, captcha=captcha)
        except AlexaCaptchaRequired as err:
            self._captcha_url = err.captcha_url
            return await self.async_step_captcha()
        except AlexaMfaRequired:
            return await self.async_step_mfa()
        except AlexaAuthError as err:
            _LOGGER.debug("Auth failed: %s", err)
            errors["base"] = "invalid_auth"
            if self._reauth_id:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
                    errors=errors,
                )
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)
        except Exception:
            _LOGGER.exception("Unexpected login error")
            errors["base"] = "unknown"
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

        data = {
            CONF_EMAIL: self._email,
            CONF_PASSWORD: self._password,
            CONF_URL: self._url,
            CONF_COOKIES: state.get("cookies", {}),
        }

        if self._reauth_id:
            entry = self.hass.config_entries.async_get_entry(self._reauth_id)
            assert entry is not None
            self.hass.config_entries.async_update_entry(entry, data=data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(title=f"Alexa: {self._email}", data=data)
