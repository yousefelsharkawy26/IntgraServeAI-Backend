import pytest
from pydantic import ValidationError

from unittest.mock import patch

from ai_engine.action_engine import ActionEngine
from utils.exceptions import (
    InvalidActionStructure, ActionNotFound, ActionNotActive,
    ActionRequiresConfirmationError, ExecutionException, PathParamNotFound,
    BodyParamOnGetRequest
)


@pytest.fixture
def minimal_agent_path(write_temp_json):
    return write_temp_json({"system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"}, "global_defaults": {}}, "agent.json")


class TestToolBuilding:
    def test_active_filter(self, minimal_agent_path):
        actions = [
            {"name": "active1", "description": "A", "type": "internal", "active": True},
            {"name": "inactive1", "description": "I", "type": "internal", "active": False}
        ]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        tools = engine.build_tools()
        assert len(tools) == 1
        assert tools[0].name == "active1"

    def test_all_inactive_returns_empty(self, minimal_agent_path):
        actions = [
            {"name": "inactive", "description": "I", "type": "internal", "active": False}
        ]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        assert engine.build_tools() == []

    def test_tool_schema_generation(self, minimal_agent_path):
        actions = [{
            "name": "get_order",
            "description": "Get order",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "/orders/{order_id}"},
            "parameters": {
                "order_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "path",
                    "description": "Order ID"
                }
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        tools = engine.build_tools()
        schema = tools[0].args_schema
        assert "order_id" in schema.model_fields
        field = schema.model_fields["order_id"]
        assert field.annotation == str
        assert field.is_required() is True

    def test_tool_schema_optional_with_default(self, minimal_agent_path):
        actions = [{
            "name": "check_hours",
            "description": "Check hours",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "/hours"},
            "parameters": {
                "city": {
                    "type": "string",
                    "required": False,
                    "default": "New York",
                    "param_type": "query",
                    "description": "City"
                }
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        tools = engine.build_tools()
        schema = tools[0].args_schema
        field = schema.model_fields["city"]
        from typing import Optional
        assert field.annotation == Optional[str]
        assert field.default == "New York"

    def test_tool_schema_enum_validation(self, minimal_agent_path):
        actions = [{
            "name": "refund",
            "description": "Process refund",
            "type": "rpc_request",
            "active": True,
            "execution_config": {
                "host": "localhost:50051",
                "service": "S",
                "method": "M",
                "proto_file": "x.proto"
            },
            "parameters": {
                "reason_code": {
                    "type": "string",
                    "required": True,
                    "param_type": "message_field",
                    "description": "Reason",
                    "enum": ["DEFECTIVE", "WRONG_ITEM", "CUSTOMER_REQUEST"]
                }
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        tools = engine.build_tools()
        schema = tools[0].args_schema

        valid = schema(reason_code="DEFECTIVE")
        assert valid.reason_code == "DEFECTIVE"

        with pytest.raises(ValidationError) as exc_info:
            schema(reason_code="INVALID")
        assert "DEFECTIVE" in str(exc_info.value)

    def test_tool_description_matches(self, minimal_agent_path):
        actions = [{
            "name": "desc_test",
            "description": "This is the description",
            "type": "internal",
            "active": True
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        tools = engine.build_tools()
        assert tools[0].description == "This is the description"


class TestDirectExecution:
    def test_happy_path_api(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "test_api",
            "description": "Test",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/test"},
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {"status": "ok"}

        result = engine.execute_action_directly("test_api", {})
        assert "ok" in result

    def test_not_found(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        with pytest.raises(ActionNotFound) as exc_info:
            engine.execute_action_directly("missing", {})
        assert "missing" in str(exc_info.value)

    def test_inactive(self, minimal_agent_path):
        actions = [
            {"name": "inactive", "description": "I", "type": "internal", "active": False}
        ]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        with pytest.raises(ActionNotActive) as exc_info:
            engine.execute_action_directly("inactive", {})
        assert "inactive" in str(exc_info.value)

    def test_param_validation_failure(self, minimal_agent_path):
        actions = [{
            "name": "typed_action",
            "description": "Test",
            "type": "internal",
            "active": True,
            "parameters": {
                "count": {
                    "type": "integer",
                    "required": True,
                    "param_type": "query",
                    "description": "Count"
                }
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        with pytest.raises(InvalidActionStructure) as exc_info:
            engine.execute_action_directly("typed_action", {"count": "not_an_int"})
        assert "validation" in str(exc_info.value).lower()

    def test_confirmation_gate(self, minimal_agent_path):
        actions = [{
            "name": "dangerous",
            "description": "Dangerous action",
            "type": "internal",
            "active": True,
            "requires_confirmation": True
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        with pytest.raises(ActionRequiresConfirmationError) as exc_info:
            engine.execute_action_directly("dangerous", {"x": 1})
        assert exc_info.value.action_name == "dangerous"
        assert exc_info.value.params == {"x": 1}

    def test_skip_confirmation(self, minimal_agent_path):
        actions = [{
            "name": "dangerous",
            "description": "Dangerous action",
            "type": "internal",
            "active": True,
            "requires_confirmation": True
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        result = engine.execute_action_directly("dangerous", {"x": 1}, skip_confirmation=True)
        assert "processed successfully" in result

    def test_param_validation_success(self, minimal_agent_path):
        actions = [{
            "name": "typed_action",
            "description": "Test",
            "type": "internal",
            "active": True,
            "parameters": {
                "count": {
                    "type": "integer",
                    "required": True,
                    "param_type": "query",
                    "description": "Count"
                }
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        result = engine.execute_action_directly("typed_action", {"count": 42})
        assert "42" in result

    def test_vector_execution_direct(
        self, 
        mock_generate_embedding,
        mock_get_vector_driver,  
        minimal_agent_path       
    ):
        actions = [{
            "name": "search_vec",
            "description": "Search",
            "type": "vector_query",
            "active": True,
            "execution_config": {
                "collection_name": "products",
                "connector": "postgres",
                "embedding_config": {
                    "provider": "test_provider",
                    "model_name": "test_model"
                }
            },
            "parameters": {
                "topic": {
                    "type": "string",
                    "required": True,
                    "param_type": "vector",
                    "description": "Topic"
                }
            },
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        result = engine.execute_action_directly("search_vec", {"topic": "shoes"})
        assert "Product" in result
        mock_generate_embedding.assert_called_once_with("shoes", engine.actions[0].execution_config.embedding_config)


class TestPathParamSanitization:
    def test_valid_path_param(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        result = engine._sanitize_path_param("id", "ORD-123")
        assert result == "ORD-123"

    def test_valid_path_param_numeric(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        result = engine._sanitize_path_param("id", 123)
        assert result == "123"

    @pytest.mark.parametrize("bad_value", [
        "../etc/passwd",
        "test\x00",
        "path?query=1",
        "path#fragment",
        "path\\backslash"
    ])
    def test_invalid_path_param_rejected(self, minimal_agent_path, bad_value):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        with pytest.raises(ExecutionException) as exc_info:
            engine._sanitize_path_param("id", bad_value)
        assert "invalid characters" in str(exc_info.value)

    def test_url_encoded_traversal_documented(self, minimal_agent_path):
        # Documented limitation: %2e%2e is not blocked by current sanitizer
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        result = engine._sanitize_path_param("id", "%2e%2e")
        assert result == "%2e%2e"


class TestInternalExecution:
    def test_internal_action(self, minimal_agent_path):
        actions = [{
            "name": "notify",
            "description": "Notify",
            "type": "internal",
            "active": True
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        result = engine.execute_action_directly("notify", {"msg": "hello"})
        assert "notify" in result
        assert "hello" in result

    def test_internal_action_no_params(self, minimal_agent_path):
        actions = [{
            "name": "ping",
            "description": "Ping",
            "type": "internal",
            "active": True
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        result = engine.execute_action_directly("ping", {})
        assert "ping" in result.lower()
