from datetime import datetime, timezone
from uuid import uuid4

from apis.v1.agent_config import router
from models.agent_config import AgentActionDefault, AgentConfig, AgentPrompt
from models.llm_config import LLMConfiguration
from services.agent_config_backup_service import AgentConfigBackupService
from services.agent_config_service import AgentConfigService
from utils.agent_config_mapper import AgentConfigMapper


def make_agent():
    now = datetime.now(timezone.utc)
    llm = LLMConfiguration(
        id=uuid4(),
        tenant_key="default",
        name="Production Groq",
        provider="groq",
        location="remote",
        model_name="llama-3.3-70b-versatile",
        temperature=0.2,
        max_tokens=1024,
        api_key_reference="GROQ_API_KEY",
        system_prompt_template="Identity: {{title}}\nRole: {{description}}\nTone: {{tone}}",
        active=True,
        config_json={"rate_limit_delay_seconds": 0},
        updated_at=now,
    )
    agent = AgentConfig(
        id=uuid4(),
        tenant_key="default",
        name="default",
        title="ShopEasy Virtual Assistant",
        description="Original prompt",
        tone="Professional, helpful, and concise.",
        version="1.0",
        active=True,
        llm_config_id=llm.id,
        updated_at=now,
    )
    agent.llm_config = llm
    agent.action_defaults = [
        AgentActionDefault(action_type="api_request", config_json={"protocol": "http", "timeout": 5000}),
        AgentActionDefault(action_type="future_action_type", config_json={"future_option": True}),
    ]
    agent.prompts = [
        AgentPrompt(name="system", content="Versioned active prompt", version=1, active=True)
    ]
    return agent


def test_mapper_preserves_existing_engine_contract():
    agent = make_agent()
    config = AgentConfigMapper.to_engine_dict(agent)

    assert config["system_context"]["description"] == "Versioned active prompt"
    assert config["llm_config"]["provider"] == "groq"
    assert config["llm_config"]["api_key"] == "{{env.GROQ_API_KEY}}"
    assert config["global_defaults"]["api_request"]["timeout"] == 5000

    api_config = AgentConfigMapper.to_api_dict(agent)
    assert api_config["llm_config_id"] == agent.llm_config_id
    assert "llm_config" not in api_config


def test_full_config_validation_uses_llm_configuration_id():
    config = AgentConfigMapper.to_api_dict(make_agent())
    validated = AgentConfigService._validate(config)
    assert validated["system_context"]["title"] == "ShopEasy Virtual Assistant"
    assert validated["llm_config_id"] == str(config["llm_config_id"])


def test_backup_snapshot_contains_complete_runtime_configuration_without_plaintext_key():
    agent = make_agent()
    agent.llm_config.api_key = "secret"
    snapshot = AgentConfigBackupService._snapshot(agent)

    assert snapshot["agent_config"]["id"] == str(agent.id)
    assert snapshot["active_prompt"]["content"] == "Versioned active prompt"
    assert snapshot["llm_config"]["id"] == str(agent.llm_config_id)
    assert snapshot["llm_config"]["has_api_key"] is True
    assert "api_key" not in snapshot["llm_config"]
    assert snapshot["action_defaults"]["api_request"]["timeout"] == 5000


def test_agent_config_api_includes_database_backup_routes():
    operations = {
        (route.path, method)
        for route in router.routes
        for method in route.methods
    }
    assert operations == {
        ("", "GET"),
        ("", "PUT"),
        ("/backups", "GET"),
        ("/backups", "POST"),
        ("/backups/{backup_id}", "GET"),
        ("/backups/{backup_id}/restore", "POST"),
        ("/backups/{backup_id}", "DELETE"),
    }
