""" Sequence and Logic Node implementations for Red-Fastapi.

Mirrors upstream Node-RED core nodes:
- ChangeNode: Property transformation rules (set, change, delete, move)
- SwitchNode: Multi-port conditional message routing
- RangeNode: Linear numeric scaling with clamp/roll/drop actions
- DelayNode: Pauses and rate-limiting queue throttling
- TriggerNode: Timed pulses, secondary payloads, and timer reset
- CommentNode: Canvas metadata documentation node (no-op)
"""

import asyncio
import copy
import logging
import math
import random
import re
import time
from typing import Any, Dict, List, Optional
from red_fastapi.runtime.node import Node
from red_fastapi.runtime.eval import (
    get_property,
    set_property,
    delete_property,
    evaluate_value,
    evaluate_jsonata_expression,
)



logger = logging.getLogger("red_fastapi.runtime.logic_nodes")


class ChangeNode(Node):
    """ Implements rule-based property transformations (set, change, delete, move),
    matching ChangeNode in @node-red/nodes/core/function/15-change.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.rules: List[Dict[str, Any]] = config.get("rules", [])

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Applies configured transformation rules sequentially to incoming message.
        """
        for rule in self.rules:
            t = rule.get("t", "set")  # Rule type: set, change, delete, move
            p = rule.get("p", "payload")  # Target property path
            pt = rule.get("pt", "msg")  # Property container type (msg)

            if pt == "flow":
                from red_fastapi.runtime.context import context_manager
                flow_id = self.z or "default"
                store = context_manager.get_flow(flow_id)
                if t == "set":
                    to_val = rule.get("to", "")
                    tot = rule.get("tot", "str")
                    val = evaluate_value(tot, to_val, msg, node=self)
                    store.set(p, copy.deepcopy(val))
                elif t == "delete":
                    store.set(p, None)
                continue

            elif pt == "global":
                from red_fastapi.runtime.context import context_manager
                store = context_manager.get_global()
                if t == "set":
                    to_val = rule.get("to", "")
                    tot = rule.get("tot", "str")
                    val = evaluate_value(tot, to_val, msg, node=self)
                    store.set(p, copy.deepcopy(val))
                elif t == "delete":
                    store.set(p, None)
                continue

            if t == "set":
                to_val = rule.get("to", "")
                tot = rule.get("tot", "str")
                val = evaluate_value(tot, to_val, msg, node=self)
                set_property(msg, p, copy.deepcopy(val))


            elif t == "change":
                from_val = rule.get("from", "")
                from_type = rule.get("fromt", "str")
                to_val = rule.get("to", "")
                to_type = rule.get("tot", "str")

                target_val = get_property(msg, p)
                if isinstance(target_val, str):
                    replacement = str(evaluate_value(to_type, to_val, msg, node=self))
                    if from_type == "re":
                        try:
                            new_str = re.sub(from_val, replacement, target_val)
                            set_property(msg, p, new_str)
                        except Exception as err:
                            await self.error(f"Invalid regex: {err}", msg)
                    else:
                        new_str = target_val.replace(str(from_val), replacement)
                        set_property(msg, p, new_str)

            elif t == "delete":
                delete_property(msg, p)

            elif t == "move":
                to_prop = rule.get("to", "")
                val = get_property(msg, p)
                delete_property(msg, p)
                set_property(msg, to_prop, val)

        await self.send(msg)


class SwitchNode(Node):
    """ Routes messages conditionally across multiple output ports based on rules,
    matching SwitchNode in @node-red/nodes/core/function/10-switch.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.property: str = config.get("property", "payload")
        self.property_type: str = config.get("propertyType", "msg")
        self.rules: List[Dict[str, Any]] = config.get("rules", [])
        self.checkall: bool = config.get("checkall", "true") == "true" or config.get("checkall", True) is True

    def _eval_rule(self, rule: Dict[str, Any], val: Any, msg: Dict[str, Any]) -> bool:
        """ Evaluates a single rule operator against value.
        """
        op = rule.get("t", "eq")
        v = rule.get("v")
        vt = rule.get("vt", "str")
        v2 = rule.get("v2")
        v2t = rule.get("v2t", "str")

        v_evaluated = evaluate_value(vt, v, msg, node=self) if v is not None else None
        v2_evaluated = evaluate_value(v2t, v2, msg, node=self) if v2 is not None else None

        # Operator matching
        if op == "eq":
            if isinstance(val, (int, float)) and isinstance(v_evaluated, (int, float)):
                return val == v_evaluated
            return str(val) == str(v_evaluated)
        elif op == "neq":
            if isinstance(val, (int, float)) and isinstance(v_evaluated, (int, float)):
                return val != v_evaluated
            return str(val) != str(v_evaluated)
        elif op == "lt":
            try:
                return float(val) < float(v_evaluated)
            except (ValueError, TypeError):
                return False
        elif op == "lte":
            try:
                return float(val) <= float(v_evaluated)
            except (ValueError, TypeError):
                return False
        elif op == "gt":
            try:
                return float(val) > float(v_evaluated)
            except (ValueError, TypeError):
                return False
        elif op == "gte":
            try:
                return float(val) >= float(v_evaluated)
            except (ValueError, TypeError):
                return False
        elif op == "btwn":
            try:
                num = float(val)
                low = float(v_evaluated)
                high = float(v2_evaluated)
                return (low <= num <= high) or (high <= num <= low)
            except (ValueError, TypeError):
                return False
        elif op == "cont":
            return str(v_evaluated) in str(val)
        elif op == "regex":
            try:
                case_insensitive = rule.get("case", False)
                flags = re.IGNORECASE if case_insensitive else 0
                return bool(re.search(str(v_evaluated), str(val), flags=flags))
            except Exception:
                return False
        elif op == "true":
            return val is True or str(val).lower() == "true"
        elif op == "false":
            return val is False or str(val).lower() == "false"
        elif op == "null":
            return val is None
        elif op == "nnull":
            return val is not None
        elif op == "empty":
            if val is None:
                return True
            if isinstance(val, (str, list, dict, bytes)):
                return len(val) == 0
            return False
        elif op == "nempty":
            if val is None:
                return False
            if isinstance(val, (str, list, dict, bytes)):
                return len(val) > 0
            return True
        elif op == "jsonata_exp":
            res = evaluate_jsonata_expression(str(v), msg=msg, node=self)
            return bool(res)
        elif op in ("exp", "py"):
            res = evaluate_value("py", v, msg=msg, node=self)
            return bool(res)
        elif op == "else":
            return True

        return False

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Evaluates message property against rules and routes to matched ports.

        """
        val = get_property(msg, self.property) if self.property_type == "msg" else None
        num_rules = len(self.rules)
        if num_rules == 0:
            return

        output: List[Optional[Dict[str, Any]]] = [None] * num_rules
        matched_any = False

        for idx, rule in enumerate(self.rules):
            if rule.get("t") == "else":
                if not matched_any:
                    output[idx] = copy.deepcopy(msg)
                    matched_any = True
                continue

            if self._eval_rule(rule, val, msg):
                output[idx] = copy.deepcopy(msg)
                matched_any = True
                if not self.checkall:
                    # Stop checking rules after first match
                    break

        await self.send(output)


class RangeNode(Node):
    """ Scales numeric values linearly from one range to another,
    matching RangeNode in @node-red/nodes/core/function/16-range.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.action: str = config.get("action", "scale")
        self.round_result: bool = config.get("round", False)
        self.minin: float = float(config.get("minin", 0))
        self.maxin: float = float(config.get("maxin", 100))
        self.minout: float = float(config.get("minout", 0))
        self.maxout: float = float(config.get("maxout", 100))
        self.property: str = config.get("property", "payload")

        if self.minin > self.maxin:
            self.minin, self.maxin = self.maxin, self.minin
            self.minout, self.maxout = self.maxout, self.minout

        if self.round_result:
            self.minout = math.ceil(self.minout)
            self.maxout = math.floor(self.maxout)

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Scales input number according to configured range parameters.
        """
        raw_val = get_property(msg, self.property)
        if raw_val is None:
            await self.send(msg)
            return

        try:
            n = float(raw_val)
        except (ValueError, TypeError):
            await self.warn(f"Range node received non-numeric value: {raw_val}")
            return

        if self.action == "drop":
            if n < self.minin or n > self.maxin:
                return

        if self.action == "clamp":
            if n < self.minin:
                n = self.minin
            elif n > self.maxin:
                n = self.maxin

        if self.action == "roll":
            divisor = self.maxin - self.minin
            if divisor != 0:
                n = ((n - self.minin) % divisor + divisor) % divisor + self.minin

        in_span = self.maxin - self.minin
        if in_span == 0:
            res = self.minout
        else:
            res = ((n - self.minin) / in_span * (self.maxout - self.minout)) + self.minout

        if self.round_result:
            res = round(res)

        set_property(msg, self.property, res)
        await self.send(msg)


class DelayNode(Node):
    """ Implements pause delays and rate-limiting queues,
    matching DelayNode in @node-red/nodes/core/function/89-delay.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.pause_type: str = config.get("pauseType", "delay")
        self.timeout: float = float(config.get("timeout", 5))
        self.timeout_units: str = config.get("timeoutUnits", "seconds")

        # Convert delay timeout to seconds
        if self.timeout_units == "milliseconds":
            self.delay_seconds = self.timeout / 1000.0
        elif self.timeout_units == "minutes":
            self.delay_seconds = self.timeout * 60.0
        elif self.timeout_units == "hours":
            self.delay_seconds = self.timeout * 3600.0
        else:
            self.delay_seconds = self.timeout

        self.random_first: float = float(config.get("randomFirst", 1))
        self.random_last: float = float(config.get("randomLast", 5))
        self.random_units: str = config.get("randomUnits", "seconds")
        mult = 1.0
        if self.random_units == "milliseconds":
            mult = 0.001
        elif self.random_units == "minutes":
            mult = 60.0
        self.random_first_sec = self.random_first * mult
        self.random_last_sec = self.random_last * mult

        # Rate limiting configuration
        self.rate: float = float(config.get("rate", 1))
        self.rate_units: str = config.get("rateUnits", "second")
        rate_unit_mult = 1.0
        if self.rate_units == "minute":
            rate_unit_mult = 60.0
        elif self.rate_units == "hour":
            rate_unit_mult = 3600.0

        self.rate_interval = rate_unit_mult / max(self.rate, 0.001)
        self.drop: bool = config.get("drop", False)

        # Rate limiting queue & worker task
        self.queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        if self.pause_type == "rate":
            self._worker_task = asyncio.create_task(self._rate_limit_worker())

    async def _rate_limit_worker(self) -> None:
        """ Asynchronous worker draining the message queue at the designated rate.
        """
        try:
            while not self._closed:
                msg = await self.queue.get()
                if self._closed:
                    break
                await self.send(msg)
                await asyncio.sleep(self.rate_interval)
        except asyncio.CancelledError:
            pass

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Handles message delay or rate limiting enqueueing.
        """
        # Dynamic reset message check
        if msg.get("reset") is True:
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            return

        if self.pause_type == "delay":
            asyncio.create_task(self._delayed_send(msg, self.delay_seconds))

        elif self.pause_type == "random":
            wait_time = random.uniform(min(self.random_first_sec, self.random_last_sec), max(self.random_first_sec, self.random_last_sec))
            asyncio.create_task(self._delayed_send(msg, wait_time))

        elif self.pause_type == "rate":
            if self.drop and self.queue.qsize() > 0:
                # Drop incoming messages if one is already waiting
                return
            await self.queue.put(msg)

    async def _delayed_send(self, msg: Dict[str, Any], seconds: float) -> None:
        """ Waits for specified seconds then sends message if not closed.
        """
        try:
            await asyncio.sleep(seconds)
            if not self._closed:
                await self.send(msg)
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        """ Clean up background tasks.
        """
        await super().close()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()


class TriggerNode(Node):
    """ Emits an initial message then waits duration before sending secondary payload,
    matching TriggerNode in @node-red/nodes/core/function/89-trigger.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.op1: str = config.get("op1", "1")
        self.op1type: str = config.get("op1type", "str")
        self.op2: str = config.get("op2", "0")
        self.op2type: str = config.get("op2type", "str")
        self.duration: float = float(config.get("duration", 250))
        self.units: str = config.get("units", "ms")
        self.extend: bool = str(config.get("extend", "false")).lower() == "true"
        self.reset_prop: str = config.get("reset", "")

        # Calculate duration in seconds
        mult = 0.001
        if self.units == "s":
            mult = 1.0
        elif self.units == "min":
            mult = 60.0
        elif self.units == "hr":
            mult = 3600.0
        self.delay_seconds = self.duration * mult

        self._current_task: Optional[asyncio.Task] = None

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Processes trigger pulse, payload evaluation, and scheduled follow-up.
        """
        # Check for reset property on message
        if self.reset_prop and get_property(msg, self.reset_prop) is not None:
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()
            return
        if msg.get("reset") is True:
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()
            return

        # If extend is enabled and a timer is active, extend it
        if self.extend and self._current_task and not self._current_task.done():
            self._current_task.cancel()

        # Emit initial payload (op1) if not nulled
        if self.op1type != "nul":
            msg1 = copy.deepcopy(msg)
            val1 = evaluate_value(self.op1type, self.op1, msg, node=self)
            msg1["payload"] = val1
            await self.send(msg1)

        # Schedule secondary payload (op2)
        if self.op2type != "nul":
            self._current_task = asyncio.create_task(self._scheduled_second_send(copy.deepcopy(msg)))

    async def _scheduled_second_send(self, msg: Dict[str, Any]) -> None:
        """ Waits for delay duration and emits op2.
        """
        try:
            await asyncio.sleep(self.delay_seconds)
            if not self._closed:
                val2 = evaluate_value(self.op2type, self.op2, msg, node=self)
                msg["payload"] = val2
                await self.send(msg)
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        """ Cancels active trigger timers.
        """
        await super().close()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()


class CommentNode(Node):
    """ Documentation placeholder node on workspace canvas (no-op in execution engine),
    matching CommentNode in @node-red/nodes/core/common/90-comment.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Comment node is a passive metadata node; ignores runtime messages.
        """
        pass

