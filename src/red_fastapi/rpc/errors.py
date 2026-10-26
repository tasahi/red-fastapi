""" JSON-RPC 2.0 Error Definitions and Standard Exceptions.\n
Follows JSON-RPC 2.0 specification specifications and MCP standard error codes.
"""

from typing import Any, Optional


# Standard JSON-RPC 2.0 Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Server error range (-32000 to -32099)
SERVER_ERROR_START = -32099
SERVER_ERROR_END = -32000

# Common MCP Error Extension Codes
RESOURCE_NOT_FOUND = -32002
TOOL_EXECUTION_ERROR = -32000


class JSONRPCError(Exception):
    """ Base exception for all JSON-RPC errors."""

    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self.data
        return result


class ParseError(JSONRPCError):
    def __init__(self, data: Optional[Any] = None):
        super().__init__(PARSE_ERROR, "Parse error", data)


class InvalidRequest(JSONRPCError):
    def __init__(self, data: Optional[Any] = None, message: str = "Invalid Request"):
        super().__init__(INVALID_REQUEST, message, data)


class MethodNotFound(JSONRPCError):
    def __init__(self, method: str = ""):
        super().__init__(
            METHOD_NOT_FOUND,
            f"Method not found: '{method}'" if method else "Method not found",
            {"method": method} if method else None,
        )


class InvalidParams(JSONRPCError):
    def __init__(self, data: Optional[Any] = None, message: str = "Invalid params"):
        super().__init__(INVALID_PARAMS, message, data)


class InternalError(JSONRPCError):
    def __init__(self, data: Optional[Any] = None, message: str = "Internal error"):
        super().__init__(INTERNAL_ERROR, message, data)
