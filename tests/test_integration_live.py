"""Live integration tests that hit the real Alexa API.

Gated by @pytest.mark.integration. Run with:

    cp .env.example .env  # fill in credentials
    make test-int

These tests:
1. Log in with real credentials (incl. OTP if ALEXA_OTP_SECRET set)
2. Discover the SHOPPING_LIST id
3. Add a uniquely-named test item
4. Verify it appears in fetch_items
5. Mark it completed
6. Delete it
7. Verify it's gone

Each test self-cleans so a partial run doesn't pollute the list.
"""

from __future__ import annotations

import os
import uuid

import pytest

from custom_components.alexa_shopping_list_sync.alexa_client import AlexaClient

pytestmark = pytest.mark.integration


def _creds_or_skip() -> tuple[str, str, str, str | None]:
    email = os.environ.get("ALEXA_EMAIL")
    password = os.environ.get("ALEXA_PASSWORD")
    url = os.environ.get("ALEXA_URL", "amazon.de")
    otp = os.environ.get("ALEXA_OTP_SECRET") or None
    if not email or not password:
        pytest.skip("ALEXA_EMAIL/ALEXA_PASSWORD not set")
    return email, password, url, otp


@pytest.fixture
async def live_client():
    email, password, url, otp = _creds_or_skip()
    client = AlexaClient(url, email, password)
    await client.login(otp=otp)
    yield client
    # Best-effort cleanup of any leftover test items
    try:
        for item in await client.fetch_items():
            if item.value.startswith("__hass_test__"):
                await client.delete_item(item)
    except Exception:
        pass


async def test_live_discover_shopping_list(live_client):
    list_id = await live_client.discover_shopping_list_id()
    assert list_id


async def test_live_full_round_trip(live_client):
    tag = f"__hass_test__{uuid.uuid4().hex[:8]}"

    # Add
    created = await live_client.add_item(tag)
    assert created.value == tag

    # Read-back
    items = await live_client.fetch_items()
    assert any(it.id == created.id for it in items), "added item not in list"

    # Complete
    completed = await live_client.update_item(created, completed=True)
    assert completed.completed is True

    # Delete
    await live_client.delete_item(completed)

    # Verify gone
    items = await live_client.fetch_items()
    assert not any(it.id == created.id for it in items), "item still present after delete"
