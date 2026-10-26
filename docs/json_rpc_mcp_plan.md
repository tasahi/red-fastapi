---
title: JSON-RPC & MCP Implementation Plan
document_type: Technical Architecture & Implementation Plan
project: red-fastapi
status: Proposed
phases:
  planned: 4 (Phases 14.1 through 14.4)
date: October 2026
---

# JSON-RPC 2.0 & MCP Adapter Implementation Plan

**Project:** `red-fastapi`  
**Document Type:** Technical Architecture & Implementation Plan  
**Status:** Proposed / Ready for Implementation  
**Target Module:** `red_fastapi.rpc` & `red_fastapi.mcp`  

---

## 1. Executive Summary & Design Goals

The objective of this plan is to introduce **JSON-RPC 2.0** capabilities to `red-fastapi` with a direct architectural evolution path toward hosting **MCP (Model Context Protocol)** servers and clients.

### Architectural Constraints & Strategy
1. **Option A Foundation (Pydantic v2 Custom Implementation)**:
   - Build using native FastAPI, Starlette, and Pydantic v2 (`>=2.10.0`) without immediate third-party RPC dependencies.
   - Zero vendor lock-in; lightweight and zero overhead.
2. **Interface Parity with Options B & C**:
   - **Option B Parity (Standard JSON-RPC Libraries like `jsonrpc-async` / `aiohttp-json-rpc`)**: Mirror standard method signatures, naming conventions, and dispatch interfaces (`Dispatcher`, `add_method`, `dispatch`, standard error hierarchies).
   - **Option C Parity (Official `mcp` SDK)**: Follow official MCP schema naming conventions (`tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`), session lifecycle management, and transport abstraction (HTTP POST, SSE, WebSocket, Stdio).
3. **Pluggable & Swappable Backend**:
   - Write standard adapter protocols (`Protocol` / ABC) so that migrating from our custom Option A implementation to official external packages (such as `mcp>=1.0.0` or specialized RPC dispatchers) requires zero changes to flow nodes or registered application handlers.

---

## 2. Architectural Blueprint

```
              ┌─────────────────────────────────────────────────────────┐
              │                    FastAPI App Router                   │
              │   POST /api/rpc  │  GET /mcp/sse  │  WS /api/rpc/ws     │
              └────────────────────────────┬────────────────────────────┘
                                           │
                            ┌──────────────▼──────────────┐
                            │   JSON-RPC Protocol Layer   │
                            │    (Pydantic v2 Models)     │
                            └──────────────┬──────────────┘
                                           │
                  ┌────────────────────────┴────────────────────────┐
                  ▼                                                 ▼
   ┌───────────────────────────────┐               ┌───────────────────────────────┐
   │    Generic RPC Dispatcher     │               │      MCP Server Protocol      │
   │  (Compatible with Option B)   │               │  (Compatible with Option C)   │
   │ • add_method(name, handler)   │               │ • list_tools() / call_tool()  │
   │ • dispatch(request)           │               │ • list_resources() / read()   │
   │ • batch execution support     │               │ • SSE session management      │
   └──────────────┬────────────────┘               └────────────────┬──────────────┘
                  │                                                 │
                  └────────────────────────┬────────────────────────┘
                                           │
                            ┌──────────────▼──────────────┐
                            │   red-fastapi Core Engine   │
                            │ • Flow Node Triggers        │
                            │ • Runtime Action Dispatcher │
                            │ • Flow-as-a-Tool Registry   │
                            └─────────────────────────────┘
```

---

## 3. Directory & File Structure

All RPC and MCP functionality is isolated within dedicated packages under `src/red_fastapi/`:

```
src/red_fastapi/
├── rpc/
│   ├── __init__.py                # Package exports (Dispatcher, Request, Response, etc.)
│   ├── models.py                  # Standard JSON-RPC 2.0 Pydantic models (compatible with MCP wire types)
│   ├── errors.py                  # Standard JSON-RPC & MCP error codes and exceptions
│   ├── protocols.py               # Abstract protocol definitions (BaseDispatcher, BaseTransport)
│   ├── dispatcher.py              # Option A core dispatcher (methods, notifications, batching)
│   └── transports/
│       ├── __init__.py
│       ├── http.py                # HTTP POST endpoint handler (/api/rpc)
│       └── websocket.py           # WebSocket bidirectional transport (/api/rpc/ws)
├── mcp/
│   ├── __init__.py                # MCP server adapter entrypoint
│   ├── types.py                   # MCP spec types (Tool, Resource, Prompt, CallToolResult)
│   ├── server.py                  # McpServer adapter (routes MCP methods to red-fastapi flows)
│   ├── sse.py                     # Server-Sent Events (SSE) transport handler (/mcp/sse, /mcp/messages)
│   └── registry.py               # Registry discovering flows/nodes annotated as MCP tools
└── api/
    ├── rpc.py                     # FastAPI router mounting /api/rpc endpoints
    └── mcp.py                     # FastAPI router mounting /mcp endpoints
```

---

## 4. Detailed Specification: Option B & C Compatibility

To ensure full drop-in compatibility when exchanging with `jsonrpc-async` or Anthropic's `mcp` SDK, class definitions, function signatures, and method names strictly adhere to standard contracts.

### 4.1. JSON-RPC Models (`src/red_fastapi/rpc/models.py`)

Adheres strictly to the JSON-RPC 2.0 Specification and Anthropic's MCP wire types:

```python
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

JSONRPC_VERSION: Literal["2.0"] = "2.0"

class JSONRPCMessage(BaseModel):
    jsonrpc: Literal["2.0"] = Field(default=JSONRPC_VERSION)

class JSONRPCRequest(JSONRPCMessage):
    id: Union[str, int]
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None

class JSONRPCNotification(JSONRPCMessage):
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None

class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None

class JSONRPCResponse(JSONRPCMessage):
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None
```

### 4.2. Option B Compatibility Contract: RPC Dispatcher (`src/red_fastapi/rpc/dispatcher.py`)

The dispatcher uses method names matching common Python JSON-RPC libraries (`add_method`, `dispatch`, `register`):

```python
from typing import Any, Callable, Coroutine, Dict, Optional, Union
from red_fastapi.rpc.models import (
    JSONRPCRequest, JSONRPCResponse, JSONRPCNotification, JSONRPCError
)
from red_fastapi.rpc.errors import MethodNotFound, InvalidParams, InternalError

class JSONRPCDispatcher:
    """Async JSON-RPC 2.0 Dispatcher.
    
    Provides 100% signature compatibility with jsonrpc-async and aiohttp-json-rpc,
    allowing frictionless drop-in replacement.
    """
    def __init__(self):
        self._methods: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

    def add_method(self, name_or_func: Union[str, Callable], func: Optional[Callable] = None) -> None:
        """Register an async RPC method. Can be used as a decorator or direct call."""
        if func is None and callable(name_or_func):
            method_name = name_or_func.__name__
            self._methods[method_name] = name_or_func
            return name_or_func
        self._methods[name_or_func] = func

    async def dispatch(
        self,
        payload: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """Process incoming JSON-RPC request, batch, or notification."""
        if isinstance(payload, list):
            # Batch execution
            results = [await self._handle_single(item) for item in payload]
            filtered = [r.model_dump(exclude_none=True) for r in results if r is not None]
            return filtered if filtered else None
        
        resp = await self._handle_single(payload)
        return resp.model_dump(exclude_none=True) if resp is not None else None
```

### 4.3. Option C Compatibility Contract: MCP Server Adapter (`src/red_fastapi/mcp/server.py`)

The MCP adapter implements the standard MCP protocol methods as defined by the official SDK:

| MCP Protocol Method | Implementation Target in `red-fastapi` | Functionality |
| :--- | :--- | :--- |
| `initialize` | `server.initialize(client_info, capabilities)` | Negotiate protocol version and server capabilities (`tools`, `resources`). |
| `notifications/initialized`| `server.on_initialized()` | Confirm handshake completion. |
| `tools/list` | `server.list_tools()` | Returns tools registered from Node-RED flows. |
| `tools/call` | `server.call_tool(name, arguments)` | Injects payload into target flow and returns result message. |
| `resources/list` | `server.list_resources()` | Lists exposed storage buckets or context variables as MCP resources. |
| `resources/read` | `server.read_resource(uri)` | Reads file or context data via red-fastapi storage/context subsystem. |
| `ping` | `server.ping()` | Keep-alive verification. |

Signature parity is preserved:
```python
class Server:
    """MCP Server Adapter matching the official `mcp.server.lowlevel.Server` interface."""
    def __init__(self, name: str = "red-fastapi-mcp"):
        self.name = name

    async def list_tools(self) -> List[Tool]:
        ...

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        ...
```

---

## 5. Flow-as-a-Tool: Integrating MCP with Node-RED Runtime

One of the most powerful features of `red-fastapi` is allowing flow authors to visually compose LLM tools.

### Mechanism
1. **Tool Annotation**:
   - A standard flow can be designated as an MCP Tool by placing an `mcp-in` node (or tagging an `http-in` node).
   - Configuration fields:
     - `name`: e.g. `query_database`
     - `description`: "Executes a parameterized query against company SQLite database"
     - `inputSchema`: JSON Schema matching tool parameters
2. **Execution Lifecycle**:
   - Incoming MCP `tools/call`:
     1. MCP adapter retrieves the designated tool node.
     2. An async `Future` or `asyncio.Event` is allocated with a unique correlation ID (`_msgid`).
     3. The payload `{"payload": arguments, "_msgid": correlation_id, "_mcp": True}` enters the flow engine via `runtime_flows.receive(node_id, msg)`.
     4. When the flow reaches an `mcp-out` node (or `http-response`), the correlated `Future` resolves.
     5. The MCP adapter packages the result into `CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])`.

---

## 6. Implementation Phases & Milestones

### Phase 14.1: Core JSON-RPC 2.0 Engine (Option A) — [COMPLETED]
- **Goal:** Implement clean, isolated JSON-RPC 2.0 dispatcher and models.
- **Deliverables:**
  - `src/red_fastapi/rpc/models.py`
  - `src/red_fastapi/rpc/errors.py`
  - `src/red_fastapi/rpc/dispatcher.py`
  - `src/red_fastapi/rpc/protocols.py`
  - `src/red_fastapi/rpc/transports/http.py`
  - `src/red_fastapi/api/rpc.py` (FastAPI router with `POST /api/rpc` and `POST /rpc`)
  - Integration into `src/red_fastapi/main.py`
  - Full test coverage in `tests/test_rpc.py` (16 unit and integration tests passing).

### Phase 14.2: Built-in Management RPC Methods — [COMPLETED]
- **Goal:** Expose red-fastapi system management over JSON-RPC.
- **Methods:**
  - `system.info`: Runtime version, active nodes, flow engine status, storage configuration.
  - `flows.status` / `flows.get` / `flows.start` / `flows.stop` / `flows.set`: Lifecycle control and programmatic flow deployment.
  - `nodes.list`: List active running nodes and registered node catalog.
  - `nodes.trigger`: Programmatically trigger inject nodes or send messages into node handlers.
- **Deliverables:**
  - `src/red_fastapi/rpc/management.py`
  - Integration with `default_dispatcher` in `src/red_fastapi/api/rpc.py`
  - Comprehensive unit and integration test suite in `tests/test_rpc_management.py` (all tests passing).

### Phase 14.3: WebSocket & Bidirectional Transport — [COMPLETED]
- **Goal:** Real-time push, streaming notifications, and subscriptions.
- **Deliverables:**
  - `src/red_fastapi/rpc/transports/websocket.py` mounted at `/api/rpc/ws` and `/rpc/ws`.
  - `RPCWebSocketSession` and `RPCWebSocketManager` handling bidirectional event queues and connection tracking.
  - `src/red_fastapi/rpc/streaming.py` exposing `stream.subscribe`, `stream.unsubscribe`, and `stream.broadcast`.
  - Integration with `red_fastapi.runtime.comms` for event bridge forwarding.
  - Comprehensive automated tests in `tests/test_rpc_websocket.py` (all tests passing).

### Phase 14.4: MCP Adapter & SSE Transport (Option C Parity)
- **Goal:** Connect AI Agents (Claude Desktop, Cursor, Antigravity) to `red-fastapi`.
- **Deliverables:**
  - `src/red_fastapi/mcp/` module implementing `initialize`, `tools/list`, `tools/call`.
  - Server-Sent Events (SSE) router at `/mcp/sse` and message intake at `POST /mcp/messages`.
  - MCP Node pair: `mcp-in` and `mcp-out` registered in `runtime_nodes`.
  - Validation test suite matching official Model Context Protocol compliance test cases.

---

## 7. Migration & Swapping Path (Options B & C)

When the time comes to swap custom components for external packages:
1. **Replacing the RPC Dispatcher with Option B (`jsonrpc-async`)**:
   - Because `JSONRPCDispatcher` implements `.add_method()` and `.dispatch()`, swapping consists of simply importing the external dispatcher in `src/red_fastapi/rpc/__init__.py` without touching `api/rpc.py` or runtime nodes.
2. **Upgrading to Official MCP SDK (`mcp` package)**:
   - Our `McpServer` class mirrors the official Anthropic SDK's `FastMCP` / `Server` signatures.
   - Simply change the underlying import in `src/red_fastapi/mcp/server.py` to `from mcp.server.fastmcp import FastMCP`, while retaining the flow bridge logic.

---

## 8. Verification & Acceptance Criteria

1. **Protocol Compliance**:
   - Adheres 100% to JSON-RPC 2.0 specifications (Error code range `-32700` to `-32600`).
   - Adheres to MCP 2024-11-05 specification (`initialize`, `tools/list`, `tools/call`).
2. **Zero Regressions**:
   - Stock `@node-red/editor-client` UI continues functioning without any alterations.
   - All 69 existing automated tests in `tests/` continue to pass.
3. **Automated Test Coverage**:
   - New tests added to `tests/test_rpc.py` and `tests/test_mcp.py` achieving >90% code coverage on the new modules.

