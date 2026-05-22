"""Shared fixtures."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations in every test."""
    yield


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def alexa_responses() -> dict:
    with (FIXTURES / "alexa_responses.json").open() as f:
        return json.load(f)


@pytest.fixture
def mock_client(alexa_responses) -> MagicMock:
    """A mock AlexaClient with sane defaults."""
    from custom_components.alexa_shopping_list_sync.alexa_client import AlexaItem

    raw_items = alexa_responses["items"]["listItems"]
    items = [AlexaItem.from_api(it) for it in raw_items]

    client = MagicMock()
    client.is_authenticated = True
    client.login = AsyncMock(
        return_value={"cookies": {"sess": "abc"}, "customer_id": "C1", "csrf": "csrf1"}
    )
    client.discover_shopping_list_id = AsyncMock(return_value="LIST-1")
    client.fetch_items = AsyncMock(return_value=items)
    client.add_item = AsyncMock(
        return_value=AlexaItem(id="new-1", value="new", completed=False, version=1)
    )
    client.update_item = AsyncMock(
        side_effect=lambda item, value=None, completed=None: AlexaItem(
            id=item.id,
            value=value if value is not None else item.value,
            completed=completed if completed is not None else item.completed,
            version=item.version + 1,
        )
    )
    client.delete_item = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_alexa_client_class(monkeypatch, mock_client):
    """Patch AlexaClient class so the integration uses our mock."""
    from custom_components.alexa_shopping_list_sync import (
        alexa_client as alexa_client_mod,
    )
    from custom_components.alexa_shopping_list_sync import (
        config_flow,
        coordinator,
    )

    def factory(*_args, **_kwargs):
        return mock_client

    monkeypatch.setattr(alexa_client_mod, "AlexaClient", factory)
    monkeypatch.setattr(coordinator, "AlexaClient", factory)
    monkeypatch.setattr(config_flow, "AlexaClient", factory)
    return mock_client


@pytest.fixture
async def loaded_entry(hass, mock_alexa_client_class) -> AsyncGenerator:
    """Set up the integration with a mock client and a populated entry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.alexa_shopping_list_sync.const import (
        CONF_COOKIES,
        CONF_EMAIL,
        CONF_PASSWORD,
        CONF_URL,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com@amazon.de",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "pw",
            CONF_URL: "amazon.de",
            CONF_COOKIES: {"sess": "abc"},
        },
        title="Alexa: user@example.com",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
