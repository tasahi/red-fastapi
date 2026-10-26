""" JSON-RPC 2.0 Module for red-fastapi.\n
Exports the core dispatcher, models, error classes, and protocol definitions.
"""

from red_fastapi.rpc.dispatcher import JSONRPCDispatcher
from red_fastapi.rpc.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    InternalError,
    InvalidParams,
    InvalidRequest,
    JSONRPCError,
    MethodNotFound,
    ParseError,
)
from red_fastapi.rpc.models import (
    JSONRPCErrorData,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from red_fastapi.rpc.protocols import BaseDispatcherProtocol
from red_fastapi.rpc.management import register_management_methods
from red_fastapi.rpc.streaming import register_streaming_methods
from red_fastapi.rpc.transports.websocket import (
    RPCWebSocketManager,
    RPCWebSocketSession,
    handle_rpc_websocket,
    rpc_ws_manager,
)

__all__ = [
    "JSONRPCDispatcher",
    "BaseDispatcherProtocol",
    "register_management_methods",
    "register_streaming_methods",
    "RPCWebSocketManager",
    "RPCWebSocketSession",
    "handle_rpc_websocket",
    "rpc_ws_manager",
    "JSONRPCMessage",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCNotification",
    "JSONRPCErrorData",
    "JSONRPCError",
    "ParseError",
    "InvalidRequest",
    "MethodNotFound",
    "InvalidParams",
    "InternalError",
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
]
