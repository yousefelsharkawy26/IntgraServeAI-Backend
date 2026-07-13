from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ai_engine.providers import ModelFactory
from apis.v1.llm_configs import router
from models.llm_config import LLMConfiguration
from services.llm_config_service import LLMConfigService
from utils.schemas.llm_config_schemas import LLMConfigurationCreate


def row(**overrides):
    values = {
        "id": uuid4(),
        "tenant_key": "default",
        "name": "Local Ollama",
        "provider": "ollama",
        "location": "local",
        "model_name": "llama3",
        "api_key": None,
        "api_key_reference": None,
        "temperature": 0.2,
        "max_tokens": 1024,
        "system_prompt_template": "{{description}}",
        "active": True,
        "config_json": {"local_loading_params": {"base_url": "http://localhost:11434"}},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return LLMConfiguration(**values)


def test_llm_config_api_exposes_crud_and_provider_discovery():
    operations = {
        (route.path, method)
        for route in router.routes
        for method in route.methods
    }
    assert operations == {
        ("/providers", "GET"),
        ("", "GET"),
        ("", "POST"),
        ("/{config_id}", "GET"),
        ("/{config_id}", "PUT"),
        ("/{config_id}", "PATCH"),
        ("/{config_id}", "DELETE"),
    }


def test_provider_discovery_comes_from_model_factory_registry():
    providers = LLMConfigService.providers()
    assert {item["id"] for item in providers} == set(ModelFactory._providers)
    assert {item["id"]: item["name"] for item in providers}["google"] == "Google Gemini"


def test_response_never_exposes_api_key():
    response = LLMConfigService.to_response(row(api_key="secret"))
    assert response["has_api_key"] is True
    assert "api_key" not in response


@pytest.mark.asyncio
async def test_create_validates_with_existing_provider_architecture():
    repository = AsyncMock()
    repository.get_by_name.return_value = None
    repository.create.side_effect = lambda values: row(**values)
    service = LLMConfigService(repository)
    payload = LLMConfigurationCreate(
        name="Local Ollama",
        provider="ollama",
        location="local",
        model_name="llama3",
        temperature=0.2,
        max_tokens=1024,
        config_json={"local_loading_params": {"base_url": "http://localhost:11434"}},
    )

    result = await service.create(payload)
    assert result["provider"] == "ollama"
    repository.create.assert_awaited_once()
