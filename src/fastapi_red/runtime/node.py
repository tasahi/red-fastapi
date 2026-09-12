""" Base Node class for Python node implementations.

Mirrors @node-red/runtime/lib/nodes/Node.js:
- id, type, z, name, wires
- on_input
- send
- status
- error / warn
- close
"""

import copy
import logging
from typing import Any, Callable, Dict, List, Optional, Union
from fastapi_red.runtime import comms


logger = logging.getLogger("fastapi_red.runtime.node")


class Node:
    """ The base class that all Python flow runtime nodes extend,
    matching Node(n) in @node-red/runtime/lib/nodes/Node.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        self.id: str = str(config.get("id", ""))
        self.type: str = str(config.get("type", ""))
        self.z: str = str(config.get("z", ""))
        self.name: str = str(config.get("name", ""))
        self.config: Dict[str, Any] = copy.deepcopy(config)
        self.wires: List[List[str]] = config.get("wires", [])
        self.flow: Optional[Any] = flow
        self._closed: bool = False

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Subclasses implement message processing here,
        matching this.on('input', ...) in Node-RED.
        """
        pass

    async def receive(self, msg: Optional[Dict[str, Any]] = None) -> None:
        """ Entrypoint when a message arrives at this node,
        matching this.receive(msg) in Node-RED.
        """
        if self._closed:
            return
        if msg is None:
            msg = {}
        await self.on_input(msg)

    async def send(self, msg: Union[Dict[str, Any], List[Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]]], port: int = 0) -> None:
        """ Dispatches message(s) to downstream connected nodes along configured wires,
        matching this.send(msg) in @node-red/runtime/lib/nodes/Node.js.
        """
        if self._closed or not self.flow:
            return

        # Single message sent to specific output port
        if isinstance(msg, dict):
            await self.flow.route_message(self.id, port, msg)
        # Array of messages for multiple output ports: [[msg_port0], [msg_port1], ...]
        elif isinstance(msg, list):
            for out_port, port_msgs in enumerate(msg):
                if port_msgs is None:
                    continue
                if isinstance(port_msgs, dict):
                    await self.flow.route_message(self.id, out_port, port_msgs)
                elif isinstance(port_msgs, list):
                    for m in port_msgs:
                        if isinstance(m, dict):
                            await self.flow.route_message(self.id, out_port, m)

    async def status(self, fill: str = "", shape: str = "", text: str = "") -> None:
        """ Updates the node's visual status badge in the editor,
        matching this.status({...}) in @node-red/runtime/lib/nodes/Node.js.
        """
        await comms.publish_status(self.id, fill=fill, shape=shape, text=text)
        if self.flow and hasattr(self.flow, "handle_status"):
            await self.flow.handle_status(self, {"fill": fill, "shape": shape, "text": text})

    async def error(self, log_message: str, msg: Optional[Dict[str, Any]] = None) -> None:
        """ Logs an error and notifies the runtime,
        matching this.error(err, msg) in @node-red/runtime/lib/nodes/Node.js.
        """
        logger.error(f"[{self.type}:{self.name or self.id}] {log_message}")
        if self.flow and hasattr(self.flow, "handle_error"):
            await self.flow.handle_error(self, log_message, msg)


    async def warn(self, log_message: str) -> None:
        """ Logs a warning,
        matching this.warn(msg) in @node-red/runtime/lib/nodes/Node.js.
        """
        logger.warning(f"[{self.type}:{self.name or self.id}] {log_message}")

    def get_env(self, name: str) -> Any:
        """ Resolves an environment variable in the context of this node,
        checking subflow or flow context if available, falling back to os.environ.
        """
        if self.flow and hasattr(self.flow, "get_env"):
            val = self.flow.get_env(name)
            if val is not None:
                return val
        import os
        return os.environ.get(name, "")

    async def close(self) -> None:
        """ Called when the node is stopped or flow is redeployed,
        matching this.close() in @node-red/runtime/lib/nodes/Node.js.
        """
        self._closed = True
