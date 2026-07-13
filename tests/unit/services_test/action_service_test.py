from unittest.mock import AsyncMock

import pytest

from models.action import Action
from Seeding.import_actions_to_postgres import persistence_values
from services.action_service import ActionService
from utils.exceptions import ActionNotFoundException, InternalActionNotAllowedException
from utils.schemas.action_schemas import ActionCreate, ActionUpdate


def action_row(**overrides):
    values = {
        "id": "ACT-001",
        "name": "get_order",
        "description": "Get an order",
        "type": "api_request",
        "active": True,
        "requires_confirmation": False,
        "requires_human_input": False,
        "execution_config": {"protocol": "https", "method": "GET", "url": "https://example.com/orders"},
        "parameters": None,
        "response_config": None,
    }
    values.update(overrides)
    return Action(**values)


@pytest.fixture
def repository():
    repository = AsyncMock()
    repository.list.return_value = []
    return repository


@pytest.fixture
def service(repository):
    instance = ActionService(repository)
    instance._refresh_cached_engine = AsyncMock()
    return instance


@pytest.mark.asyncio
async def test_create_preserves_nested_config(service, repository):
    repository.get_by_name.return_value = None

    async def assign_id(action):
        action.id = "ACT-001"
        return action

    repository.create.side_effect = assign_id
    payload = ActionCreate(
        name="get_order",
        description="Get an order",
        type="api_request",
        active=True,
        requires_confirmation=False,
        execution_config={
            "protocol": "https",
            "method": "GET",
            "url": "https://example.com/orders",
            "headers": {"X-API-Key": "secret"},
        },
        parameters={
            "order_id": {
                "type": "string",
                "required": True,
                "param_type": "query",
                "description": "Order ID",
            }
        },
    )

    assert await service.create_action(payload) == ("ACT-001", "get_order")
    persisted = repository.create.await_args.args[0]
    assert persisted.execution_config["headers"] == {"X-API-Key": "secret"}
    assert persisted.parameters["order_id"]["param_type"] == "query"


def test_parameterless_create_and_legacy_seed_use_empty_object():
    payload = ActionCreate(
        name="health_check",
        description="Health check",
        type="api_request",
        execution_config={
            "protocol": "https",
            "method": "GET",
            "url": "https://example.com/health",
        },
        parameters=None,
    )
    assert payload.parameters == {}

    legacy = persistence_values(
        "INT-005",
        {
            "name": "request_confirmation",
            "description": "Request confirmation",
            "type": "internal",
        },
    )
    assert legacy["parameters"] == {}


@pytest.mark.asyncio
async def test_list_response_contract_is_unchanged(service, repository):
    repository.list.return_value = [action_row()]
    actions, total = await service.get_all_actions()
    assert total == 1
    assert actions[0].model_dump(mode="json") == {
        "id": "ACT-001",
        "name": "get_order",
        "description": "Get an order",
        "type": "api_request",
        "active": True,
        "requires_confirmation": False,
    }


@pytest.mark.asyncio
async def test_update_merges_execution_config(service, repository):
    row = action_row()
    repository.get_by_id.return_value = row
    repository.get_by_name.return_value = None

    async def apply_update(action, values):
        for key, value in values.items():
            setattr(action, key, value)
        return action

    repository.update.side_effect = apply_update
    await service.update_action("ACT-001", ActionUpdate(execution_config={"timeout": 5000}))
    values = repository.update.await_args.args[1]
    assert values["execution_config"]["url"] == "https://example.com/orders"
    assert values["execution_config"]["timeout"] == 5000


@pytest.mark.asyncio
async def test_internal_action_cannot_be_deleted(service, repository):
    repository.get_by_id.return_value = action_row(id="INT-001", type="internal")
    with pytest.raises(InternalActionNotAllowedException):
        await service.delete_action("INT-001")


@pytest.mark.asyncio
async def test_missing_action_uses_existing_exception(service, repository):
    repository.get_by_id.return_value = None
    with pytest.raises(ActionNotFoundException):
        await service.get_action_by_id("ACT-404")
