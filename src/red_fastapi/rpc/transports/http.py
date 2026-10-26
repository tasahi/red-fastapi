""" JSON-RPC Transport Handlers."""

from typing import Any, Dict, List, Optional, Union
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from red_fastapi.rpc.dispatcher import JSONRPCDispatcher


async def handle_http_rpc(
        request: Request,
        dispatcher: JSONRPCDispatcher,
    ) -> Response:
    """ Handle incoming JSON-RPC 2.0 requests over HTTP POST."""
    body = await request.body()
    result = await dispatcher.dispatch(body)

    if result is None:
        # All requests were notifications
        return Response(status_code=204)

    return JSONResponse(content=result)
