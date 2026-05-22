"""Tests for the AlexaClient — exercising parsing and transport-layer behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.alexa_shopping_list_sync.alexa_client import (
    AlexaClient,
    AlexaItem,
)
from custom_components.alexa_shopping_list_sync.exceptions import (
    AlexaAuthError,
    AlexaConflict,
    AlexaListNotFound,
)


def test_item_from_api_full():
    item = AlexaItem.from_api({"id": "x", "value": "milk", "completed": True, "version": 3})
    assert item.id == "x"
    assert item.value == "milk"
    assert item.completed is True
    assert item.version == 3


def test_item_from_api_defaults():
    item = AlexaItem.from_api({"id": "y"})
    assert item.value == ""
    assert item.completed is False
    assert item.version == 1


def test_item_unicode_and_emoji():
    item = AlexaItem.from_api({"id": "u", "value": "Brot 🍞", "version": 1})
    assert "🍞" in item.value


def test_item_very_long_name():
    name = "x" * 1000
    item = AlexaItem.from_api({"id": "long", "value": name, "version": 1})
    assert len(item.value) == 1000


class _FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, text: str = ""):
        self.status = status
        self._payload = payload or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return self._text


def _make_client_with_session(response: _FakeResponse) -> AlexaClient:
    client = AlexaClient("amazon.de", "u@x", "pw")
    fake_session = MagicMock()
    fake_session.request = MagicMock(return_value=response)
    # Pretend a successful alexapy login already happened.
    client._login = MagicMock()
    client._login._session = fake_session
    client._login._headers = {}
    client._login._csrf = "csrf-token"
    client._login.status = {"login_successful": True}
    return client


async def test_request_401_raises_auth_error():
    client = _make_client_with_session(_FakeResponse(401))
    with pytest.raises(AlexaAuthError):
        await client._get("/api/namedLists")


async def test_request_403_raises_auth_error():
    client = _make_client_with_session(_FakeResponse(403))
    with pytest.raises(AlexaAuthError):
        await client._get("/api/namedLists")


async def test_request_409_raises_conflict():
    client = _make_client_with_session(_FakeResponse(409))
    with pytest.raises(AlexaConflict):
        await client._put("/api/namedLists/L/item/X", {"id": "X"})


async def test_request_204_returns_empty_dict():
    client = _make_client_with_session(_FakeResponse(204))
    result = await client._delete("/api/namedLists/L/item/X")
    assert result == {}


async def test_request_unauthenticated_raises():
    client = AlexaClient("amazon.de", "u@x", "pw")  # _login is None
    with pytest.raises(AlexaAuthError):
        await client._get("/api/namedLists")


async def test_discover_shopping_list_id_finds_correct_list(alexa_responses):
    client = _make_client_with_session(_FakeResponse(200, alexa_responses["namedLists"]))
    list_id = await client.discover_shopping_list_id()
    assert list_id == "LIST-1"


async def test_discover_shopping_list_id_caches(alexa_responses):
    client = _make_client_with_session(_FakeResponse(200, alexa_responses["namedLists"]))
    first = await client.discover_shopping_list_id()
    # Second call must not hit the network — break the session to prove it.
    client._login._session.request = MagicMock(side_effect=AssertionError("re-fetched"))
    second = await client.discover_shopping_list_id()
    assert first == second == "LIST-1"


async def test_discover_shopping_list_id_missing_raises():
    client = _make_client_with_session(_FakeResponse(200, {"lists": []}))
    with pytest.raises(AlexaListNotFound):
        await client.discover_shopping_list_id()


async def test_fetch_items_parses_payload(alexa_responses):
    client = AlexaClient("amazon.de", "u@x", "pw")
    client._list_id = "LIST-1"
    client._get = AsyncMock(return_value=alexa_responses["items"])  # type: ignore[method-assign]
    items = await client.fetch_items()
    assert [it.id for it in items] == ["item-1", "item-2", "item-3"]
    assert items[2].completed is True


async def test_add_item(alexa_responses):
    client = AlexaClient("amazon.de", "u@x", "pw")
    client._list_id = "LIST-1"
    client._post = AsyncMock(return_value=alexa_responses["item_added"])  # type: ignore[method-assign]
    new = await client.add_item("Eggs")
    assert new.id == "item-new"
    assert new.value == "Eggs"


async def test_update_item_409_refetches_and_retries(alexa_responses):
    client = AlexaClient("amazon.de", "u@x", "pw")
    client._list_id = "LIST-1"

    target = AlexaItem(id="item-1", value="Milk", completed=False, version=1)
    new_version = {"id": "item-1", "value": "Milk", "completed": True, "version": 5}

    call_count = {"n": 0}

    async def fake_put(path, payload):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise AlexaConflict("409")
        return new_version

    client._put = fake_put  # type: ignore[method-assign]
    client.fetch_items = AsyncMock(
        return_value=[AlexaItem(id="item-1", value="Milk", completed=False, version=4)]
    )

    result = await client.update_item(target, completed=True)
    assert call_count["n"] == 2
    assert result.version == 5


async def test_delete_item(alexa_responses):
    client = AlexaClient("amazon.de", "u@x", "pw")
    client._list_id = "LIST-1"
    client._delete = AsyncMock(return_value={})  # type: ignore[method-assign]
    await client.delete_item(AlexaItem(id="item-1", value="Milk", completed=False, version=1))
    client._delete.assert_awaited_once()
