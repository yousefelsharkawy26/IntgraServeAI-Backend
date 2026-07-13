from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_config import AgentConfig
from models.llm_config import LLMConfiguration


class LLMConfigRepository:
    """Persistence boundary for reusable LLM configurations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, tenant_key: str = "default") -> list[LLMConfiguration]:
        result = await self.session.execute(
            select(LLMConfiguration)
            .where(LLMConfiguration.tenant_key == tenant_key)
            .order_by(LLMConfiguration.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, config_id: UUID) -> Optional[LLMConfiguration]:
        return await self.session.get(LLMConfiguration, config_id)

    async def get_by_name(self, name: str, tenant_key: str = "default") -> Optional[LLMConfiguration]:
        result = await self.session.execute(
            select(LLMConfiguration).where(
                LLMConfiguration.tenant_key == tenant_key,
                LLMConfiguration.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, values: dict[str, Any]) -> LLMConfiguration:
        row = LLMConfiguration(**values)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def update(self, row: LLMConfiguration, values: dict[str, Any]) -> LLMConfiguration:
        for key, value in values.items():
            setattr(row, key, value)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def is_referenced(self, config_id: UUID) -> bool:
        result = await self.session.execute(
            select(func.count(AgentConfig.id)).where(AgentConfig.llm_config_id == config_id)
        )
        return bool(result.scalar())

    async def delete(self, row: LLMConfiguration) -> None:
        await self.session.delete(row)
        await self.session.flush()
