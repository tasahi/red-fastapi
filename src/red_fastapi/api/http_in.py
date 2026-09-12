""" Dynamic HTTP Ingress Router for Red-Fastapi.

Manages user-defined HTTP endpoints created by 'http in' and 'http response' nodes.
Matches @node-red/nodes/core/network/21-httpin.js:
- Dispatches incoming requests directly to connected 'http in' nodes
- Correlates asynchronous responses via msg._res_id
- Returns JSON, string, binary, or custom status/headers
"""

import asyncio
import copy
import json
import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse


logger = logging.getLogger("red_fastapi.api.http_in")

router = APIRouter(tags=["http-in"])

# In-flight response futures: res_id -> asyncio.Future
_inflight_responses: Dict[str, asyncio.Future] = {}


def register_response_future(res_id: str, future: asyncio.Future) -> None:
    """ Registers an in-flight HTTP request waiting for an http response node.
    """
    _inflight_responses[res_id] = future


def complete_response(res_id: str, msg: Dict[str, Any]) -> bool:
    """ Resolves an in-flight HTTP request with the outgoing message data.
    """
    fut = _inflight_responses.pop(res_id, None)
    if fut and not fut.done():
        fut.set_result(msg)
        return True
    return False


@router.api_route("/http/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def handle_dynamic_http_request(path: str, request: Request):
    """ Catch-all dispatcher for dynamic HTTP In endpoints mounted at /http/* or root.
    """
    from red_fastapi.runtime.engine import engine

    url_path = f"/{path}".rstrip("/")
    method = request.method.lower()

    # Find matching active HTTPInNode
    target_node = None
    for node in engine.active_nodes.values():
        if node.type == "http in":
            node_url = str(node.config.get("url", "")).rstrip("/")
            if node_url and not node_url.startswith("/"):
                node_url = f"/{node_url}"
            node_method = str(node.config.get("method", "get")).lower()

            if node_url == url_path and node_method == method:
                target_node = node
                break

    if not target_node:
        return Response(status_code=404, content=f"Cannot {request.method} /http/{path}\n")

    # Read body
    req_body: Any = None
    raw_bytes = await request.body()
    if raw_bytes:
        try:
            req_body = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            try:
                req_body = raw_bytes.decode("utf-8")
            except Exception:
                req_body = raw_bytes

    # Parse query params
    req_query = dict(request.query_params)
    req_headers = dict(request.headers)

    res_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    response_future: asyncio.Future = loop.create_future()
    register_response_future(res_id, response_future)

    # Build msg envelope matching Node-RED
    msg: Dict[str, Any] = {
        "_msgid": str(uuid.uuid4()),
        "_res_id": res_id,
        "req": {
            "method": request.method,
            "url": str(request.url),
            "path": url_path,
            "headers": req_headers,
            "query": req_query,
            "params": {},
            "body": req_body,
        },
        "res": {
            "_res_id": res_id,
        },
        "payload": req_body if method in ("post", "put", "patch", "delete") else req_query,
    }

    # Dispatch to HTTPInNode
    await target_node.receive(msg)

    # Await response from HTTPResponseNode (timeout after 60s)
    try:
        completed_msg = await asyncio.wait_for(response_future, timeout=60.0)
    except asyncio.TimeoutError:
        _inflight_responses.pop(res_id, None)
        return Response(status_code=504, content="Gateway Timeout: http response node did not reply\n")

    # Construct HTTP response
    status_code = int(completed_msg.get("statusCode", 200))
    resp_headers = completed_msg.get("headers", {})
    payload = completed_msg.get("payload")

    if isinstance(payload, (dict, list)):
        return JSONResponse(content=payload, status_code=status_code, headers=resp_headers)
    elif isinstance(payload, bytes):
        return Response(content=payload, status_code=status_code, headers=resp_headers, media_type="application/octet-stream")
    elif payload is None:
        return Response(status_code=status_code, headers=resp_headers)
    else:
        return PlainTextResponse(content=str(payload), status_code=status_code, headers=resp_headers)

