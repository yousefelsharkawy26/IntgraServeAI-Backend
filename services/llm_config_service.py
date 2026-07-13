from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from pydantic import SecretStr

from ai_engine.config import LLMConfig
from ai_engine.providers import ModelFactory
from repositories.action_repository import ActionRepository
from repositories.agent_config_repository import AgentConfigRepository
from repositories.llm_config_repository import LLMConfigRepository
from services.ai_gateway_service import AIGatewayService
from utils.agent_config_mapper import AgentConfigMapper
from utils.exceptions import BadRequestException, ConflictException, NotFoundException


class LLMConfigService:
    """Business operations for reusable ModelFactory configurations."""

    def __init__(self, repository: LLMConfigRepository):
        self.repository = repository

    async def list(self):
        return [self.to_response(row) for row in await self.repository.list()]

    async def get(self, config_id: UUID):
        row = await self._get(config_id)
        return self.to_response(row)

    async def create(self, payload) -> dict[str, Any]:
        values = self._payload_values(payload, preserve_api_key=False)
        if await self.repository.get_by_name(values["name"]):
            raise ConflictException(f"LLM configuration '{values['name']}' already exists")
        self._validate_values(values)
        row = await self.repository.create(values)
        return self.to_response(row)

    async def replace(self, config_id: UUID, payload) -> dict[str, Any]:
        row = await self._get(config_id)
        values = self._payload_values(payload, preserve_api_key=True, current=row)
        await self._ensure_name_available(values["name"], row.id)
        await self._ensure_selected_stays_active(row, values)
        self._validate_values(values)
        row = await self.repository.update(row, values)
        await self._reload_if_selected(row.id)
        return self.to_response(row)

    async def patch(self, config_id: UUID, payload) -> dict[str, Any]:
        row = await self._get(config_id)
        changes = payload.model_dump(exclude_unset=True)
        if "api_key" in changes:
            changes["api_key"] = self._secret_value(changes["api_key"])
        merged = self._row_values(row)
        merged.update(changes)
        await self._ensure_name_available(merged["name"], row.id)
        await self._ensure_selected_stays_active(row, merged)
        self._validate_values(merged)
        row = await self.repository.update(row, changes)
        await self._reload_if_selected(row.id)
        return self.to_response(row)

    async def delete(self, config_id: UUID) -> None:
        row = await self._get(config_id)
        if await self.repository.is_referenced(row.id):
            raise ConflictException("Cannot delete an LLM configuration selected by an agent")
        await self.repository.delete(row)

    @staticmethod
    def providers() -> list[dict[str, str]]:
        return ModelFactory.get_supported_providers()

    async def _get(self, config_id: UUID):
        row = await self.repository.get_by_id(config_id)
        if row is None:
            raise NotFoundException(f"LLM configuration '{config_id}' not found")
        return row

    async def _ensure_name_available(self, name: str, current_id: UUID) -> None:
        duplicate = await self.repository.get_by_name(name)
        if duplicate is not None and duplicate.id != current_id:
            raise ConflictException(f"LLM configuration '{name}' already exists")

    async def _ensure_selected_stays_active(self, row, values: dict[str, Any]) -> None:
        if not values.get("active", True) and await self.repository.is_referenced(row.id):
            raise ConflictException("Cannot deactivate an LLM configuration selected by an agent")

    @staticmethod
    def _secret_value(value) -> str | None:
        return value.get_secret_value() if isinstance(value, SecretStr) else value

    def _payload_values(self, payload, preserve_api_key: bool, current=None) -> dict[str, Any]:
        values = payload.model_dump()
        supplied = "api_key" in payload.model_fields_set
        secret = self._secret_value(values.pop("api_key", None))
        if supplied:
            values["api_key"] = secret
        elif preserve_api_key and current is not None:
            values["api_key"] = current.api_key
        return values

    @staticmethod
    def _row_values(row) -> dict[str, Any]:
        return {
            "tenant_key": row.tenant_key,
            "name": row.name,
            "provider": row.provider,
            "location": row.location,
            "model_name": row.model_name,
            "api_key": row.api_key,
            "api_key_reference": row.api_key_reference,
            "temperature": row.temperature,
            "max_tokens": row.max_tokens,
            "system_prompt_template": row.system_prompt_template,
            "active": row.active,
            "config_json": dict(row.config_json or {}),
        }

    @staticmethod
    def _validate_values(values: dict[str, Any]) -> None:
        runtime = dict(values.get("config_json") or {})
        runtime.update(
            {
                "provider": values["provider"],
                "location": values["location"],
                "model_name": values["model_name"],
                "temperature": values["temperature"],
                "max_tokens": values["max_tokens"],
                "system_prompt_template": values.get("system_prompt_template", ""),
            }
        )
        api_key = values.get("api_key")
        reference = values.get("api_key_reference")
        if api_key:
            runtime["api_key"] = api_key
        elif reference:
            runtime["api_key"] = os.getenv(reference)
        try:
            config = LLMConfig.model_validate(runtime)
            ModelFactory.validate_llm_config(config)
        except Exception as exc:
            raise BadRequestException(str(exc))

    async def _reload_if_selected(self, config_id: UUID) -> None:
        if not await self.repository.is_referenced(config_id):
            return
        agent = await AgentConfigRepository(self.repository.session).get_active()
        if agent is None:
            return
        actions = await ActionRepository(self.repository.session).list()
        AIGatewayService.configure_engine(
            AgentConfigMapper.to_engine_dict(agent),
            [
                row.to_dict(include_id=False, include_engine_fields=True)
                | {"_backend_id": row.id}
                for row in actions
            ],
        )

    @staticmethod
    def to_response(row) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "provider": row.provider,
            "location": row.location,
            "model_name": row.model_name,
            "api_key_reference": row.api_key_reference,
            "has_api_key": bool(row.api_key),
            "temperature": row.temperature,
            "max_tokens": row.max_tokens,
            "system_prompt_template": row.system_prompt_template,
            "active": row.active,
            "config_json": dict(row.config_json or {}),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
