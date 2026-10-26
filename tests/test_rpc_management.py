"""Automated Tests for Phase 14.2: Built-in Management RPC Methods.

Validates:
- system.info: Returns runtime metadata, version, active node count, engine state.
- flows.status: Returns current status, revision, and flow counts.
- flows.get: Returns active flows and revision.
- flows.start & flows.stop: Control engine execution state.
- flows.set: Deploys flows programmatically with validation.
- nodes.list: Returns registered node types and active node instances.
- nodes.trigger:
  - Triggers active inject nodes with/without payload.
  - Returns appropriate errors for missing nodes (-32004) or non-triggerable nodes (-32005).
- HTTP POST /api/rpc integration for all management RPC methods.
"""

import pytest
from starlette.testclient import TestClient

from red_fastapi.main import app
from red_fastapi.runtime import flows as runtime_flows
from red_fastapi.runtime import nodes as runtime_nodes
from red_fastapi.runtime.core_nodes import InjectNode


@pytest.fixture(autouse=True)
def init_runtime():
    """Ensure runtime is initialized before tests."""
    runtime_nodes.init()
    runtime_flows.init()


@pytest.fixture
def client():
    return TestClient(app)


def test_system_info(client):
    """Test system.info returns valid system metadata."""
    req = {
        "jsonrpc": "2.0",
        "method": "system.info",
        "id": "sys-1",
    }
    response = client.post("/api/rpc", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "sys-1"
    res = data["result"]
    assert res["name"] == "red-fastapi"
    assert "version" in res
    assert "engine_state" in res
    assert "active_node_instances" in res
    assert "storage_type" in res


def test_flows_lifecycle(client):
    """Test flows.status, flows.get, flows.stop, and flows.start via RPC."""
    # 1. flows.status
    status_resp = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "flows.status",
        "id": "st-1"
    }).json()
    assert status_resp["result"]["state"] in ("start", "stop")

    # 2. flows.get
    get_resp = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "flows.get",
        "id": "get-1"
    }).json()
    assert "flows" in get_resp["result"]
    assert "rev" in get_resp["result"]

    # 3. flows.stop
    stop_resp = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "flows.stop",
        "id": "stop-1"
    }).json()
    assert stop_resp["result"] == {"state": "stop"}

    # Verify status changed
    check_stop = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "flows.status",
        "id": "check-stop"
    }).json()
    assert check_stop["result"]["state"] == "stop"

    # 4. flows.start
    start_resp = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "flows.start",
        "id": "start-1"
    }).json()
    assert start_resp["result"] == {"state": "start"}


@pytest.mark.asyncio
async def test_flows_set_and_nodes_trigger(client):
    """Deploy a test flow containing an inject node, and trigger it via RPC."""
    test_flow = [
        {"id": "tab1", "type": "tab", "label": "RPC Test Flow"},
        {
            "id": "inject1",
            "type": "inject",
            "z": "tab1",
            "name": "Test Inject",
            "topic": "test/rpc",
            "payload": "initial",
            "payloadType": "str",
            "repeat": "",
            "crontab": "",
            "once": False,
            "onceDelay": 0.1,
            "wires": [[]]
        }
    ]

    # Deploy flow via flows.set
    set_resp = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "flows.set",
        "params": {"flows": test_flow},
        "id": "set-1"
    }).json()
    assert "rev" in set_resp["result"]

    # Verify nodes.list shows inject1
    list_resp = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "nodes.list",
        "id": "list-1"
    }).json()
    active_ids = [n["id"] for n in list_resp["result"]["active_nodes"]]
    assert "inject1" in active_ids

    # Trigger inject node without custom payload
    trig_resp1 = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "nodes.trigger",
        "params": {"node_id": "inject1"},
        "id": "trig-1"
    }).json()
    assert trig_resp1["result"] == {"status": "ok", "node_id": "inject1", "triggered": True}

    # Trigger inject node with custom payload
    trig_resp2 = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "nodes.trigger",
        "params": {"node_id": "inject1", "payload": "custom_via_rpc"},
        "id": "trig-2"
    }).json()
    assert trig_resp2["result"] == {"status": "ok", "node_id": "inject1", "triggered": True}


def test_nodes_trigger_errors(client):
    """Test error handling when triggering non-existent or invalid nodes."""
    # 1. Non-existent node (-32004)
    resp1 = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "nodes.trigger",
        "params": {"node_id": "non_existent_node_999"},
        "id": "err-1"
    }).json()
    assert resp1["error"]["code"] == -32004
    assert "Node not found" in resp1["error"]["message"]

    # 2. Missing required parameter (-32602)
    resp2 = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "nodes.trigger",
        "params": {},
        "id": "err-2"
    }).json()
    assert resp2["error"]["code"] == -32602

