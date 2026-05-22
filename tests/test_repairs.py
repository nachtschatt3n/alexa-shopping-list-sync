"""Tests for the repairs handler."""

from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow

from custom_components.alexa_shopping_list_sync.repairs import async_create_fix_flow


async def test_create_fix_flow_returns_confirm_flow(hass):
    flow = await async_create_fix_flow(hass, "auth_expired", None)
    assert isinstance(flow, ConfirmRepairFlow)
