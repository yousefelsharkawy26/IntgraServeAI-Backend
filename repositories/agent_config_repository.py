from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.agent_config import AgentActionDefault, AgentConfig, AgentLLMConfig, AgentPrompt


class AgentConfigRepository:
    """SQLAlchemy persistence boundary for agent configuration."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _graph_options():
        return (
            selectinload(AgentConfig.llm_configs),
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

    async def save_full_config(
        self,
        agent: AgentConfig,
        config: dict[str, Any],
        updated_by: Optional[UUID] = None,
    ) -> AgentConfig:
        system = config["system_context"]
        agent.title = system["title"]
        agent.description = system["description"]
        agent.tone = system["tone"]
        agent.version = system["version"]
        agent.updated_by_id = updated_by

        await self._save_llm(agent, config["llm_config"])
        await self._replace_action_defaults(agent, config.get("global_defaults") or {})
        await self._save_prompt_version(agent, system["description"])
        await self.session.flush()
        await self.session.refresh(
            agent,
            attribute_names=["llm_configs", "action_defaults", "prompts"],
        )
        return agent

    async def _save_llm(self, agent: AgentConfig, llm_data: dict[str, Any]) -> None:
        await self.session.execute(
            update(AgentLLMConfig)
            .where(AgentLLMConfig.agent_config_id == agent.id)
            .values(active=False)
        )

        provider = llm_data["provider"]
        location = llm_data.get("location", "remote")
        model_name = llm_data["model_name"]
        result = await self.session.execute(
            select(AgentLLMConfig).where(
                AgentLLMConfig.agent_config_id == agent.id,
                AgentLLMConfig.provider == provider,
                AgentLLMConfig.location == location,
                AgentLLMConfig.model_name == model_name,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = AgentLLMConfig(
                agent_config_id=agent.id,
                provider=provider,
                location=location,
                model_name=model_name,
            )
            self.session.add(row)

        known = {
            "provider", "location", "model_name", "temperature", "max_tokens",
            "api_key", "api_key_reference", "system_prompt_template", "active",
        }
        row.temperature = llm_data.get("temperature", 0.7)
        row.max_tokens = llm_data.get("max_tokens", 2048)
        row.api_key_reference = self._api_key_reference(llm_data)
        row.system_prompt_template = llm_data.get("system_prompt_template", "")
        row.config_json = {key: value for key, value in llm_data.items() if key not in known}
        row.active = True

    @staticmethod
    def _api_key_reference(llm_data: dict[str, Any]) -> Optional[str]:
        explicit = llm_data.get("api_key_reference")
        if explicit:
            return explicit
        value = llm_data.get("api_key")
        if isinstance(value, str) and value.startswith("{{env.") and value.endswith("}}"):
            return value[6:-2]
        return None

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
        next_version = (version_result.scalar() or 0) + 1
        self.session.add(
            AgentPrompt(
                agent_config_id=agent.id,
                name="system",
                content=content,
                version=next_version,
                active=True,
            )
        )
