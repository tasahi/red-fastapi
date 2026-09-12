---
title: Implementation Plan - Core Execution Nodes and Sequence & Logic Nodes
document_type: OKF (Objectives & Key Findings) / Architecture & Implementation Plan
project: red-fastapi
target: Plan the implementation of Core Execution Nodes and Sequence & Logic Nodes for Red-Fastapi Python runtime
status: Ready for Review
date: September 2026
baseline:
  frontend_compatibility: 100% (Unmodified @node-red/editor-client)
  runtime_phase_operational: Phase 5 (Flow Execution Engine)
---

# Implementation Plan: Core Execution Nodes & Sequence & Logic Nodes

**Project:** `red-fastapi`  
**Document Type:** Architecture & Implementation Plan  
**Status:** Ready for Review  
**Date:** September 2026  

---

## 1. Executive Summary & Objective

In Phase 5, `red-fastapi` successfully established an asynchronous message-passing flow execution engine (`FlowEngine` and `Node` base class), supporting `inject`, `debug`, and `function` (Python code evaluation).

The objective of this plan is to expand `red-fastapi`'s node library to include the most essential **Core Execution Nodes** and **Sequence & Logic Nodes** from upstream Node-RED (`@node-red/nodes/core`), implementing their execution logic in Python while maintaining complete wire-protocol and visual editor compatibility with `@node-red/editor-client`.

---

## 2. Target Nodes & Scope Breakdown

We organize the implementation into cohesive sequential phases:

### Phase 6: Core Sequence & Logic Nodes (Foundational Data Manipulation & Routing)
1. **`change`** (`nodes/core/function/15-change.html`):
   - Rules-based property transformation (`set`, `change`/search-replace, `delete`, `move`).
   - Supports message properties (`msg.payload`, `msg.topic`), JSONata expressions / regex / string replacements, and context.
2. **`switch`** (`nodes/core/function/10-switch.html`):
   - Multi-output conditional routing based on rule evaluation (`==`, `!=`, `<`, `<=`, `>`, `>=`, `between`, `contains`, `matches regex`, `is true/false/null/empty`, `otherwise`).
   - Multi-port routing modes: `"all"` (send to all matching outputs) or `"first"` (stop at first match).
3. **`range`** (`nodes/core/function/16-range.html`):
   - Linear numeric scaling: maps input `[a, b]` to target `[c, d]`.
   - Scale actions: scale and clamp, wrap around, or pass through.
4. **`delay`** (`nodes/core/function/89-delay.html`):
   - Fixed or random delay via `asyncio.sleep`.
   - Rate limiting: leaky bucket queue or drop intermediate messages at configured rates (msg/sec, msg/min, msg/hour).
5. **`trigger`** (`nodes/core/function/89-trigger.html`):
   - Sends initial payload immediately, waits duration, then sends secondary payload.
   - Resettable or extendable with incoming messages matching a reset criterion.
6. **`comment`** (`nodes/core/common/90-comment.html`):
   - Visual documentation node on workspace canvas (no-op in execution engine).

### Phase 7: Advanced Sequence & Flow Control Nodes
1. **`split`** & **`join`** (`nodes/core/sequence/17-split.html`):
   - `split`: Dissects arrays, strings (delimiter/regex), or binary buffers into message sequences carrying `msg.parts` (`id`, `index`, `count`).
   - `join`: Reassembles sequenced messages matching `msg.parts` into aggregated arrays, strings, or merged objects.
2. **`sort`** (`nodes/core/sequence/18-sort.html`):
   - Sorts sequences of messages based on property values or JSONata expressions.
3. **`catch`** (`nodes/core/common/25-catch.html`):
   - Catches unhandled errors emitted by nodes on the flow or specific targeted nodes, routing an error message (`msg.error`).
4. **`status`** (`nodes/core/common/25-status.html`):
   - Listens to status updates (`node.status(...)`) from nodes on the flow canvas and outputs `msg.status`.
5. **`complete`** (`nodes/core/common/24-complete.html`):
   - Fires when configured upstream nodes finish processing a message.

---

## 3. Architecture & Technical Design

### 3.1 Property Evaluation Helper (`red_fastapi.runtime.eval.py`)
To handle `change`, `switch`, and `range` nodes consistently with Node-RED, we introduce a unified property accessor / evaluator utility:
- **`get_property(msg, prop_path)`**: Resolves dotted / indexed paths (e.g. `payload.user.id`, `req.headers["content-type"]`).
- **`set_property(msg, prop_path, value)`**: Dynamically creates sub-dicts / lists and sets the target property.
- **`delete_property(msg, prop_path)`**: Removes a key or nested key safely.
- **`evaluate_value(val_type, val_value, msg)`**: Evaluates types (`str`, `num`, `bool`, `json`, `bin`, `date`, `msg`, `flow`, `global`, `env`).

### 3.2 Multi-Port Wire Routing
The base `Node.send()` in `runtime/node.py` already supports multi-port outputs (`[[msg_port0], [msg_port1], None, ...]`).
The `switch` node will construct an output array of length equal to configured rules:
```python
# Output port routing for SwitchNode
output = [None] * len(self.rules)
for idx, rule in enumerate(self.rules):
    if self._match_rule(rule, msg):
        output[idx] = copy.deepcopy(msg)
        if not self.checkall:
            break
await self.send(output)
```

### 3.3 Asynchronous Queueing in `DelayNode`
- **Delay Mode**: Simple `asyncio.sleep(delay_seconds)`.
- **Rate Limit Mode**: Backed by `asyncio.Queue` and a background worker task spawned on start:
  - Supports `"queue"` (queue up messages and emit at steady pace).
  - Supports `"drop"` (drop intermediate messages, emit latest or first).
  - Clean lifecycle: `close()` cancels background consumer tasks.

---

## 4. Step-by-Step Implementation Roadmap

### Step 1: Copy Node HTML Templates from Upstream Node-RED
Copy HTML node definitions to make them available to the Node-RED editor client:
- `C:\Documents\Programming\node-red\packages\node_modules\@node-red\nodes\core\function\10-switch.html` -> `static/nodes/core/function/10-switch.html`
- `15-change.html`, `16-range.html`, `89-delay.html`, `89-trigger.html` -> `static/nodes/core/function/`
- `C:\Documents\Programming\node-red\packages\node_modules\@node-red\nodes\core\common\90-comment.html` -> `static/nodes/core/common/90-comment.html`
- Register the new nodes in `src/red_fastapi/runtime/registry.py` under `load_core_nodes()`.

### Step 2: Implement Property Utility (`src/red_fastapi/runtime/eval.py`)
- Implement path resolution, type evaluation, and mutation functions.
- Add unit tests for deep property path getting/setting/deleting.

### Step 3: Implement Sequence & Logic Nodes (`src/red_fastapi/runtime/logic_nodes.py`)
- `ChangeNode`: Implement `set`, `change`, `delete`, `move` operations.
- `SwitchNode`: Implement operators (`eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `btwn`, `cont`, `regex`, `true`, `false`, `null`, `nnull`, `empty`, `nempty`, `else`).
- `RangeNode`: Implement linear interpolation `(val - a_min) / (a_max - a_min) * (b_max - b_min) + b_min` with clamp/wrap/roll options.
- `DelayNode`: Implement fixed delay, random range delay, and rate-limiting queues.
- `TriggerNode`: Implement timed sequence, reset messages, and extendable timers.
- `CommentNode`: Pure metadata dummy node.

### Step 4: Register in `FlowEngine`
- Update `_node_constructors` in `src/red_fastapi/runtime/engine.py` to map:
  - `"change"` -> `ChangeNode`
  - `"switch"` -> `SwitchNode`
  - `"range"` -> `RangeNode`
  - `"delay"` -> `DelayNode`
  - `"trigger"` -> `TriggerNode`
  - `"comment"` -> `CommentNode`

### Step 5: Test Suite Verification
- Create `tests/test_logic_nodes.py`:
  - Test `change` rule execution on nested dictionaries and strings.
  - Test `switch` single and multi-rule routing across multiple ports.
  - Test `range` scaling and clamping arithmetic.
  - Test `delay` timing precision and queue throttling.
  - Test `trigger` reset and timeout sequencing.

---

## 5. Coding Standards Compliance

1. **Blank Lines**: Exactly 2 blank lines between all top-level functions and classes.
2. **Docstrings**: All docstrings start with a space after opening triple quotes (`""" `).
3. **Developer Comments**: Main functions and branches will be clearly commented.
4. **Environment**: Verified using Python `fapi` interpreter (`C:\Programs\Python3\envs\fapi\python.exe`).
5. **No Regressions**: Existing 28 unit tests must continue to pass without changes.

