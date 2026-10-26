""" JSON-RPC 2.0 Pydantic Data Models.\n
Strictly adheres to JSON-RPC 2.0 specification and wire compatibility
with the Model Context Protocol (MCP) data envelope.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

JSONRPC_VERSION: Literal["2.0"] = "2.0"


class JSONRPCMessage(BaseModel):
    """ Base message containing JSON-RPC version."""
    model_config = ConfigDict(extra="ignore")
    jsonrpc: Literal["2.0"] = Field(default=JSONRPC_VERSION)


class JSONRPCRequest(JSONRPCMessage):
    """ JSON-RPC 2.0 Request Object."""
    id: Union[str, int]
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None


class JSONRPCNotification(JSONRPCMessage):
    """ JSON-RPC 2.0 Notification Object (Request without id)."""
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None


class JSONRPCErrorData(BaseModel):
    """ JSON-RPC 2.0 Error Object."""
    model_config = ConfigDict(extra="ignore")
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCResponse(JSONRPCMessage):
    """ JSON-RPC 2.0 Response Object."""
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCErrorData] = None

    def to_dict(self) -> Dict[str, Any]:
        """ Serialize to JSON-RPC 2.0 compliant dictionary.

        According to the JSON-RPC 2.0 specification:
        - 'id' MUST always be present in the response (can be null/None on parse or request errors).
        - exactly one of 'result' or 'error' MUST be present.
        """
        payload: Dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
        }
        if self.error is not None:
            err_dict: Dict[str, Any] = {
                "code": self.error.code,
                "message": self.error.message,
            }
            if self.error.data is not None:
                err_dict["data"] = self.error.data
            payload["error"] = err_dict
        else:
            payload["result"] = self.result
        return payload
