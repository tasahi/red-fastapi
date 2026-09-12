""" Core node implementations in Python:
- InjectNode (20-inject)
- DebugNode (21-debug)
- FunctionNode (10-function)
"""

import asyncio
import copy
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi_red.runtime.node import Node
from fastapi_red.runtime import comms


logger = logging.getLogger("fastapi_red.nodes.core")


class InjectNode(Node):
    """ Inject node: Generates messages at intervals or when triggered manually via POST /inject/:id.
    Mirrors @node-red/nodes/core/common/20-inject.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.props = config.get("props", [{"p": "payload"}, {"p": "topic", "vt": "str"}])
        self.repeat = config.get("repeat")
        self.once = config.get("once", False)
        self.once_delay = float(config.get("onceDelay", 0.1))
        self._interval_task: Optional[asyncio.Task] = None
        self._once_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """ Schedules initial delay and recurring timer loops.
        """
        if self.once:
            self._once_task = asyncio.create_task(self._run_once())
        elif self.repeat:
            self._schedule_repeater()

    async def _run_once(self) -> None:
        """ Handles initial run-once delay.
        """
        try:
            await asyncio.sleep(self.once_delay)
            await self.trigger()
            self._schedule_repeater()
        except asyncio.CancelledError:
            pass

    def _schedule_repeater(self) -> None:
        """ Starts recurring interval timer loop if repeat is configured.
        """
        try:
            repeat_secs = float(self.repeat) if self.repeat else 0
            if repeat_secs > 0:
                self._interval_task = asyncio.create_task(self._interval_loop(repeat_secs))
        except (ValueError, TypeError):
            pass

    async def _interval_loop(self, interval: float) -> None:
        """ Background recurring injection loop.
        """
        try:
            while not self._closed:
                await asyncio.sleep(interval)
                await self.trigger()
        except asyncio.CancelledError:
            pass

    async def trigger(self, custom_msg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """ Constructs the injected msg dictionary and dispatches downstream.
        """
        msg: Dict[str, Any] = {
            "_msgid": uuid.uuid4().hex[:16]
        }

        # Handle user-configured properties
        payload_val: Any = int(time.time() * 1000)  # default timestamp
        topic_val: str = self.config.get("topic", "")

        # Evaluate properties list
        for prop in self.props:
            prop_name = prop.get("p", "payload")
            prop_type = prop.get("vt", "date")
            prop_val = prop.get("v")

            val: Any
            if prop_type == "date":
                val = int(time.time() * 1000)
            elif prop_type == "str":
                val = str(prop_val or "")
            elif prop_type == "num":
                try:
                    val = float(prop_val) if "." in str(prop_val) else int(prop_val)
                except Exception:
                    val = 0
            elif prop_type == "bool":
                val = str(prop_val).lower() == "true"
            elif prop_type == "json":
                try:
                    val = json.loads(prop_val)
                except Exception:
                    val = prop_val
            else:
                val = prop_val if prop_val is not None else int(time.time() * 1000)

            msg[prop_name] = val

        # Merge custom payload if provided (from POST /inject/:id)
        if custom_msg:
            msg.update(custom_msg)

        await self.send(msg)
        return msg

    async def close(self) -> None:
        """ Cancels scheduled interval timers on shutdown.
        """
        await super().close()
        if self._once_task:
            self._once_task.cancel()
        if self._interval_task:
            self._interval_task.cancel()


class DebugNode(Node):
    """ Debug node: Emits received messages to console and WebSocket /comms for editor Debug sidebar.
    Mirrors @node-red/nodes/core/common/21-debug.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.active: bool = config.get("active", True)
        self.complete: str = str(config.get("complete", "payload"))
        self.tosidebar: bool = config.get("tosidebar", True)
        self.console: bool = config.get("console", False)
        self.tostatus: bool = config.get("tostatus", False)

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Processes incoming message and publishes debug events.
        """
        if not self.active:
            return

        # Extract target property to display
        display_val: Any
        if self.complete in ("true", True):
            display_val = msg
        elif self.complete in ("false", False, "payload"):
            display_val = msg.get("payload")
        else:
            display_val = msg.get(self.complete)

        # 1. Update node status if tostatus is enabled
        if self.tostatus:
            status_text = str(display_val)[:32]
            await self.status(fill="grey", shape="dot", text=status_text)

        # 2. Output to console if enabled
        if self.console:
            logger.info(f"[{self.name or self.id}] {display_val}")

        # 3. Publish to WebSocket /comms for frontend Debug sidebar
        if self.tosidebar:
            debug_packet = {
                "id": self.id,
                "name": self.name or "debug",
                "topic": msg.get("topic", ""),
                "msg": {
                    "payload": display_val,
                    "_msgid": msg.get("_msgid", ""),
                    **{k: v for k, v in msg.items() if k not in ("payload", "_msgid")}
                }
            }
            await comms.publish("debug", debug_packet, retain=False)


class FunctionNode(Node):
    """ Function node: Executes Python code snippets with msg passed in local scope.
    Mirrors @node-red/nodes/core/function/10-function.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.func_code: str = config.get("func", "")
        self.compiled_code: Optional[Any] = None
        self._compile()

    def _compile(self) -> None:
        """ Pre-compiles the user-provided Python code block.
        """
        if not self.func_code:
            return
        # If code contains top-level return without function wrapper, wrap in an async callable
        indented = "\n".join("    " + line for line in self.func_code.splitlines())
        wrapper = f"async def _user_function(msg, node, flow_ctx, global_ctx, env=None, flow=None):\n{indented}\n"
        namespace: Dict[str, Any] = {}

        try:
            exec(wrapper, namespace)
            self.compiled_code = namespace.get("_user_function")
        except Exception as err:
            logger.error(f"Function node {self.id} compilation error: {err}")
            self.compiled_code = None

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Executes the Python function block and dispatches the returned message.
        """
        if not self.compiled_code:
            # Fallback: pass through unmodified if no code or compile failed
            await self.send(msg)
            return

        # Prepare execution sandbox
        msg_copy = copy.deepcopy(msg)
        try:
            from fastapi_red.runtime.context import context_manager
            flow_id = self.z or "default"
            flow_ctx = context_manager.get_flow(flow_id)
            global_ctx = context_manager.get_global()
            
            # Scoped env helper
            class _EnvAccessor:
                def __init__(self, node):
                    self._node = node
                def get(self, key, default=""):
                    val = self._node.get_env(key)
                    return val if val is not None and val != "" else default
                def __getitem__(self, key):
                    val = self.get(key)
                    if not val:
                        raise KeyError(key)
                    return val

            env_helper = _EnvAccessor(self)
            res = await self.compiled_code(msg_copy, self, flow_ctx, global_ctx, env_helper)
            if res is not None:
                await self.send(res)
        except Exception as err:
            await self.error(f"Function error: {err}", msg)

            await self.status(fill="red", shape="dot", text="error")
