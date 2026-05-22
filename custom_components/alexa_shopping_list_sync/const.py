"""Constants for the Alexa Shopping List Sync integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "alexa_shopping_list_sync"

PLATFORMS = ["todo"]

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_URL = "url"
CONF_OTP_SECRET = "otp_secret"
CONF_COOKIES = "cookies"
CONF_CUSTOMER_ID = "customer_id"
CONF_CSRF = "csrf"
CONF_LIST_ID = "list_id"

DEFAULT_URL = "amazon.de"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)
MIN_SCAN_INTERVAL = timedelta(minutes=5)

ATTR_LAST_SYNC = "last_sync"

LIST_TYPE_SHOPPING = "SHOPPING_LIST"
