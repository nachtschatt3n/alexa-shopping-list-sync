"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.alexa_shopping_list_sync.const import (
    CONF_COOKIES,
    CONF_EMAIL,
    CONF_OTP_SECRET,
    CONF_URL,
    DOMAIN,
)
from custom_components.alexa_shopping_list_sync.exceptions import (
    AlexaAuthError,
    AlexaCaptchaRequired,
    AlexaMfaRequired,
)


async def test_user_flow_happy_path(hass, mock_alexa_client_class):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_EMAIL] == "u@example.com"
    assert result["data"][CONF_COOKIES] == {"sess": "abc"}


async def test_user_flow_invalid_auth_shows_error(hass, mock_alexa_client_class):
    mock_alexa_client_class.login = AsyncMock(side_effect=AlexaAuthError("bad"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "wrong", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_mfa_branch(hass, mock_alexa_client_class):
    # First login raises MFA, second succeeds
    mock_alexa_client_class.login = AsyncMock(
        side_effect=[
            AlexaMfaRequired("mfa"),
            {"cookies": {"sess": "abc"}, "customer_id": "C", "csrf": "x"},
        ]
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mfa"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_OTP_SECRET: "123456"}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_user_flow_captcha_branch(hass, mock_alexa_client_class):
    mock_alexa_client_class.login = AsyncMock(
        side_effect=[
            AlexaCaptchaRequired("https://example/cap.png"),
            {"cookies": {"sess": "abc"}, "customer_id": "C", "csrf": "x"},
        ]
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "captcha"
    assert "https://example/cap.png" in (result["description_placeholders"] or {}).get(
        "captcha_url", ""
    )

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"captcha": "ABCD"})
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_unknown_error_shows_unknown(hass, mock_alexa_client_class):
    mock_alexa_client_class.login = AsyncMock(side_effect=RuntimeError("boom"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_duplicate_account_aborts(hass, mock_alexa_client_class):
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u@example.com@amazon.de",
        data={CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_succeeds(hass, mock_alexa_client_class):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u@example.com@amazon.de",
        data={
            CONF_EMAIL: "u@example.com",
            "password": "old",
            CONF_URL: "amazon.de",
            CONF_COOKIES: {},
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "newpw"}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "newpw"
