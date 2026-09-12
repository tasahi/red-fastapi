""" Advanced Sequence and Flow Control Node implementations for FastAPI-Red.

Mirrors upstream Node-RED core nodes:
- SplitNode: Dissects arrays, strings, or objects into message sequences with msg.parts
- JoinNode: Reassembles message sequences matching msg.parts into arrays, strings, or merged objects
- SortNode: In-memory sorting of arrays or message sequences
- CatchNode: Listens for unhandled or explicitly emitted node errors
- StatusNode: Listens for node status changes
- CompleteNode: Listens for node message processing completion
"""

import asyncio
import copy
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from fastapi_red.runtime.node import Node
from fastapi_red.runtime.eval import get_property, set_property, delete_property


logger = logging.getLogger("fastapi_red.runtime.sequence_nodes")


class SplitNode(Node):
    """ Dissects arrays, strings, or objects into message sequences with msg.parts metadata,
    matching SplitNode in @node-red/nodes/core/sequence/17-split.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.property: str = config.get("property", "payload")
        self.splt_type: str = config.get("spltType", "str")
        raw_splt = config.get("splt", "\\n")
        # Unescape standard escape characters for string delimiter
        self.splt: str = (
            raw_splt.replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace("\\0", "\0")
        )
        self.array_splt: int = int(config.get("arraySplt", 1))

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Splits property into individual messages.
        """
        val = get_property(msg, self.property)
        if val is None:
            await self.send(msg)
            return

        parts_id = str(uuid.uuid4())

        # 1. Array splitting
        if isinstance(val, list):
            count = len(val)
            for idx, item in enumerate(val):
                new_msg = copy.deepcopy(msg)
                set_property(new_msg, self.property, item)
                new_msg["parts"] = {
                    "id": parts_id,
                    "type": "array",
                    "index": idx,
                    "count": count,
                    "len": 1,
                }
                await self.send(new_msg)

        # 2. String splitting
        elif isinstance(val, str):
            if self.splt_type == "len":
                length = max(1, int(self.splt))
                chunks = [val[i : i + length] for i in range(0, len(val), length)]
            else:
                chunks = val.split(self.splt)

            count = len(chunks)
            for idx, chunk in enumerate(chunks):
                new_msg = copy.deepcopy(msg)
                set_property(new_msg, self.property, chunk)
                new_msg["parts"] = {
                    "id": parts_id,
                    "type": "string",
                    "index": idx,
                    "count": count,
                    "ch": self.splt,
                }
                await self.send(new_msg)

        # 3. Object / Dict splitting
        elif isinstance(val, dict):
            items = list(val.items())
            count = len(items)
            for idx, (k, v) in enumerate(items):
                new_msg = copy.deepcopy(msg)
                set_property(new_msg, self.property, v)
                new_msg["parts"] = {
                    "id": parts_id,
                    "type": "object",
                    "key": k,
                    "index": idx,
                    "count": count,
                }
                await self.send(new_msg)
        else:
            await self.send(msg)


class JoinNode(Node):
    """ Reassembles sequenced messages matching msg.parts into arrays, strings, or objects,
    matching JoinNode in @node-red/nodes/core/sequence/17-split.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.mode: str = config.get("mode", "auto")
        self.property: str = config.get("property", "payload")
        self.joiner: str = (
            config.get("joiner", "\\n")
            .replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
        )
        self.count: int = int(config.get("count", 0))
        self.build: str = config.get("build", "array")  # string, array, object, merged

        # Pending groups: parts_id -> list of msg
        self.inflight: Dict[str, List[Dict[str, Any]]] = {}

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Buffers and aggregates sequence messages.
        """
        parts = msg.get("parts")
        if not parts or "id" not in parts:
            await self.send(msg)
            return

        parts_id = parts["id"]
        if parts_id not in self.inflight:
            self.inflight[parts_id] = []

        self.inflight[parts_id].append(copy.deepcopy(msg))
        group = self.inflight[parts_id]

        expected_count = parts.get("count") or self.count
        parts_type = parts.get("type", "array")

        if expected_count and len(group) >= expected_count:
            del self.inflight[parts_id]
            # Sort group messages by index if present
            group.sort(key=lambda m: m.get("parts", {}).get("index", 0))

            base_msg = group[-1]
            if "parts" in base_msg:
                del base_msg["parts"]

            # Auto or explicit assembly
            mode_build = parts_type if self.mode == "auto" else self.build

            if mode_build == "string":
                items = [str(get_property(m, self.property) or "") for m in group]
                joiner = parts.get("ch", self.joiner)
                set_property(base_msg, self.property, joiner.join(items))

            elif mode_build == "object":
                merged_obj = {}
                for m in group:
                    k = m.get("parts", {}).get("key")
                    v = get_property(m, self.property)
                    if k is not None:
                        merged_obj[str(k)] = v
                set_property(base_msg, self.property, merged_obj)

            else:
                # Default: array
                items = [get_property(m, self.property) for m in group]
                set_property(base_msg, self.property, items)

            await self.send(base_msg)


class SortNode(Node):
    """ Sorts payload arrays or message sequences,
    matching SortNode in @node-red/nodes/core/sequence/18-sort.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.order: str = config.get("order", "ascending")
        self.as_num: bool = config.get("as_num", False)
        self.target: str = config.get("target", "payload")
        self.target_prop: str = config.get("key", "payload")
        self.reverse: bool = self.order == "descending"

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Sorts array in message property.
        """
        val = get_property(msg, self.target)
        if isinstance(val, list):
            def sort_key(item):
                if isinstance(item, dict):
                    v = get_property(item, self.target_prop)
                else:
                    v = item
                if self.as_num:
                    try:
                        return (0, float(v))
                    except (ValueError, TypeError):
                        return (1, str(v))
                return (0, str(v))

            try:
                sorted_list = sorted(val, key=sort_key, reverse=self.reverse)
                set_property(msg, self.target, sorted_list)
            except Exception as err:
                await self.error(f"Failed to sort list: {err}", msg)

        await self.send(msg)


class CatchNode(Node):
    """ Catches errors emitted by nodes in the flow,
    matching CatchNode in @node-red/nodes/core/common/25-catch.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.scope: Optional[List[str]] = config.get("scope")
        self.uncaught: bool = config.get("uncaught", False)

    async def handle_error(self, source_node: Node, error_message: str, original_msg: Optional[Dict[str, Any]]) -> None:
        """ Called by FlowEngine when an active node emits an error.
        """
        if self._closed:
            return

        # Check scope filter
        if self.scope and source_node.id not in self.scope:
            return

        out_msg = copy.deepcopy(original_msg) if original_msg else {}
        out_msg["error"] = {
            "message": error_message,
            "source": {
                "id": source_node.id,
                "type": source_node.type,
                "name": source_node.name,
            },
        }
        await self.send(out_msg)


class StatusNode(Node):
    """ Listens to node status updates across the flow canvas,
    matching StatusNode in @node-red/nodes/core/common/25-status.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.scope: Optional[List[str]] = config.get("scope")

    async def handle_status(self, source_node: Node, status_info: Dict[str, Any]) -> None:
        """ Called by FlowEngine when an active node publishes a visual status.
        """
        if self._closed:
            return

        if self.scope and source_node.id not in self.scope:
            return

        msg = {
            "status": status_info,
            "source": {
                "id": source_node.id,
                "type": source_node.type,
                "name": source_node.name,
            },
        }
        await self.send(msg)


class CompleteNode(Node):
    """ Emits a message when targeted upstream nodes complete message execution,
    matching CompleteNode in @node-red/nodes/core/common/24-complete.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.scope: List[str] = config.get("scope", [])

    async def handle_complete(self, source_node: Node, completed_msg: Dict[str, Any]) -> None:
        """ Called by FlowEngine when a scoped node finishes message processing.
        """
        if self._closed:
            return

        if source_node.id in self.scope:
            out_msg = copy.deepcopy(completed_msg)
            await self.send(out_msg)


class LinkInNode(Node):
    """ Receives messages dispatched across workspace tabs from LinkOut or LinkCall nodes,
    matching LinkInNode in @node-red/nodes/core/common/60-link.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Passes received link message along connected wires.
        """
        await self.send(msg)


class LinkOutNode(Node):
    """ Dispatches messages to target LinkIn nodes or returns to a calling LinkCall node,
    matching LinkOutNode in @node-red/nodes/core/common/60-link.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.mode: str = config.get("mode", "link")  # "link" or "return"
        self.links: List[str] = config.get("links", [])

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Routes message to linked LinkIn nodes or handles return call stack.
        """
        if self.mode == "return":
            link_source = msg.get("_linkSource", [])
            if isinstance(link_source, list) and len(link_source) > 0:
                call_info = link_source.pop()
                caller_id = call_info.get("node")
                event_id = call_info.get("id")
                if len(link_source) == 0:
                    msg.pop("_linkSource", None)
                if self.flow:
                    caller = self.flow.get_node(caller_id)
                    if caller and hasattr(caller, "return_link_message"):
                        await caller.return_link_message(event_id, msg)
                        return
            await self.warn("Link out node in return mode has no calling context")
            return

        # Default mode: "link" -> route directly to all linked LinkIn nodes
        if self.flow:
            for target_id in self.links:
                target_node = self.flow.get_node(target_id)
                if target_node:
                    await target_node.receive(copy.deepcopy(msg))


class LinkCallNode(Node):
    """ Calls a LinkIn subflow and waits for a returning LinkOut node message,
    matching LinkCallNode in @node-red/nodes/core/common/60-link.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        links = config.get("links", [])
        self.target: str = links[0] if isinstance(links, list) and len(links) > 0 else str(links)
        self.link_type: str = config.get("linkType", "static")
        self.timeout: float = float(config.get("timeout", 30))
        self._pending_calls: Dict[str, asyncio.Future] = {}

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Dispatches message to target LinkIn and awaits response future.
        """
        target_id = msg.get("target") if self.link_type == "dynamic" else self.target
        if not self.flow:
            return

        target_node = self.flow.get_node(target_id)
        if not target_node:
            await self.error(f"Link call target node '{target_id}' not found", msg)
            return

        event_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_calls[event_id] = fut

        msg_copy = copy.deepcopy(msg)
        if "_linkSource" not in msg_copy:
            msg_copy["_linkSource"] = []
        msg_copy["_linkSource"].append({"id": event_id, "node": self.id})

        await target_node.receive(msg_copy)

        try:
            res_msg = await asyncio.wait_for(fut, timeout=self.timeout)
            await self.send(res_msg)
        except asyncio.TimeoutError:
            self._pending_calls.pop(event_id, None)
            await self.error("Link call timed out waiting for return message", msg)

    async def return_link_message(self, event_id: str, msg: Dict[str, Any]) -> None:
        """ Resolves the pending call future with the returned message.
        """
        fut = self._pending_calls.pop(event_id, None)
        if fut and not fut.done():
            fut.set_result(msg)

    async def close(self) -> None:
        """ Cancels any pending link call futures.
        """
        await super().close()
        for fut in self._pending_calls.values():
            if not fut.done():
                fut.cancel()
        self._pending_calls.clear()


