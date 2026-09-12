# Phase 11: Subflows & Custom Modules Specification

## Goal
Implement Phase 11: Subflows & Custom Modules (`subflow:*` instances, subflow template definitions, internal wiring, input/output port mapping, env variable resolution, status/catch propagation) in `red-fastapi`.

## Proposed Architecture
1. **`src/red_fastapi/runtime/subflow.py`**:
   - `SubflowInstanceNode(Node)`:
     - Instantiated for any node whose `type.startswith("subflow:")`.
     - Maintains a dictionary of internal cloned nodes (`self.internal_nodes`).
     - Maintains an internal wire map (`self.internal_wire_map`).
     - Handles `in` ports mapping:
       - When `on_input(msg)` is called on the subflow instance, routes the message to the internal nodes wired from the subflow input port (`subflow_def.in[port]["wires"]`).
     - Handles `out` ports mapping:
       - Subflow definition specifies `out: [{"wires": [{"id": "<internal_node_id>", "port": 0}]}]`.
       - When an internal node with `(id, port)` calls `send(msg)`, the subflow intercepts or routes the output message to the outer downstream wires `self.send(msg, subflow_out_port)`.
     - Scoped environment:
       - Calculates hierarchical environment variables combining definition `env` and instance `env`.
       - Provides `get_env(name)`.
     - Lifecycle:
       - `start()` calls `start()` on internal nodes.
       - `close()` calls `close()` on internal nodes.
     - Error & Status:
       - Catches internal errors / status updates and propagates to parent flow or subflow instance status badge.

2. **`src/red_fastapi/runtime/node.py`**:
   - Add `get_env(name: str)` method to `Node` base class, traversing `self.flow` / subflow instance or falling back to `os.environ.get(name, "")`.

3. **`src/red_fastapi/runtime/eval.py`**:
   - In `evaluate_value`:
     - When `val_type == "env"`, check `node.get_env(str(val_value))` if `node` has `get_env`, else `os.environ.get(...)`.

4. **`src/red_fastapi/runtime/core_nodes.py`**:
   - In `FunctionNode`:
     - Inject `env` helper dictionary/accessor into the Python execution sandbox so functions can read `env.get("KEY")`.

5. **`src/red_fastapi/runtime/engine.py`**:
   - In `FlowEngine.start()`:
     - Index subflow definitions (`type == "subflow"`).
     - When instantiating nodes, if `node_type.startswith("subflow:")`, instantiate `SubflowInstanceNode(config, flow=self, subflow_def=subflow_def)`.
     - Support recursive `get_node(node_id)` searching inside subflow instances so `CompleteNode` / `StatusNode` / `CatchNode` / editor can locate internal nodes if addressed with full ID or namespace.

6. **`tests/test_subflows.py`**:
   - Test basic subflow data pass-through.
   - Test multi-port input and output subflow routing.
   - Test nested subflows (subflow instance inside another subflow).
   - Test subflow environment variables and template overrides.
   - Test subflow error catching / status propagation.

