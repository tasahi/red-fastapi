---
title: Implementation Plan - FastAPI-Red (Python Backend for Node-RED Frontend)
document_type: Implementation Plan & Architecture Specification
project: fastapi-red
target: Port Node-RED backend to Python (FastAPI) while preserving 100% of the stock frontend editor
status: Completed
phases:
  phase_1: Completed (Editor shell & static asset hosting)
  phase_2: Completed (Node registry & palette discovery)
  phase_3: Completed (Flow persistence & deployment workflow)
  phase_4: Completed (Real-time WebSocket /comms event bus)
  phase_5: Completed (Asyncio flow execution engine)
  phase_6: Completed (Core sequence & logic nodes)
  phase_7: Completed (Advanced sequence & flow control nodes)
  phase_8: Completed (Hierarchical context & cross-flow link routing)
  phase_9: Completed (Network ingress & egress - HTTP In/Response/Request)
  phase_10: Completed (MQTT & Sockets - TCP, UDP, WebSocket)
  phase_11: Completed (Subflows & custom composite modules)
  phase_12: Completed (Storage & Parsers - Filesystem, AWS S3/MinIO, JSON, CSV, YAML, XML, HTML)
  phase_13: Completed (Expression Evaluator - JSONata & Python expressions)
date: September 2026
---

# Implementation Plan: FastAPI-Red (Python Backend for Node-RED Frontend)

**Project Name:** `fastapi-red`  
**Goal:** Implement a 100% compatible Python backend (using FastAPI + asyncio) that hosts and drives the unmodified stock Node-RED frontend editor (`@node-red/editor-client`).

---

## 1. Architectural Overview & Component Boundaries

The project is structured into three clean layers:

```
                  ┌──────────────────────────────────────────────┐
                  │    Stock Node-RED Frontend (Unmodified)      │
                  │   HTML5 Canvas (D3.js), jQuery, SASS, Ace    │
                  └──────────────────────┬───────────────────────┘
                                         │ HTTP REST + WebSocket (/comms)
 ┌───────────────────────────────────────┴────────────────────────────────────────┐
 │                      FastAPI Application (Server Layer)                        │
 │  ├── Static Assets Server      : / (index), /vendor/*, /red/*, /icons/*        │
 │  ├── Settings & Locales API    : GET /settings, GET /locales/*                 │
 │  ├── Node Registry API         : GET /nodes, GET /nodes/messages (HTML)        │
 │  ├── Flow Management API       : GET /flows, POST /flows, POST /flow           │
 │  ├── Dynamic HTTP Ingress      : /http/* (catch-all listener router)           │
 │  └── WebSocket Event Bus       : /comms (real-time debug, status, deploys)     │
 └───────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Internal Python Async Bus
 ┌───────────────────────────────────────┴────────────────────────────────────────┐
 │                   FastAPI-Red Engine (Runtime Layer)                           │
 │  ├── Flow Graph Compiler       : Parses flows.json into Directed Acyclic Graph │
 │  ├── Message Routing Bus       : asyncio.create_task / wire dispatch           │
 │  ├── Node Base Class & Registry: Lifecycle hooks (init, on_input, send, close) │
 │  ├── Subflow Runtime Engine    : Namespaced child graphs, port pin routing     │
 │  ├── Context Store             : Node, Flow, Global state (in-memory / disk)   │
 │  ├── Cloud & Filesystem Storage: File writer/reader, AWS S3 / MinIO client     │
 │  ├── Expression Evaluators     : Native JSONata (jsonata-python) & Python eval │
 │  └── Core Node Library         : 34+ executable Python nodes                   │
 └────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure

```text
fastapi-red/
├── pyproject.toml              # Dependencies (fastapi, uvicorn, paho-mqtt, httpx, boto3, xmltodict, jsonata-python, etc.)
├── run.bat                     # Server runner helper script
├── static/                     # Upstream @node-red/editor-client build
│   ├── index.html              # Rendered HTML entrypoint with Monaco bootstrap
│   ├── red/                    # red.min.js, style.min.css, images
│   ├── vendor/                 # monaco, d3, jquery, font-awesome
│   ├── debug/view/             # Node external dependencies (debug-utils.js)
│   ├── icons/                  # SVG and PNG icons
│   └── locales/                # i18n JSON strings
├── nodes/                      # Node HTML templates and client registrations
│   └── core/
│       ├── common/             # inject, debug, complete, catch, status, link, comment
│       ├── function/           # function, switch, change, range, delay, trigger
│       ├── sequence/           # split, sort, batch
│       ├── network/            # http, mqtt, websocket, tcpin, udp
│       ├── storage/            # file, watch
│       └── parsers/            # json, csv, xml, yaml, html
├── src/fastapi_red/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entrypoint & lifespan
│   ├── config.py               # Settings and environmental config
│   ├── api/                    # REST API routers
│   │   ├── settings.py         # GET /settings, GET/POST /settings/user
│   │   ├── nodes.py            # GET /nodes, GET /nodes/messages, GET /icons
│   │   ├── flows.py            # GET/POST /flows, GET/POST /flows/state, /flow CRUD
│   │   ├── node_actions.py     # POST /inject/:id, POST /debug/:id/:action
│   │   ├── http_in.py          # Dynamic HTTP Ingress router (/http/*)
│   │   ├── locales.py          # GET /locales/*
│   │   ├── core.py             # GET /theme, GET /plugins
│   │   └── comms.py            # WebSocket /comms router
│   └── runtime/                # Engine & Message passing
│       ├── engine.py           # FlowEngine task compiler & wire message router
│       ├── node.py             # Base Node class
│       ├── subflow.py          # SubflowInstanceNode & composite module execution
│       ├── core_nodes.py       # Inject, Debug, Function (Python sandbox)
│       ├── logic_nodes.py      # Change, Switch, Range, Delay, Trigger, Comment
│       ├── sequence_nodes.py   # Split, Join, Sort, Catch, Status, Complete, Link
│       ├── network_nodes.py    # HTTP In, HTTP Response, HTTP Request
│       ├── socket_nodes.py     # MQTT In/Out/Broker, TCP In/Out, UDP In/Out, WS
│       ├── storage_nodes.py    # File, File In, S3 In/Out/Config (AWS S3 & MinIO)
│       ├── parser_nodes.py     # JSON, CSV, YAML, XML, HTML
│       ├── context.py          # Node, Flow, Global Context stores
│       ├── eval.py             # JSONata & Python expression evaluation, deep paths
│       ├── comms.py            # WebSocket connection manager & topic broadcast
│       ├── storage.py          # flows.json and credentials persistence
│       ├── flows_util.py       # parse_config and diff_configs
│       ├── flows.py            # Flow runtime lifecycle & tab management
│       ├── nodes.py            # Node catalog & module registry access
│       └── registry.py         # Node type discovery & HTML template concatenator
├── storage/
│   ├── flows.json              # Active flow deployment file
│   └── flows_cred.json         # Encrypted credentials store
├── tests/
│   ├── test_phase1.py          # Phase 1: Static assets & settings
│   ├── test_phase2.py          # Phase 2: Node registry & discovery
│   ├── test_phase3.py          # Phase 3: Flow persistence & deploy
│   ├── test_phase4.py          # Phase 4: WebSocket /comms event bus
│   ├── test_phase5.py          # Phase 5: Asyncio engine (Inject, Debug, Function)
│   ├── test_logic_nodes.py     # Phase 6: Core sequence & logic nodes
│   ├── test_sequence_nodes.py  # Phase 7: Advanced sequence & flow control nodes
│   ├── test_context_and_links.py # Phase 8: Hierarchical context & link routing
│   ├── test_network_nodes.py   # Phase 9: HTTP ingress & egress
│   ├── test_socket_nodes.py    # Phase 10: MQTT, TCP, UDP, WebSocket
│   ├── test_subflows.py        # Phase 11: Subflows & custom modules
│   ├── test_storage_and_parsers.py # Phase 12: Storage (Filesystem, S3/MinIO) & Parsers
│   └── test_expressions.py     # Phase 13: JSONata & Python expression evaluation
└── docs/
    ├── fast-api_basics.md      # OKF technical specification document
    ├── implementation_plan.md  # Unified 13-phase architectural roadmap
    ├── gap_analysis.md         # Comprehensive gap analysis & matrix
    ├── plan_core_and_sequence_nodes.md # Phase 6 & 7 detailed specifications
    └── subflow_plan.md         # Phase 11 detailed subflow specifications
```

---

## 3. Unified Phase-by-Phase Technical Implementation

### Phase 1: Environment Setup & Static Editor Asset Serving `[COMPLETED]`
- [x] Extracted and mounted `@node-red/editor-client` static assets (`/vendor`, `/red`, `/locales`).
- [x] Pre-rendered HTML entrypoint `static/index.html`.
- [x] Configured settings endpoints (`GET /settings`, `GET /settings/user`, `POST /settings/user`).
- [x] Implemented i18n locales router (`GET /locales/{namespace}`).
- [x] Handled theme endpoint (`GET /theme`) and source maps.
- [x] Validated with automated tests (`tests/test_phase1.py`).

### Phase 2: Node Registry & Discovery Contract `[COMPLETED]`
- [x] Built node registry subsystem (`fastapi_red.runtime.registry`) mirroring `@node-red/registry`.
- [x] Built runtime nodes layer (`fastapi_red.runtime.nodes`) mirroring `@node-red/runtime/lib/nodes/index.js`.
- [x] Built nodes API router (`fastapi_red.api.nodes`) mirroring `@node-red/editor-api/lib/admin/nodes.js`.
- [x] Supported HTTP `Accept` header content negotiation for `GET /nodes` (`application/json` vs `text/html`).
- [x] Served node i18n catalogs (`GET /nodes/messages`) and icons (`GET /icons`, `GET /icons/{module}/{icon}`).
- [x] Integrated Monaco code editor bootstrap and served external script dependencies (`debug-utils.js`).
- [x] Validated with automated tests (`tests/test_phase2.py`).

### Phase 3: Flow Persistence & Deployment Workflow `[COMPLETED]`
- [x] Implemented storage layer (`fastapi_red.runtime.storage`) writing to `storage/flows.json` with MD5 revision (`rev`) tracking.
- [x] Implemented flow parser and diffing utility (`fastapi_red.runtime.flows_util`).
- [x] Implemented runtime flow management (`fastapi_red.runtime.flows`).
- [x] Implemented flows API router (`fastapi_red.api.flows`): `GET/POST /flows`, `GET/POST /flows/state`, and workspace CRUD.
- [x] Validated with automated tests (`tests/test_phase3.py`).

### Phase 4: Real-time Event Bus (WebSocket `/comms`) `[COMPLETED]`
- [x] Connection lifecycle & client connection registry (`fastapi_red.runtime.comms`).
- [x] Topic-based pub/sub broadcast mechanism (`debug`, `status/{node-id}`, `runtime-state`, `runtime-deploy`).
- [x] Client subscription handling (`{"subscribe": "debug"}`).
- [x] Batched message array delivery over WebSocket matching Node-RED client expectations.
- [x] Validated with automated tests (`tests/test_phase4.py`).

### Phase 5: Asyncio Flow Execution Engine `[COMPLETED]`
- [x] Built flow graph compiler & wire router (`fastapi_red.runtime.engine`) mirroring `@node-red/runtime/lib/flows/Flow.js`.
- [x] Built abstract `Node` base class (`fastapi_red.runtime.node`) with `on_input`, `send`, `status`, `warn`, `error`.
- [x] Built core executable Python nodes (`fastapi_red.runtime.core_nodes`):
  - `InjectNode`: Manual trigger via `POST /inject/{id}` + interval timers.
  - `DebugNode`: Emits payloads to console and WebSocket `/comms` debug topic.
  - `FunctionNode`: Evaluates Python code blocks with `msg` in local scope.
- [x] Built node action routes (`fastapi_red.api.node_actions`): `POST /inject/{id}` and `POST /debug/{id}/{action}`.
- [x] Validated end-to-end execution (`Inject` -> `Function` -> `Debug` -> WebSocket `/comms`) with automated tests (`tests/test_phase5.py`).

### Phase 6: Core Sequence & Logic Nodes `[COMPLETED]`
- [x] Built property evaluation & deep path resolution utility (`fastapi_red.runtime.eval`).
- [x] Built executable Python sequence & logic nodes (`fastapi_red.runtime.logic_nodes`):
  - `ChangeNode`: Rules-based property transformation (`set`, `change`/replace, `delete`, `move`).
  - `SwitchNode`: Conditional multi-port routing with operators (`==`, `!=`, `<`, `<=`, `>`, `>=`, `between`, `contains`, `regex`, `true`, `false`, `null`, `empty`, `otherwise`).
  - `RangeNode`: Linear numeric scaling with `clamp`, `roll`, and `drop` actions.
  - `DelayNode`: Pauses and queue rate-limiting.
  - `TriggerNode`: Timed pulses, secondary payloads, and reset triggers.
  - `CommentNode`: Workspace canvas documentation node.
- [x] Registered node HTML templates in `nodes/core/` and loaded into registry (`fastapi_red.runtime.registry`).
- [x] Validated with automated tests (`tests/test_logic_nodes.py`).

### Phase 7: Advanced Sequence & Flow Control `[COMPLETED]`
- [x] Built advanced sequence & flow control nodes (`fastapi_red.runtime.sequence_nodes`):
  - `SplitNode`: Dissects arrays, strings, and objects into message sequences with `msg.parts` metadata (`id`, `index`, `count`).
  - `JoinNode`: Aggregates sequenced messages into arrays, joined strings, or merged objects.
  - `SortNode`: In-memory sorting for lists and sequences (ascending/descending, numeric or string).
  - `CatchNode`: Intercepts unhandled errors across flow or scoped nodes.
  - `StatusNode`: Listens to visual status events emitted by nodes.
  - `CompleteNode`: Triggers downstream flows upon upstream node completion.
- [x] Registered templates in `nodes/core/sequence/` and `nodes/core/common/`.
- [x] Hooked FlowEngine event dispatchers (`handle_error`, `handle_status`, `handle_complete`).
- [x] Validated with automated tests (`tests/test_sequence_nodes.py`).

### Phase 8: Hierarchical Context & Cross-Flow Link Routing `[COMPLETED]`
- [x] Built hierarchical context manager (`fastapi_red.runtime.context`): Node, Flow, and Global stores with thread-safe access.
- [x] Linked context to `eval.py`, `ChangeNode` (`pt` flow/global targets), and `FunctionNode` (`flow_ctx`, `global_ctx` injected into Python scopes).
- [x] Built Link nodes (`fastapi_red.runtime.sequence_nodes`):
  - `LinkInNode`: Receives cross-link messages.
  - `LinkOutNode`: Routes to linked nodes or executes returns for subflow callers.
  - `LinkCallNode`: Calls designated link targets and awaits asynchronous return message responses.
- [x] Registered template `nodes/core/common/60-link.html` in registry (`fastapi_red.runtime.registry`).
- [x] Validated with automated tests (`tests/test_context_and_links.py`).

### Phase 9: Network Ingress & Egress (HTTP) `[COMPLETED]`
- [x] Built dynamic HTTP ingress router (`fastapi_red.api.http_in`):
  - Mounts catch-all dynamic route handler `/http/{path:path}` in FastAPI app.
  - Bridges requests to active `HTTPInNode` instances and awaits `HTTPResponseNode` response completion via futures.
- [x] Built executable Python network nodes (`fastapi_red.runtime.network_nodes`):
  - `HTTPInNode`: Endpoint listener extracting `method`, `url`, `headers`, `query`, and `body`.
  - `HTTPResponseNode`: Responds to in-flight HTTP requests with JSON/text/binary content and custom HTTP status codes/headers.
  - `HTTPRequestNode`: Non-blocking outbound HTTP client using `httpx.AsyncClient`.
- [x] Registered HTML templates in `nodes/core/network/` (`21-httpin.html`, `21-httprequest.html`).
- [x] Validated with automated tests (`tests/test_network_nodes.py`).

### Phase 10: MQTT & Sockets (TCP, UDP, WebSocket) `[COMPLETED]`
- [x] Built executable Python socket & MQTT nodes (`fastapi_red.runtime.socket_nodes`):
  - `MQTTBrokerNode`: Connection manager managing client connections to external MQTT brokers via `paho-mqtt` with auto-reconnect and QoS/retain support.
  - `MQTTInNode`: Topic subscriber with wildcard support (`#`, `+`) and automatic payload decoding (`auto`, `utf-8`, `json`, `binary`).
  - `MQTTOutNode`: Publishes messages to designated MQTT broker topics.
  - `TCPInNode`: Asynchronous non-blocking TCP socket server listener (`asyncio.start_server`).
  - `TCPOutNode`: Outbound TCP client transmitter (`asyncio.open_connection`).
  - `UDPInNode`: Non-blocking UDP datagram listener (`asyncio.DatagramProtocol`).
  - `UDPOutNode`: Non-blocking UDP datagram sender (`loop.sock_sendto`).
  - `WebSocketInNode` & `WebSocketOutNode`: Flow-level custom WebSocket endpoints.
- [x] Registered HTML templates in `nodes/core/network/` (`10-mqtt.html`, `22-websocket.html`, `31-tcpin.html`, `32-udp.html`).
- [x] Validated with automated tests (`tests/test_socket_nodes.py`).

### Phase 11: Subflows & Custom Modules `[COMPLETED]`
- [x] Built subflow execution runtime and composite node (`fastapi_red.runtime.subflow`):
  - `SubflowInstanceNode`: Encapsulates cloned internal nodes with scoped IDs (`{instance_id}:{node_id}`).
  - Resolves multi-port input wiring (`subflow_def.in`) and routes directly to internal entry nodes.
  - Intercepts internal node outputs mapped in `subflow_def.out` and dispatches to outer flow downstream wires.
  - Supports nested subflows (subflow instances embedded inside other subflow definitions).
  - Implements hierarchical environment variables (`env`) merging template defaults and instance overrides, accessible in `eval.py` and `FunctionNode` via `env.get(...)`.
  - Propagates internal errors to `CatchNode` instances and status badges to outer subflow nodes.
  - Enables transparent internal node lookup via `engine.get_node`.
- [x] Validated with automated tests (`tests/test_subflows.py`).

### Phase 12: Storage & Parsers (Local Files, AWS S3 / MinIO & Parsers) `[COMPLETED]`
- [x] Built parser nodes (`fastapi_red.runtime.parser_nodes`):
  - `JSONNode`: Bidirectional JSON parser and stringifier with formatting (`pretty`) and forced modes (`str`/`obj`).
  - `CSVNode`: Converts CSV lines/text into objects or arrays of dicts, and formats dicts/arrays back to CSV with customizable delimiters and headers.
  - `YAMLNode`: Bidirectional YAML parser and serializer using `pyyaml`.
  - `XMLNode`: Bidirectional XML parser and builder using `xmltodict` with attribute and prefix support.
  - `HTMLNode`: Tag and text extractor with HTML stripping.
- [x] Built filesystem and Cloud Blob Storage nodes (`fastapi_red.runtime.storage_nodes`):
  - `FileNode`: Non-blocking async file writer with append, overwrite, and delete actions via `aiofiles`.
  - `FileInNode`: Non-blocking async file reader with `utf8`, `lines` (streaming line-by-line messages), or raw `buffer` modes.
  - `S3ConfigNode`: Centralized credential and endpoint configuration for AWS S3 and MinIO instances.
  - `S3InNode`: Downloads and fetches blob objects from AWS S3 or MinIO buckets into strings, JSON objects, or bytes.
  - `S3OutNode`: Uploads, creates, or deletes blob objects in AWS S3 or MinIO buckets.
- [x] Registered HTML templates in `nodes/core/storage/` and `nodes/core/parsers/`.
- [x] Validated with automated tests (`tests/test_storage_and_parsers.py`).

### Phase 13: Expression Evaluator (JSONata & Python Expressions) `[COMPLETED]`
- [x] Built JSONata & Python expression evaluation engine (`fastapi_red.runtime.eval`):
  - `evaluate_jsonata_expression`: Direct evaluation of standard Node-RED JSONata expressions against incoming messages and context hierarchies using `jsonata-python`.
  - Supports deep object path traversal, arithmetic expressions, string formatting, and array filtering.
  - Supports `val_type: "jsonata"` across property evaluation in `ChangeNode`, `SwitchNode`, etc.
  - Supports `val_type: "py"` for safe embedded Python expression execution.
  - Extended `SwitchNode` with `jsonata_exp` and `py` rule operators for dynamic condition matching.
- [x] Validated with automated tests (`tests/test_expressions.py`).

---

## 4. Summary Matrix of All 13 Phases

| Phase | Subsystem / Focus | Deliverables & Implemented Capabilities | Automated Tests |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Editor Shell & Static Assets | Mounted `@node-red/editor-client`, settings, user prefs, i18n locales, theme | 7 tests (`test_phase1.py`) |
| **Phase 2** | Node Registry & Discovery | Node set registration, HTML template discovery, icons, Monaco code editor | 8 tests (`test_phase2.py`) |
| **Phase 3** | Flow Persistence & Deploy | `storage/flows.json` with MD5 rev tracking, tab CRUD, deploy button pipeline | 5 tests (`test_phase3.py`) |
| **Phase 4** | Real-time WebSocket Bus | `/comms` WebSocket broadcast, subscriptions, status badges, debug streaming | 5 tests (`test_phase4.py`) |
| **Phase 5** | Asyncio Execution Engine | FlowEngine DAG compiler, `Node` base class, Inject, Debug, Function (Python) | 3 tests (`test_phase5.py`) |
| **Phase 6** | Core Sequence & Logic | Change (rules), Switch (multi-port), Range (scaling), Delay, Trigger, Comment | 8 tests (`test_logic_nodes.py`) |
| **Phase 7** | Advanced Sequence & Flow | Split, Join, Sort, Catch (error bus), Status (badges), Complete (completion) | 6 tests (`test_sequence_nodes.py`) |
| **Phase 8** | Context & Link Routing | Node/Flow/Global Context stores, Link In, Link Out, Link Call stack | 5 tests (`test_context_and_links.py`) |
| **Phase 9** | Network Ingress & Egress | Dynamic `/http/*` listener, HTTP In, HTTP Response, HTTP Request (httpx) | 3 tests (`test_network_nodes.py`) |
| **Phase 10** | MQTT & Socket Protocols | MQTT Broker/In/Out (paho-mqtt), TCP In/Out, UDP In/Out, WebSocket In/Out | 4 tests (`test_socket_nodes.py`) |
| **Phase 11** | Subflows & Modules | Subflow templates, instances, nested subflows, port remapping, scoped env | 5 tests (`test_subflows.py`) |
| **Phase 12** | Storage & Parsers | Filesystem (File, File In), AWS S3 / MinIO (In/Out/Config), JSON, CSV, YAML, XML, HTML | 5 tests (`test_storage_and_parsers.py`) |
| **Phase 13** | Expression Evaluator | JSONata expressions (`jsonata-python`), Python expressions, Switch & Change integration | 4 tests (`test_expressions.py`) |
| **Total** | **Full Application Runtime** | **Complete FastAPI-Red Backend (34+ Executable Nodes)** | **68/68 Passing Tests** |
