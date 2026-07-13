from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.agent_config import AgentActionDefault, AgentConfig, AgentPrompt


class AgentConfigRepository:
    """Persistence boundary for normalized agent configuration."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _graph_options():
        return (
            selectinload(AgentConfig.llm_config),
            selectinload(AgentConfig.action_defaults),
            selectinload(AgentConfig.prompts),
        )

    async def get_active(self, tenant_key: str = "default") -> Optional[AgentConfig]:
        result = await self.session.execute(
            select(AgentConfig)
            .options(*self._graph_options())
            .where(AgentConfig.tenant_key == tenant_key, AgentConfig.active.is_(True))
            .order_by(AgentConfig.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, agent_config_id: UUID) -> Optional[AgentConfig]:
        result = await self.session.execute(
            select(AgentConfig)
            .options(*self._graph_options())
            .where(AgentConfig.id == agent_config_id)
        )
        return result.scalar_one_or_none()

    async def save_full_config(
        self,
        agent: AgentConfig,
        config: dict[str, Any],
        llm_config_id: UUID,
        updated_by: Optional[UUID] = None,
    ) -> AgentConfig:
        system = config["system_context"]
        agent.title = system["title"]
        agent.description = system["description"]
        agent.tone = system["tone"]
        agent.version = system["version"]
        agent.llm_config_id = llm_config_id
        agent.updated_by_id = updated_by

        await self._replace_action_defaults(agent, config.get("global_defaults") or {})
        await self._save_prompt_version(agent, system["description"])
        await self.session.flush()
        await self.session.refresh(
            agent,
            attribute_names=["llm_config", "action_defaults", "prompts"],
        )
        return agent

    async def replace_action_defaults(self, agent: AgentConfig, defaults: dict[str, Any]) -> None:
        await self._replace_action_defaults(agent, defaults)

    async def restore_prompt(self, agent: AgentConfig, prompt: dict[str, Any]) -> None:
        await self.session.execute(
            update(AgentPrompt)
            .where(AgentPrompt.agent_config_id == agent.id)
            .values(active=False)
        )
        existing_result = await self.session.execute(
            select(AgentPrompt).where(
                AgentPrompt.agent_config_id == agent.id,
                AgentPrompt.name == prompt["name"],
                AgentPrompt.version == prompt["version"],
            )
        )
        row = existing_result.scalar_one_or_none()
        if row is None:
            max_result = await self.session.execute(
                select(func.max(AgentPrompt.version)).where(AgentPrompt.agent_config_id == agent.id)
            )
            row = AgentPrompt(
                agent_config_id=agent.id,
                name=prompt["name"],
                content=prompt["content"],
                version=max(prompt["version"], (max_result.scalar() or 0) + 1),
                active=True,
            )
            self.session.add(row)
        else:
            row.content = prompt["content"]
            row.active = True
        agent.description = prompt["content"]
        await self.session.flush()

    async def _replace_action_defaults(self, agent: AgentConfig, defaults: dict[str, Any]) -> None:
        await self.session.execute(
            delete(AgentActionDefault).where(AgentActionDefault.agent_config_id == agent.id)
        )
        for action_type, config_json in defaults.items():
            self.session.add(
                AgentActionDefault(
                    agent_config_id=agent.id,
                    action_type=action_type,
                    config_json=config_json or {},
                )
            )

    async def _save_prompt_version(self, agent: AgentConfig, content: str) -> None:
        active_result = await self.session.execute(
            select(AgentPrompt).where(
                AgentPrompt.agent_config_id == agent.id,
                AgentPrompt.active.is_(True),
            )
        )
        active_prompt = active_result.scalar_one_or_none()
        if active_prompt is not None and active_prompt.content == content:
            return

        await self.session.execute(
            update(AgentPrompt)
            .where(AgentPrompt.agent_config_id == agent.id)
            .values(active=False)
        )
        version_result = await self.session.execute(
            select(func.max(AgentPrompt.version)).where(AgentPrompt.agent_config_id == agent.id)
        )
        self.session.add(
            AgentPrompt(
                agent_config_id=agent.id,
                name="system",
                content=content,
                version=(version_result.scalar() or 0) + 1,
                active=True,
            )
        )
