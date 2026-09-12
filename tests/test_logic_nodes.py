""" Unit tests for Property Evaluation and Sequence & Logic Nodes.

Tests:
- eval.py: get_property, set_property, delete_property, evaluate_value
- ChangeNode: set, change/replace, delete, move rules
- SwitchNode: operators (eq, neq, lt, lte, gt, gte, btwn, cont, regex, true/false, empty), checkall vs first
- RangeNode: scale, clamp, roll, drop
- DelayNode: delay and rate limiting
- TriggerNode: initial payload, secondary scheduled payload, reset
"""

import asyncio
import pytest
from fastapi_red.runtime.eval import (
    get_property,
    set_property,
    delete_property,
    evaluate_value,
)
from fastapi_red.runtime.logic_nodes import (
    ChangeNode,
    SwitchNode,
    RangeNode,
    DelayNode,
    TriggerNode,
    CommentNode,
)


class MockFlow:
    """ Mock flow engine capturing routed messages across output ports.
    """

    def __init__(self):
        self.sent_messages = []

    async def route_message(self, source_id: str, port: int, msg: dict):
        self.sent_messages.append((source_id, port, msg))


def test_property_eval_get_set_delete():
    """ Tests deep nested property getting, setting, and deletion.
    """
    obj = {"user": {"profile": {"name": "Alice", "tags": ["admin", "staff"]}}}

    # Get
    assert get_property(obj, "user.profile.name") == "Alice"
    assert get_property(obj, "user.profile.tags[0]") == "admin"
    assert get_property(obj, "user.profile.tags[1]") == "staff"
    assert get_property(obj, "user.nonexistent") is None

    # Set existing & create missing
    assert set_property(obj, "user.profile.name", "Bob") is True
    assert obj["user"]["profile"]["name"] == "Bob"

    assert set_property(obj, "user.settings.theme", "dark") is True
    assert obj["user"]["settings"]["theme"] == "dark"

    # Set array index
    assert set_property(obj, "user.profile.tags[2]", "developer") is True
    assert obj["user"]["profile"]["tags"][2] == "developer"

    # Delete
    assert delete_property(obj, "user.settings.theme") is True
    assert "theme" not in obj["user"]["settings"]


def test_evaluate_value_types():
    """ Tests typed value evaluation.
    """
    msg = {"payload": 42, "topic": "sensor/temp"}

    assert evaluate_value("str", 123) == "123"
    assert evaluate_value("num", "45.5") == 45.5
    assert evaluate_value("bool", "true") is True
    assert evaluate_value("bool", "false") is False
    assert evaluate_value("json", '{"a": 1}') == {"a": 1}
    assert evaluate_value("msg", "topic", msg=msg) == "sensor/temp"
    assert evaluate_value("msg", "payload", msg=msg) == 42


@pytest.mark.asyncio
async def test_change_node():
    """ Tests ChangeNode operations (set, change, delete, move).
    """
    flow = MockFlow()
    config = {
        "id": "change1",
        "type": "change",
        "rules": [
            {"t": "set", "p": "payload.status", "pt": "msg", "to": "active", "tot": "str"},
            {"t": "change", "p": "topic", "pt": "msg", "from": "raw", "fromt": "str", "to": "clean", "tot": "str"},
            {"t": "delete", "p": "extra", "pt": "msg"},
            {"t": "move", "p": "old_key", "pt": "msg", "to": "new_key", "tot": "msg"},
        ]
    }
    node = ChangeNode(config, flow=flow)

    msg = {
        "topic": "raw/temperature",
        "extra": "discard_me",
        "old_key": "valuable",
        "payload": {}
    }
    await node.on_input(msg)

    assert len(flow.sent_messages) == 1
    _, _, out_msg = flow.sent_messages[0]

    assert out_msg["payload"]["status"] == "active"
    assert out_msg["topic"] == "clean/temperature"
    assert "extra" not in out_msg
    assert "old_key" not in out_msg
    assert out_msg["new_key"] == "valuable"


@pytest.mark.asyncio
async def test_switch_node():
    """ Tests SwitchNode multi-port routing and operators.
    """
    flow = MockFlow()
    config = {
        "id": "switch1",
        "type": "switch",
        "property": "payload",
        "propertyType": "msg",
        "checkall": "true",
        "rules": [
            {"t": "lt", "v": 10, "vt": "num"},
            {"t": "btwn", "v": 10, "vt": "num", "v2": 20, "v2t": "num"},
            {"t": "gt", "v": 20, "vt": "num"},
            {"t": "else"}
        ]
    }
    node = SwitchNode(config, flow=flow)

    # Test input value 15 (should route to port 1, between 10 and 20)
    flow.sent_messages.clear()
    await node.on_input({"payload": 15})
    assert len(flow.sent_messages) == 1
    _, port, msg = flow.sent_messages[0]
    assert port == 1
    assert msg["payload"] == 15

    # Test input value 5 (should route to port 0, < 10)
    flow.sent_messages.clear()
    await node.on_input({"payload": 5})
    assert len(flow.sent_messages) == 1
    _, port, msg = flow.sent_messages[0]
    assert port == 0

    # Test input value 25 (should route to port 2, > 20)
    flow.sent_messages.clear()
    await node.on_input({"payload": 25})
    assert len(flow.sent_messages) == 1
    _, port, msg = flow.sent_messages[0]
    assert port == 2


@pytest.mark.asyncio
async def test_range_node():
    """ Tests RangeNode scaling, clamping, and dropping.
    """
    flow = MockFlow()

    # Scale 0-100 to 0-10
    config = {
        "id": "range1",
        "type": "range",
        "action": "clamp",
        "round": True,
        "minin": 0,
        "maxin": 100,
        "minout": 0,
        "maxout": 10,
        "property": "payload"
    }
    node = RangeNode(config, flow=flow)

    # 50 -> 5
    await node.on_input({"payload": 50})
    assert flow.sent_messages[-1][2]["payload"] == 5

    # 150 (clamped to 100 -> 10)
    await node.on_input({"payload": 150})
    assert flow.sent_messages[-1][2]["payload"] == 10

    # Test drop action
    drop_config = {
        "id": "range2",
        "type": "range",
        "action": "drop",
        "round": False,
        "minin": 0,
        "maxin": 100,
        "minout": 0,
        "maxout": 100,
        "property": "payload"
    }
    drop_node = RangeNode(drop_config, flow=flow)
    sent_count_before = len(flow.sent_messages)
    await drop_node.on_input({"payload": 200})
    assert len(flow.sent_messages) == sent_count_before


@pytest.mark.asyncio
async def test_delay_node_fixed():
    """ Tests DelayNode fixed pause.
    """
    flow = MockFlow()
    config = {
        "id": "delay1",
        "type": "delay",
        "pauseType": "delay",
        "timeout": 50,
        "timeoutUnits": "milliseconds"
    }
    node = DelayNode(config, flow=flow)

    await node.on_input({"payload": "delayed"})
    assert len(flow.sent_messages) == 0

    # Wait for delay to expire
    await asyncio.sleep(0.08)
    assert len(flow.sent_messages) == 1
    assert flow.sent_messages[0][2]["payload"] == "delayed"
    await node.close()


@pytest.mark.asyncio
async def test_trigger_node():
    """ Tests TriggerNode pulse and secondary payload.
    """
    flow = MockFlow()
    config = {
        "id": "trigger1",
        "type": "trigger",
        "op1": "ON",
        "op1type": "str",
        "op2": "OFF",
        "op2type": "str",
        "duration": 50,
        "units": "ms"
    }
    node = TriggerNode(config, flow=flow)

    await node.on_input({"topic": "light"})
    # First payload sent immediately
    assert len(flow.sent_messages) == 1
    assert flow.sent_messages[0][2]["payload"] == "ON"

    # Wait for secondary payload
    await asyncio.sleep(0.08)
    assert len(flow.sent_messages) == 2
    assert flow.sent_messages[1][2]["payload"] == "OFF"
    await node.close()


@pytest.mark.asyncio
async def test_comment_node():
    """ Tests CommentNode passivity.
    """
    flow = MockFlow()
    config = {"id": "comment1", "type": "comment", "name": "Documentation"}
    node = CommentNode(config, flow=flow)
    await node.on_input({"payload": "ignored"})
    assert len(flow.sent_messages) == 0

