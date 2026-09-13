# Project Overview: red-fastapi

Why another implementation?
The idea behind this project is to have the backend in Python, in order to add future funcionalities using all the Python ecosystem .

`red-fastapi` is a lightweight, high-performance Python (FastAPI) implementation of the [Node-RED](https://nodered.org/) backend, designed to host and drive the official, unmodified Node-RED frontend editor (`@node-red/editor-client`).

---

## Getting Started

### 1. Environment Activation
Using your Anaconda environment `redapi`:

```
conda activate redapi
```

### 2. Compile the Frontend with Vite (Modular Compilation)

Before starting the server (or after modifying node UI templates), compile the editor shell, stylesheets, and modular node chunks:

```
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

```
npm run update:upstream
```

This single command:
1. Installs the latest `@node-red/editor-client` and `@node-red/nodes` from npm.
2. Runs `scripts/sync-upstream.js` to synchronize the compiled web assets into `static/` and node templates into `nodes/core/`.
3. Runs `npm run build` to re-bundle and minify everything into `dist/`.

### 3. Run the Backend Server

Once built (or directly in dev mode using fallback to `static/`):

Using the runner script:
```
.\run.bat
```

Or directly with python/uvicorn:
```
python -m uvicorn red_fastapi.main:app --host 127.0.0.1 --port 8080 --reload
```

Navigate to:  
**`http://127.0.0.1:8080/`**

### 4. Run with Docker

Build and run using Docker Compose:
```
docker compose up -d --build
```

Or using Docker directly:
```
docker build -t red-fastapi .
docker run -d -p 8080:8080 -v ${PWD}/storage:/app/storage --name red-fastapi red-fastapi
```

The editor will be accessible at **`http://localhost:8080/`** with persistent flow storage in `./storage`.

---

## Technical Documentation

Detailed architectural notes, specifications, production deployment guides, and implementation statuses are available in the [`docs/`](./docs) folder:

- **[Technical Documentation Hub (`index.md`)](./docs/index.md)**: Main entry point for all technical specifications and guides.
- **[Production Architecture & Phase Implementation (`production_and_phases.md`)](./docs/production_and_phases.md)**: Production architecture (Apache ingress / reverse proxy), S3/MinIO & Local storage configuration, test suite details, code style conventions, and complete phase-by-phase implementation statuses (Phases 1–13).
- **[Objectives & Key Findings (`fast-api_basics.md`)](./docs/fast-api_basics.md)**: Technical OKF analysis comparing Node-RED frontend/backend SLOC distribution and wire protocols.
- **[Comprehensive Implementation Plan (`implementation_plan.md`)](./docs/implementation_plan.md)**: Detailed roadmap and architectural breakdown.
- **[Core & Sequence Nodes Plan (`plan_core_and_sequence_nodes.md`)](./docs/plan_core_and_sequence_nodes.md)**: Architecture for Core Execution and Sequence & Logic Nodes.
- **[Technical Gap Analysis (`gap_analysis.md`)](./docs/gap_analysis.md)**: Technical gap analysis comparing Node-RED (Node.js) vs Red-FastAPI (Python).
- **[Subflow Implementation Plan (`subflow_plan.md`)](./docs/subflow_plan.md)**: Subflow execution runtime architecture and port mapping.

## License

This project incorporates and builds upon components from Node-RED, licensed under the [Apache License, Version 2.0](./LICENSE).

## Note:
For this implementation, AI agents were used to plan and create the code, with stage by stage implementation and validation. Please create your examples and please help to test it.
