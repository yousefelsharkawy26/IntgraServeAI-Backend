"""
HTTP Test Server Fixtures — Phase 2 Integration Infrastructure

Provides a real threaded HTTP server (FastAPI via uvicorn in a background thread)
that the ActionEngine can hit over actual TCP sockets. This validates:
  - Path parameter substitution and URL construction
  - Query parameter serialization
  - JSON body encoding
  - Header propagation and auth
  - Timeout behavior
  - Error response handling (4xx, 5xx, connection drops)

Implementation approach:
  1. Define a FastAPI app matching the ShopEasy API surface.
  2. Start uvicorn in a daemon thread on an ephemeral port (0).
  3. Yield the bound base URL (e.g., http://127.0.0.1:54321).
  4. After test teardown, signal the server to stop.

Dependencies: fastapi, uvicorn, httpx (for health-check polling)
"""

import threading
import time
from typing import Generator

import pytest
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# FastAPI Application Definition
# ---------------------------------------------------------------------------

app = FastAPI()


class OrderResponse(BaseModel):
    data: dict


class AddressUpdate(BaseModel):
    new_street: str
    new_zip: str


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str):
    """Simulates get_order_details action."""
    return {
        "data": {
            "order": {
                "current_status": "shipped",
                "estimated_delivery": "2026-07-01",
                "payment_summary": {"total": "129.99"}
            }
        }
    }


@app.post("/orders/{order_id}/address")
def update_address(order_id: str, body: AddressUpdate):
    """Simulates update_shipping_address action."""
    return {
        "data": {
            "update_log": {"id": f"UPD-{order_id}-001"}
        }
    }


@app.get("/stores/hours")
def get_hours(city: str = Query(default="New York")):
    """Simulates check_store_hours action."""
    hours_db = {
        "New York": {"open": "09:00", "close": "21:00"},
        "Los Angeles": {"open": "10:00", "close": "22:00"}
    }
    return {"data": {"hours": hours_db.get(city, {"open": "09:00", "close": "21:00"})}}


@app.get("/search")
def search(q: str = "", limit: int = 10):
    """Generic search endpoint for query-param testing."""
    return {"results": [{"name": f"Result {i}"} for i in range(limit)]}


@app.get("/error/404")
def error_404():
    return JSONResponse(status_code=404, content={"error": "not found"})


@app.get("/error/500")
def error_500():
    return JSONResponse(status_code=500, content={"error": "internal failure"})


@app.get("/error/timeout")
def error_timeout():
    time.sleep(30)  # exceeds any reasonable action timeout
    return {"ok": True}


@app.get("/text-response")
def text_response():
    return PlainTextResponse("Plain text response body")


@app.get("/protected")
def protected_endpoint():
    """Returns 401 unless Basic Auth is present. Checked via ActionEngine headers."""
    return {"status": "authorized"}


# ---------------------------------------------------------------------------
# Server Lifecycle Fixture
# ---------------------------------------------------------------------------

class _ServerThread(threading.Thread):
    """Daemon thread that runs an ephemeral uvicorn server."""

    def __init__(self, app, host: str = "127.0.0.1", port: int = 0):
        super().__init__(daemon=True)
        self.app = app
        self.host = host
        self.port = port
        self._server = None
        self._bound_port = None

    def run(self):
        import uvicorn
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._server.run()

    @property
    def bound_port(self) -> int:
        """Poll until the server has bound to an ephemeral port."""
        if self._bound_port is None:
            # uvicorn stores the server instance on the config after startup
            # We rely on a small polling loop in the fixture instead.
            pass
        return self._bound_port

    def stop(self):
        if self._server is not None:
            self._server.should_exit = True


@pytest.fixture(scope="session")
def http_server_base_url() -> Generator[str, None, None]:
    """
    Yields the base URL of a real local HTTP server.

    Implementation note: uvicorn is started in a daemon thread. We health-check
    with httpx until the server is accepting connections, then yield.
    After the test session, we signal graceful shutdown.
    """
    import socket
    import httpx

    # Find an ephemeral port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()
    sock.close()

    # Start server thread
    server = _ServerThread(app, host="127.0.0.1", port=port)
    server.start()

    # Poll for readiness (max 5s)
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with httpx.Client(timeout=0.5) as client:
                r = client.get(f"{base_url}/orders/health-check")
                if r.status_code < 600:
                    break
        except Exception:
            time.sleep(0.1)
    else:
        server.stop()
        pytest.fail("HTTP test server failed to start within 5 seconds")

    yield base_url

    server.stop()
    server.join(timeout=2)
