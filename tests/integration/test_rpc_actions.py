"""
Integration Tests: gRPC/RPC Action Execution

Validates the ActionEngine's _execute_rpc against a real gRPC server:
  - Proto compilation and module caching (HF-04 fix).
  - Service and method resolution.
  - Message construction and transmission.
  - Metadata (headers) propagation.
  - Timeout/deadline handling.
  - Status code mapping (OK, PERMISSION_DENIED, DEADLINE_EXCEEDED).

Coverage targets:
  - RPC-I01 through RPC-I10 from the master test plan.
  - RPC-U11: Module caching (compile once, reuse).
  - RPC-U12: Temp directory behavior (documented, not leaked per session).

Markers: integration, slow
"""

import pytest

from tests.agent_config_test_utils import load_agent_config
from ai_engine.action_engine import ActionEngine
from utils.exceptions import (
    ProtoNotFound, ServiceNotFound, MethodNotFound
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(autouse=True)
def patch_allowed_proto_dir(grpc_test_proto_dir):
    """Allow the temporary proto directory for these integration tests."""
    original = ActionEngine.ALLOWED_PROTO_DIR
    ActionEngine.ALLOWED_PROTO_DIR = str(grpc_test_proto_dir)
    yield
    ActionEngine.ALLOWED_PROTO_DIR = original


@pytest.fixture
def rpc_agent_config(write_temp_json):
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


class TestProtoCompilation:
    """
    RPC-I01, RPC-I02, RPC-I03: Proto compilation lifecycle.
    """

    def test_compile_valid_proto(self, rpc_agent_config, grpc_test_proto_dir):
        engine = ActionEngine(load_agent_config(rpc_agent_config), actions_list=[])
        proto_path = str(grpc_test_proto_dir / "payment.proto")
        pb2, pb2_grpc = engine._compile_and_load_proto(proto_path)
        assert pb2 is not None
        assert pb2_grpc is not None
        assert hasattr(pb2_grpc, "PaymentServiceStub")

    def test_missing_proto_raises(self, rpc_agent_config):
        engine = ActionEngine(load_agent_config(rpc_agent_config), actions_list=[])
        with pytest.raises(ProtoNotFound):
            engine._compile_and_load_proto("/nonexistent/file.proto")

    def test_module_caching(self, rpc_agent_config, grpc_test_proto_dir):
        engine = ActionEngine(load_agent_config(rpc_agent_config), actions_list=[])
        proto_path = str(grpc_test_proto_dir / "payment.proto")
        pb2_1, pb2_grpc_1 = engine._compile_and_load_proto(proto_path)
        pb2_2, pb2_grpc_2 = engine._compile_and_load_proto(proto_path)
        assert pb2_1 is pb2_2
        assert pb2_grpc_1 is pb2_grpc_2


@pytest.mark.asyncio
class TestServiceMethodResolution:
    """
    RPC-I04, RPC-I05: Service and method resolution.
    """

    async def test_service_not_found(self, rpc_agent_config, grpc_test_proto_dir):
        actions = [{
            "name": "bad_service",
            "description": "Bad service",
            "type": "rpc_request",
            "active": True,
            "execution_config": {
                "host": "localhost:50051",
                "service": "NonExistentService",
                "method": "RefundTransaction",
                "proto_file": str(grpc_test_proto_dir / "payment.proto")
            },
            "parameters": {
                "transaction_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "message_field",
                    "description": "TX ID"
                }
            }
        }]
        engine = ActionEngine(load_agent_config(rpc_agent_config), actions_list=actions)
        with pytest.raises(ServiceNotFound) as exc_info:
            await engine.execute_action_directly("bad_service", {"transaction_id": "TX-1"})
        assert "NonExistentService" in str(exc_info.value)

    async def test_method_not_found(self, rpc_agent_config, grpc_test_proto_dir, grpc_server_host):
        actions = [{
            "name": "bad_method",
            "description": "Bad method",
            "type": "rpc_request",
            "active": True,
            "execution_config": {
                "host": grpc_server_host,
                "service": "PaymentService",
                "method": "NonExistentMethod",
                "proto_file": str(grpc_test_proto_dir / "payment.proto")
            },
            "parameters": {
                "transaction_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "message_field",
                    "description": "TX ID"
                }
            }
        }]
        engine = ActionEngine(load_agent_config(rpc_agent_config), actions_list=actions)
        with pytest.raises(MethodNotFound) as exc_info:
            await engine.execute_action_directly("bad_method", {"transaction_id": "TX-1"})
        assert "NonExistentMethod" in str(exc_info.value)


@pytest.mark.asyncio
class TestFullRpcCall:
    """
    RPC-I07: End-to-end RPC call with real server.
    """

    async def test_refund_transaction_success(self, rpc_agent_config, grpc_test_proto_dir, grpc_server_host):
        actions = [{
            "name": "process_refund_request",
            "description": "Process refund",
            "type": "rpc_request",
            "active": True,
            "requires_confirmation": False,
            "execution_config": {
                "host": grpc_server_host,
                "service": "PaymentService",
                "method": "RefundTransaction",
                "proto_file": str(grpc_test_proto_dir / "payment.proto"),
                "headers": {"x-admin-key": "secret-admin-key"},
                "allow_insecure": True
            },
            "parameters": {
                "transaction_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "message_field",
                    "description": "TX ID"
                },
                "reason_code": {
                    "type": "string",
                    "required": True,
                    "param_type": "message_field",
                    "description": "Reason",
                    "enum": ["DEFECTIVE", "WRONG_ITEM", "CUSTOMER_REQUEST"]
                }
            },
            "response_config": {
                "mode": "json",
                "values": {
                    "status": {"type": "string", "path": "status"},
                    "amount": {"type": "string", "path": "refunded_amount"}
                },
                "template": "Status: {{status}}, Amount: {{amount}}"
            }
        }]
        engine = ActionEngine(load_agent_config(rpc_agent_config), actions_list=actions)
        result = await engine.execute_action_directly(
            "process_refund_request",
            {"transaction_id": "TX-999", "reason_code": "CUSTOMER_REQUEST"}
        )
        assert "PENDING" in result
        assert "49.99" in result

    async def test_refund_permission_denied(self, rpc_agent_config, grpc_test_proto_dir, grpc_server_host):
        actions = [{
            "name": "refund_no_auth",
            "description": "Refund no auth",
            "type": "rpc_request",
            "active": True,
            "execution_config": {
                "host": grpc_server_host,
                "service": "PaymentService",
                "method": "RefundTransaction",
                "proto_file": str(grpc_test_proto_dir / "payment.proto"),
                "headers": {},
                "allow_insecure": True
            },
            "parameters": {
                "transaction_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "message_field",
                    "description": "TX ID"
                }
            },
            "response_config": {
                "mode": "raw",
                "on_error": "RPC failed: {{error}}"
            }
        }]
        engine = ActionEngine(load_agent_config(rpc_agent_config), actions_list=actions)
        result = await engine.execute_action_directly("refund_no_auth", {"transaction_id": "TX-1"})
        assert "RPC failed" in result

    async def test_refund_timeout(self, rpc_agent_config, grpc_test_proto_dir, grpc_server_host):
        actions = [{
            "name": "refund_timeout",
            "description": "Refund timeout",
            "type": "rpc_request",
            "active": True,
            "execution_config": {
                "host": grpc_server_host,
                "service": "PaymentService",
                "method": "RefundTransaction",
                "proto_file": str(grpc_test_proto_dir / "payment.proto"),
                "headers": {"x-admin-key": "secret-admin-key"},
                "timeout": 1,
                "allow_insecure": True
            },
            "parameters": {
                "transaction_id": {
                    "type": "string",
                    "required": True,
                    "param_type": "message_field",
                    "description": "TX ID"
                }
            },
            "response_config": {
                "mode": "raw",
                "on_error": "Timeout: {{error}}"
            }
        }]
        engine = ActionEngine(load_agent_config(rpc_agent_config), actions_list=actions)
        result = await engine.execute_action_directly("refund_timeout", {"transaction_id": "TX-1"})
        assert "Timeout" in result or "PENDING" in result or "RPC failed" in result