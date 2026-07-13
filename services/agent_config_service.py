import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID, uuid4

from pydantic import ValidationError

from repositories.action_repository import ActionRepository
from repositories.agent_config_repository import AgentConfigRepository
from services.ai_gateway_service import AIGatewayService
from utils.agent_config_mapper import AgentConfigMapper
from utils.exceptions import BadRequestException, NotFoundException
from utils.schemas import agent_config_schemas as schemas

logger = logging.getLogger(__name__)


def deep_merge(source: dict, destination: dict) -> dict:
    """Recursively merge source into a deep copy of destination."""
    result = copy.deepcopy(destination)
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(value, result[key])
        else:
            result[key] = value
    return result


class AgentConfigService:
    """Agent configuration business operations backed exclusively by PostgreSQL."""

    def __init__(self, repository: AgentConfigRepository):
        self.repository = repository

    async def _active_agent(self):
        agent = await self.repository.get_active()
        if agent is None:
            raise NotFoundException("No active agent configuration found")
        return agent

    async def get_full_config(self) -> Dict[str, Any]:
        return AgentConfigMapper.to_api_dict(await self._active_agent())

    async def get_section(self, section_name: str) -> Dict[str, Any]:
        config = await self.get_full_config()
        if section_name not in config:
            raise NotFoundException(f"Section '{section_name}' not found.")
        content = config[section_name]
        if not isinstance(content, dict):
            raise NotFoundException(f"Section '{section_name}' not found.")
        return content

    @staticmethod
    def _validate(config_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return schemas.AgentConfig.model_validate(config_data).model_dump(mode="json")
        except (ValueError, ValidationError) as exc:
            raise BadRequestException(str(exc))

    @staticmethod
    def _snapshot_json(config: Dict[str, Any]) -> Dict[str, Any]:
        return json.loads(json.dumps(config, default=str))

    async def _create_snapshot(self, agent, config: Dict[str, Any]) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"agent_config_backup_{timestamp}_{uuid4().hex[:8]}.json"
        await self.repository.create_snapshot(
            agent.id,
            filename,
            self._snapshot_json(config),
        )
        return filename

    async def update_full_config(self, config_data: Dict, updated_by: UUID) -> Optional[str]:
        validated = self._validate(config_data)
        agent = await self._active_agent()
        backup = await self._create_snapshot(agent, AgentConfigMapper.to_api_dict(agent))
        agent = await self.repository.save_full_config(agent, validated, updated_by=updated_by)
        await self._refresh_engine(agent)
        return backup

    async def update_section(
        self,
        section_name: str,
        update_data: Dict,
        updated_by: UUID,
    ) -> Optional[str]:
        current = await self.get_full_config()
        if section_name not in {"system_context", "llm_config", "global_defaults"}:
            raise NotFoundException(f"Section '{section_name}' not found.")
        current[section_name] = deep_merge(update_data, current.get(section_name, {}))
        return await self.update_full_config(current, updated_by)

    async def list_backups(self) -> list[Dict[str, Any]]:
        agent = await self._active_agent()
        rows = await self.repository.list_snapshots(agent.id)
        return [
            {
                "filename": row.filename,
                "created_at": row.created_at,
                "size_kb": round(
                    len(json.dumps(row.config_json, default=str).encode("utf-8")) / 1024,
                    2,
                ),
            }
            for row in rows
        ]

    async def get_backup_content(self, filename: str) -> Dict[str, Any]:
        agent = await self._active_agent()
        snapshot = await self.repository.get_snapshot(agent.id, filename)
        if snapshot is None:
            raise NotFoundException(f"Backup '{filename}' not found.")
        return snapshot.config_json

    async def restore_from_backup(self, filename: str, updated_by: UUID) -> Tuple[str, str]:
        agent = await self._active_agent()
        snapshot = await self.repository.get_snapshot(agent.id, filename)
        if snapshot is None:
            raise NotFoundException(f"Backup '{filename}' not found.")
        validated = self._validate(snapshot.config_json)
        current_backup = await self._create_snapshot(agent, AgentConfigMapper.to_api_dict(agent))
        agent = await self.repository.save_full_config(
            agent,
            validated,
            updated_by=updated_by,
            restored_from=filename,
        )
        await self._refresh_engine(agent)
        return filename, current_backup

    async def delete_backup(self, filename: str) -> None:
        agent = await self._active_agent()
        snapshot = await self.repository.get_snapshot(agent.id, filename)
        if snapshot is None:
            raise NotFoundException(f"Backup '{filename}' not found.")
        await self.repository.delete_snapshot(snapshot)

    async def delete_all_backups(self) -> int:
        agent = await self._active_agent()
        return await self.repository.delete_all_snapshots(agent.id)

    async def _refresh_engine(self, agent) -> None:
        actions = await ActionRepository(self.repository.session).list()
        AIGatewayService.configure_engine(
            AgentConfigMapper.to_engine_dict(agent),
            [
                row.to_dict(include_id=False, include_engine_fields=True)
                | {"_backend_id": row.id}
                for row in actions
            ],
        )
