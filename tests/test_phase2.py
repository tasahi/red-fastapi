""" Automated unit & integration tests for Phase 2 endpoints:
- GET /nodes (application/json)
- GET /nodes (text/html)
- GET /nodes/messages
- GET /icons
- GET /icons/node-red/inject.svg
"""

import pytest
from fastapi.testclient import TestClient
from red_fastapi.main import app
from red_fastapi.runtime import nodes as runtime_nodes


# Initialize runtime nodes for tests
runtime_nodes.init()
client = TestClient(app)


def test_get_nodes_json():
    """ Tests that GET /nodes with Accept: application/json returns the list of registered node sets.
    """
    response = client.get("/nodes", headers={"Accept": "application/json"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3

    types = [t for n in data for t in n.get("types", [])]
    assert "inject" in types
    assert "debug" in types
    assert "function" in types


def test_get_nodes_html_configs():
    """ Tests that GET /nodes with Accept: text/html returns the concatenated HTML templates.
    """
    response = client.get("/nodes", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    text = response.text

    # Check red-module separator markers
    assert "<!-- --- [red-module:node-red/inject] --- -->" in text
    assert "<!-- --- [red-module:node-red/debug] --- -->" in text
    assert "<!-- --- [red-module:node-red/function] --- -->" in text

    # Check template definitions
    assert 'data-template-name="inject"' in text
    assert 'data-template-name="debug"' in text
    assert 'data-template-name="function"' in text

    # Check RED.nodes.registerType definitions
    assert "RED.nodes.registerType('inject'" in text or 'RED.nodes.registerType("inject"' in text
    assert "RED.nodes.registerType('debug'" in text or 'RED.nodes.registerType("debug"' in text
    assert "RED.nodes.registerType('function'" in text or 'RED.nodes.registerType("function"' in text


def test_get_node_messages():
    """ Tests that GET /nodes/messages returns the node message catalog.
    """
    response = client.get("/nodes/messages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_get_icons_list():
    """ Tests that GET /icons returns the map of icons for installed modules.
    """
    response = client.get("/icons")
    assert response.status_code == 200
    data = response.json()
    assert "node-red" in data
    assert "inject.svg" in data["node-red"]
    assert "debug.svg" in data["node-red"]
    assert "function.svg" in data["node-red"]


def test_get_icon_file():
    """ Tests serving an individual icon via GET /icons/{module}/{icon}.
    """
    response = client.get("/icons/node-red/inject.svg")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    assert len(response.content) > 50


def test_get_plugins_content_negotiation():
    """ Tests that GET /plugins returns JSON list when requested as JSON,
    and returns text/html when requested as HTML.
    """
    res_json = client.get("/plugins", headers={"Accept": "application/json"})
    assert res_json.status_code == 200
    assert isinstance(res_json.json(), list)

    res_html = client.get("/plugins", headers={"Accept": "text/html"})
    assert res_html.status_code == 200
    assert "text/html" in res_html.headers["content-type"]
    assert res_html.text == ""


def test_get_flows_initial_tab():
    """ Tests that GET /flows returns an initial tab so the editor canvas can initialize.
    """
    response = client.get("/flows", headers={"Accept": "application/json"})
    assert response.status_code == 200
    data = response.json()
    assert "flows" in data
    assert len(data["flows"]) >= 1
    assert data["flows"][0]["type"] == "tab"


def test_get_debug_utils_script():
    """ Tests that the debug node script dependency debug/view/debug-utils.js is served.
    """
    response = client.get("/debug/view/debug-utils.js")
    assert response.status_code == 200
    assert len(response.content) > 1000

