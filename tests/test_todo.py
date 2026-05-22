"""Tests for the todo platform."""

from __future__ import annotations

from homeassistant.components.todo import TodoItem, TodoItemStatus

from custom_components.alexa_shopping_list_sync.alexa_client import AlexaItem


async def test_entity_registered(hass, loaded_entry):
    entities = [s for s in hass.states.async_all("todo") if "alexa" in s.entity_id]
    assert entities, "Expected at least one alexa todo entity"


async def test_items_exposed_with_stable_uids(hass, loaded_entry, mock_client):
    entities = [s for s in hass.states.async_all("todo") if "alexa" in s.entity_id]
    state = entities[0]
    # Pull the entity object via registry to inspect todo_items
    er = hass.data["entity_registry"]
    entity_id = state.entity_id
    entity_entry = er.async_get(entity_id)
    assert entity_entry is not None
    # Fetch the actual entity by walking platforms
    from homeassistant.helpers import entity_platform

    found = None
    for platform in entity_platform.async_get_platforms(hass, "alexa_shopping_list_sync"):
        for ent in platform.entities.values():
            found = ent
            break
    assert found is not None
    items = found.todo_items
    assert items is not None
    ids = [it.uid for it in items]
    assert ids == ["item-1", "item-2", "item-3"]


async def test_create_calls_client_and_refreshes(hass, loaded_entry, mock_client):
    from homeassistant.helpers import entity_platform

    found = None
    for platform in entity_platform.async_get_platforms(hass, "alexa_shopping_list_sync"):
        for ent in platform.entities.values():
            found = ent
            break
    assert found is not None
    await found.async_create_todo_item(TodoItem(summary="Eggs"))
    mock_client.add_item.assert_awaited_with("Eggs")


async def test_create_with_empty_summary_is_noop(hass, loaded_entry, mock_client):
    from homeassistant.helpers import entity_platform

    found = None
    for platform in entity_platform.async_get_platforms(hass, "alexa_shopping_list_sync"):
        for ent in platform.entities.values():
            found = ent
            break
    assert found is not None
    mock_client.add_item.reset_mock()
    await found.async_create_todo_item(TodoItem(summary=""))
    mock_client.add_item.assert_not_awaited()


async def test_update_marks_completed(hass, loaded_entry, mock_client):
    from homeassistant.helpers import entity_platform

    found = None
    for platform in entity_platform.async_get_platforms(hass, "alexa_shopping_list_sync"):
        for ent in platform.entities.values():
            found = ent
            break
    assert found is not None
    await found.async_update_todo_item(
        TodoItem(uid="item-1", summary="Milk", status=TodoItemStatus.COMPLETED)
    )
    mock_client.update_item.assert_awaited()
    call = mock_client.update_item.await_args
    passed_item: AlexaItem = call.args[0]
    assert passed_item.id == "item-1"
    assert call.kwargs.get("completed") is True


async def test_update_unknown_uid_is_silent(hass, loaded_entry, mock_client):
    from homeassistant.helpers import entity_platform

    found = None
    for platform in entity_platform.async_get_platforms(hass, "alexa_shopping_list_sync"):
        for ent in platform.entities.values():
            found = ent
            break
    assert found is not None
    mock_client.update_item.reset_mock()
    await found.async_update_todo_item(
        TodoItem(uid="does-not-exist", summary="x", status=TodoItemStatus.COMPLETED)
    )
    mock_client.update_item.assert_not_awaited()


async def test_delete_calls_client_per_uid(hass, loaded_entry, mock_client):
    from homeassistant.helpers import entity_platform

    found = None
    for platform in entity_platform.async_get_platforms(hass, "alexa_shopping_list_sync"):
        for ent in platform.entities.values():
            found = ent
            break
    assert found is not None
    await found.async_delete_todo_items(["item-1", "item-3"])
    assert mock_client.delete_item.await_count == 2


async def test_last_sync_attribute_present(hass, loaded_entry):
    entities = [s for s in hass.states.async_all("todo") if "alexa" in s.entity_id]
    assert entities
    last = entities[0].attributes.get("last_sync")
    assert last is not None
