"""DataUpdateCoordinator polling the Alexa shopping list."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .alexa_client import AlexaClient, AlexaItem
from .const import (
    CONF_COOKIES,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .exceptions import AlexaAuthError, AlexaError

_LOGGER = logging.getLogger(__name__)


class AlexaListCoordinator(DataUpdateCoordinator[list[AlexaItem]]):
    """Coordinator that fetches the Alexa shopping list on a schedule."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.title}",
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.entry = entry
        self.client = AlexaClient(
            url=entry.data[CONF_URL],
            email=entry.data[CONF_EMAIL],
            password=entry.data[CONF_PASSWORD],
        )
        self.last_sync: datetime | None = None
        self._authed = False

    async def _ensure_login(self) -> None:
        if self._authed and self.client.is_authenticated:
            return
        try:
            state = await self.client.login(cookies=self.entry.data.get(CONF_COOKIES))
        except AlexaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        # Persist refreshed cookies back to the entry
        new_data = {**self.entry.data, CONF_COOKIES: state.get("cookies", {})}
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        self._authed = True

    async def _async_update_data(self) -> list[AlexaItem]:
        try:
            await self._ensure_login()
            items = await self.client.fetch_items()
        except AlexaAuthError as err:
            self._authed = False
            raise ConfigEntryAuthFailed(str(err)) from err
        except AlexaError as err:
            raise UpdateFailed(str(err)) from err
        self.last_sync = datetime.now(UTC)
        return items

    async def async_shutdown(self) -> None:
        """Best-effort cleanup."""
        try:
            login = getattr(self.client, "_login", None)
            if login and getattr(login, "_session", None):
                await login._session.close()
        except Exception:
            _LOGGER.debug("Error during shutdown", exc_info=True)
