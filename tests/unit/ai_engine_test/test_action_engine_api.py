import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

from tests.agent_config_test_utils import load_agent_config
from ai_engine.action_engine import ActionEngine
from utils.exceptions import (
    PathParamNotFound, BodyParamOnGetRequest, ExecutionException
)

@pytest.fixture(autouse=True)
def patch_structured_tool():
    import langchain_core.tools
    original_from_function = langchain_core.tools.StructuredTool.from_function

    def patched_from_function(*args, **kwargs):
        if len(args) > 0 and isinstance(args[0], tuple):
            args = list(args)
            coroutine = args[0][1]
            args[0] = args[0][0]
            kwargs['coroutine'] = coroutine
        elif 'func' in kwargs and isinstance(kwargs['func'], tuple):
            kwargs['coroutine'] = kwargs['func'][1]
            kwargs['func'] = kwargs['func'][0]
        return original_from_function(*args, **kwargs)

    with patch('ai_engine.action_engine.StructuredTool.from_function', side_effect=patched_from_function):
        yield

@pytest.fixture
def mock_requests():
    with patch('ai_engine.action_engine.httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_req = AsyncMock()
        mock_client.request = mock_req
        mock_req.client_class = mock_client_class
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.text = "{}"
        
        def raise_for_status():
            if mock_response.status_code >= 400:
                raise httpx.HTTPStatusError(
                    message=f"Error {mock_response.status_code}", 
                    request=AsyncMock(), 
                    response=mock_response
                )
        mock_response.raise_for_status.side_effect = raise_for_status
        mock_req.return_value = mock_response
        
        yield mock_req


@pytest.fixture
def minimal_agent_path(write_temp_json):
    return write_temp_json({
        "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
        "global_defaults": {}
    }, "agent.json")


@pytest.mark.asyncio
class TestApiRequestExecution:
    async def test_path_param_substitution(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {"id": "ORD-123"}

        await engine.execute_action_directly("get_order", {"order_id": "ORD-123"})

        call_args = mock_requests.call_args
        assert call_args.kwargs["url"] == "http://example.com/orders/ORD-123"

    async def test_query_param_building(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        await engine.execute_action_directly("search", {"q": "shoes", "limit": 10})

        call_args = mock_requests.call_args
        assert call_args.kwargs["params"] == {"q": "shoes", "limit": '10'}

    async def test_null_query_params_excluded(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        await engine.execute_action_directly("search", {})
        assert mock_requests.call_args.kwargs["params"] == {}

    async def test_body_param_on_post(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {"ok": True}

        await engine.execute_action_directly("update", {"data": "payload"})

        call_args = mock_requests.call_args
        assert call_args.kwargs["json"] == {"data": "payload"}

    async def test_body_param_on_get_rejected(self, minimal_agent_path):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)
        with pytest.raises(BodyParamOnGetRequest):
            await engine.execute_action_directly("bad_get", {"data": "payload"})

    async def test_unresolved_path_param_raises(self, minimal_agent_path):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)
        with pytest.raises(PathParamNotFound) as exc_info:
            await engine.execute_action_directly("bad_path", {"user_id": "123"})
        assert "user_id" in str(exc_info.value)

    async def test_remaining_placeholders_raises(self, minimal_agent_path):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)
        with pytest.raises(PathParamNotFound) as exc_info:
            await engine.execute_action_directly("bad_url", {})
        assert "unresolved" in str(exc_info.value).lower()

    async def test_basic_auth(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        await engine.execute_action_directly("auth_test", {})
        assert mock_requests.client_class.call_args.kwargs["auth"] == ("user", "pass")

    async def test_timeout_conversion(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        await engine.execute_action_directly("timeout_test", {})
        assert mock_requests.client_class.call_args.kwargs["timeout"] == 5.0

    async def test_4xx_error_handling(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 404
        mock_requests.return_value.json.return_value = {"error": "not found"}

        with pytest.raises(ExecutionException):
            result = await engine.execute_action_directly("err_test", {})
            assert "Custom error:" in result
            assert "not found" in result

    async def test_5xx_error_handling(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 500
        mock_requests.return_value.text = "Internal Server Error"
        with pytest.raises(ExecutionException):
            result = await engine.execute_action_directly("err_test", {})
            assert "Server error:" in result

    async def test_non_json_response(self, minimal_agent_path, mock_requests):
        actions = [{
            "name": "text_test",
            "description": "Text response",
            "type": "api_request",
            "active": True,
            "execution_config": {"method": "GET", "url": "http://example.com/text"},
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.side_effect = ValueError("Not JSON")
        mock_requests.return_value.text = "Plain text response"

        result = await engine.execute_action_directly("text_test", {})
        assert "Plain text response" in result

    async def test_connection_error_fallback(self, minimal_agent_path, mock_requests):
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
        engine = ActionEngine(load_agent_config(minimal_agent_path), actions_list=actions)

        mock_requests.side_effect = httpx.RequestError("Connection refused", request=AsyncMock())
        with pytest.raises(ExecutionException):
            result = await engine.execute_action_directly("conn_test", {})
            assert "Connection failed:" in result

    @pytest.mark.parametrize("base_url,url,protocol,expected", [
        ("api.example.com", "/orders", "https", "https://api.example.com/orders"),
        ("api.example.com/", "/orders", "https", "https://api.example.com/orders"),
        ("api.example.com", "orders", "https", "https://api.example.com/orders"),
        ("https://api.example.com", "/orders", "https", "https://api.example.com/orders"),
    ])
    async def test_url_construction_matrix(self, write_temp_json, base_url, url, protocol, expected, mock_requests):
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
        engine = ActionEngine(load_agent_config(agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        await engine.execute_action_directly("url_test", {})
        assert mock_requests.call_args.kwargs["url"] == expected

    async def test_absolute_url_not_modified(self, write_temp_json, mock_requests):
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
        engine = ActionEngine(load_agent_config(agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        await engine.execute_action_directly("abs_test", {})
        assert mock_requests.call_args.kwargs["url"] == "http://other.com/orders"

    async def test_header_override(self, write_temp_json, mock_requests):
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
        engine = ActionEngine(load_agent_config(agent_path), actions_list=actions)

        mock_requests.return_value.status_code = 200
        mock_requests.return_value.json.return_value = {}

        await engine.execute_action_directly("header_test", {})
        headers = mock_requests.call_args.kwargs["headers"]
        assert headers["X-Global"] == "1"
        assert headers["X-Action"] == "2"
        # Action header overrides global
        assert headers["Content-Type"] == "text/plain"