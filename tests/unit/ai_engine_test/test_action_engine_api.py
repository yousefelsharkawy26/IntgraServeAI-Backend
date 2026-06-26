import pytest

from ai_engine.action_engine import ActionEngine
from utils.exceptions import (
    PathParamNotFound, BodyParamOnGetRequest
)


@pytest.fixture
def minimal_agent_path(write_temp_json):
    return write_temp_json({
        "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
        "global_defaults": {}
    }, "agent.json")


class TestApiRequestExecution:
    def test_path_param_substitution(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "get_order",
            "description": "Get order",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/orders/{order_id}"},
            "parameters": {
                "order_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "path",
                    "description": "Order ID"
                }
            },
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {"id": "ORD-123"}

        engine.execute_action_directly("get_order", {"order_id": "ORD-123"})

        call_args = mock_requests.call_args
        assert call_args.kwargs["url"] == "http://example.com/orders/ORD-123"

    def test_query_param_building(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "search",
            "description": "Search",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/search"},
            "parameters": {
                "q": {
                    "type": "string",
                    "required": False,
                    "param_type": "query",
                    "description": "Query"
                },
                "limit": {
                    "type": "integer",
                    "required": False,
                    "param_type": "query",
                    "description": "Limit"
                }
            },
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        engine.execute_action_directly("search", {"q": "shoes", "limit": 10})

        call_args = mock_requests.call_args
        assert call_args.kwargs["params"] == {"q": "shoes", "limit": 10}

    def test_null_query_params_excluded(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "search",
            "description": "Search",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/search"},
            "parameters": {
                "q": {
                    "type": "string",
                    "required": False,
                    "param_type": "query",
                    "description": "Query"
                }
            },
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        engine.execute_action_directly("search", {})
        assert mock_requests.call_args.kwargs["params"] == {}

    def test_body_param_on_post(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "update",
            "description": "Update",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "POST", "url": "http://example.com/update"},
            "parameters": {
                "data": {
                    "type": "string",
                    "required": True,
                    "param_type": "body",
                    "description": "Data"
                }
            },
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {"ok": True}

        engine.execute_action_directly("update", {"data": "payload"})

        call_args = mock_requests.call_args
        assert call_args.kwargs["json"] == {"data": "payload"}

    def test_body_param_on_get_rejected(self, minimal_agent_path):
        actions = [{
            "name": "bad_get",
            "description": "Bad GET",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/test"},
            "parameters": {
                "data": {
                    "type": "string",
                    "required": True,
                    "param_type": "body",
                    "description": "Data"
                }
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        with pytest.raises(BodyParamOnGetRequest):
            engine.execute_action_directly("bad_get", {"data": "payload"})

    def test_unresolved_path_param_raises(self, minimal_agent_path):
        actions = [{
            "name": "bad_path",
            "description": "Bad path",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/orders/{order_id}"},
            "parameters": {
                "user_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "path",
                    "description": "User ID"
                }
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        with pytest.raises(PathParamNotFound) as exc_info:
            engine.execute_action_directly("bad_path", {"user_id": "123"})
        assert "user_id" in str(exc_info.value)

    def test_remaining_placeholders_raises(self, minimal_agent_path):
        actions = [{
            "name": "bad_url",
            "description": "Bad URL",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/orders/{{order_id}}"},
            "parameters": {
                "order_id": {
                    "type": "string",
                    "required": False,
                    "param_type": "path",
                    "description": "Order ID"
                }
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)
        with pytest.raises(PathParamNotFound) as exc_info:
            engine.execute_action_directly("bad_url", {})
        assert "unresolved" in str(exc_info.value).lower()

    def test_basic_auth(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "auth_test",
            "description": "Auth test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": "http://example.com/protected",
                "auth": {"username": "user", "password": "pass"}
            },
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        engine.execute_action_directly("auth_test", {})
        assert mock_requests.call_args.kwargs["auth"] == ("user", "pass")

    def test_timeout_conversion(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "timeout_test",
            "description": "Timeout",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": "http://example.com/slow",
                "timeout": 5000
            },
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        engine.execute_action_directly("timeout_test", {})
        assert mock_requests.call_args.kwargs["timeout"] == 5.0

    def test_4xx_error_handling(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "err_test",
            "description": "Error test",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/missing"},
            "parameters": {},
            "response_config": {
                "mode": "raw",
                "on_error": "Custom error: {{error}}"
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 404
        mock_requests.return_value.json.return_value = {"error": "not found"}

        result = engine.execute_action_directly("err_test", {})
        assert "Custom error:" in result
        assert "not found" in result

    def test_5xx_error_handling(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "err_test",
            "description": "Error test",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/boom"},
            "parameters": {},
            "response_config": {
                "mode": "raw",
                "on_error": "Server error: {{error}}"
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 500
        mock_requests.return_value.text = "Internal Server Error"

        result = engine.execute_action_directly("err_test", {})
        assert "Server error:" in result

    def test_non_json_response(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "text_test",
            "description": "Text response",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/text"},
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.side_effect = ValueError("Not JSON")
        mock_requests.return_value.text = "Plain text response"

        result = engine.execute_action_directly("text_test", {})
        assert "Plain text response" in result

    def test_connection_error_fallback(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "conn_test",
            "description": "Connection test",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/fail"},
            "parameters": {},
            "response_config": {
                "mode": "raw",
                "on_error": "Connection failed: {{error}}"
            }
        }]
        engine = ActionEngine(minimal_agent_path, actions_list=actions)

        mock_requests.side_effect = Exception("Connection refused")

        result = engine.execute_action_directly("conn_test", {})
        assert "Connection failed:" in result

    @pytest.mark.parametrize("base_url,url,protocol,expected", [
        ("api.example.com", "/orders", "https", "https://api.example.com/orders"),
        ("api.example.com/", "/orders", "https", "https://api.example.com/orders"),
        ("api.example.com", "orders", "https", "https://api.example.com/orders"),
        ("https://api.example.com", "/orders", "https", "https://api.example.com/orders"),
    ])
    def test_url_construction_matrix(self, write_temp_json, base_url, url, protocol, expected, mock_requests):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "api_request": {
                    "protocol": protocol,
                    "base_url": base_url,
                    "timeout": 10000,
                    "headers": {},
                    "on_error": "Error"
                }
            }
        }, "agent.json")

        actions = [{
            "name": "url_test",
            "description": "URL test",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": url},
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        engine.execute_action_directly("url_test", {})
        assert mock_requests.call_args.kwargs["url"] == expected

    def test_absolute_url_not_modified(self, write_temp_json, mock_requests):
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
            "name": "abs_test",
            "description": "Absolute URL",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://other.com/orders"},
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        engine.execute_action_directly("abs_test", {})
        assert mock_requests.call_args.kwargs["url"] == "http://other.com/orders"

    def test_header_override(self, write_temp_json, mock_requests):
        agent_path = write_temp_json({
            "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
            "global_defaults": {
                "api_request": {
                    "protocol": "https",
                    "base_url": "api.example.com",
                    "timeout": 10000,
                    "headers": {"X-Global": "1", "Content-Type": "application/json"},
                    "on_error": "Error"
                }
            }
        }, "agent.json")

        actions = [{
            "name": "header_test",
            "description": "Header test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": "/test",
                "headers": {"X-Action": "2", "Content-Type": "text/plain"}
            },
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(agent_path, actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        engine.execute_action_directly("header_test", {})
        headers = mock_requests.call_args.kwargs["headers"]
        assert headers["X-Global"] == "1"
        assert headers["X-Action"] == "2"
        # Action header overrides global
        assert headers["Content-Type"] == "text/plain"
