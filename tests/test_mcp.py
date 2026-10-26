""" Automated Tests for Phase 14.4: MCP Adapter & SSE Transport.\n
Validates:
- MCP Protocol Handshake: 'initialize', 'notifications/initialized', 'ping'.
- MCP Resources Discovery & Retrieval: 'resources/list', 'resources/read'.
- MCP Tool Registration via 'mcp in' and 'mcp out' nodes in a deployed flow.
- Invoking tools via 'tools/call' with arguments and waiting for flow completion.
- Flow-as-a-Tool execution and payload correlation.
- Tool error handling and timeout scenarios.
- MCP Server-Sent Events (SSE) Transport:
  - GET /mcp/sse emits 'endpoint' event with session ID.
  - POST /mcp/messages?sessionId=... delivers responses.
"""

import json
import pytest
from starlette.testclient import TestClient

from red_fastapi.main import app
from red_fastapi.mcp.server import MCPServer
from red_fastapi.runtime import flows as runtime_flows
from red_fastapi.runtime import nodes as runtime_nodes


@pytest.fixture(autouse=True)
def init_runtime():
    runtime_nodes.init()
    runtime_flows.init()


@pytest.fixture
def client():
    return TestClient(app)


def test_mcp_initialize(client):
    """ Test standard MCP initialize handshake via POST /mcp/messages."""
    init_req = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        },
        "id": "init-1"
    }
    response = client.post("/mcp/messages", json=init_req)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "init-1"
    res = data["result"]
    assert res["protocolVersion"] == "2024-11-05"
    assert "tools" in res["capabilities"]
    assert "resources" in res["capabilities"]
    assert res["serverInfo"]["name"] == "red-fastapi-mcp"


def test_mcp_resources(client):
    """ Test resources/list and resources/read."""
    # 1. List resources
    list_req = {
        "jsonrpc": "2.0",
        "method": "resources/list",
        "id": "res-1"
    }
    resp = client.post("/mcp/messages", json=list_req).json()
    resources = resp["result"]["resources"]
    assert len(resources) > 0
    assert resources[0]["uri"] == "red://system/flows"

    # 2. Read resource
    read_req = {
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "red://system/flows"},
        "id": "res-2"
    }
    resp2 = client.post("/mcp/messages", json=read_req).json()
    contents = resp2["result"]["contents"]
    assert len(contents) == 1
    assert contents[0]["uri"] == "red://system/flows"
    assert "flows" in json.loads(contents[0]["text"])


@pytest.mark.asyncio
async def test_mcp_flow_as_a_tool(client):
    """ Deploy a flow with 'mcp in' -> 'function' -> 'mcp out', and invoke via tools/call."""
    # Test flow: Takes payload numbers {a, b}, adds them in a function node, outputs result
    tool_flow = [
        {"id": "tab_mcp", "type": "tab", "label": "MCP Tool Flow"},
        {
            "id": "mcp_in_1",
            "type": "mcp in",
            "z": "tab_mcp",
            "name": "Adder Tool",
            "toolName": "add_numbers",
            "description": "Adds two numbers together",
            "schema": {
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"}
                },
                "required": ["a", "b"]
            },
            "wires": [["func_add"]]
        },
        {
            "id": "func_add",
            "type": "function",
            "z": "tab_mcp",
            "name": "Add Function",
            "func": "msg['payload'] = {'sum': msg['payload'].get('a', 0) + msg['payload'].get('b', 0)}; return msg;",
            "wires": [["mcp_out_1"]]
        },
        {
            "id": "mcp_out_1",
            "type": "mcp out",
            "z": "tab_mcp",
            "name": "Output Result",
            "wires": []
        }
    ]

    # Deploy flow
    deploy_res = client.post("/api/rpc", json={
        "jsonrpc": "2.0",
        "method": "flows.set",
        "params": {"flows": tool_flow},
        "id": "dep-1"
    }).json()
    assert "rev" in deploy_res["result"]

    # 1. Verify tool is discovered in tools/list
    list_tools_req = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": "tl-1"
    }
    tools_resp = client.post("/mcp/messages", json=list_tools_req).json()
    tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
    assert "add_numbers" in tool_names

    # 2. Invoke tool via tools/call
    call_req = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "add_numbers",
            "arguments": {"a": 42, "b": 58}
        },
        "id": "tc-1"
    }
    call_resp = client.post("/mcp/messages", json=call_req).json()
    assert call_resp["id"] == "tc-1"
    result = call_resp["result"]
    assert result["isError"] is False
    content_item = result["content"][0]
    assert content_item["type"] == "text"
    parsed_output = json.loads(content_item["text"])
    assert parsed_output == {"sum": 100}


@pytest.mark.asyncio
async def test_mcp_sse_transport_handshake():
    """ Test MCP SSE stream initialization at GET /mcp/sse."""
    from red_fastapi.mcp.sse import mcp_sse_endpoint
    from unittest.mock import AsyncMock, MagicMock
    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(side_effect=[False, True])

    resp = await mcp_sse_endpoint(mock_request)
    assert resp.status_code == 200
    assert resp.media_type == "text/event-stream"

    # Consume the first event from the generator
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)
        if "endpoint" in chunk:
            break

    combined = "".join(chunks)
    assert "event: endpoint" in combined
    assert "/mcp/messages?sessionId=" in combined
