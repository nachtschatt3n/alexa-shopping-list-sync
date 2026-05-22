"""Repair flow for expired Alexa sessions."""

from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict | None,
) -> RepairsFlow:
    """Create a Repair fix flow. We defer to HA's standard reauth machinery."""
    return ConfirmRepairFlow()
