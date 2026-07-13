from datetime import datetime, timezone
from uuid import uuid4

from apis.v1.agent_config import router
from models.agent_config import AgentActionDefault, AgentConfig, AgentLLMConfig, AgentPrompt
from services.agent_config_service import AgentConfigService
from utils.agent_config_mapper import AgentConfigMapper


def make_agent():
    now = datetime.now(timezone.utc)
    agent = AgentConfig(
        id=uuid4(),
        tenant_key="default",
        name="default",
        title="ShopEasy Virtual Assistant",
        description="Original prompt",
        tone="Professional, helpful, and concise.",
        version="1.0",
        active=True,
        updated_at=now,
    )
    agent.llm_configs = [
        AgentLLMConfig(
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
    ]
    agent.action_defaults = [
        AgentActionDefault(
            action_type="api_request",
            config_json={"protocol": "http", "timeout": 5000},
        ),
        AgentActionDefault(
            action_type="future_action_type",
            config_json={"future_option": True},
        ),
    ]
    agent.prompts = [
        AgentPrompt(name="system", content="Versioned active prompt", version=1, active=True)
    ]
    return agent


def test_mapper_preserves_existing_engine_contract():
    config = AgentConfigMapper.to_engine_dict(make_agent())

    assert config["system_context"] == {
        "title": "ShopEasy Virtual Assistant",
        "description": "Versioned active prompt",
        "tone": "Professional, helpful, and concise.",
        "version": "1.0",
    }
    assert config["llm_config"]["provider"] == "groq"
    assert config["llm_config"]["api_key"] == "{{env.GROQ_API_KEY}}"
    assert config["global_defaults"]["api_request"]["timeout"] == 5000
    assert config["global_defaults"]["future_action_type"] == {"future_option": True}


def test_full_config_validation_preserves_shape():
    config = AgentConfigMapper.to_api_dict(make_agent())
    validated = AgentConfigService._validate(config)
    assert validated["system_context"]["title"] == "ShopEasy Virtual Assistant"


def test_agent_config_api_exposes_only_full_get_and_put():
    operations = {
        (route.path, method)
        for route in router.routes
        for method in route.methods
    }
    assert operations == {("", "GET"), ("", "PUT")}
