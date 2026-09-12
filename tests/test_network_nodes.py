""" Unit tests for Network Nodes (Batch 4: http in, http response, http request).

Tests:
- HTTPInNode & HTTPResponseNode: dynamic endpoint execution and synchronous client response
- Custom status code and header propagation in HTTPResponseNode
- HTTPRequestNode: outbound HTTP request dispatching using httpx
"""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi_red.main import app
from fastapi_red.runtime.engine import engine
from fastapi_red.runtime.network_nodes import HTTPInNode, HTTPResponseNode, HTTPRequestNode


@pytest.mark.asyncio
async def test_dynamic_http_in_and_response_pipeline():
    """ Tests an end-to-end HTTP In -> Change/Function -> HTTP Response flow.
    """
    flow_configs = [
        {
            "id": "http_in_1",
            "type": "http in",
            "url": "/hello",
            "method": "get",
            "wires": [["res_1"]]
        },
        {
            "id": "res_1",
            "type": "http response",
            "statusCode": 200,
            "headers": {"X-Custom-Header": "FastAPI-Red"},
            "wires": []
        }
    ]

    await engine.start(flow_configs)

    # Make request to the dynamic endpoint using ASGI test client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Matching GET /http/hello
        resp = await client.get("/http/hello?name=world")
        assert resp.status_code == 200
        assert resp.headers.get("x-custom-header") == "FastAPI-Red"
        assert resp.json() == {"name": "world"}

        # 2. Non-matching endpoint 404
        resp404 = await client.get("/http/nonexistent")
        assert resp404.status_code == 404

    await engine.stop()


@pytest.mark.asyncio
async def test_dynamic_http_post_with_json_body():
    """ Tests dynamic POST request with JSON payload processing.
    """
    flow_configs = [
        {
            "id": "http_post_1",
            "type": "http in",
            "url": "/submit",
            "method": "post",
            "wires": [["fn_transform"]]
        },
        {
            "id": "fn_transform",
            "type": "function",
            "func": "msg['payload']['received'] = True\nmsg['statusCode'] = 201\nreturn msg",
            "wires": [["http_res_2"]]
        },
        {
            "id": "http_res_2",
            "type": "http response",
            "wires": []
        }
    ]

    await engine.start(flow_configs)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/http/submit", json={"order_id": 999})
        assert resp.status_code == 201
        data = resp.json()
        assert data["order_id"] == 999
        assert data["received"] is True

    await engine.stop()


@pytest.mark.asyncio
async def test_http_request_node():
    """ Tests HTTPRequestNode making an outbound call to a local test route.
    """
    node = HTTPRequestNode({
        "id": "req_node",
        "type": "http request",
        "url": "http://test/settings",
        "method": "GET",
        "ret": "obj"
    })
    await node.start()

    transport = ASGITransport(app=app)
    # Inject ASGI client into node.client to test internally without network dependency
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        node.client = client

        flow_results = []

        class MockFlowInstance:
            async def route_message(self, source_id, port, msg):
                flow_results.append(msg)

        node.flow = MockFlowInstance()
        node.wires = [["dummy"]]



        # Dispatch input message
        await node.on_input({"url": "http://test/settings"})

        assert len(flow_results) == 1
        res = flow_results[0]
        assert res["statusCode"] == 200
        assert isinstance(res["payload"], dict)
        assert "httpNodeRoot" in res["payload"]

    await node.close()
