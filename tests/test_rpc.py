"""Comprehensive Test Suite for Phase 14.1: JSON-RPC 2.0 Engine.

Validates:
- Standard JSON-RPC 2.0 request/response cycles (single call)
- Named (dictionary) and positional (list) parameters
- Notification handling (no response, HTTP 204)
- Batch requests (mixed success, errors, notifications)
- Full error code coverage:
  - Parse error (-32700)
  - Invalid request (-32600)
  - Method not found (-32601)
  - Invalid params (-32602)
  - Internal error (-32603)
- HTTP endpoint integration via FastAPI TestClient
- Option B signature compatibility (add_method, register, dispatch)
"""

import pytest
from starlette.testclient import TestClient

from red_fastapi.main import app
from red_fastapi.rpc.dispatcher import JSONRPCDispatcher
from red_fastapi.rpc.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    InvalidParams,
    JSONRPCError,
)
from red_fastapi.rpc.protocols import BaseDispatcherProtocol


@pytest.fixture
def dispatcher():
    """Create a clean isolated dispatcher for testing."""
    d = JSONRPCDispatcher()

    @d.add_method("add")
    async def add(a: int, b: int) -> int:
        return a + b

    @d.add_method("greet")
    async def greet(name: str = "World") -> str:
        return f"Hello, {name}!"

    @d.register("fail")
    async def failing_method():
        raise RuntimeError("Something blew up inside")

    @d.add_method("custom_error")
    async def custom_error():
        raise JSONRPCError(code=-32001, message="Custom domain error", data={"details": "info"})

    return d


@pytest.mark.asyncio
async def test_protocol_conformance(dispatcher):
    """Test that the dispatcher satisfies the BaseDispatcherProtocol."""
    assert isinstance(dispatcher, BaseDispatcherProtocol)


@pytest.mark.asyncio
async def test_single_request_named_params(dispatcher):
    """Test standard call with named parameters."""
    req = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": {"a": 10, "b": 25},
        "id": 1,
    }
    resp = await dispatcher.dispatch(req)
    assert resp == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": 35,
    }


@pytest.mark.asyncio
async def test_single_request_positional_params(dispatcher):
    """Test standard call with positional parameters."""
    req = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": [7, 8],
        "id": "req-2",
    }
    resp = await dispatcher.dispatch(req)
    assert resp == {
        "jsonrpc": "2.0",
        "id": "req-2",
        "result": 15,
    }


@pytest.mark.asyncio
async def test_single_request_no_params(dispatcher):
    """Test call with default parameter values and no params sent."""
    req = {
        "jsonrpc": "2.0",
        "method": "greet",
        "id": 3,
    }
    resp = await dispatcher.dispatch(req)
    assert resp == {
        "jsonrpc": "2.0",
        "id": 3,
        "result": "Hello, World!",
    }


@pytest.mark.asyncio
async def test_notification(dispatcher):
    """Test notification (no id provided). Should return None."""
    notification = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": [1, 2],
    }
    resp = await dispatcher.dispatch(notification)
    assert resp is None


@pytest.mark.asyncio
async def test_method_not_found(dispatcher):
    """Test call to an unregistered method returns -32601."""
    req = {
        "jsonrpc": "2.0",
        "method": "non_existent_method",
        "id": "err-1",
    }
    resp = await dispatcher.dispatch(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "err-1"
    assert resp["error"]["code"] == METHOD_NOT_FOUND


@pytest.mark.asyncio
async def test_invalid_params(dispatcher):
    """Test argument mismatch returns -32602."""
    req = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": {"wrong_arg": 123},
        "id": "err-2",
    }
    resp = await dispatcher.dispatch(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "err-2"
    assert resp["error"]["code"] == INVALID_PARAMS


@pytest.mark.asyncio
async def test_internal_error_handling(dispatcher):
    """Test unhandled exception inside handler maps to -32603."""
    req = {
        "jsonrpc": "2.0",
        "method": "fail",
        "id": 99,
    }
    resp = await dispatcher.dispatch(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 99
    assert resp["error"]["code"] == INTERNAL_ERROR
    assert "Something blew up" in resp["error"]["data"]


@pytest.mark.asyncio
async def test_custom_jsonrpc_error(dispatcher):
    """Test custom JSONRPCError propagates specific code, message, and data."""
    req = {
        "jsonrpc": "2.0",
        "method": "custom_error",
        "id": "cust-1",
    }
    resp = await dispatcher.dispatch(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "cust-1"
    assert resp["error"]["code"] == -32001
    assert resp["error"]["message"] == "Custom domain error"
    assert resp["error"]["data"] == {"details": "info"}


@pytest.mark.asyncio
async def test_parse_error(dispatcher):
    """Test malformed JSON string payload returns -32700."""
    invalid_raw_json = "{\"jsonrpc\": \"2.0\", \"method\": \"add\", ...INVALID...}"
    resp = await dispatcher.dispatch(invalid_raw_json)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] is None
    assert resp["error"]["code"] == PARSE_ERROR


@pytest.mark.asyncio
async def test_invalid_request_structure(dispatcher):
    """Test invalid request structures return -32600."""
    # Missing jsonrpc version
    resp1 = await dispatcher.dispatch({"method": "add", "id": 1})
    assert resp1["error"]["code"] == INVALID_REQUEST

    # Wrong jsonrpc version
    resp2 = await dispatcher.dispatch({"jsonrpc": "1.0", "method": "add", "id": 1})
    assert resp2["error"]["code"] == INVALID_REQUEST

    # Method not a string
    resp3 = await dispatcher.dispatch({"jsonrpc": "2.0", "method": 12345, "id": 1})
    assert resp3["error"]["code"] == INVALID_REQUEST

    # Empty batch
    resp4 = await dispatcher.dispatch([])
    assert resp4["error"]["code"] == INVALID_REQUEST


@pytest.mark.asyncio
async def test_batch_request(dispatcher):
    """Test batch call containing normal calls, errors, and notifications."""
    batch = [
        {"jsonrpc": "2.0", "method": "add", "params": [1, 2], "id": "b1"},
        {"jsonrpc": "2.0", "method": "add", "params": [3, 4]},  # Notification
        {"jsonrpc": "2.0", "method": "non_existent", "id": "b2"},  # Error
        {"jsonrpc": "2.0", "method": "greet", "params": {"name": "Alice"}, "id": "b3"},
    ]
    resp = await dispatcher.dispatch(batch)
    assert isinstance(resp, list)
    assert len(resp) == 3  # Notification excluded from response

    # Map by id
    by_id = {item["id"]: item for item in resp}
    assert by_id["b1"]["result"] == 3
    assert by_id["b2"]["error"]["code"] == METHOD_NOT_FOUND
    assert by_id["b3"]["result"] == "Hello, Alice!"


@pytest.mark.asyncio
async def test_batch_all_notifications(dispatcher):
    """Test batch consisting only of notifications returns None."""
    batch = [
        {"jsonrpc": "2.0", "method": "add", "params": [1, 2]},
        {"jsonrpc": "2.0", "method": "greet"},
    ]
    resp = await dispatcher.dispatch(batch)
    assert resp is None


def test_http_endpoint_ping():
    """Test HTTP POST /api/rpc with built-in rpc.ping."""
    client = TestClient(app)
    payload = {
        "jsonrpc": "2.0",
        "method": "rpc.ping",
        "id": 100,
    }
    response = client.post("/api/rpc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "jsonrpc": "2.0",
        "id": 100,
        "result": "pong",
    }


def test_http_endpoint_list_methods():
    """Test HTTP POST /api/rpc with built-in rpc.listMethods."""
    client = TestClient(app)
    payload = {
        "jsonrpc": "2.0",
        "method": "rpc.listMethods",
        "id": "list-1",
    }
    response = client.post("/api/rpc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "rpc.ping" in data["result"]
    assert "rpc.listMethods" in data["result"]


def test_http_endpoint_notification():
    """Test HTTP POST /api/rpc notification returns 204 No Content."""
    client = TestClient(app)
    payload = {
        "jsonrpc": "2.0",
        "method": "rpc.ping",
    }
    response = client.post("/api/rpc", json=payload)
    assert response.status_code == 204
    assert response.content == b""

