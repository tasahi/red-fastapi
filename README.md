# Project Overview: red-fastapi

`red-fastapi` is a lightweight, high-performance Python (FastAPI) implementation of the Node-RED backend, designed to host and drive the official, unmodified Node-RED frontend editor (`@node-red/editor-client`).

---

## Getting Started

### 1. Environment Activation
Using your Anaconda environment `fapi`:

```powershell
C:\Programs\Python3\Scripts\activate fapi
```

### 2. Compile the Frontend with Vite (Modular Compilation)

Before starting the server (or after modifying node UI templates), compile the editor shell, stylesheets, and modular node chunks:

```bash
# 1. Install frontend build dependencies (first time only)
npm install

# 2. Build editor bundle and modular node chunks to dist/
npm run build
```

> **What `npm run build` does:**
> - Compiles and minifies the editor shell HTML and CSS into `dist/`.
> - Pre-compiles each node template into an isolated, modular chunk in `dist/nodes/core/` (minifying `<script type="text/html">` forms and tree-shaking `<script type="text/javascript">` blocks via ESBuild).
> - Copies standalone runtime resources (`locales`, `icons`, `vendor`, `debug`) into `dist/`.
> - When `dist/` is present, FastAPI automatically serves from `dist/` and loads pre-compiled modular node chunks.

#### Automated Upstream Updates (Node-RED Releases)

To pull the latest official Node-RED editor UI and core node templates from upstream npm packages (`@node-red/editor-client` and `@node-red/nodes`), run:

```cmd
npm run update:upstream
```

This single command:
1. Installs the latest `@node-red/editor-client` and `@node-red/nodes` from npm.
2. Runs `scripts/sync-upstream.js` to synchronize the compiled web assets into `static/` and node templates into `nodes/core/`.
3. Runs `npm run build` to re-bundle and minify everything into `dist/`.

### 3. Run the Backend Server

Once built (or directly in dev mode using fallback to `static/`):

Using the runner script:
```cmd
.\run.bat
```

Or directly with python/uvicorn:
```cmd
python -m uvicorn red_fastapi.main:app --host 127.0.0.1 --port 8080 --reload
```

Navigate to:  
**`http://127.0.0.1:8080/`**

### 4. Run with Docker

Build and run using Docker Compose:
```bash
docker compose up -d --build
```

Or using Docker directly:
```bash
docker build -t red-fastapi .
docker run -d -p 8080:8080 -v ${PWD}/storage:/app/storage --name red-fastapi red-fastapi
```

The editor will be accessible at **`http://localhost:8080/`** with persistent flow storage in `./storage`.

### 5. Production Architecture: Serving Static Files with Apache at the Entrance

In production environments, an **Apache HTTP Server (`httpd`)** can sit at the entrance to serve the compiled static assets (`dist/`) directly at wire speed, while reverse-proxying API calls and WebSockets to the `red-fastapi` container.

#### Request Routing Flow:
```
Client Browser
     │
     ▼ (Port 80 / 443)
┌────────────────────────────────────────────────────────┐
│ Apache HTTP Server (Gateway / Ingress)                 │
│                                                        │
│  • Static assets (/assets/*, /vendor/*, /locales/*)    │──> Delivered directly from dist/ volume
│  • Dynamic APIs (/nodes, /flows, /settings, etc.)      │──> ProxyPass to http://red-fastapi:8080
│  • Real-time WebSocket event bus (/comms)              │──> ProxyPass to ws://red-fastapi:8080/comms
└────────────────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────────────────┐
│ Red-Fastapi Backend (Execution Engine)                 │
│  • Asyncio flow engine & node executors                │
│  • Node registry & dynamic catalog resolution          │
│  • WebSocket /comms event streaming                    │
└────────────────────────────────────────────────────────┘
```

#### Apache VirtualHost Configuration Example:
```apache
<VirtualHost *:80>
    ServerName localhost
    DocumentRoot "/var/www/html/dist"

    <Directory "/var/www/html/dist">
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    # 1. Reverse-Proxy WebSocket comms (Node-RED real-time event bus)
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} =websocket [NC]
    RewriteRule ^/comms(.*) ws://red-fastapi:8080/comms$1 [P,L]

    # 2. Reverse-Proxy Dynamic FastAPI Endpoints
    ProxyPreserveHost On
    ProxyPass /nodes http://red-fastapi:8080/nodes
    ProxyPassReverse /nodes http://red-fastapi:8080/nodes

    ProxyPass /flows http://red-fastapi:8080/flows
    ProxyPassReverse /flows http://red-fastapi:8080/flows

    ProxyPass /settings http://red-fastapi:8080/settings
    ProxyPassReverse /settings http://red-fastapi:8080/settings

    ProxyPass /locales http://red-fastapi:8080/locales
    ProxyPassReverse /locales http://red-fastapi:8080/locales

    # 3. Static Files (HTML, JS, CSS, vendor, icons, fonts)
    DirectoryIndex index.html
</VirtualHost>
```

---

## Running the Automated Tests

All tests can be executed via `pytest`:

```cmd
C:\Programs\Python3\Scripts\activate fapi
pytest tests/
```

Currently, **69 automated unit and integration tests** are active across core runtime phases, sequence/logic nodes, flow control nodes, context hierarchy, link routing, dynamic HTTP ingress/egress, socket/MQTT network nodes, composite subflow modules, local file storage, AWS S3 / MinIO blob storage, and the JSONata & Python expression evaluator engine.

---

## Storage Backend Configuration (Local, AWS S3, MinIO)

`red-fastapi` features a pluggable project flow storage engine. By default, it saves flows and credentials to the local disk. You can switch to AWS S3 or MinIO by configuring environment variables or a `.env` file:

### 1. Local Filesystem (Default)
```bash
STORAGE_TYPE=local
USER_DIR=storage           # Defaults to <root>/storage
FLOWS_FILE=storage/flows.json
CREDENTIALS_FILE=storage/flows_cred.json
```

### 2. AWS S3 Storage
```bash
STORAGE_TYPE=s3
S3_BUCKET=my-company-flows
S3_REGION_NAME=us-east-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
S3_FLOWS_KEY=production/flows.json
S3_CREDENTIALS_KEY=production/flows_cred.json
```

### 3. MinIO Object Storage
```bash
STORAGE_TYPE=s3
S3_BUCKET=node-red-flows
S3_ENDPOINT_URL=http://127.0.0.1:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_FLOWS_KEY=flows.json
S3_CREDENTIALS_KEY=flows_cred.json
```

---

## Architecture & Code Conventions

The backend is organized cleanly into modular layers aligned with upstream `@node-red` packages:

- **`src/red_fastapi/api/`**: REST and WebSocket routers matching `@node-red/editor-api` (`settings.py`, `nodes.py`, `flows.py`, `comms.py`, `node_actions.py`, `http_in.py`, `locales.py`, `core.py`).
- **`src/red_fastapi/runtime/`**: Runtime engine matching `@node-red/runtime` (`engine.py`, `subflow.py`, `node.py`, `storage_nodes.py`, `parser_nodes.py`, `core_nodes.py`, `logic_nodes.py`, `sequence_nodes.py`, `network_nodes.py`, `socket_nodes.py`, `context.py`, `eval.py`, `comms.py`, `storage.py`, `flows.py`, `flows_util.py`, `nodes.py`, `registry.py`).
- **`nodes/core/`**: Node HTML templates and client registration scripts extracted from `@node-red/nodes`.
- **`storage/`**: Stores active user flows (`storage/flows.json`) and credentials (`storage/flows_cred.json`).

### Code Style Rules
- Exactly **2 blank lines** between top-level function definitions and classes.
- A single space after the opening triple quotes (`""" `) in all docstrings.
- Developer comments on main functions.
- Module and function naming mapped closely to upstream Node-RED.

---

## Phase & Node Status

```
[x] Phase 1: Editor Shell & Static Asset Hosting
[x] Phase 2: Node Registry & Palette Discovery
[x] Phase 3: Flow Persistence & Deployment Workflow
[x] Phase 4: Real-time Event Bus (WebSocket /comms)
[x] Phase 5: Asyncio Flow Execution Engine (Inject, Debug, Python Function)
[x] Phase 6: Core Sequence & Logic Nodes (Change, Switch, Range, Delay, Trigger, Comment)
[x] Phase 7: Advanced Sequence & Flow Control (Split, Join, Sort, Catch, Status, Complete)
[x] Phase 8: Hierarchical Context & Link Cross-Flow Routing (Global/Flow/Node Context, Link In/Out/Call)
[x] Phase 9: Network Ingress & Egress (HTTP In, HTTP Response, HTTP Request)
[x] Phase 10: MQTT & Sockets (MQTT Broker/In/Out, TCP In/Out, UDP In/Out, WebSocket In/Out)
[x] Phase 11: Subflows & Custom Modules (Subflow Template, Instances, Port Mapping, Scoped Env, Nested Subflows)
[x] Phase 12: Storage & Parsers (File, File In, S3/MinIO Blob In/Out/Config, JSON, CSV, YAML, XML, HTML)
[x] Phase 13: Expression Evaluator (JSONata Expressions, Python Expressions, Change/Switch Integration)
```

### Phase 1: Editor Shell & Static Hosting
- [x] Extracted and mounted `@node-red/editor-client` static assets (`/vendor`, `/red`, `/locales`).
- [x] Pre-rendered HTML entrypoint `static/index.html`.
- [x] Configured settings endpoints (`GET /settings`, `GET /settings/user`, `POST /settings/user`).
- [x] Implemented i18n locales router (`GET /locales/{namespace}`).
- [x] Handled theme and vendor sourcemaps (`GET /theme`, `purify.min.js.map`).
- [x] Validated with automated tests (`tests/test_phase1.py`).

### Phase 2: Node Registry & Discovery
- [x] Built registry system (`red_fastapi.runtime.registry`) mirroring `@node-red/registry/lib/registry.js`.
- [x] Built runtime nodes layer (`red_fastapi.runtime.nodes`) mirroring `@node-red/runtime/lib/nodes/index.js`.
- [x] Built nodes API router (`red_fastapi.api.nodes`) mirroring `@node-red/editor-api/lib/admin/nodes.js`:
  - `GET /nodes` (JSON list or concatenated HTML templates depending on `Accept`).
  - `GET /nodes/messages` and `GET /nodes/{module}/{set}/messages`.
  - `GET /icons` and `GET /icons/{module}/{icon}`.
- [x] Integrated core nodes (`inject`, `debug`, `function`) with HTML templates and icons from `C:\Documents\Programming\node-red`.
- [x] Integrated Monaco code editor bootstrap and served external script dependencies (`debug-utils.js`).
- [x] Validated with automated tests (`tests/test_phase2.py`).

### Phase 3: Flow Persistence & Deployment Workflow
- [x] Built storage subsystem (`red_fastapi.runtime.storage`) writing to `storage/flows.json` with revision (`rev`) tracking.
- [x] Built flow parser and diffing utility (`red_fastapi.runtime.flows_util`) mirroring `@node-red/runtime/lib/flows/util.js`.
- [x] Built runtime flow manager (`red_fastapi.runtime.flows`) mirroring `@node-red/runtime/lib/flows/index.js`.
- [x] Built flows API router (`red_fastapi.api.flows`) mirroring `@node-red/editor-api/lib/admin/flows.js` and `flow.js`:
  - `GET /flows`: Supports both `v1` and `v2` protocols.
  - `POST /flows`: Handles Deploy button requests (`full`, `nodes`, `reload`).
  - `GET /flows/state` and `POST /flows/state`: Controls runtime state (`start` / `stop`).
  - Workspace/tab CRUD (`GET /flow/{id}`, `POST /flow`, `PUT /flow/{id}`, `DELETE /flow/{id}`).
- [x] Validated with automated tests (`tests/test_phase3.py`).

### Phase 4: Real-time Event Bus (WebSocket /comms)
- [x] Built connection manager & client registry (`red_fastapi.runtime.comms`) mirroring `@node-red/runtime/lib/api/comms.js`.
- [x] Built WebSocket `/comms` router (`red_fastapi.api.comms`) mirroring `@node-red/editor-api/lib/editor/comms.js`.
- [x] Implemented batched array message delivery (`[{topic, data}, ...]`).
- [x] Implemented retained message caching for initial client synchronization (e.g. node statuses, runtime state).
- [x] Implemented topic subscriptions (`{"subscribe": "debug"}`) and auth packets.
- [x] Added automated notifications on flow deployment (`notification/runtime-deploy`).
- [x] Validated with automated tests (`tests/test_phase4.py`).

### Phase 5: Asyncio Flow Execution Engine
- [x] Built flow graph compiler & wire router (`red_fastapi.runtime.engine`) mirroring `@node-red/runtime/lib/flows/Flow.js`.
- [x] Built abstract `Node` base class (`red_fastapi.runtime.node`) with `on_input`, `send`, `status`, `warn`, `error`.
- [x] Built core executable Python nodes (`red_fastapi.runtime.core_nodes`):
  - `InjectNode`: Manual trigger via `POST /inject/{id}` + interval timers.
  - `DebugNode`: Emits payloads to console and WebSocket `/comms` debug topic.
  - `FunctionNode`: Evaluates Python code blocks with `msg` in local scope.
- [x] Built node action routes (`red_fastapi.api.node_actions`): `POST /inject/{id}` and `POST /debug/{id}/{action}`.
- [x] Validated end-to-end execution (`Inject` -> `Function` -> `Debug` -> WebSocket `/comms`) with automated tests (`tests/test_phase5.py`).

### Phase 6: Core Sequence & Logic Nodes
- [x] Built property evaluation & deep path resolution utility (`red_fastapi.runtime.eval`).
- [x] Built executable Python sequence & logic nodes (`red_fastapi.runtime.logic_nodes`):
  - `ChangeNode`: Rules-based property transformation (`set`, `change`/replace, `delete`, `move`).
  - `SwitchNode`: Conditional multi-port routing with operators (`==`, `!=`, `<`, `<=`, `>`, `>=`, `between`, `contains`, `regex`, `true`, `false`, `null`, `empty`, `otherwise`).
  - `RangeNode`: Linear numeric scaling with `clamp`, `roll`, and `drop` actions.
  - `DelayNode`: Pauses and queue rate-limiting.
  - `TriggerNode`: Timed pulses, secondary payloads, and reset triggers.
  - `CommentNode`: Workspace canvas documentation node.
- [x] Registered node HTML templates in `nodes/core/` and loaded into registry (`red_fastapi.runtime.registry`).
- [x] Validated with automated tests (`tests/test_logic_nodes.py`).

### Phase 7: Advanced Sequence & Flow Control
- [x] Built advanced sequence & flow control nodes (`red_fastapi.runtime.sequence_nodes`):
  - `SplitNode`: Dissects arrays, strings, and objects into message sequences with `msg.parts` metadata (`id`, `index`, `count`).
  - `JoinNode`: Aggregates sequenced messages into arrays, joined strings, or merged objects.
  - `SortNode`: In-memory sorting for lists and sequences (ascending/descending, numeric or string).
  - `CatchNode`: Intercepts unhandled errors across flow or scoped nodes.
  - `StatusNode`: Listens to visual status events emitted by nodes.
  - `CompleteNode`: Triggers downstream flows upon upstream node completion.
- [x] Registered templates in `nodes/core/sequence/` and `nodes/core/common/`.
- [x] Hooked FlowEngine event dispatchers (`handle_error`, `handle_status`, `handle_complete`).
- [x] Validated with automated tests (`tests/test_sequence_nodes.py`).

### Phase 8: Hierarchical Context & Link Cross-Flow Routing
- [x] Built hierarchical context manager (`red_fastapi.runtime.context`): Node, Flow, and Global stores with thread-safe access.
- [x] Linked context to `eval.py`, `ChangeNode` (`pt` flow/global targets), and `FunctionNode` (`flow_ctx`, `global_ctx` injected into Python scopes).
- [x] Built Link nodes (`red_fastapi.runtime.sequence_nodes`):
  - `LinkInNode`: Receives cross-link messages.
  - `LinkOutNode`: Routes to linked nodes or executes returns for subflow callers.
  - `LinkCallNode`: Calls designated link targets and awaits asynchronous return message responses.
- [x] Registered template `nodes/core/common/60-link.html` in registry (`red_fastapi.runtime.registry`).
- [x] Validated with automated tests (`tests/test_context_and_links.py`).

### Phase 9: Network Ingress & Egress (HTTP)
- [x] Built dynamic HTTP ingress router (`red_fastapi.api.http_in`):
  - Mounts catch-all dynamic route handler `/http/{path:path}` in FastAPI app.
  - Bridges requests to active `HTTPInNode` instances and awaits `HTTPResponseNode` response completion via futures.
- [x] Built executable Python network nodes (`red_fastapi.runtime.network_nodes`):
  - `HTTPInNode`: Endpoint listener extracting `method`, `url`, `headers`, `query`, and `body`.
  - `HTTPResponseNode`: Responds to in-flight HTTP requests with JSON/text/binary content and custom HTTP status codes/headers.
  - `HTTPRequestNode`: Non-blocking outbound HTTP client using `httpx.AsyncClient`.
- [x] Registered HTML templates in `nodes/core/network/` (`21-httpin.html`, `21-httprequest.html`).
- [x] Validated with automated tests (`tests/test_network_nodes.py`).

### Phase 10: MQTT & Sockets (TCP, UDP, WebSocket)
- [x] Built executable Python socket & MQTT nodes (`red_fastapi.runtime.socket_nodes`):
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

### Phase 11: Subflows & Custom Modules
- [x] Built subflow execution runtime and composite node (`red_fastapi.runtime.subflow`):
  - `SubflowInstanceNode`: Encapsulates cloned internal nodes with scoped IDs (`{instance_id}:{node_id}`).
  - Resolves multi-port input wiring (`subflow_def.in`) and routes directly to internal entry nodes.
  - Intercepts internal node outputs mapped in `subflow_def.out` and dispatches to outer flow downstream wires.
  - Supports nested subflows (subflow instances embedded inside other subflow definitions).
  - Implements hierarchical environment variables (`env`) merging template defaults and instance overrides, accessible in `eval.py` and `FunctionNode` via `env.get(...)`.
  - Propagates internal errors to `CatchNode` instances and status badges to outer subflow nodes.
  - Enables transparent internal node lookup via `engine.get_node`.
- [x] Validated with automated tests (`tests/test_subflows.py`).

### Phase 12: Storage & Parsers (Local Files, AWS S3 / MinIO & Parsers)
- [x] Built parser nodes (`red_fastapi.runtime.parser_nodes`):
  - `JSONNode`: Bidirectional JSON parser and stringifier with formatting (`pretty`) and forced modes (`str`/`obj`).
  - `CSVNode`: Converts CSV lines/text into objects or arrays of dicts, and formats dicts/arrays back to CSV with customizable delimiters and headers.
  - `YAMLNode`: Bidirectional YAML parser and serializer using `pyyaml`.
  - `XMLNode`: Bidirectional XML parser and builder using `xmltodict` with attribute and prefix support.
  - `HTMLNode`: Tag and text extractor with HTML stripping.
- [x] Built filesystem and Cloud Blob Storage nodes (`red_fastapi.runtime.storage_nodes`):
  - `FileNode`: Non-blocking async file writer with append, overwrite, and delete actions via `aiofiles`.
  - `FileInNode`: Non-blocking async file reader with `utf8`, `lines` (streaming line-by-line messages), or raw `buffer` modes.
  - `S3ConfigNode`: Centralized credential and endpoint configuration for AWS S3 and MinIO instances.
  - `S3InNode`: Downloads and fetches blob objects from AWS S3 or MinIO buckets into strings, JSON objects, or bytes.
  - `S3OutNode`: Uploads, creates, or deletes blob objects in AWS S3 or MinIO buckets.
- [x] Registered HTML templates in `nodes/core/storage/` and `nodes/core/parsers/`.
- [x] Validated with automated tests (`tests/test_storage_and_parsers.py`).

### Phase 13: Expression Evaluator (JSONata & Python Expressions)
- [x] Built JSONata & Python expression evaluation engine (`red_fastapi.runtime.eval`):
  - `evaluate_jsonata_expression`: Direct evaluation of standard Node-RED JSONata expressions against incoming messages and context hierarchies using `jsonata-python`.
  - Supports deep object path traversal, arithmetic expressions, string formatting, and array filtering.
  - Supports `val_type: "jsonata"` across property evaluation in `ChangeNode`, `SwitchNode`, etc.
  - Supports `val_type: "py"` for safe embedded Python expression execution.
  - Extended `SwitchNode` with `jsonata_exp` and `py` rule operators for dynamic condition matching.
- [x] Validated with automated tests (`tests/test_expressions.py`, 68/68 tests passing).

---

## Technical Documentation

Detailed architectural notes and specifications are available in the `docs/` folder:
- [fast-api_basics.md](file:///c:/Documents/Programming/red-fastapi/docs/fast-api_basics.md): Objectives & Key Findings (OKF) technical specification document.
- [implementation_plan.md](file:///c:/Documents/Programming/red-fastapi/docs/implementation_plan.md): Comprehensive implementation plan and architectural breakdown.
- [plan_core_and_sequence_nodes.md](file:///c:/Documents/Programming/red-fastapi/docs/plan_core_and_sequence_nodes.md): Architecture and roadmap for Core Execution and Sequence & Logic Nodes.
- [gap_analysis.md](file:///c:/Documents/Programming/red-fastapi/docs/gap_analysis.md): Technical gap analysis comparing Node-RED (Node.js) vs Red-Fastapi (Python).
