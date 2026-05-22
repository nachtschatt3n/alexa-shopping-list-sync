"""Tests for setup/unload."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.alexa_shopping_list_sync.const import (
    CONF_COOKIES,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_URL,
    DOMAIN,
)


async def test_setup_and_unload(hass, mock_alexa_client_class):
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
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
