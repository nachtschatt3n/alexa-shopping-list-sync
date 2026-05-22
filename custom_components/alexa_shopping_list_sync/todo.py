"""Todo platform exposing the Alexa shopping list."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .alexa_client import AlexaItem
from .const import ATTR_LAST_SYNC, DOMAIN
from .coordinator import AlexaListCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AlexaListCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AlexaShoppingListEntity(coordinator, entry)])


class AlexaShoppingListEntity(CoordinatorEntity[AlexaListCoordinator], TodoListEntity):
    """A HA todo list backed by the Alexa shopping list."""

    _attr_has_entity_name = True
    _attr_name = "Alexa Shopping List"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator: AlexaListCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_shopping_list"

    @property
    def todo_items(self) -> list[TodoItem] | None:
        if self.coordinator.data is None:
            return None
        return [_to_todo(it) for it in self.coordinator.data]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self.coordinator.last_sync
        return {ATTR_LAST_SYNC: last.isoformat() if last else None}

    async def async_create_todo_item(self, item: TodoItem) -> None:
        if not item.summary:
            return
        await self.coordinator.client.add_item(item.summary)
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        existing = _find(self.coordinator.data or [], item.uid)
        if existing is None:
            _LOGGER.debug("update_todo_item: unknown uid %s", item.uid)
            return
        completed = item.status == TodoItemStatus.COMPLETED if item.status is not None else None
        await self.coordinator.client.update_item(existing, value=item.summary, completed=completed)
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        items = self.coordinator.data or []
        for uid in uids:
            existing = _find(items, uid)
            if existing is None:
                continue
            await self.coordinator.client.delete_item(existing)
        await self.coordinator.async_request_refresh()


def _to_todo(item: AlexaItem) -> TodoItem:
    return TodoItem(
        uid=item.id,
        summary=item.value,
        status=(TodoItemStatus.COMPLETED if item.completed else TodoItemStatus.NEEDS_ACTION),
    )


def _find(items: list[AlexaItem], uid: str | None) -> AlexaItem | None:
    if uid is None:
        return None
    for it in items:
        if it.id == uid:
            return it
    return None
