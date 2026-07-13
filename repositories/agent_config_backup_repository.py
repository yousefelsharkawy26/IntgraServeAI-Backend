from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_config import AgentConfigBackup


class AgentConfigBackupRepository:
    """Persistence boundary for complete agent configuration snapshots."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, agent_config_id: UUID) -> list[AgentConfigBackup]:
        result = await self.session.execute(
            select(AgentConfigBackup)
            .where(AgentConfigBackup.agent_config_id == agent_config_id)
            .order_by(AgentConfigBackup.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, backup_id: UUID) -> Optional[AgentConfigBackup]:
        return await self.session.get(AgentConfigBackup, backup_id)

    async def create(
        self,
        agent_config_id: UUID,
        name: str,
        snapshot_json: dict[str, Any],
        llm_api_key: Optional[str],
        created_by_id: Optional[UUID],
    ) -> AgentConfigBackup:
        row = AgentConfigBackup(
            agent_config_id=agent_config_id,
            name=name,
            snapshot_json=snapshot_json,
            encrypted_llm_api_key=llm_api_key,
            created_by_id=created_by_id,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def delete(self, row: AgentConfigBackup) -> None:
        await self.session.delete(row)
        await self.session.flush()
