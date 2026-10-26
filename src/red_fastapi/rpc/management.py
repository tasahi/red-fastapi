""" Built-in JSON-RPC Methods for red-fastapi Management.\n
Implements Phase 14.2:
- system.info: Runtime version, engine state, active nodes count, registered types.
- flows.get: Retrieve active flow definitions and revision.
- flows.start: Start flow execution engine.
- flows.stop: Stop flow execution engine.
- flows.status: Get engine state ("start" / "stop") and active node count.
- flows.set: Deploy flows programmatically via RPC.
- nodes.trigger: Programmatically trigger an inject node or action.
- nodes.list: List registered node types and active node instances.
"""

from typing import Any, Dict, List, Optional, Union
from red_fastapi.config import settings
from red_fastapi.rpc.dispatcher import JSONRPCDispatcher
from red_fastapi.rpc.errors import InvalidParams, JSONRPCError, METHOD_NOT_FOUND
from red_fastapi.runtime import flows as runtime_flows
from red_fastapi.runtime import registry as runtime_registry
from red_fastapi.runtime.core_nodes import InjectNode


class NodeNotFoundError(JSONRPCError):
    """ Raised when a referenced node ID is not found in the runtime."""
    def __init__(self, node_id: str):
        super().__init__(code=-32004, message=f"Node not found: '{node_id}'", data={"node_id": node_id})


class NodeNotTriggerableError(JSONRPCError):
    """ Raised when a node cannot be triggered programmatically."""
    def __init__(self, node_id: str, node_type: str):
        super().__init__(
            code=-32005,
            message=f"Node '{node_id}' of type '{node_type}' is not triggerable",
            data={"node_id": node_id, "node_type": node_type},
        )


def register_management_methods(dispatcher: JSONRPCDispatcher) -> None:
    """ Register all Phase 14.2 management and lifecycle RPC methods on the given dispatcher."""

    # 1. System Management Methods
    @dispatcher.add_method("system.info")
    async def system_info() -> Dict[str, Any]:
        """ Returns runtime system status, version, registered node counts, and storage configuration."""
        flow_state = runtime_flows.get_state()
        active_nodes = getattr(runtime_flows.engine, "active_nodes", {})
        return {
            "name": settings.app_name,
            "version": settings.version,
            "engine_state": flow_state.get("state", "unknown"),
            "active_node_instances": len(active_nodes),
            "registered_modules": len(runtime_registry.module_configs),
            "storage_type": settings.storage_type,
        }

    # 2. Flows Lifecycle Management
    @dispatcher.add_method("flows.status")
    async def flows_status() -> Dict[str, Any]:
        """ Returns current engine execution state and flow counts."""
        flow_state = runtime_flows.get_state()
        current_flows = runtime_flows.get_flows()
        active_nodes = getattr(runtime_flows.engine, "active_nodes", {})
        return {
            "state": flow_state.get("state", "stop"),
            "rev": current_flows.get("rev", ""),
            "flow_count": len(current_flows.get("flows", [])),
            "active_node_instances": len(active_nodes),
        }

    @dispatcher.add_method("flows.get")
    async def flows_get() -> Dict[str, Any]:
        """ Returns the full active flow definition and revision."""
        return runtime_flows.get_flows()

    @dispatcher.add_method("flows.start")
    async def flows_start() -> Dict[str, str]:
        """ Starts flow engine execution."""
        return await runtime_flows.set_state("start")

    @dispatcher.add_method("flows.stop")
    async def flows_stop() -> Dict[str, str]:
        """ Stops flow engine execution."""
        return await runtime_flows.set_state("stop")

    @dispatcher.add_method("flows.set")
    async def flows_set(flows: Any, deployment_type: str = "full") -> Dict[str, str]:
        """Deploys a new flow configuration programmatically.
        
        Args:
            flows: List of node configurations or dict with 'flows' list.
            deployment_type: 'full' or 'nodes'.
        """
        if not isinstance(flows, (list, dict)):
            raise InvalidParams(message="Parameter 'flows' must be a list of nodes or an object with 'flows' key")
        return await runtime_flows.set_flows(flows, deployment_type=deployment_type)

    # 3. Nodes Management & Interaction
    @dispatcher.add_method("nodes.list")
    async def nodes_list() -> Dict[str, Any]:
        """Lists active nodes in the flow engine and available registered node types."""
        active_nodes = getattr(runtime_flows.engine, "active_nodes", {})
        active_summary = [
            {"id": nid, "type": getattr(node, "type", type(node).__name__), "name": getattr(node, "name", "")}
            for nid, node in active_nodes.items()
        ]
        return {
            "active_nodes": active_summary,
            "registered_types": list(runtime_registry.node_type_to_id.keys()),
        }

    @dispatcher.add_method("nodes.trigger")
    async def nodes_trigger(node_id: str, payload: Optional[Any] = None) -> Dict[str, Any]:
        """Programmatically triggers an execution on an active node (such as an InjectNode).
        
        Args:
            node_id: ID of the node to trigger.
            payload: Optional custom payload to pass into the trigger.
        """
        if not node_id:
            raise InvalidParams(message="Parameter 'node_id' is required")

        node = runtime_flows.get_node(node_id)
        if node is None:
            raise NodeNotFoundError(node_id)

        # Handle inject nodes
        if hasattr(node, "trigger") and callable(getattr(node, "trigger")):
            custom_data = {"payload": payload} if payload is not None else None
            await node.trigger(custom_data)
            return {"status": "ok", "node_id": node_id, "triggered": True}
        
        # If node has receive method, we can trigger by sending a message
        if hasattr(node, "receive") and callable(getattr(node, "receive")):
            msg = {"payload": payload} if payload is not None else {}
            await node.receive(msg)
            return {"status": "ok", "node_id": node_id, "triggered": True}

        raise NodeNotTriggerableError(node_id, getattr(node, "type", type(node).__name__))

