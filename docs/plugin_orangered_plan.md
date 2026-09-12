---
title: Implementation Plan - OrangeRed as a Red-Fastapi Plugin
document_type: Architecture & Implementation Plan
project: red-fastapi
target: Plan the migration of OrangeRed into an external, decoupled plugin for Red-Fastapi
repository_status: Separate Git Repository (red-fastapi-orangered)
status: Ready for Review
date: September 2026
---

# Architecture & Implementation Plan: OrangeRed Plugin for Red-Fastapi

**Target Package:** `red-fastapi-orangered`  
**Repository Model:** Independent Git repository (`git@github.com:.../red-fastapi-orangered.git`)  
**Host Framework:** `red-fastapi` Core Runtime  
**Document Type:** Plugin Architecture & Migration Specification  
**Date:** September 2026  

---

## 1. Executive Summary & Value Proposition

### Background
Currently, **OrangeRed** runs as a split-brain, multi-process application:
1. **Node.js Process:** Runs Node-RED, hosting the UI and running `orangered-client.js` to intercept deployments and sync flows via HTTP.
2. **Python Process:** Runs a standalone FastAPI service with Orange3, SciPy, and xarray to execute headless data mining widgets.
3. **Communication Overhead:** State, synchronization loops (500ms debounce), and bridge endpoints (`or-bridge-in`, `or-bridge-out`) introduce network serialization, latency, and operational complexity.

### Unified Vision
Because **Red-Fastapi** is a 100% Python rewrite of the Node-RED runtime engine that hosts the unmodified Node-RED editor, **OrangeRed can be transformed into a native, single-process Python plugin**.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   red-fastapi Core Runtime (Single Python Process)              │
│                                                                                  │
│   FastAPI Server Layer (/nodes, /flows, /comms, /settings, /static)              │
│     │                                                                            │
│     ├── Plugin Discovery System (`importlib.metadata` entry points)              │
│     │     │                                                                      │
│     │     └──► Loads `red-fastapi-orangered` (External Git Repo / PyPI Package)  │
│     │            ├── 1. Registers Node Templates (.html) in Node Registry       │
│     │            ├── 2. Registers Orange Node Types in FlowEngine               │
│     │            └── 3. Mounts Data & Preview APIRouter (/api/orangered/*)       │
│     │                                                                            │
│     ├── FlowEngine (Asyncio DAG & Event Bus)                                     │
│     │     ├── Core Nodes : inject, debug, change, switch, mqtt, http in/out      │
│     │     └── Plugin Nodes: or-file-loader, or-tree, or-scatter-plot, etc.       │
│     │                                                                            │
│     └── Shared In-Memory Data Passing                                            │
│           • Zero-copy in-memory references for Orange Tables, Models & xarrays   │
│           • Automatic bidirectional type coercion between JSON/Dict and Table    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Multi-Repository Boundary & Contract

The plugin will be developed, versioned, and maintained in its **own dedicated Git repository** separate from `red-fastapi`.

### Repository Structure

```
red-fastapi-orangered/               <-- Dedicated Git Repository
├── .git/
├── pyproject.toml                  <-- Declares entry-point hook
├── requirements.txt                <-- Orange3, scikit-learn, scipy, xarray
├── README.md
├── src/
│   └── red_fastapi_orangered/
│       ├── __init__.py             <-- Plugin entrypoint hook
│       ├── plugin.py               <-- OrangeRedPlugin lifecycle implementation
│       ├── api.py                  <-- APIRouter for previews, metrics, images
│       ├── base_node.py            <-- OrangeBaseNode(red_fastapi.runtime.node.Node)
│       ├── conversion.py           <-- Orange.data.Table <-> DataFrame / Dict
│       ├── nodes/                  <-- Node definitions mapped to widget types
│       │   ├── data_nodes.py       <-- or-file-loader, or-data-sampler, etc.
│       │   ├── model_nodes.py      <-- or-tree, or-random-forest, etc.
│       │   ├── preprocess_nodes.py <-- or-impute, or-pca, etc.
│       │   ├── evaluate_nodes.py   <-- or-test-and-score, or-predictions, etc.
│       │   ├── bridge_nodes.py     <-- or-bridge-in, or-bridge-out (pass-through)
│       │   └── scipy_nodes.py      <-- sp-image-*, sp-audio-*
│       └── widgets/                <-- Reused Orange3/SciPy HeadlessWidget library
├── templates/                      <-- HTML/JS dialog templates & icons
│   ├── icons/                      <-- Node icons (.png / .svg)
│   └── nodes/                      <-- or-file-loader.html, or-tree.html, etc.
└── tests/
    ├── test_plugin_registration.py
    ├── test_in_memory_pipeline.py
    └── test_bridge_integration.py
```

---

## 3. Core Framework Prerequisites (`red-fastapi`)

Before the plugin can be attached, `red-fastapi` requires a lightweight, extensible plugin architecture:

### 3.1. Plugin Contract (`red_fastapi.plugins.base`)
```python
class BasePlugin:
    name: str
    version: str

    def register_nodes(self, registry) -> None:
        """Register HTML node templates and icons into the editor registry."""
        pass

    def register_engine_types(self, engine) -> None:
        """Register executable Python Node subclasses into FlowEngine."""
        pass

    def get_routers(self) -> list:
        """Return custom FastAPI APIRouters to mount on the main app."""
        return []
```

### 3.2. Entry-Point Auto-Discovery
In `red_fastapi.main` during application startup (`lifespan`):
```python
from importlib.metadata import entry_points

def load_installed_plugins(app, registry, engine):
    discovered = entry_points(group="red_fastapi.plugins")
    for ep in discovered:
        plugin_cls = ep.load()
        plugin = plugin_cls()
        plugin.register_nodes(registry)
        plugin.register_engine_types(engine)
        for router in plugin.get_routers():
            app.include_router(router)
```

In `red-fastapi-orangered/pyproject.toml`:
```toml
[project.entry-points."red_fastapi.plugins"]
orangered = "red_fastapi_orangered.plugin:OrangeRedPlugin"
```

---

## 4. OrangeRed Plugin Architecture (`red-fastapi-orangered`)

### 4.1. Base Node Adapter (`base_node.py`)
Each Orange node runs as an `asyncio` task within the flow graph. The `OrangeBaseNode` wraps the existing `HeadlessWidget` classes:

```python
from red_fastapi.runtime.node import Node
from red_fastapi_orangered.widgets import HeadlessWidget

class OrangeBaseNode(Node):
    widget_class: type[HeadlessWidget]

    def __init__(self, config, flow=None):
        super().__init__(config, flow)
        self.widget = self.widget_class()
        self.widget.configure(config)

    async def on_input(self, msg: dict) -> None:
        # 1. Update UI status to 'running'
        await self.status(fill="blue", shape="dot", text="computing...")

        try:
            # 2. Extract or coerce input data to Orange Table / Learner
            data = self.extract_input(msg)

            # 3. Execute widget computation in threadpool if CPU-bound
            output = await asyncio.to_thread(self.widget.run, data)

            # 4. Cache output for frontend preview endpoints
            self.store_preview_cache(output)

            # 5. Dispatch message along wire
            out_msg = {"payload": output, "_orange_signal": True}
            await self.send(out_msg)

            # 6. Update UI status to 'completed'
            await self.status(fill="green", shape="dot", text="ready")
        except Exception as e:
            await self.status(fill="red", shape="dot", text="error")
            await self.error(str(e), msg)
```

### 4.2. In-Memory Bridge & Type Coercion
* **Zero-Copy Pipeline:** When wiring an `or-*` node to another `or-*` node, the message payload holds the native `Orange.data.Table` or `Orange.base.Model` object in Python memory. No disk serialization or JSON conversion occurs.
* **Core Node Interoperability:**
  * When fed by a standard node (e.g. `inject`, `http in`, `mqtt in`, `file in`), `OrangeBaseNode` automatically parses JSON/dict records into an `Orange.data.Table`.
  * When feeding into a standard node (e.g. `debug`, `http response`, `mqtt out`), `OrangeBaseNode` or `or-bridge-out` automatically serializes the predictions or summary into a standard JSON-compatible structure.

### 4.3. Eliminating `orangered-client.js`
* The old Node.js client file (`orangered-client.js`) with its debounced HTTP deployment calls is **completely deleted**.
* Node lifecycle, wire routing, and deployments are directly handled by `red-fastapi`'s native deployment workflow.

### 4.4. Unified REST API for Previews
The existing preview and diagnostic endpoints are packaged into an `APIRouter` in `red_fastapi_orangered.api` and mounted at `/api/orangered`:
* `GET /api/orangered/preview/{node_id}/{output_name}`: Paginated Tabulator preview rows.
* `GET /api/orangered/image/{node_id}/{output_name}`: PNG array buffer for SciPy image nodes.
* `GET /api/orangered/metrics/{node_id}`: Classification/Regression metrics for Test & Score.
* `GET /api/orangered/coefficients/{node_id}`: Logistic & Linear regression model coefficients.
* `GET /api/orangered/correlations/{node_id}`: Correlation matrices and p-values.

---

## 5. Phased Implementation Roadmap

### Phase 1: `red-fastapi` Plugin Hook System
- [ ] Define `BasePlugin` interface in `red_fastapi.plugins`.
- [ ] Implement `importlib.metadata` entry-point discovery in `red_fastapi.main:lifespan`.
- [ ] Extend `red_fastapi.runtime.registry` to accept external node template directories and icons.
- [ ] Add unit test verifying that dummy plugins can register nodes and routes.

### Phase 2: Repository Scaffolding & Core Wrapper
- [ ] Initialize `red-fastapi-orangered` Git repository with modern `pyproject.toml`.
- [ ] Port `src/headless_widget.py`, `src/conversion.py`, and `src/widgets/` from OrangeRed.
- [ ] Implement `OrangeBaseNode` extending `red_fastapi.runtime.node.Node`.
- [ ] Implement entry-point class `OrangeRedPlugin`.

### Phase 3: Node Migration & Category Packaging
- [ ] Map all 40+ widgets to `Node` subclasses across categories:
  - `OR Data`, `OR Transform`, `OR Unsupervised`, `OR Model`, `OR Evaluate`, `OR Visualize`, `OR Scripting`, `OR Bridge`, `OR SciPy`.
- [ ] Port HTML templates to `templates/nodes/` and update internal AJAX URLs from `orangered/preview/...` to `/api/orangered/preview/...`.

### Phase 4: Preview APIRouter & Bridge Integration
- [ ] Port preview endpoints from OrangeRed `src/api.py` into a modular `APIRouter`.
- [ ] Adapt `or-bridge-in` and `or-bridge-out` to serve as seamless type-adapters between native Node-RED event streams and Orange tables.

### Phase 5: Verification & End-to-End Testing
- [ ] **E2E DAG Tests:** Load dataset (`iris`) -> Preprocess (Normalize) -> Train (Random Forest) -> Evaluate (Test & Score) within Red-Fastapi.
- [ ] **Bridge Stream Tests:** Trigger via HTTP In -> Model Inference -> Emit via HTTP Response.
- [ ] **UI Validation:** Verify all 40+ node dialogs, Tabulator tables, and Plotly charts load seamlessly in the stock Node-RED canvas.

---

## 6. Developer & User Experience

### Installation & Run Workflow

```bash
# 1. Install Red-Fastapi
pip install red-fastapi

# 2. Install the OrangeRed plugin from its repository or PyPI
pip install git+https://github.com/tasahi/red-fastapi-orangered.git

# 3. Start the unified server
red-fastapi
```

### Result
When navigating to `http://127.0.0.1:1880`, the Node-RED editor automatically displays:
* All stock Node-RED nodes (`common`, `function`, `sequence`, `network`, `storage`, `parser`).
* The complete suite of **`OR`** data mining and machine learning palette categories.
* Complete execution occurs in a **single high-performance Python process**, with zero-copy in-memory ML data pipelines.

