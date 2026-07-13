from typing import Any

from models.agent_config import AgentConfig, AgentPrompt
from models.llm_config import LLMConfiguration


class AgentConfigMapper:
    """Maps normalized configuration rows to API and Action Engine contracts."""

    @staticmethod
    def _active_prompt(agent: AgentConfig) -> AgentPrompt | None:
        active = [row for row in agent.prompts if row.active]
        return max(active, key=lambda row: row.version) if active else None

    @staticmethod
    def llm_to_runtime_dict(llm: LLMConfiguration) -> dict[str, Any]:
        config = dict(llm.config_json or {})
        config.update(
            {
                "location": llm.location,
                "provider": llm.provider,
                "model_name": llm.model_name,
                "temperature": llm.temperature,
                "max_tokens": llm.max_tokens,
                "system_prompt_template": llm.system_prompt_template,
            }
        )
        if llm.api_key:
            config["api_key"] = llm.api_key
        elif llm.api_key_reference:
            config["api_key"] = f"{{{{env.{llm.api_key_reference}}}}}"
        return config

    @classmethod
    def to_engine_dict(cls, agent: AgentConfig) -> dict[str, Any]:
        if agent.llm_config is None:
            raise ValueError(f"Agent '{agent.name}' has no selected LLM configuration")
        if not agent.llm_config.active:
            raise ValueError(f"Agent '{agent.name}' selected an inactive LLM configuration")
        prompt = cls._active_prompt(agent)
        return {
            "system_context": {
                "title": agent.title,
                "description": prompt.content if prompt is not None else agent.description,
                "version": agent.version,
                "tone": agent.tone,
            },
            "global_defaults": {
                row.action_type: dict(row.config_json or {})
                for row in agent.action_defaults
            },
            "llm_config": cls.llm_to_runtime_dict(agent.llm_config),
        }

    @classmethod
    def to_api_dict(cls, agent: AgentConfig) -> dict[str, Any]:
        prompt = cls._active_prompt(agent)
        return {
            "system_context": {
                "title": agent.title,
                "description": prompt.content if prompt is not None else agent.description,
                "version": agent.version,
                "tone": agent.tone,
            },
            "global_defaults": {
                row.action_type: dict(row.config_json or {})
                for row in agent.action_defaults
            },
            "llm_config_id": agent.llm_config_id,
            "metadata": {
                "last_updated": agent.updated_at,
                "updated_by": agent.updated_by_id,
            },
        }
