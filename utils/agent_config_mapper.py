from typing import Any

from models.agent_config import AgentConfig, AgentLLMConfig, AgentPrompt


class AgentConfigMapper:
    """Maps normalized configuration rows to the existing public/engine shape."""

    @staticmethod
    def _active_llm(agent: AgentConfig) -> AgentLLMConfig:
        active = [row for row in agent.llm_configs if row.active]
        if not active:
            raise ValueError(f"Active agent '{agent.name}' has no active LLM configuration")
        return max(active, key=lambda row: row.updated_at)

    @staticmethod
    def _active_prompt(agent: AgentConfig) -> AgentPrompt | None:
        active = [row for row in agent.prompts if row.active]
        return max(active, key=lambda row: row.version) if active else None

    @classmethod
    def to_engine_dict(cls, agent: AgentConfig) -> dict[str, Any]:
        llm = cls._active_llm(agent)
        prompt = cls._active_prompt(agent)
        llm_config = dict(llm.config_json or {})
        llm_config.update(
            {
                "location": llm.location,
                "provider": llm.provider,
                "model_name": llm.model_name,
                "temperature": llm.temperature,
                "max_tokens": llm.max_tokens,
                "system_prompt_template": llm.system_prompt_template,
            }
        )
        if llm.api_key_reference:
            llm_config["api_key"] = f"{{{{env.{llm.api_key_reference}}}}}"

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
            "llm_config": llm_config,
        }

    @classmethod
    def to_api_dict(cls, agent: AgentConfig) -> dict[str, Any]:
        result = cls.to_engine_dict(agent)
        result["metadata"] = {
            "last_updated": agent.updated_at,
            "updated_by": agent.updated_by_id,
            "restored_from": agent.restored_from,
        }
        return result
