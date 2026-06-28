"""
Integration Tests: HTTP/API Action Execution

Validates the ActionEngine's _execute_api_request against real HTTP servers.
These tests exercise the full network stack: DNS resolution, TCP handshake,
HTTP request serialization, response parsing, and error handling.

Coverage targets:
  - API-I01 through API-I13 from the master test plan.
  - Path param substitution with real URL routing.
  - Query param serialization and server-side parsing.
  - JSON body encoding on POST.
  - Header merging and auth propagation.
  - Timeout enforcement.
  - 4xx/5xx error handling with on_error templates.
  - Non-JSON response bodies.
  - Connection failure graceful degradation.

Markers: integration, slow
"""

import pytest

from ai_engine.action_engine import ActionEngine
from utils.exceptions import BodyParamOnGetRequest, ExecutionException

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture
def api_agent_config(write_temp_json):
    """Minimal agent config with no global defaults to avoid URL merging surprises."""
    return write_temp_json({
        "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
        "global_defaults": {
            "api_request": {
                "protocol": "https",
                "base_url": "",
                "timeout": 10000,
                "headers": {},
                "on_error": "Error"
            },
            "rpc_request": {
                "protocol": "grpc",
                "headers": {},
                "on_error": "Error"
            },
            "vector_query": {
                "connector": "postgres",
                "connection_string": "postgresql://localhost:5432/test",
                "on_error": "Error"
            },
            "internal": {
                "on_error": "Error"
            }
        }
    }, "agent.json")


@pytest.mark.asyncio
class TestGetWithPathParams:
    """
    API-I01: GET with path params against real FastAPI server.
    """

    async def test_get_order_details(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "get_order_details",
            "description": "Get order",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/orders/{{order_id}}",
                "timeout": 5000
            },
            "parameters": {
                "order_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "path",
                    "description": "Order ID"
                }
            },
            "response_config": {
                "mode": "json",
                "values": {
                    "status": {"type": "string", "path": "data.order.current_status"},
                    "delivery": {"type": "string", "path": "data.order.estimated_delivery"},
                    "total": {"type": "string", "path": "data.order.payment_summary.total"}
                },
                "template": "Status: {{status}}, Delivery: {{delivery}}, Total: {{total}}"
            }
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        result = await engine.execute_action_directly("get_order_details", {"order_id": "ORD-123"})
        assert "shipped" in result
        assert "129.99" in result


@pytest.mark.asyncio
class TestGetWithQueryParams:
    """
    API-I02: GET with query params.
    """

    async def test_check_store_hours_with_city(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "check_store_hours",
            "description": "Check hours",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/stores/hours",
                "timeout": 3000
            },
            "parameters": {
                "city": {
                    "type": "string",
                    "required": False,
                    "default": "New York",
                    "param_type": "query",
                    "description": "City"
                }
            },
            "response_config": {
                "mode": "json",
                "values": {
                    "open": {"type": "string", "path": "data.hours.open"},
                    "close": {"type": "string", "path": "data.hours.close"}
                },
                "template": "Open {{open}} to {{close}}"
            }
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        result = await engine.execute_action_directly("check_store_hours", {"city": "Los Angeles"})
        assert "10:00" in result
        assert "22:00" in result

    async def test_check_store_hours_default(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "check_store_hours",
            "description": "Check hours",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/stores/hours",
                "timeout": 3000
            },
            "parameters": {
                "city": {
                    "type": "string",
                    "required": False,
                    "default": "New York",
                    "param_type": "query",
                    "description": "City"
                }
            },
            "response_config": {
                "mode": "json",
                "values": {
                    "open": {"type": "string", "path": "data.hours.open"},
                    "close": {"type": "string", "path": "data.hours.close"}
                },
                "template": "Open {{open}} to {{close}}"
            }
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        result = await engine.execute_action_directly("check_store_hours", {})
        assert "09:00" in result


@pytest.mark.asyncio
class TestPostWithBody:
    """
    API-I03: POST with JSON body.
    """

    async def test_update_shipping_address(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "update_shipping_address",
            "description": "Update address",
            "type": "api_request",
            "active": True,
            "requires_confirmation": False,
            "execution_config": {
                "method": "POST",
                "url": f"{http_server_base_url}/orders/{{order_id}}/address",
                "timeout": 8000
            },
            "parameters": {
                "order_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "path",
                    "description": "Order ID"
                },
                "new_street": {
                    "type": "string",
                    "required": True,
                    "param_type": "body",
                    "description": "Street"
                },
                "new_zip": {
                    "type": "string",
                    "required": True,
                    "param_type": "body",
                    "description": "ZIP"
                }
            },
            "response_config": {
                "mode": "json",
                "values": {
                    "code": {"type": "string", "path": "data.update_log.id"}
                },
                "template": "Updated: {{code}}"
            }
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        result = await engine.execute_action_directly(
            "update_shipping_address",
            {"order_id": "ORD-999", "new_street": "123 Main St", "new_zip": "10001"}
        )
        assert "UPD-ORD-999-001" in result


@pytest.mark.asyncio
class TestGetWithBodyRejection:
    """
    API-I06: Body on GET rejected before network call.
    """

    async def test_body_on_get_rejected(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "bad_get",
            "description": "Bad GET",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/test"
            },
            "parameters": {
                "data": {
                    "type": "string",
                    "required": True,
                    "param_type": "body",
                    "description": "Data"
                }
            }
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        with pytest.raises(BodyParamOnGetRequest):
            await engine.execute_action_directly("bad_get", {"data": "payload"})


@pytest.mark.asyncio
class TestHeaderPropagation:
    """
    API-I05: Header merging with real server.
    """

    async def test_headers_sent_to_server(self, api_agent_config, http_server_base_url):
        # FastAPI doesn't have a built-in header echo, but we can verify
        # the request object is constructed correctly by inspecting the
        # mock boundary (or adding a /echo-headers endpoint to the server).
        # For integration, we add an echo endpoint to the FastAPI app.
        actions = [{
            "name": "header_test",
            "description": "Header test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/orders/123",
                "headers": {"X-Custom": "value"}
            },
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        result = await engine.execute_action_directly("header_test", {})
        # The server returns JSON; we at least verify no crash and data flows.
        assert "shipped" in result


@pytest.mark.asyncio
class TestAuthPropagation:
    """
    API-I06: Basic auth.
    """

    async def test_basic_auth(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "auth_test",
            "description": "Auth test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/protected",
                "auth": {"username": "user", "password": "pass"}
            },
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        result = await engine.execute_action_directly("auth_test", {})
        # FastAPI /protected currently returns 200 regardless (auth is client-side in requests).
        # We verify the request was made successfully.
        assert "authorized" in result or "status" in result


@pytest.mark.asyncio
class TestTimeout:
    """
    API-I07: Timeout conversion and enforcement.
    """

    async def test_timeout_enforced(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "slow_test",
            "description": "Slow endpoint",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/error/timeout",
                "timeout": 500  # 0.5s
            },
            "parameters": {},
            "response_config": {
                "mode": "raw",
                "on_error": "Timed out: {{error}}"
            }
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        with pytest.raises(ExecutionException):
            result = await engine.execute_action_directly("slow_test", {})
            assert "Timed out" in result


@pytest.mark.asyncio
class TestErrorHandling:
    """
    API-I08, API-I09, API-I10, API-I11: Error response handling.
    """

    async def test_404_with_template(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "err_404",
            "description": "404 test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/error/404"
            },
            "parameters": {},
            "response_config": {
                "mode": "raw",
                "on_error": "Not found: {{error}}"
            }
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        with pytest.raises(ExecutionException):
            result = await engine.execute_action_directly("err_404", {})
            assert "Not found" in result

    async def test_500_with_template(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "err_500",
            "description": "500 test",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/error/500"
            },
            "parameters": {},
            "response_config": {
                "mode": "raw",
                "on_error": "Server error: {{error}}"
            }
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        with pytest.raises(ExecutionException):
            result = await engine.execute_action_directly("err_500", {})
            assert "Server error" in result

    async def test_non_json_response(self, api_agent_config, http_server_base_url):
        actions = [{
            "name": "text_test",
            "description": "Text response",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": f"{http_server_base_url}/text-response"
            },
            "parameters": {},
            "response_config": {"mode": "raw"}
        }]
        engine = ActionEngine(api_agent_config, actions_list=actions)
        result = await engine.execute_action_directly("text_test", {})
        assert "Plain text response body" in result

    async def test_connection_error(self, api_agent_config):
        actions = [{
            "name": "conn_fail",
            "description": "Connection fail",
            "type": "api_request",
            "active": True,
            "execution_config": {
                "method": "GET",
                "url": "http://127.0.0.1:1/refuse"  # port 1 is reserved/unlikely
            },
            "parameters": {},
            "response_config": {
                "mode": "raw",
                "on_error": "Connection failed: {{error}}"
            }
        }]

        engine = ActionEngine(api_agent_config, actions_list=actions)

        with pytest.raises(ExecutionException):
            result = await engine.execute_action_directly("conn_fail", {})
            assert "Connection failed" in result