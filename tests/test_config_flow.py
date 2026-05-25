"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.alexa_shopping_list_sync.config_flow import _normalize_otp_secret
from custom_components.alexa_shopping_list_sync.const import (
    CONF_COOKIES,
    CONF_EMAIL,
    CONF_OTP_SECRET,
    CONF_URL,
    DOMAIN,
)
from custom_components.alexa_shopping_list_sync.exceptions import (
    AlexaAuthError,
    AlexaAuthSelectRequired,
    AlexaCaptchaRequired,
    AlexaClaimsPickerRequired,
    AlexaInvalidOtpSecret,
    AlexaMfaRequired,
    MfaKind,
)

_OK_STATE = {"cookies": {"sess": "abc"}, "customer_id": "C", "csrf": "x"}


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


async def test_user_flow_with_otp_secret_persisted(hass, mock_alexa_client_class):
    """User provides TOTP shared secret upfront → stored on entry, no MFA prompt."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "u@example.com",
            "password": "pw",
            CONF_URL: "amazon.de",
            CONF_OTP_SECRET: "JBSWY3DPEHPK3PXP",
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_OTP_SECRET] == "JBSWY3DPEHPK3PXP"


async def test_user_flow_invalid_auth_shows_error(hass, mock_alexa_client_class):
    mock_alexa_client_class.login = AsyncMock(side_effect=AlexaAuthError("bad"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "wrong", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_mfa_authenticator_branch_submits_securitycode(hass, mock_alexa_client_class):
    """Authenticator-app MFA → mfa_app step → posts as `securitycode`."""
    mock_alexa_client_class.login = AsyncMock(
        side_effect=[AlexaMfaRequired(MfaKind.AUTHENTICATOR, "Enter code"), _OK_STATE]
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mfa_app"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "123456"})
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Second login call should have used securitycode, not verificationcode
    second_call = mock_alexa_client_class.login.await_args_list[1]
    assert second_call.kwargs.get("securitycode") == "123456"
    assert second_call.kwargs.get("verificationcode") is None


async def test_mfa_sms_branch_submits_verificationcode(hass, mock_alexa_client_class):
    """SMS/email MFA → mfa_sms step → posts as `verificationcode`."""
    mock_alexa_client_class.login = AsyncMock(
        side_effect=[AlexaMfaRequired(MfaKind.SMS_OR_EMAIL, "SMS sent"), _OK_STATE]
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mfa_sms"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "987654"})
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    second_call = mock_alexa_client_class.login.await_args_list[1]
    assert second_call.kwargs.get("verificationcode") == "987654"
    assert second_call.kwargs.get("securitycode") is None


async def test_claimspicker_branch(hass, mock_alexa_client_class):
    mock_alexa_client_class.login = AsyncMock(
        side_effect=[
            AlexaClaimsPickerRequired("1) SMS to ***1234  2) Email"),
            _OK_STATE,
        ]
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "claimspicker"
    assert "SMS" in (result["description_placeholders"] or {}).get("message", "")

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"option": "1"})
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    second_call = mock_alexa_client_class.login.await_args_list[1]
    assert second_call.kwargs.get("claimsoption") == "1"


async def test_authselect_branch(hass, mock_alexa_client_class):
    mock_alexa_client_class.login = AsyncMock(
        side_effect=[AlexaAuthSelectRequired("Pick one"), _OK_STATE]
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["step_id"] == "authselect"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"option": "2"})
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    second_call = mock_alexa_client_class.login.await_args_list[1]
    assert second_call.kwargs.get("authselectoption") == "2"


async def test_captcha_then_mfa_chain(hass, mock_alexa_client_class):
    """Realistic flow: captcha first, then MFA, then success."""
    mock_alexa_client_class.login = AsyncMock(
        side_effect=[
            AlexaCaptchaRequired("https://example/cap.png"),
            AlexaMfaRequired(MfaKind.AUTHENTICATOR, ""),
            _OK_STATE,
        ]
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "u@example.com", "password": "pw", CONF_URL: "amazon.de"},
    )
    assert result["step_id"] == "captcha"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"captcha": "XYZ"})
    assert result["step_id"] == "mfa_app"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "654321"})
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


def test_normalize_otp_secret_strips_spaces_and_hyphens():
    assert _normalize_otp_secret("  abcd efgh ") == "ABCDEFGH"
    assert _normalize_otp_secret("ABCD-EFGH-IJKL") == "ABCDEFGHIJKL"
    assert _normalize_otp_secret("") == ""


def test_normalize_otp_secret_extracts_from_otpauth_url():
    url = "otpauth://totp/Amazon:user@x.com?secret=JBSWY3DPEHPK3PXP&issuer=Amazon"
    assert _normalize_otp_secret(url) == "JBSWY3DPEHPK3PXP"


async def test_invalid_otp_secret_at_form_level(hass, mock_alexa_client_class):
    """Client-side validation rejects non-base32 chars BEFORE hitting alexapy."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "u@example.com",
            "password": "pw",
            CONF_URL: "amazon.de",
            CONF_OTP_SECRET: "INVALID-0189",  # 0,1,8,9 not in base32
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_OTP_SECRET: "invalid_otp_secret"}


async def test_invalid_otp_secret_from_alexapy(hass, mock_alexa_client_class):
    """If validation passes but alexapy still rejects (edge case), error path is the same."""
    mock_alexa_client_class.login = AsyncMock(side_effect=AlexaInvalidOtpSecret("bad"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "u@example.com",
            "password": "pw",
            CONF_URL: "amazon.de",
            CONF_OTP_SECRET: "JBSWY3DPEHPK3PXP",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_OTP_SECRET: "invalid_otp_secret"}


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
