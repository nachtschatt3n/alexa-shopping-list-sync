"""Exceptions for Alexa Shopping List Sync."""

from __future__ import annotations

from enum import StrEnum


class MfaKind(StrEnum):
    """Which kind of MFA Amazon is asking for, on this login attempt."""

    AUTHENTICATOR = "securitycode"  # TOTP / authenticator app
    SMS_OR_EMAIL = "verificationcode"  # SMS or email code


class AlexaError(Exception):
    """Base exception."""


class AlexaAuthError(AlexaError):
    """Raised when Amazon rejects the session (401/403 or cookie expiry)."""


class AlexaMfaRequired(AlexaError):
    """Raised when Amazon requires an MFA code.

    Carries the kind of code Amazon is asking for so the config flow can
    submit it under the right alexapy field name.
    """

    def __init__(self, kind: MfaKind, message: str = "") -> None:
        super().__init__(f"MFA required ({kind.name}): {message}".strip())
        self.kind = kind
        self.message = message


class AlexaClaimsPickerRequired(AlexaError):
    """Raised when Amazon asks the user to pick a 2FA delivery method.

    Carries the message Amazon sent (the picker options text). The user
    just answers which option (typically a number) and we submit it as
    `claimsoption`.
    """

    def __init__(self, message: str) -> None:
        super().__init__(f"Claims picker required: {message}")
        self.message = message


class AlexaAuthSelectRequired(AlexaError):
    """Raised when Amazon asks the user to pick a primary auth method."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Auth select required: {message}")
        self.message = message


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


class AlexaInvalidOtpSecret(AlexaError):
    """Raised when the TOTP shared secret is not valid base32.

    Valid TOTP secrets are uppercase A-Z and digits 2-7 (RFC 3548 base32).
    Common mistakes: pasting an `otpauth://` URL, including hyphens or
    spaces, including `0`/`1`/`8`/`9`.
    """
