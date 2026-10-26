""" Server-Sent Events (SSE) Transport for MCP.\n
Implements the official MCP HTTP+SSE transport specification:
- GET /mcp/sse: Opens SSE stream, emits 'endpoint' event with session-specific POST URL.
- POST /mcp/messages?sessionId=...: Receives JSON-RPC messages and routes responses back through SSE stream or HTTP response.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from red_fastapi.mcp.server import MCPServer, register_mcp_dispatcher_methods
from red_fastapi.rpc.dispatcher import JSONRPCDispatcher

logger = logging.getLogger("red_fastapi.mcp.sse")

router = APIRouter(tags=["MCP"])

# Dedicated dispatcher and server instance for MCP
mcp_server = MCPServer()
mcp_dispatcher = JSONRPCDispatcher()
register_mcp_dispatcher_methods(mcp_dispatcher, mcp_server)

# Active SSE sessions: session_id -> asyncio.Queue
_active_sse_sessions: Dict[str, asyncio.Queue] = {}


@router.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request) -> StreamingResponse:
    """ Establishes an SSE stream for an MCP client (such as Claude Desktop or Cursor)."""
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _active_sse_sessions[session_id] = queue

    logger.info(f"MCP SSE connection opened: session={session_id}")

    async def event_generator():
        try:
            # Emit the standard MCP initial 'endpoint' event containing the POST message target URL
            # with query param sessionId
            endpoint_url = f"/mcp/messages?sessionId={session_id}"
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"

            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                try:
                    # Wait for message with short timeout to allow disconnect checking
                    msg = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                    queue.task_done()
                except asyncio.TimeoutError:
                    # Send keep-alive comment
                    yield ": ping\n\n"
        finally:
            _active_sse_sessions.pop(session_id, None)
            logger.info(f"MCP SSE connection closed: session={session_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/mcp/messages")
async def mcp_post_message(request: Request) -> Response:
    """ Processes incoming MCP JSON-RPC messages and queues result on the SSE session."""
    session_id = request.query_params.get("sessionId")
    body = await request.body()

    if not body:
        return Response(status_code=400, content="Missing request body")

    result = await mcp_dispatcher.dispatch(body)

    # If SSE session exists, send response through the SSE stream as well
    if session_id and session_id in _active_sse_sessions and result is not None:
        await _active_sse_sessions[session_id].put(result)
        return Response(status_code=202, content="Accepted")

    if result is None:
        return Response(status_code=204)

    return JSONResponse(content=result)
