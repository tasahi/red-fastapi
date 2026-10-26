""" MCP Server Adapter for red-fastapi.\n
Implements the official Model Context Protocol 2024-11-05 methods:
- initialize: Protocol version negotiation and capabilities exchange.
- notifications/initialized: Handshake confirmation.
- ping: Liveness check.
- tools/list: Discover available tools exposed by flows ('mcp in' nodes).
- tools/call: Invoke a flow-based tool and wait for 'mcp out' response.
- resources/list: Expose red-fastapi context/storage resources.
- resources/read: Read resource contents.

Option C interface compatible with official `mcp.server.Server`.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from red_fastapi.config import settings
from red_fastapi.mcp import registry as mcp_registry
from red_fastapi.mcp.types import (
    CallToolResult,
    Implementation,
    InitializeResult,
    ReadResourceResult,
    Resource,
    ResourceContent,
    ServerCapabilities,
    TextContent,
    Tool,
)
from red_fastapi.rpc.dispatcher import JSONRPCDispatcher
from red_fastapi.rpc.errors import INVALID_PARAMS, METHOD_NOT_FOUND, InvalidParams, JSONRPCError

logger = logging.getLogger("red_fastapi.mcp.server")


class MCPServer:
    """ Model Context Protocol (MCP) Server Adapter.\n
    Compatible with Anthropic MCP Python SDK Server interface.
    """

    def __init__(self, name: str = "red-fastapi-mcp", version: str = "0.1.0"):
        self.name = name
        self.version = version
        self.protocol_version = "2024-11-05"
        self._initialized = False

    async def initialize(self, **kwargs) -> Dict[str, Any]:
        """ Handle 'initialize' protocol handshake."""
        self._initialized = True
        result = InitializeResult(
            protocolVersion=self.protocol_version,
            capabilities=ServerCapabilities(
                tools={"listChanged": True},
                resources={"subscribe": False, "listChanged": False},
                prompts={"listChanged": False},
            ),
            serverInfo=Implementation(name=self.name, version=self.version),
        )
        return result.model_dump(exclude_none=True)

    async def on_initialized(self, **kwargs) -> None:
        """ Handle 'notifications/initialized' notification."""
        logger.info("MCP client confirmed initialization handshake.")

    async def ping(self, **kwargs) -> Dict[str, Any]:
        """ Keep-alive ping."""
        return {}

    async def list_tools(self, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """ Returns tools exposed by active Node-RED flows."""
        tools = mcp_registry.list_registered_tools()
        return {"tools": [t.model_dump(exclude_none=True) for t in tools]}

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Dict[str, Any]:
        """ Executes a tool call by routing it into the corresponding flow."""
        tool_node = mcp_registry.get_tool_node(name)
        if tool_node is None:
            raise JSONRPCError(code=-32001, message=f"Tool '{name}' not found", data={"name": name})

        correlation_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        mcp_registry.register_mcp_future(correlation_id, future)

        # Build message packet for Node-RED flow
        msg = {
            "payload": arguments if arguments is not None else {},
            "_mcp_id": correlation_id,
            "_msgid": correlation_id,
            "tool": name,
        }

        try:
            # Inject message into target 'mcp in' node
            await tool_node.receive(msg)
            # Await completion by 'mcp out'
            res = await asyncio.wait_for(future, timeout=timeout)
            raw_result = res.get("result")
            is_err = res.get("is_error", False)

            text_output = raw_result if isinstance(raw_result, str) else json.dumps(raw_result)
            return CallToolResult(
                content=[TextContent(type="text", text=text_output)],
                isError=is_err,
            ).model_dump(exclude_none=True)

        except asyncio.TimeoutError:
            mcp_registry.complete_mcp_future(correlation_id, None)
            return CallToolResult(
                content=[TextContent(type="text", text=f"Tool '{name}' timed out after {timeout} seconds")],
                isError=True,
            ).model_dump(exclude_none=True)
        except Exception as err:
            logger.exception(f"Error invoking tool {name}: {err}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Execution error in tool '{name}': {str(err)}")],
                isError=True,
            ).model_dump(exclude_none=True)

    async def list_resources(self, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """ List exposed red-fastapi resources."""
        res_list = [
            Resource(
                uri="red://system/flows",
                name="Current Flows",
                description="Export of current Node-RED flow configuration",
                mimeType="application/json",
            )
        ]
        return {"resources": [r.model_dump(exclude_none=True) for r in res_list]}

    async def read_resource(self, uri: str, **kwargs) -> Dict[str, Any]:
        """ Read a specified resource by URI."""
        if uri == "red://system/flows":
            from red_fastapi.runtime import flows as runtime_flows
            flows_data = runtime_flows.get_flows()
            return ReadResourceResult(
                contents=[
                    ResourceContent(
                        uri=uri,
                        mimeType="application/json",
                        text=json.dumps(flows_data),
                    )
                ]
            ).model_dump(exclude_none=True)

        raise JSONRPCError(code=-32002, message=f"Resource not found: '{uri}'", data={"uri": uri})


def register_mcp_dispatcher_methods(dispatcher: JSONRPCDispatcher, server: Optional[MCPServer] = None) -> MCPServer:
    """ Wire MCP methods to a JSONRPCDispatcher for unified JSON-RPC / MCP transport."""
    if server is None:
        server = MCPServer()

    dispatcher.add_method("initialize", server.initialize)
    dispatcher.add_method("notifications/initialized", server.on_initialized)
    dispatcher.add_method("ping", server.ping)
    dispatcher.add_method("tools/list", server.list_tools)
    dispatcher.add_method("tools/call", server.call_tool)
    dispatcher.add_method("resources/list", server.list_resources)
    dispatcher.add_method("resources/read", server.read_resource)

    return server
