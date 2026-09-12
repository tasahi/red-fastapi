""" Flow graph execution engine for Red-Fastapi.

Mirrors @node-red/runtime/lib/flows/Flow.js:
- Instantiates active Node instances from flows.json
- Compiles wire maps for message routing
- Routes messages between connected nodes
- Manages start, stop, and clean lifecycle hooks
"""

import asyncio
import copy
import logging
from typing import Any, Dict, List, Optional, Type
from red_fastapi.runtime.node import Node
from red_fastapi.runtime.core_nodes import InjectNode, DebugNode, FunctionNode
from red_fastapi.runtime.logic_nodes import (
    ChangeNode,
    SwitchNode,
    RangeNode,
    DelayNode,
    TriggerNode,
    CommentNode,
)
from red_fastapi.runtime.sequence_nodes import (
    SplitNode,
    JoinNode,
    SortNode,
    CatchNode,
    StatusNode,
    CompleteNode,
    LinkInNode,
    LinkOutNode,
    LinkCallNode,
)
from red_fastapi.runtime.network_nodes import (
    HTTPInNode,
    HTTPResponseNode,
    HTTPRequestNode,
)
from red_fastapi.runtime.socket_nodes import (
    MQTTBrokerNode,
    MQTTInNode,
    MQTTOutNode,
    TCPInNode,
    TCPOutNode,
    UDPInNode,
    UDPOutNode,
    WebSocketInNode,
    WebSocketOutNode,
)
from red_fastapi.runtime.parser_nodes import (
    JSONNode,
    CSVNode,
    YAMLNode,
    XMLNode,
    HTMLNode,
)
from red_fastapi.runtime.storage_nodes import (
    FileNode,
    FileInNode,
    S3ConfigNode,
    S3InNode,
    S3OutNode,
)
from red_fastapi.runtime import comms


logger = logging.getLogger("red_fastapi.runtime.engine")

# Registered node type constructors
_node_constructors: Dict[str, Type[Node]] = {
    "inject": InjectNode,
    "debug": DebugNode,
    "function": FunctionNode,
    "change": ChangeNode,
    "switch": SwitchNode,
    "range": RangeNode,
    "delay": DelayNode,
    "trigger": TriggerNode,
    "comment": CommentNode,
    "split": SplitNode,
    "join": JoinNode,
    "sort": SortNode,
    "catch": CatchNode,
    "status": StatusNode,
    "complete": CompleteNode,
    "link in": LinkInNode,
    "link out": LinkOutNode,
    "link call": LinkCallNode,
    "http in": HTTPInNode,
    "http response": HTTPResponseNode,
    "http request": HTTPRequestNode,
    "mqtt-broker": MQTTBrokerNode,
    "mqtt in": MQTTInNode,
    "mqtt out": MQTTOutNode,
    "tcp in": TCPInNode,
    "tcp out": TCPOutNode,
    "udp in": UDPInNode,
    "udp out": UDPOutNode,
    "websocket in": WebSocketInNode,
    "websocket out": WebSocketOutNode,
    "json": JSONNode,
    "csv": CSVNode,
    "yaml": YAMLNode,
    "xml": XMLNode,
    "html": HTMLNode,
    "file": FileNode,
    "file in": FileInNode,
    "s3-config": S3ConfigNode,
    "s3 in": S3InNode,
    "s3 out": S3OutNode,
}


class FlowEngine:
    """ Manages active node instances and asynchronous wire message routing,
    matching Flow class in @node-red/runtime/lib/flows/Flow.js.
    """

    def __init__(self):


        self.active_nodes: Dict[str, Node] = {}
        # Wire routing map: node_id -> [ [downstream_node_id_list_for_port_0], [port_1], ... ]
        self.wire_map: Dict[str, List[List[str]]] = {}
        self.started: bool = False

    def register_type(self, type_name: str, constructor: Type[Node]) -> None:
        """ Registers a custom node constructor class.
        """
        _node_constructors[type_name] = constructor

    def get_node(self, node_id: str) -> Optional[Node]:
        """ Retrieves an active node instance by ID,
        matching flow.getNode(id) in Node-RED.
        Also searches within subflow instances if not found at root level.
        """
        node = self.active_nodes.get(node_id)
        if node:
            return node
        # Check inside subflows
        for active in self.active_nodes.values():
            if hasattr(active, "get_node"):
                child = active.get_node(node_id)
                if child:
                    return child
        return None

    async def start(self, flow_configs: List[Dict[str, Any]]) -> None:
        """ Stops any existing nodes, instantiates new nodes, builds the wire map, and starts them.
        """
        await self.stop()
        self.active_nodes.clear()
        self.wire_map.clear()

        # Step A: Collect subflow definitions and their internal nodes
        from red_fastapi.runtime.subflow import SubflowInstanceNode
        subflows_def_map: Dict[str, Dict[str, Any]] = {}
        for config in flow_configs:
            if config.get("type") == "subflow":
                sf_id = str(config.get("id", ""))
                subflows_def_map[sf_id] = copy.deepcopy(config)
                if "nodes" not in subflows_def_map[sf_id]:
                    subflows_def_map[sf_id]["nodes"] = []

        # Associate nodes whose z matches a subflow ID to that subflow definition
        for config in flow_configs:
            z = str(config.get("z", ""))
            if z in subflows_def_map and config.get("type") not in ("subflow", "tab"):
                subflows_def_map[z]["nodes"].append(copy.deepcopy(config))

        # 1. Instantiate nodes
        for config in flow_configs:
            node_id = str(config.get("id", ""))
            node_type = str(config.get("type", ""))

            # Tabs, subflow definitions, and nodes inside subflows are not root-level executable nodes
            if node_type in ("tab", "subflow", "group"):
                continue
            if str(config.get("z", "")) in subflows_def_map:
                continue

            # Build wiring index
            wires = config.get("wires", [])
            self.wire_map[node_id] = wires

            # Construct node instance
            if node_type.startswith("subflow:"):
                sf_template_id = node_type[8:]
                sf_def = subflows_def_map.get(sf_template_id, {})
                node_instance = SubflowInstanceNode(
                    config,
                    flow=self,
                    subflow_def=sf_def,
                    all_subflow_defs=subflows_def_map,
                )
            else:
                constructor = _node_constructors.get(node_type, Node)
                node_instance = constructor(config, flow=self)

            self.active_nodes[node_id] = node_instance

        # 2. Start node lifecycle (e.g. inject timer schedules)
        for node in self.active_nodes.values():
            if hasattr(node, "start") and callable(node.start):
                await node.start()

        self.started = True
        logger.info(f"FlowEngine started {len(self.active_nodes)} active nodes")

    async def stop(self) -> None:
        """ Closes all active nodes and cancels timers,
        matching flow.stop() in Node-RED.
        """
        for node in list(self.active_nodes.values()):
            try:
                await node.close()
            except Exception as err:
                logger.error(f"Error closing node {node.id}: {err}")

        self.active_nodes.clear()
        self.wire_map.clear()
        self.started = False

    async def route_message(self, source_node_id: str, output_port: int, msg: Dict[str, Any]) -> None:
        """ Dispatches a message along configured wires to downstream target nodes,
        matching Node-RED's wire dispatch pipeline.
        """
        ports = self.wire_map.get(source_node_id, [])
        if output_port >= len(ports):
            return

        target_node_ids = ports[output_port]
        for target_id in target_node_ids:
            target_node = self.active_nodes.get(target_id)
            if target_node:
                # Dispatch asynchronously without blocking caller
                asyncio.create_task(self._deliver(target_node, copy.deepcopy(msg)))

    async def _deliver(self, node: Node, msg: Dict[str, Any]) -> None:
        """ Delivers a message to a specific node instance and notifies complete nodes.
        """
        try:
            await node.receive(msg)
            # Notify any complete nodes listening for this node
            for other_node in self.active_nodes.values():
                if isinstance(other_node, CompleteNode):
                    await other_node.handle_complete(node, msg)
        except Exception as err:
            logger.error(f"Error delivering message to node {node.id}: {err}")
            await self.handle_error(node, str(err), msg)

    async def handle_error(self, source_node: Node, error_message: str, original_msg: Optional[Dict[str, Any]] = None) -> None:
        """ Dispatches error notifications to active CatchNode instances.
        """
        for node in self.active_nodes.values():
            if isinstance(node, CatchNode):
                await node.handle_error(source_node, error_message, original_msg)

    async def handle_status(self, source_node: Node, status_info: Dict[str, Any]) -> None:
        """ Dispatches status notifications to active StatusNode instances.
        """
        for node in self.active_nodes.values():
            if isinstance(node, StatusNode):
                await node.handle_status(source_node, status_info)


# Global runtime engine singleton
engine = FlowEngine()
