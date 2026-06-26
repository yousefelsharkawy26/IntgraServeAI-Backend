import pytest
from pydantic import ValidationError

from ai_engine.config import (
    inject_env, ActionParameter, ExecutionConfig, AgentConfiguration,
    ActionDefinition, ResponseConfig, ResponseValue, GlobalDefaults,
    ApiRequestDefaults, LLMConfig, EmbeddingConfig, LocalLoadingParams
)
from utils.exceptions import MissingField, InvalidParamValueType, InvalidActionStructure
from ai_engine.action_engine import ActionEngine


class TestInjectEnv:
    def test_string_substitution_success(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "secret123")
        result = inject_env("Bearer {{env.TEST_KEY}}")
        assert result == "Bearer secret123"

    def test_missing_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(MissingField) as exc_info:
            inject_env("{{env.MISSING_VAR}}")
        assert "MISSING_VAR" in str(exc_info.value)

    def test_malformed_syntax_preserved(self):
        # After the regex fix, malformed syntax is left as literal
        result = inject_env("{{env.BAD{{nested}}}}")
        assert result == "{{env.BAD{{nested}}}}"

    def test_dict_injection(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "key123")
        result = inject_env({"auth": "Bearer {{env.API_KEY}}", "other": "static"})
        assert result == {"auth": "Bearer key123", "other": "static"}

    def test_list_injection(self, monkeypatch):
        monkeypatch.setenv("VAL", "v")
        result = inject_env(["{{env.VAL}}", "static"])
        assert result == ["v", "static"]

    def test_nested_injection(self, monkeypatch):
        monkeypatch.setenv("DEEP", "deep_val")
        result = inject_env({"outer": {"inner": "{{env.DEEP}}"}})
        assert result == {"outer": {"inner": "deep_val"}}

    def test_no_match_returns_unchanged(self):
        result = inject_env("no env vars here")
        assert result == "no env vars here"


class TestActionParameterValidation:
    @pytest.mark.parametrize("ptype,default", [
        ("string", "hello"),
        ("integer", 42),
        ("number", 3.14),
        ("boolean", True),
        ("array", [1, 2]),
        ("object", {"a": 1}),
    ])
    def test_valid_types_accepted(self, ptype, default):
        param = ActionParameter(
            type=ptype, required=False, default=default,
            param_type="query", description="test"
        )
        assert param.type == ptype
        assert param.default == default

    def test_invalid_type_rejected(self):
        with pytest.raises(InvalidParamValueType) as exc_info:
            ActionParameter(
                type="invalid_type", required=True,
                param_type="query", description="test"
            )
        assert "invalid_type" in str(exc_info.value)

    def test_integer_default_bool_rejected(self):
        with pytest.raises(InvalidParamValueType) as exc_info:
            ActionParameter(
                type="integer", required=False, default=True,
                param_type="query", description="count"
            )
        assert "integer" in str(exc_info.value)

    def test_number_default_bool_rejected(self):
        with pytest.raises(InvalidParamValueType):
            ActionParameter(
                type="number", required=False, default=True,
                param_type="query", description="count"
            )

    def test_enum_default_mismatch_rejected(self):
        with pytest.raises(InvalidParamValueType) as exc_info:
            ActionParameter(
                type="string", required=False, default="C",
                param_type="query", description="status",
                enum=["A", "B"]
            )
        assert "C" in str(exc_info.value)

    def test_valid_enum_default_accepted(self):
        param = ActionParameter(
            type="string", required=False, default="A",
            param_type="query", description="status",
            enum=["A", "B"]
        )
        assert param.default == "A"

    def test_invalid_param_type_literal(self):
        with pytest.raises(ValidationError):
            ActionParameter(
                type="string", required=True,
                param_type="invalid", description="test"
            )


class TestExecutionConfigValidation:
    def test_method_normalization(self):
        # HTTP method normalization now happens at ActionDefinition level
        action = ActionDefinition(
            name="test", description="Test", type="api_request",
            active=True, execution_config={"method": "get", "url": "/test"}
        )
        assert action.execution_config.method == "GET"

    def test_invalid_method_rejected(self):
        with pytest.raises(InvalidActionStructure) as exc_info:
            ActionDefinition(
                name="test", description="Test", type="api_request",
                active=True, execution_config={"method": "INVALID", "url": "/test"}
            )
        assert "INVALID" in str(exc_info.value)

    def test_allowed_methods(self):
        for method in ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]:
            action = ActionDefinition(
                name="test", description="Test", type="api_request",
                active=True, execution_config={"method": method, "url": "/test"}
            )
            assert action.execution_config.method == method

    def test_env_injection_in_execution_config(self, monkeypatch):
        monkeypatch.setenv("TEST_URL", "http://example.com")
        ec = ExecutionConfig(method="GET", url="{{env.TEST_URL}}/path")
        assert ec.url == "http://example.com/path"


class TestAgentConfigurationLoading:
    def test_minimal_agent_config(self, load_json):
        data = load_json("valid/minimal_agent_config.json")
        config = AgentConfiguration(**data)
        assert config.system_context.title == "Test Agent"
        assert config.system_context.version == "1.0.0"
        assert config.global_defaults.api_request.protocol == "https"

    def test_full_agent_config(self, load_json):
        data = load_json("valid/full_agent_config.json")
        config = AgentConfiguration(**data)
        assert config.system_context.title == "ShopEasy Customer Support Agent"
        assert config.llm_config.provider == "groq"
        assert config.llm_config.model_name == "llama-3.3-70b-versatile"

    def test_global_defaults_factory(self):
        config = AgentConfiguration(
            system_context={"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            global_defaults={}
        )
        assert config.global_defaults.api_request is not None
        assert config.global_defaults.vector_query is not None


class TestActionDefinitionLoading:
    def test_minimal_actions(self, load_json):
        data = load_json("valid/minimal_actions.json")
        actions = [ActionDefinition(**item) for item in data]
        assert len(actions) == 2
        assert actions[0].name == "get_status"
        assert actions[1].name == "internal_notify"

    def test_title_alias_resolved(self):
        action = ActionDefinition(
            title="escalate_to_human", description="Transfer", type="internal", active=True
        )
        assert action.name == "escalate_to_human"

    def test_missing_required_fields(self, load_json):
        data = load_json("invalid/missing_required_fields.json")
        with pytest.raises(MissingField):
            ActionDefinition(**data[0])

    def test_bad_param_type(self, load_json):
        data = load_json("invalid/bad_param_type.json")
        with pytest.raises(InvalidParamValueType):
            ActionDefinition(**data[0])

    def test_bad_http_method(self, load_json):
        data = load_json("invalid/bad_http_method.json")
        with pytest.raises(InvalidActionStructure):
            ActionDefinition(**data[0])

    def test_integer_default_bool(self, load_json):
        data = load_json("invalid/integer_default_bool.json")
        with pytest.raises(InvalidParamValueType):
            ActionDefinition(**data[0])

    def test_enum_default_mismatch(self, load_json):
        data = load_json("invalid/enum_default_mismatch.json")
        with pytest.raises(InvalidParamValueType):
            ActionDefinition(**data[0])

    def test_api_request_missing_url(self):
        with pytest.raises(MissingField):
            ActionDefinition(
                name="bad", description="Bad", type="api_request",
                execution_config={"method": "GET"}
            )

    def test_rpc_request_missing_host(self):
        with pytest.raises(InvalidActionStructure):
            ActionDefinition(
                name="bad", description="Bad", type="rpc_request",
                execution_config={"service": "S", "method": "M"}
            )

    def test_action_extra_forbidden(self):
        with pytest.raises(ValidationError):
            ActionDefinition(
                name="bad", description="Bad", type="internal", active=True,
                extra_field="not_allowed"
            )


class TestActionEngineInitialization:
    def test_duplicate_action_names_rejected(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {}
        }, "agent.json")

        actions = [
            {"name": "dup", "description": "First", "type": "internal", "active": True},
            {"name": "dup", "description": "Second", "type": "internal", "active": True}
        ]
        with pytest.raises(InvalidActionStructure) as exc_info:
            ActionEngine(agent_path, actions_list=actions)
        assert "Duplicate action name 'dup'" in str(exc_info.value)

    def test_empty_actions_list_accepted(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {}
        }, "agent.json")
        engine = ActionEngine(agent_path, actions_list=[])
        assert engine.actions == []
        assert engine.build_tools() == []

    def test_actions_config_path_loading(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {}
        }, "agent.json")
        actions_path = write_temp_json([
            {"name": "from_file", "description": "File", "type": "internal", "active": True}
        ], "actions.json")
        engine = ActionEngine(agent_path, actions_config_path=actions_path)
        assert len(engine.actions) == 1
        assert engine.actions[0].name == "from_file"

    def test_missing_agent_config_file(self, write_temp_json):
        with pytest.raises(Exception):
            ActionEngine("/nonexistent/agent_config.json", actions_list=[])

    def test_invalid_agent_config_json(self, write_temp_json):
        bad_path = write_temp_json("not json", "bad_agent.json")
        with pytest.raises(Exception):
            ActionEngine(bad_path, actions_list=[])

    def test_actions_config_not_list(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {}
        }, "agent.json")
        bad_path = write_temp_json({"not": "a list"}, "bad_actions.json")
        with pytest.raises(InvalidActionStructure):
            ActionEngine(agent_path, actions_config_path=bad_path)

    def test_actions_list_not_list(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {}
        }, "agent.json")
        with pytest.raises(InvalidActionStructure):
            ActionEngine(agent_path, actions_list="not a list")

class TestGlobalDefaultsMerging:
    def test_api_request_url_merging(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "api_request": {
                    "protocol": "https",
                    "base_url": "api.example.com",
                    "timeout": 10000,
                    "headers": {"X-Global": "1"},
                    "on_error": "Global Error"
                }
            }
        }, "agent.json")

        actions = [{
            "name": "test_api",
            "description": "Test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": "/orders",
                "timeout": 5000,
                "headers": {"X-Action": "2"}
            }
        }]

        engine = ActionEngine(agent_path, actions_list=actions)
        config = engine.actions[0].execution_config
        assert config.url == "https://api.example.com/orders"
        assert config.timeout == 5000
        assert config.headers == {"X-Global": "1", "X-Action": "2"}
        assert config.protocol == "https"

    def test_api_request_url_with_protocol_in_base(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "api_request": {
                    "protocol": "https",
                    "base_url": "https://api.example.com",
                    "timeout": 10000,
                    "headers": {},
                    "on_error": "Error"
                }
            }
        }, "agent.json")

        actions = [{
            "name": "test",
            "description": "Test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": "/orders"
            }
        }]

        engine = ActionEngine(agent_path, actions_list=actions)
        assert engine.actions[0].execution_config.url == "https://api.example.com/orders"

    def test_api_request_url_already_absolute(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "api_request": {
                    "protocol": "https",
                    "base_url": "api.example.com",
                    "timeout": 10000,
                    "headers": {},
                    "on_error": "Error"
                }
            }
        }, "agent.json")

        actions = [{
            "name": "test",
            "description": "Test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": "http://other.com/orders"
            }
        }]

        engine = ActionEngine(agent_path, actions_list=actions)
        assert engine.actions[0].execution_config.url == "http://other.com/orders"

    def test_vector_query_connector_fallback(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "vector_query": {
                    "connector": "postgres",
                    "connection_string": "postgres://localhost/db",
                    "on_error": "Vector Error"
                }
            }
        }, "agent.json")

        actions = [{
            "name": "test_vec",
            "description": "Test",
            "type": "vector_query",
            "active": True,
            "execution_config": {
                "collection_name": "products"
            }
        }]

        engine = ActionEngine(agent_path, actions_list=actions)
        config = engine.actions[0].execution_config
        assert config.connector == "postgres"
        assert config.connection_string == "postgres://localhost/db"

    def test_vector_query_embedding_deep_merge(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "vector_query": {
                    "connector": "postgres",
                    "connection_string": "postgres://localhost/db",
                    "embedding_config": {
                        "location": "local",
                        "provider": "ollama",
                        "model_name": "nomic-embed-text",
                        "dimensions": 768,
                        "rate_limit_delay_seconds": 0
                    },
                    "on_error": "Vector Error"
                }
            }
        }, "agent.json")

        actions = [{
            "name": "test_vec",
            "description": "Test",
            "type": "vector_query",
            "active": True,
            "execution_config": {
                "collection_name": "products",
                "embedding_config": {
                    "location": "local",
                    "provider": "ollama",
                    "model_name": "custom-model",
                    "dimensions": 512,
                    "rate_limit_delay_seconds": 0
                }
            }
        }]

        engine = ActionEngine(agent_path, actions_list=actions)
        emb = engine.actions[0].execution_config.embedding_config
        assert emb.model_name == "custom-model"
        assert emb.dimensions == 512
        assert emb.provider == "ollama"
        assert emb.location == "local"

    def test_response_fallback_injection(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "api_request": {"on_error": "Global API Error"}
            }
        }, "agent.json")

        actions = [{
            "name": "test",
            "description": "Test",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "/test"}
        }]

        engine = ActionEngine(agent_path, actions_list=actions)
        action = engine.actions[0]
        assert action.response_config is not None
        assert action.response_config.mode == "json"
        assert action.response_config.on_error == "Global API Error"

    def test_action_response_config_preserved(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "api_request": {"on_error": "Global Error"}
            }
        }, "agent.json")

        actions = [{
            "name": "test",
            "description": "Test",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "/test"},
            "response_config": {"mode": "raw", "on_error": "Action Error"}
        }]

        engine = ActionEngine(agent_path, actions_list=actions)
        assert engine.actions[0].response_config.on_error == "Action Error"

    def test_rpc_global_defaults_merge(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "rpc_request": {
                    "headers": {"X-Global": "1"},
                    "on_error": "RPC Error"
                }
            }
        }, "agent.json")

        actions = [{
            "name": "test_rpc",
            "description": "Test",
            "type": "rpc_request",
            "active": True,
            "execution_config": {
                "host": "localhost:50051",
                "service": "PaymentService",
                "method": "Refund",
                "proto_file": "payment.proto",
                "headers": {"X-Action": "2"}
            }
        }]

        engine = ActionEngine(agent_path, actions_list=actions)
        headers = engine.actions[0].execution_config.headers
        assert headers == {"X-Global": "1", "X-Action": "2"}


class TestConfigRoundTrip:
    def test_agent_config_round_trip(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "api_request": {
                    "protocol": "https",
                    "base_url": "api.example.com",
                    "timeout": 10000,
                    "headers": {},
                    "on_error": "System Error"
                }
            }
        }, "agent.json")

        engine = ActionEngine(agent_path, actions_list=[])
        dumped = engine.agent_config.model_dump()
        reloaded = AgentConfiguration(**dumped)
        assert reloaded.system_context.title == "T"
        assert reloaded.global_defaults.api_request.base_url == "api.example.com"

    def test_action_definition_round_trip(self):
        action = ActionDefinition(
            name="test", description="D", type="internal", active=True
        )
        dumped = action.model_dump()
        reloaded = ActionDefinition(**dumped)
        assert reloaded.name == "test"
        assert reloaded.active is True


class TestSystemPrompt:
    def test_with_llm_config_template(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {
                "title": "Support Bot",
                "description": "Helps users",
                "version": "1",
                "tone": "friendly"
            },
            "global_defaults": {},
            "llm_config": {
                "provider": "openai",
                "model_name": "gpt-4",
                "system_prompt_template": "Title: {{title}}\\nDesc: {{description}}\\nTone: {{tone}}"
            }
        }, "agent.json")
        engine = ActionEngine(agent_path, actions_list=[])
        prompt = engine.get_system_prompt()
        assert "Support Bot" in prompt
        assert "Helps users" in prompt
        assert "friendly" in prompt

    def test_without_llm_config_template(self, write_temp_json):
        agent_path = write_temp_json({
            "system_context": {
                "title": "Support Bot",
                "description": "Helps users",
                "version": "1",
                "tone": "friendly"
            },
            "global_defaults": {}
        }, "agent.json")
        engine = ActionEngine(agent_path, actions_list=[])
        prompt = engine.get_system_prompt()
        assert "Support Bot" in prompt
        assert "Helps users" in prompt