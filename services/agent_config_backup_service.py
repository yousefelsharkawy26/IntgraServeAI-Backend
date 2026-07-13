from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from repositories.action_repository import ActionRepository
from repositories.agent_config_backup_repository import AgentConfigBackupRepository
from repositories.agent_config_repository import AgentConfigRepository
from repositories.llm_config_repository import LLMConfigRepository
from services.ai_gateway_service import AIGatewayService
from services.llm_config_service import LLMConfigService
from utils.agent_config_mapper import AgentConfigMapper
from utils.exceptions import ConflictException, NotFoundException


class AgentConfigBackupService:
    """Creates and atomically restores complete database configuration snapshots."""

    def __init__(
        self,
        backup_repository: AgentConfigBackupRepository,
        agent_repository: AgentConfigRepository,
    ):
        self.backups = backup_repository
        self.agents = agent_repository

    async def list(self) -> list[dict[str, Any]]:
        agent = await self._active_agent()
        return [self._summary(row) for row in await self.backups.list(agent.id)]

    async def get(self, backup_id: UUID) -> dict[str, Any]:
        row = await self._get(backup_id)
        return self._detail(row)

    async def create(self, name: str | None, created_by_id: UUID | None) -> dict[str, Any]:
        agent = await self._active_agent()
        snapshot = self._snapshot(agent)
        backup_name = name or datetime.now(timezone.utc).strftime("Agent configuration %Y-%m-%d %H:%M:%S UTC")
        row = await self.backups.create(
            agent_config_id=agent.id,
            name=backup_name,
            snapshot_json=snapshot,
            llm_api_key=agent.llm_config.api_key,
            created_by_id=created_by_id,
        )
        return self._detail(row)

    async def restore(self, backup_id: UUID, updated_by_id: UUID | None) -> None:
        backup = await self._get(backup_id)
        snapshot = backup.snapshot_json
        agent_data = snapshot["agent_config"]
        agent = await self.agents.get_by_id(UUID(agent_data["id"]))
        if agent is None or not agent.active:
            raise ConflictException("The backup's agent configuration is not active")

        llm = await self._restore_llm(snapshot["llm_config"], backup.encrypted_llm_api_key)
        prompt = snapshot.get("active_prompt")
        system_description = prompt["content"] if prompt else agent_data["description"]
        config = {
            "system_context": {
                "title": agent_data["title"],
                "description": system_description,
                "tone": agent_data["tone"],
                "version": agent_data["version"],
            },
            "global_defaults": snapshot.get("action_defaults", {}),
            "llm_config_id": str(llm.id),
        }
        agent = await self.agents.save_full_config(
            agent,
            config,
            llm_config_id=llm.id,
            updated_by=updated_by_id,
        )
        if prompt:
            await self.agents.restore_prompt(agent, prompt)
            await self.agents.session.refresh(agent, attribute_names=["prompts"])
        await self._refresh_engine(agent)

    async def delete(self, backup_id: UUID) -> None:
        await self.backups.delete(await self._get(backup_id))

    async def _restore_llm(self, data: dict[str, Any], api_key: str | None):
        repository = LLMConfigRepository(self.backups.session)
        config_id = UUID(data["id"])
        row = await repository.get_by_id(config_id)
        values = {
            "tenant_key": data.get("tenant_key", "default"),
            "name": data["name"],
            "provider": data["provider"],
            "location": data["location"],
            "model_name": data["model_name"],
            "api_key": api_key,
            "api_key_reference": data.get("api_key_reference"),
            "temperature": data["temperature"],
            "max_tokens": data["max_tokens"],
            "system_prompt_template": data.get("system_prompt_template", ""),
            "active": True,
            "config_json": data.get("config_json", {}),
        }
        LLMConfigService._validate_values(values)
        if row is not None:
            return await repository.update(row, values)

        duplicate = await repository.get_by_name(values["name"], values["tenant_key"])
        if duplicate is not None:
            return await repository.update(duplicate, values)
        return await repository.create({"id": config_id, **values})

    async def _active_agent(self):
        agent = await self.agents.get_active()
        if agent is None:
            raise NotFoundException("No active agent configuration found")
        return agent

    async def _get(self, backup_id: UUID):
        row = await self.backups.get_by_id(backup_id)
        if row is None:
            raise NotFoundException(f"Agent configuration backup '{backup_id}' not found")
        return row

    @staticmethod
    def _snapshot(agent) -> dict[str, Any]:
        prompt = AgentConfigMapper._active_prompt(agent)
        llm = agent.llm_config
        return {
            "schema_version": 1,
            "agent_config": {
                "id": str(agent.id),
                "tenant_key": agent.tenant_key,
                "name": agent.name,
                "title": agent.title,
                "description": agent.description,
                "tone": agent.tone,
                "version": agent.version,
                "active": agent.active,
            },
            "active_prompt": (
                {
                    "name": prompt.name,
                    "content": prompt.content,
                    "version": prompt.version,
                }
                if prompt else None
            ),
            "llm_config": {
                "id": str(llm.id),
                "tenant_key": llm.tenant_key,
                "name": llm.name,
                "provider": llm.provider,
                "location": llm.location,
                "model_name": llm.model_name,
                "api_key_reference": llm.api_key_reference,
                "has_api_key": bool(llm.api_key),
                "temperature": llm.temperature,
                "max_tokens": llm.max_tokens,
                "system_prompt_template": llm.system_prompt_template,
                "active": llm.active,
                "config_json": dict(llm.config_json or {}),
            },
            "action_defaults": {
                row.action_type: dict(row.config_json or {})
                for row in agent.action_defaults
            },
        }

    @classmethod
    def _summary(cls, row) -> dict[str, Any]:
        return {
            "id": row.id,
            "agent_config_id": row.agent_config_id,
            "name": row.name,
            "created_at": row.created_at,
            "created_by_id": row.created_by_id,
        }

    @classmethod
    def _detail(cls, row) -> dict[str, Any]:
        return {**cls._summary(row), "snapshot": dict(row.snapshot_json)}

    async def _refresh_engine(self, agent) -> None:
        actions = await ActionRepository(self.agents.session).list()
        AIGatewayService.configure_engine(
            AgentConfigMapper.to_engine_dict(agent),
            [
                row.to_dict(include_id=False, include_engine_fields=True)
                | {"_backend_id": row.id}
                for row in actions
            ],
        )
