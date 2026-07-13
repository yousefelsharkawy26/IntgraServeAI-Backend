from typing import Any, Dict
from uuid import UUID

from pydantic import ValidationError

from repositories.action_repository import ActionRepository
from repositories.agent_config_repository import AgentConfigRepository
from services.ai_gateway_service import AIGatewayService
from utils.agent_config_mapper import AgentConfigMapper
from utils.exceptions import BadRequestException, NotFoundException
from utils.schemas import agent_config_schemas as schemas


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

    @staticmethod
    def _validate(config_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return schemas.AgentConfig.model_validate(config_data).model_dump(mode="json")
        except (ValueError, ValidationError) as exc:
            raise BadRequestException(str(exc))

    async def update_full_config(self, config_data: Dict[str, Any], updated_by: UUID) -> None:
        validated = self._validate(config_data)
        agent = await self._active_agent()
        agent = await self.repository.save_full_config(
            agent,
            validated,
            updated_by=updated_by,
        )
        await self._refresh_engine(agent)

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
