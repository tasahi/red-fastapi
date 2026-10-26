""" MCP (Model Context Protocol) Module for red-fastapi.\n
Exports:
- MCPServer: Server adapter implementing MCP 2024-11-05 spec.
- register_mcp_dispatcher_methods: Wires MCP methods into any JSONRPCDispatcher.
- types: Pydantic schemas for Tools, Resources, Prompts, Results.
- sse_router: FastAPI router for /mcp/sse and /mcp/messages.
"""

from red_fastapi.mcp.server import MCPServer, register_mcp_dispatcher_methods
from red_fastapi.mcp.sse import router as sse_router
from red_fastapi.mcp.types import (
    CallToolResult,
    Implementation,
    InitializeParams,
    InitializeResult,
    Prompt,
    ReadResourceResult,
    Resource,
    ResourceContent,
    ServerCapabilities,
    TextContent,
    Tool,
    ToolInputSchema,
)

__all__ = [
    "MCPServer",
    "register_mcp_dispatcher_methods",
    "sse_router",
    "Tool",
    "ToolInputSchema",
    "CallToolResult",
    "TextContent",
    "Resource",
    "ResourceContent",
    "ReadResourceResult",
    "Prompt",
    "InitializeResult",
    "InitializeParams",
    "ServerCapabilities",
    "Implementation",
]
