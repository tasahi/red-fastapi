""" Automated unit & integration test for Phase 1 endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from fastapi_red.main import app


client = TestClient(app)


def test_editor_index_html():
    """ Tests serving the root editor shell.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "red-ui-editor" in response.text
    assert "vendor/vendor.js" in response.text


def test_get_settings():
    """ Tests the runtime settings endpoint.
    """
    response = client.get("/settings")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "httpNodeRoot" in data
    assert "editorTheme" in data


def test_user_settings_get_and_post():
    """ Tests getting and updating user settings.
    """
    # GET
    res_get = client.get("/settings/user")
    assert res_get.status_code == 200
    assert "view" in res_get.json()

    # POST (save user settings)
    res_post = client.post("/settings/user", json={"view": {"view-show-grid": False}})
    assert res_post.status_code == 200
    assert res_post.json() == {"status": "ok"}


def test_theme_endpoint():
    """ Tests custom theme endpoint.
    """
    response = client.get("/theme")
    assert response.status_code == 200


def test_get_locales():
    """ Tests localization JSON catalog fetching.
    """
    response = client.get("/locales/editor.json?lng=en-US")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert len(data) > 0


def test_get_flows_and_nodes():
    """ Tests initial flows list and node JSON list.
    """
    res_flows = client.get("/flows")
    assert res_flows.status_code == 200
    assert "flows" in res_flows.json()

    res_nodes = client.get("/nodes", headers={"Accept": "application/json"})
    assert res_nodes.status_code == 200
    assert isinstance(res_nodes.json(), list)


def test_static_vendor_assets():
    """ Tests that core vendor assets and source maps are accessible.
    """
    res_js = client.get("/vendor/vendor.js")
    assert res_js.status_code == 200
    assert len(res_js.content) > 1000

    res_css = client.get("/red/style.min.css")
    assert res_css.status_code == 200
    assert len(res_css.content) > 1000

    res_map = client.get("/vendor/purify.min.js.map")
    assert res_map.status_code == 200
