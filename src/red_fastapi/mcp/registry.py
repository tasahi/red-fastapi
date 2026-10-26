""" MCP Nodes Registry and In-Flight Message Correlation.\n
Connects MCP tool calls to active 'mcp in' and 'mcp out' nodes in flows.
"""

import asyncio
import logging
from typing import Any, Dict, Optional
from red_fastapi.mcp.types import Tool, ToolInputSchema

logger = logging.getLogger("red_fastapi.mcp.registry")

# In-flight tool calls: correlation_id -> asyncio.Future
_inflight_tool_calls: Dict[str, asyncio.Future] = {}

# Active MCP input nodes: tool_name -> MCPInNode instance
_active_mcp_tools: Dict[str, Any] = {}


def register_tool_node(name: str, node: Any) -> None:
    """ Register an active 'mcp in' node as an available tool."""
    _active_mcp_tools[name] = node
    logger.info(f"Registered MCP tool: {name} (node_id: {getattr(node, 'id', 'unknown')})")


def unregister_tool_node(name: str) -> None:
    """ Unregister an MCP tool."""
    _active_mcp_tools.pop(name, None)


def get_tool_node(name: str) -> Optional[Any]:
    """ Retrieve an active MCP tool node by name."""
    return _active_mcp_tools.get(name)


def list_registered_tools() -> list[Tool]:
    """ List all registered MCP tools derived from active flow nodes."""
    tools: list[Tool] = []
    for name, node in _active_mcp_tools.items():
        desc = getattr(node, "description", "") or getattr(node, "name", "") or f"Node-RED flow tool: {name}"
        schema_dict = getattr(node, "schema", {}) or {}
        input_schema = ToolInputSchema(
            type="object",
            properties=schema_dict.get("properties", {}),
            required=schema_dict.get("required", [])
        )
        tools.append(Tool(name=name, description=desc, inputSchema=input_schema))
    return tools


def register_mcp_future(correlation_id: str, future: asyncio.Future) -> None:
    """ Register a pending future waiting for an 'mcp out' node response."""
    _inflight_tool_calls[correlation_id] = future


def complete_mcp_future(correlation_id: str, result: Any, is_error: bool = False) -> bool:
    """ Resolve an in-flight tool future with output from 'mcp out' node."""
    fut = _inflight_tool_calls.pop(correlation_id, None)
    if fut and not fut.done():
        fut.set_result({"result": result, "is_error": is_error})
        return True
    return False
