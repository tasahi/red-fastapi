""" Subflow execution runtime and composite node for Red-Fastapi.

Mirrors @node-red/runtime/lib/flows/Subflow.js and subflow instance handling:
- SubflowInstanceNode encapsulates an instantiation of a subflow template
- Clones internal subflow nodes with scoped IDs
- Re-wires internal inputs and outputs to match subflow port definitions
- Resolves hierarchical subflow environment variables (env)
- Propagates errors and status messages up to parent flow
"""

import asyncio
import copy
import logging
from typing import Any, Dict, List, Optional, Union
from red_fastapi.runtime.node import Node
from red_fastapi.runtime.eval import evaluate_value


logger = logging.getLogger("red_fastapi.runtime.subflow")


class SubflowInstanceNode(Node):
    """ Represents an instantiated subflow node (`type: "subflow:<id>"`).
    Encapsulates internal cloned nodes, internal wiring, input/output port mapping,
    and scoped subflow environment variables.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        flow: Optional[Any] = None,
        subflow_def: Optional[Dict[str, Any]] = None,
        all_subflow_defs: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        super().__init__(config, flow)
        self.subflow_def: Dict[str, Any] = copy.deepcopy(subflow_def or {})
        self.all_subflow_defs: Dict[str, Dict[str, Any]] = all_subflow_defs or {}
        self.subflow_id: str = self.subflow_def.get("id", "")

        # Internal cloned nodes: internal_node_id -> Node
        self.internal_nodes: Dict[str, Node] = {}
        # Internal wiring: internal_node_id -> [ [downstream_ids], ... ]
        self.internal_wire_map: Dict[str, List[List[str]]] = {}

        # Environment variables map: key -> resolved_value
        self.env_vars: Dict[str, Any] = {}
        self._init_env()

        # Input and output port definitions
        # in: [ { "wires": [ { "id": "internal_node_1" } ] } ]
        self.in_ports: List[Dict[str, Any]] = self.subflow_def.get("in", [])
        # out: [ { "wires": [ { "id": "internal_node_x", "port": 0 } ] } ]
        self.out_ports: List[Dict[str, Any]] = self.subflow_def.get("out", [])

        # Subflow internal status mapping if defined
        self.subflow_status_config = self.subflow_def.get("status")

        self._build_internal_graph()

    def _init_env(self) -> None:
        """ Resolves environment variables merging template defaults and instance overrides.
        Hierarchy:
        1. Parent flow / system environment
        2. Subflow definition `env` entries
        3. Subflow instance `env` entries (override definition defaults)
        """
        # 1. Definition env defaults
        def_env = self.subflow_def.get("env", [])
        for entry in def_env:
            name = entry.get("name")
            if not name:
                continue
            val_type = entry.get("type", "str")
            val = entry.get("value")
            # Evaluate using parent flow / node context
            resolved = evaluate_value(val_type, val, node=self)
            self.env_vars[name] = resolved

        # 2. Instance env overrides
        inst_env = self.config.get("env", [])
        for entry in inst_env:
            name = entry.get("name")
            if not name:
                continue
            val_type = entry.get("type", "str")
            val = entry.get("value")
            resolved = evaluate_value(val_type, val, node=self)
            self.env_vars[name] = resolved

    def get_env(self, name: str) -> Any:
        """ Retrieves a scoped environment variable for this subflow or delegates upwards.
        """
        if name in self.env_vars:
            return self.env_vars[name]
        # Check parent flow / node
        if self.flow and hasattr(self.flow, "get_env"):
            return self.flow.get_env(name)
        import os
        return os.environ.get(name, "")

    def _build_internal_graph(self) -> None:
        """ Clones nodes belonging to the subflow template and re-maps internal wires.
        Each internal node is given a namespaced ID: `{self.id}:{original_id}`
        to avoid collisions across multiple subflow instances.
        """
        from red_fastapi.runtime.engine import _node_constructors

        # Nodes inside this subflow definition are those whose `z` matches subflow_id
        internal_configs = self.subflow_def.get("nodes", [])

        # Step 1: Create ID mapping: original_id -> namespaced_id
        id_map: Dict[str, str] = {}
        for c in internal_configs:
            orig_id = str(c.get("id", ""))
            id_map[orig_id] = f"{self.id}:{orig_id}"

        # Step 2: Instantiate internal nodes with cloned configs
        for c in internal_configs:
            cloned_c = copy.deepcopy(c)
            orig_id = str(cloned_c.get("id", ""))
            cloned_c["id"] = id_map[orig_id]
            cloned_c["z"] = self.id  # Scoped to this subflow instance

            # Remap wires to namespaced targets
            new_wires: List[List[str]] = []
            for port_targets in cloned_c.get("wires", []):
                new_port_targets: List[str] = []
                for target in port_targets:
                    new_port_targets.append(id_map.get(str(target), str(target)))
                new_wires.append(new_port_targets)
            cloned_c["wires"] = new_wires

            self.internal_wire_map[cloned_c["id"]] = new_wires

            node_type = str(cloned_c.get("type", ""))
            # Support nested subflows!
            if node_type.startswith("subflow:"):
                nested_subflow_id = node_type[8:]
                nested_subflow_def = self.all_subflow_defs.get(nested_subflow_id, {})
                instance = SubflowInstanceNode(
                    cloned_c,
                    flow=self,
                    subflow_def=nested_subflow_def,
                    all_subflow_defs=self.all_subflow_defs,
                )
                self.internal_nodes[cloned_c["id"]] = instance
            else:
                constructor = _node_constructors.get(node_type, Node)
                instance = constructor(cloned_c, flow=self)
                self.internal_nodes[cloned_c["id"]] = instance

        self._id_map = id_map

    async def start(self) -> None:
        """ Starts all internal nodes (timers, listeners, etc.).
        """
        for node in self.internal_nodes.values():
            if hasattr(node, "start") and callable(node.start):
                await node.start()

    async def close(self) -> None:
        """ Closes all internal nodes when subflow or parent flow stops.
        """
        await super().close()
        for node in list(self.internal_nodes.values()):
            try:
                await node.close()
            except Exception as err:
                logger.error(f"Error closing internal subflow node {node.id}: {err}")
        self.internal_nodes.clear()
        self.internal_wire_map.clear()

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Receives input from outer flow and routes to subflow's internal entry nodes.
        Subflow entry points are defined in `subflow_def.in`:
        in: [ { "wires": [ { "id": "<original_node_id>" } ] } ]
        """
        if not self.in_ports:
            return

        # Port 0 default entry point
        entry_config = self.in_ports[0]
        entry_wires = entry_config.get("wires", [])
        for target in entry_wires:
            orig_target_id = str(target.get("id", ""))
            namespaced_id = self._id_map.get(orig_target_id, orig_target_id)
            target_node = self.internal_nodes.get(namespaced_id)
            if target_node:
                asyncio.create_task(self._deliver_internal(target_node, copy.deepcopy(msg)))

    async def route_message(self, source_node_id: str, output_port: int, msg: Dict[str, Any]) -> None:
        """ Routes messages emitted by internal nodes.
        Can route either:
        1. Along internal wires to other internal nodes
        2. Out of the subflow through `subflow_def.out` mappings to the outer flow
        """
        # Check if this source_node + output_port is mapped to any subflow output port
        # out: [ { "wires": [ { "id": "<orig_id>", "port": 0 } ] } ]
        for out_idx, out_def in enumerate(self.out_ports):
            wires = out_def.get("wires", [])
            for w in wires:
                target_orig_id = str(w.get("id", ""))
                target_port = int(w.get("port", 0))
                mapped_namespaced_id = self._id_map.get(target_orig_id, target_orig_id)

                if mapped_namespaced_id == source_node_id and target_port == output_port:
                    # Send to outer flow via SubflowInstanceNode's outer output port
                    await self.send(copy.deepcopy(msg), port=out_idx)

        # Also route along internal wires
        ports = self.internal_wire_map.get(source_node_id, [])
        if output_port < len(ports):
            target_ids = ports[output_port]
            for tid in target_ids:
                target_node = self.internal_nodes.get(tid)
                if target_node:
                    asyncio.create_task(self._deliver_internal(target_node, copy.deepcopy(msg)))

    async def _deliver_internal(self, node: Node, msg: Dict[str, Any]) -> None:
        """ Delivers a message to an internal node.
        """
        try:
            await node.receive(msg)
        except Exception as err:
            logger.error(f"Error delivering message to subflow internal node {node.id}: {err}")
            await self.handle_error(node, str(err), msg)

    async def handle_error(self, source_node: Node, error_message: str, original_msg: Optional[Dict[str, Any]] = None) -> None:
        """ Handles an error originating from an internal node.
        Dispatches to internal CatchNodes first; if uncaught, bubbles to parent flow.
        """
        from red_fastapi.runtime.sequence_nodes import CatchNode

        handled = False
        for node in self.internal_nodes.values():
            if isinstance(node, CatchNode):
                await node.handle_error(source_node, error_message, original_msg)
                handled = True

        if not handled and self.flow and hasattr(self.flow, "handle_error"):
            # Bubble error to outer flow
            await self.flow.handle_error(self, f"[{source_node.type}] {error_message}", original_msg)

    async def handle_status(self, source_node: Node, status_info: Dict[str, Any]) -> None:
        """ Handles status update from internal node.
        Updates internal StatusNodes and propagates to subflow instance status badge if configured.
        """
        from red_fastapi.runtime.sequence_nodes import StatusNode

        for node in self.internal_nodes.values():
            if isinstance(node, StatusNode):
                await node.handle_status(source_node, status_info)

        # If subflow status is linked to a specific node
        if self.subflow_status_config:
            # e.g., status: { "wires": [ { "id": "..." } ] }
            status_wires = self.subflow_status_config.get("wires", [])
            for w in status_wires:
                orig_id = str(w.get("id", ""))
                if self._id_map.get(orig_id) == source_node.id:
                    await self.status(**status_info)
                    return

        # Default fallback: update subflow node status badge directly
        await self.status(**status_info)

    def get_node(self, node_id: str) -> Optional[Node]:
        """ Retrieves an internal node by ID.
        Supports both namespaced ID `{subflow_id}:{node_id}` and bare `node_id`.
        """
        if node_id in self.internal_nodes:
            return self.internal_nodes[node_id]
        namespaced = self._id_map.get(node_id)
        if namespaced and namespaced in self.internal_nodes:
            return self.internal_nodes[namespaced]
        return None

