""" FastAPI Router for JSON-RPC 2.0 Endpoint.\n
Provides standard HTTP POST endpoint at `/api/rpc` (and optional alias `/rpc`).
"""

from fastapi import APIRouter, Request, Response
from red_fastapi.rpc.dispatcher import JSONRPCDispatcher
from red_fastapi.rpc.management import register_management_methods
from red_fastapi.rpc.transports.http import handle_http_rpc

router = APIRouter(tags=["JSON-RPC"])

# Shared global dispatcher for red-fastapi
default_dispatcher = JSONRPCDispatcher()


# Register initial basic system methods
@default_dispatcher.add_method("rpc.ping")
async def ping() -> str:
    """ Basic health check and connectivity test."""
    return "pong"


@default_dispatcher.add_method("rpc.listMethods")
async def list_methods() -> list[str]:
    """ Return all registered RPC methods."""
    return default_dispatcher.list_methods()


# Register Phase 14.2 management methods (system.*, flows.*, nodes.*)
register_management_methods(default_dispatcher)


@router.post("/api/rpc")
@router.post("/rpc")
async def json_rpc_endpoint(request: Request) -> Response:
    """ Main JSON-RPC 2.0 HTTP POST endpoint.\n
    Handles single requests, batch requests, and notifications.
    """
    return await handle_http_rpc(request, default_dispatcher)
