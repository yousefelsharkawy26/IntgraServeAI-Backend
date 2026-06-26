"""
gRPC Test Server Fixtures — Phase 2 Integration Infrastructure

Provides a real Python gRPC server running in a daemon thread so that the
ActionEngine's _execute_rpc method can exercise the full stack:
  - Proto compilation and module caching
  - Stub class resolution and message construction
  - Metadata transmission (headers)
  - Deadline/timeout propagation
  - Status code handling (OK, PERMISSION_DENIED, DEADLINE_EXCEEDED)

Implementation approach:
  1. Write a minimal payment.proto to a temp directory.
  2. Use grpc_tools.protoc to compile it (or ship pre-generated _pb2.py).
  3. Implement a Servicer with RefundTransaction.
  4. Start grpc.server in a daemon thread on an ephemeral port.
  5. Yield host:port string.
  6. Stop server after test session.

Dependencies: grpcio, grpcio-tools
"""

from concurrent.futures import ThreadPoolExecutor
import time
from typing import Generator
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Proto Definition
# ---------------------------------------------------------------------------

PAYMENT_PROTO = """
syntax = "proto3";

package payment;

service PaymentService {
  rpc RefundTransaction(RefundRequest) returns (RefundResponse);
}

message RefundRequest {
  string transaction_id = 1;
  string reason_code = 2;
}

message RefundResponse {
  string status = 1;
  string refunded_amount = 2;
}
"""


# ---------------------------------------------------------------------------
# Server Lifecycle
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def grpc_test_proto_dir(tmp_path_factory) -> Path:
    """Writes payment.proto to a temp dir and returns the path."""
    proto_dir = tmp_path_factory.mktemp("grpc_proto")
    proto_file = proto_dir / "payment.proto"
    proto_file.write_text(PAYMENT_PROTO)
    return proto_dir


@pytest.fixture(scope="session")
def grpc_server_host(grpc_test_proto_dir) -> Generator[str, None, None]:
    """
    Yields "127.0.0.1:<port>" for a real gRPC PaymentService server.

    We compile the proto at session scope, import the generated modules,
    implement the servicer, and start the server in a background thread.
    """
    import grpc
    from grpc_tools import protoc
    import sys
    import importlib

    proto_dir = str(grpc_test_proto_dir)
    proto_file = "payment.proto"
    out_dir = str(grpc_test_proto_dir / "generated")
    Path(out_dir).mkdir(exist_ok=True)

    # Compile if not already cached
    pb2_path = Path(out_dir) / "payment_pb2.py"
    if not pb2_path.exists():
        protoc.main([
            "grpc_tools.protoc",
            f"-I{proto_dir}",
            f"--python_out={out_dir}",
            f"--grpc_python_out={out_dir}",
            str(grpc_test_proto_dir / proto_file)
        ])

    sys.path.insert(0, out_dir)
    try:
        import payment_pb2
        import payment_pb2_grpc
    finally:
        sys.path.remove(out_dir)

    class _Servicer(payment_pb2_grpc.PaymentServiceServicer):
        def RefundTransaction(self, request, context):
            # Simulate metadata inspection
            metadata = dict(context.invocation_metadata()) if context.invocation_metadata() else {}
            if metadata.get("x-admin-key") != "secret-admin-key":
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details("Invalid admin key")
                return payment_pb2.RefundResponse()

            # Simulate deadline/timeout
            if context.is_active() and hasattr(context, 'time_remaining'):
                if context.time_remaining() is not None and context.time_remaining() < 0.5:
                    context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
                    context.set_details("Deadline exceeded")
                    return payment_pb2.RefundResponse()

            return payment_pb2.RefundResponse(
                status="PENDING",
                refunded_amount="49.99"
            )

    server = grpc.server(ThreadPoolExecutor(max_workers=2))
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(_Servicer(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()

    yield f"127.0.0.1:{port}"

    server.stop(grace=False)
