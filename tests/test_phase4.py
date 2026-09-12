""" Automated unit & integration tests for Phase 4:
- WebSocket /comms connection lifecycle
- Batch message transmission (array of {topic, data})
- Topic subscriptions ({"subscribe": "debug"})
- Node status badge broadcast (retained status)
- Runtime notifications (deploy events, runtime state)
- Debug message streaming to editor
"""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from red_fastapi.main import app
from red_fastapi.runtime import comms as runtime_comms


client = TestClient(app)


def test_comms_websocket_connect():
    """ Tests that clients can connect to /comms WebSocket and connection is registered.
    """
    runtime_comms.init()
    with client.websocket_connect("/comms") as websocket:
        assert runtime_comms.get_active_connection_count() == 1

        # Send subscription
        websocket.send_text(json.dumps({"subscribe": "debug"}))

    # After close, connection should be removed
    assert runtime_comms.get_active_connection_count() == 0


def test_comms_status_broadcast():
    """ Tests broadcasting node status badges to connected WebSocket clients.
    """
    runtime_comms.init()
    with client.websocket_connect("/comms") as websocket:
        # Publish status for node1
        asyncio.run(runtime_comms.publish_status("node1", fill="green", shape="dot", text="running"))

        raw_msg = websocket.receive_text()
        batch = json.loads(raw_msg)
        assert isinstance(batch, list)
        assert len(batch) >= 1
        assert batch[0]["topic"] == "status/node1"
        assert batch[0]["data"]["fill"] == "green"
        assert batch[0]["data"]["text"] == "running"


def test_comms_retained_status_on_new_connection():
    """ Tests that newly connected clients automatically receive retained statuses.
    """
    runtime_comms.init()
    # Retain a status before connection opens
    asyncio.run(runtime_comms.publish_status("node2", fill="red", shape="ring", text="disconnected"))

    with client.websocket_connect("/comms") as websocket:
        raw_msg = websocket.receive_text()
        batch = json.loads(raw_msg)
        assert isinstance(batch, list)
        assert any(item["topic"] == "status/node2" and item["data"]["fill"] == "red" for item in batch)


def test_comms_debug_message_broadcast():
    """ Tests streaming debug payloads formatted for the editor Debug sidebar.
    """
    runtime_comms.init()
    with client.websocket_connect("/comms") as websocket:
        payload = {"payload": "Hello from Python", "_msgid": "test-msg-1"}
        asyncio.run(runtime_comms.publish_debug("node_debug_1", "My Debug", payload))

        raw_msg = websocket.receive_text()
        batch = json.loads(raw_msg)
        assert isinstance(batch, list)
        assert batch[0]["topic"] == "debug"
        assert batch[0]["data"]["id"] == "node_debug_1"
        assert batch[0]["data"]["msg"]["payload"] == "Hello from Python"


def test_comms_runtime_deploy_notification():
    """ Tests that deploying flows broadcasts a runtime-deploy notification over /comms.
    """
    runtime_comms.init()
    with client.websocket_connect("/comms") as websocket:
        # Deploy a flow via REST
        deploy_payload = {
            "flows": [
                {
                    "type": "tab",
                    "id": "tab_comms",
                    "label": "Comms Tab",
                    "disabled": False,
                    "info": "",
                    "env": []
                }
            ]
        }
        res = client.post("/flows", json=deploy_payload, headers={"Node-RED-Deployment-Type": "full"})
        assert res.status_code == 200
        new_rev = res.json()["rev"]

        raw_msg = websocket.receive_text()
        batch = json.loads(raw_msg)
        assert isinstance(batch, list)
        assert any(item["topic"] == "notification/runtime-deploy" and item["data"]["revision"] == new_rev for item in batch)

