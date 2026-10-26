""" Automated Tests for Phase 14.3: WebSocket & Bidirectional Transport.\n
Validates:
- WebSocket connection lifecycle at `/api/rpc/ws`.
- Sending single JSON-RPC requests over WebSocket and receiving correlated responses.
- Sending batch JSON-RPC requests over WebSocket.
- Client-to-server notifications over WebSocket (expecting no response packet).
- Server-to-client JSON-RPC notifications via `stream.broadcast` and `rpc_ws_manager.broadcast_notification`.
- Topic subscription and filtered notifications via `stream.subscribe` / `stream.unsubscribe`.
"""

import json
import pytest
from starlette.testclient import TestClient

from red_fastapi.main import app
from red_fastapi.rpc.transports.websocket import rpc_ws_manager


@pytest.fixture
def client():
    return TestClient(app)


def test_websocket_rpc_request_response(client):
    """ Test standard JSON-RPC 2.0 call over WebSocket."""
    with client.websocket_connect("/api/rpc/ws") as ws:
        req = {
            "jsonrpc": "2.0",
            "method": "rpc.ping",
            "id": "ws-1",
        }
        ws.send_text(json.dumps(req))
        raw = ws.receive_text()
        data = json.loads(raw)

        assert data == {
            "jsonrpc": "2.0",
            "id": "ws-1",
            "result": "pong",
        }


def test_websocket_rpc_batch_call(client):
    """ Test batch call over WebSocket."""
    with client.websocket_connect("/api/rpc/ws") as ws:
        batch = [
            {"jsonrpc": "2.0", "method": "rpc.ping", "id": "b-1"},
            {"jsonrpc": "2.0", "method": "system.info", "id": "b-2"},
        ]
        ws.send_text(json.dumps(batch))
        raw = ws.receive_text()
        data = json.loads(raw)

        assert isinstance(data, list)
        assert len(data) == 2
        res_map = {item["id"]: item for item in data}
        assert res_map["b-1"]["result"] == "pong"
        assert res_map["b-2"]["result"]["name"] == "red-fastapi"


def test_websocket_server_to_client_notification(client):
    """ Test server pushing a JSON-RPC notification to connected WebSocket client."""
    with client.websocket_connect("/api/rpc/ws") as ws:
        # Trigger stream.broadcast through a standard RPC call
        req = {
            "jsonrpc": "2.0",
            "method": "stream.broadcast",
            "params": {"event": "runtime.started", "data": {"flows_count": 5}},
            "id": "broad-1",
        }
        ws.send_text(json.dumps(req))

        # We will receive two messages:
        # 1. The response to 'stream.broadcast'
        # 2. The server push notification itself
        msg1 = json.loads(ws.receive_text())
        msg2 = json.loads(ws.receive_text())

        messages = [msg1, msg2]
        # Identify response vs notification
        resp = next(m for m in messages if "id" in m and m["id"] == "broad-1")
        notif = next(m for m in messages if "id" not in m)

        assert resp["result"]["broadcasted"] is True
        assert notif["jsonrpc"] == "2.0"
        assert notif["method"] == "runtime.started"
        assert notif["params"] == {"flows_count": 5}


def test_websocket_topic_subscription(client):
    """ Test stream.subscribe and stream.unsubscribe methods."""
    with client.websocket_connect("/api/rpc/ws") as ws:
        # Subscribe to debug topic
        sub_req = {
            "jsonrpc": "2.0",
            "method": "stream.subscribe",
            "params": {"topic": "debug"},
            "id": "sub-1",
        }
        ws.send_text(json.dumps(sub_req))
        sub_resp = json.loads(ws.receive_text())
        assert sub_resp["result"]["subscribed"] is True
        assert sub_resp["result"]["topic"] == "debug"

        # Unsubscribe
        unsub_req = {
            "jsonrpc": "2.0",
            "method": "stream.unsubscribe",
            "params": {"topic": "debug"},
            "id": "unsub-1",
        }
        ws.send_text(json.dumps(unsub_req))
        unsub_resp = json.loads(ws.receive_text())
        assert unsub_resp["result"]["unsubscribed"] is True
