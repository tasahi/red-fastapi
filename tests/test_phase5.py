""" Automated unit & integration tests for Phase 5:
- NodeBase lifecycle and wire message routing
- InjectNode execution (manual trigger via POST /inject/{id})
- FunctionNode execution (Python code transformation with msg)
- DebugNode execution (streaming to WebSocket /comms)
- End-to-end flow execution: [Inject] -> [Function] -> [Debug]
- Debug enable/disable toggling via POST /debug/{id}/{action}
"""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from red_fastapi.main import app
from red_fastapi.runtime import flows as runtime_flows
from red_fastapi.runtime import comms as runtime_comms


client = TestClient(app)


def test_e2e_inject_function_debug_flow():
    """ Tests full end-to-end execution of a deployed flow:
    [Inject] -> [Function (Python)] -> [Debug] -> WebSocket /comms.
    """
    runtime_comms.init()

    # Flow configuration
    flow_payload = {
        "flows": [
            {
                "type": "tab",
                "id": "tab_e2e",
                "label": "E2E Tab",
                "disabled": False,
                "info": "",
                "env": []
            },
            {
                "id": "inject_1",
                "type": "inject",
                "z": "tab_e2e",
                "name": "Trigger",
                "props": [
                    {"p": "payload", "vt": "str", "v": "hello world"},
                    {"p": "topic", "vt": "str", "v": "greeting"}
                ],
                "repeat": "",
                "crontab": "",
                "once": False,
                "wires": [["func_1"]]
            },
            {
                "id": "func_1",
                "type": "function",
                "z": "tab_e2e",
                "name": "Uppercase",
                "func": "msg['payload'] = msg['payload'].upper()\nmsg['processed'] = True\nreturn msg",
                "wires": [["debug_1"]]
            },
            {
                "id": "debug_1",
                "type": "debug",
                "z": "tab_e2e",
                "name": "Output",
                "active": True,
                "tosidebar": True,
                "complete": "payload",
                "wires": []
            }
        ]
    }

    # 1. Connect WebSocket client (simulating browser editor open)
    with client.websocket_connect("/comms") as ws:
        # Subscribe to debug messages
        ws.send_text(json.dumps({"subscribe": "debug"}))

        # 2. Deploy flow
        deploy_res = client.post("/flows", json=flow_payload, headers={"Node-RED-Deployment-Type": "full"})
        assert deploy_res.status_code == 200

        # Discard any initial retained notifications
        while True:
            try:
                raw = ws.receive_text()
                # Continue draining initial messages
            except Exception:
                break
            if "runtime-deploy" in raw:
                break

        # 3. Trigger inject node manually via POST /inject/inject_1
        inject_res = client.post("/inject/inject_1", json={})
        assert inject_res.status_code == 200
        assert inject_res.json() == {"status": "ok"}

        # 4. Receive debug message over WebSocket
        debug_raw = ws.receive_text()
        batch = json.loads(debug_raw)
        assert isinstance(batch, list)

        debug_event = next((item for item in batch if item.get("topic") == "debug"), None)
        assert debug_event is not None
        assert debug_event["data"]["id"] == "debug_1"
        # Verify function node transformation applied
        assert debug_event["data"]["msg"]["payload"] == "HELLO WORLD"
        assert debug_event["data"]["msg"]["processed"] is True
        assert debug_event["data"]["msg"]["topic"] == "greeting"


def test_inject_node_not_found():
    """ Tests that POST /inject/invalid_id returns 404.
    """
    res = client.post("/inject/invalid_id", json={})
    assert res.status_code == 404


def test_debug_toggle_action():
    """ Tests enabling and disabling debug nodes via POST /debug/{id}/{action}.
    """
    # Deploy a flow with a debug node
    flow_payload = {
        "flows": [
            {
                "type": "tab",
                "id": "tab_dbg",
                "label": "Debug Tab",
                "disabled": False,
                "info": "",
                "env": []
            },
            {
                "id": "dbg_toggle",
                "type": "debug",
                "z": "tab_dbg",
                "name": "Dbg",
                "active": True,
                "wires": []
            }
        ]
    }
    client.post("/flows", json=flow_payload)

    # Disable
    res_disable = client.post("/debug/dbg_toggle/disable")
    assert res_disable.status_code == 200
    assert res_disable.json()["active"] is False

    # Enable
    res_enable = client.post("/debug/dbg_toggle/enable")
    assert res_enable.status_code == 200
    assert res_enable.json()["active"] is True

