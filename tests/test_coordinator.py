"""Tests for AlexaListCoordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.alexa_shopping_list_sync.const import (
    CONF_COOKIES,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_URL,
    DOMAIN,
)
from custom_components.alexa_shopping_list_sync.coordinator import AlexaListCoordinator
from custom_components.alexa_shopping_list_sync.exceptions import (
    AlexaAuthError,
    AlexaError,
)


def _make_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u@example.com@amazon.de",
        data={
            CONF_EMAIL: "u@example.com",
            CONF_PASSWORD: "pw",
            CONF_URL: "amazon.de",
            CONF_COOKIES: {"sess": "abc"},
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_first_refresh_populates_items(hass, mock_client):
    entry = _make_entry(hass)
    coord = AlexaListCoordinator(hass, entry)
    coord.client = mock_client
    await coord.async_refresh()
    assert [it.id for it in coord.data] == ["item-1", "item-2", "item-3"]
    assert coord.last_sync is not None


async def test_login_state_persisted_to_entry(hass, mock_client):
    entry = _make_entry(hass)
    # Force re-login by clearing cookies on the entry.
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_COOKIES: {}})
    mock_client.is_authenticated = False
    coord = AlexaListCoordinator(hass, entry)
    coord.client = mock_client
    await coord.async_refresh()
    # New cookies from the login response should be on the entry now.
    assert entry.data[CONF_COOKIES] == {"sess": "abc"}


async def test_auth_error_becomes_config_entry_auth_failed(hass, mock_client):
    entry = _make_entry(hass)
    mock_client.is_authenticated = False
    mock_client.login = AsyncMock(side_effect=AlexaAuthError("bad cookies"))
    coord = AlexaListCoordinator(hass, entry)
    coord.client = mock_client
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


async def test_auth_error_on_fetch_becomes_config_entry_auth_failed(hass, mock_client):
    entry = _make_entry(hass)
    mock_client.fetch_items = AsyncMock(side_effect=AlexaAuthError("expired"))
    coord = AlexaListCoordinator(hass, entry)
    coord.client = mock_client
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()
    # State should be marked unauthenticated so next poll re-logs in
    assert coord._authed is False


async def test_transient_error_becomes_update_failed(hass, mock_client):
    entry = _make_entry(hass)
    mock_client.fetch_items = AsyncMock(side_effect=AlexaError("network blip"))
    coord = AlexaListCoordinator(hass, entry)
    coord.client = mock_client
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


async def test_repeat_polling_does_not_relogin_when_authed(hass, mock_client):
    entry = _make_entry(hass)
    coord = AlexaListCoordinator(hass, entry)
    coord.client = mock_client
    await coord._async_update_data()
    await coord._async_update_data()
    # login should only have happened once
    assert mock_client.login.await_count == 1


async def test_last_sync_updates_on_success(hass, mock_client):
    entry = _make_entry(hass)
    coord = AlexaListCoordinator(hass, entry)
    coord.client = mock_client
    await coord._async_update_data()
    first = coord.last_sync
    assert first is not None
    await coord._async_update_data()
    assert coord.last_sync is not None and coord.last_sync >= first
