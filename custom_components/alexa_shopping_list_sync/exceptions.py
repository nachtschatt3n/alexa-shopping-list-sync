"""Exceptions for Alexa Shopping List Sync."""

from __future__ import annotations


class AlexaError(Exception):
    """Base exception."""


class AlexaAuthError(AlexaError):
    """Raised when Amazon rejects the session (401/403 or cookie expiry)."""


class AlexaMfaRequired(AlexaError):
    """Raised when Amazon requires an MFA/OTP code during login."""


class AlexaCaptchaRequired(AlexaError):
    """Raised when Amazon requires a captcha during login.

    Carries the captcha image URL so the config flow can render it.
    """

    def __init__(self, captcha_url: str) -> None:
        super().__init__(f"Captcha required: {captcha_url}")
        self.captcha_url = captcha_url


class AlexaListNotFound(AlexaError):
    """Raised when no SHOPPING_LIST is found for the customer."""


class AlexaConflict(AlexaError):
    """Raised on 409 optimistic-lock failure (item version mismatch)."""
