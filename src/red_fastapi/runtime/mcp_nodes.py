"""MCP Node implementations for red-fastapi.

Registers:
- MCPInNode ('mcp in'): Receives incoming tool calls from MCP clients.
- MCPOutNode ('mcp out'): Resolves tool call with response data.
"""

import copy
import json
import logging
from typing import Any, Dict, Optional

from red_fastapi.mcp import registry as mcp_registry
from red_fastapi.runtime.node import Node

logger = logging.getLogger("red_fastapi.runtime.mcp_nodes")


class MCPInNode(Node):
    """Listens for incoming MCP tool invocations,
    matching MCP Tool registration and execution.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.tool_name: str = str(config.get("toolName") or config.get("name") or self.id)
        self.description: str = str(config.get("description", ""))
        raw_schema = config.get("schema")
        if isinstance(raw_schema, str):
            try:
                self.schema = json.loads(raw_schema)
            except Exception:
                self.schema = {}
        elif isinstance(raw_schema, dict):
            self.schema = raw_schema
        else:
            self.schema = {}

        # Register this node as an active tool
        mcp_registry.register_tool_node(self.tool_name, self)

    async def close(self) -> None:
        """Cleanup tool registration on flow undeploy."""
        mcp_registry.unregister_tool_node(self.tool_name)
        await super().close()

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """Forward tool call payload into downstream flow wires."""
        await self.send(msg)


class MCPOutNode(Node):
    """Completes an in-flight MCP tool invocation and returns content to client."""

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.is_error: bool = bool(config.get("isError", False))

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """Resolve the correlation future associated with this tool call."""
        correlation_id = msg.get("_mcp_id") or msg.get("_msgid")
        if not correlation_id:
            await self.warn("MCP Out node received message without _mcp_id or _msgid")
            return

        payload = msg.get("payload")
        is_err = msg.get("isError", self.is_error)
        mcp_registry.complete_mcp_future(str(correlation_id), payload, is_error=is_err)

