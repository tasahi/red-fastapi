""" Automated unit & integration tests for Phase 3:
- GET /flows (v1 and v2 API versions)
- POST /flows (full deploy, reload)
- Persistence to storage/flows.json
- Flow execution state: GET /flows/state, POST /flows/state
- Individual flow CRUD: GET /flow/{id}, POST /flow, PUT /flow/{id}, DELETE /flow/{id}
"""

import pytest
from fastapi.testclient import TestClient
from red_fastapi.main import app
from red_fastapi.config import settings
from red_fastapi.runtime import flows as runtime_flows
from red_fastapi.runtime import storage


# Initialize storage and flows for test session
storage.init()
runtime_flows.init()
client = TestClient(app)


def test_get_flows_v2():
    """ Tests that GET /flows returns dict with flows array and rev string for v2 API.
    """
    response = client.get("/flows", headers={"Node-RED-API-Version": "v2"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "flows" in data
    assert "rev" in data
    assert len(data["flows"]) >= 1
    assert data["flows"][0]["type"] == "tab"


def test_get_flows_v1():
    """ Tests that GET /flows returns just the flows array for legacy v1 API.
    """
    response = client.get("/flows", headers={"Node-RED-API-Version": "v1"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["type"] == "tab"


def test_post_flows_deploy():
    """ Tests deploying updated flows via POST /flows.
    """
    deploy_payload = {
        "flows": [
            {
                "type": "tab",
                "id": "tab1",
                "label": "Test Tab",
                "disabled": False,
                "info": "",
                "env": []
            },
            {
                "id": "node1",
                "type": "inject",
                "z": "tab1",
                "name": "My Inject",
                "props": [{"p": "payload"}],
                "repeat": "",
                "crontab": "",
                "once": False,
                "wires": [["node2"]]
            },
            {
                "id": "node2",
                "type": "debug",
                "z": "tab1",
                "name": "My Debug",
                "active": True,
                "tosidebar": True,
                "complete": "payload",
                "wires": []
            }
        ]
    }

    response = client.post(
        "/flows",
        json=deploy_payload,
        headers={"Node-RED-Deployment-Type": "full", "Node-RED-API-Version": "v2"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "rev" in data
    assert len(data["rev"]) > 0

    # Verify that GET /flows now returns the newly deployed nodes
    get_res = client.get("/flows")
    assert get_res.status_code == 200
    flow_nodes = get_res.json()["flows"]
    node_ids = [n["id"] for n in flow_nodes]
    assert "tab1" in node_ids
    assert "node1" in node_ids
    assert "node2" in node_ids

    # Verify persistence to disk
    assert settings.flows_file.is_file()
    assert "My Inject" in settings.flows_file.read_text(encoding="utf-8")


def test_flows_state():
    """ Tests getting and setting runtime flow execution state.
    """
    res_get = client.get("/flows/state")
    assert res_get.status_code == 200
    assert "state" in res_get.json()

    res_stop = client.post("/flows/state", json={"state": "stop"})
    assert res_stop.status_code == 200
    assert res_stop.json()["state"] == "stop"

    res_start = client.post("/flows/state", json={"state": "start"})
    assert res_start.status_code == 200
    assert res_start.json()["state"] == "start"


def test_individual_flow_crud():
    """ Tests individual tab CRUD via /flow endpoints.
    """
    # 1. Create a new tab
    new_tab = {
        "type": "tab",
        "label": "Tab 2",
        "disabled": False,
        "info": "",
        "env": []
    }
    res_post = client.post("/flow", json=new_tab)
    assert res_post.status_code == 200
    tab_id = res_post.json()["id"]
    assert tab_id

    # 2. Get that tab
    res_get = client.get(f"/flow/{tab_id}")
    assert res_get.status_code == 200
    assert res_get.json()["label"] == "Tab 2"

    # 3. Update tab
    updated_tab = {
        "type": "tab",
        "label": "Renamed Tab 2",
        "disabled": False,
        "info": "",
        "env": []
    }
    res_put = client.put(f"/flow/{tab_id}", json=updated_tab)
    assert res_put.status_code == 200

    res_get_updated = client.get(f"/flow/{tab_id}")
    assert res_get_updated.json()["label"] == "Renamed Tab 2"

    # 4. Delete tab
    res_del = client.delete(f"/flow/{tab_id}")
    assert res_del.status_code == 204

    res_get_deleted = client.get(f"/flow/{tab_id}")
    assert res_get_deleted.status_code == 404

