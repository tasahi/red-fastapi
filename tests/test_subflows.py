""" Unit tests for Subflows and Custom Modules in Red-Fastapi.

Validates:
- Subflow template definition (`type: "subflow"`)
- Subflow instantiation (`type: "subflow:<id>"`)
- Internal wire routing from entry ports (`in`) to exit ports (`out`)
- Multiple output ports mapping
- Scoped environment variables (`env`) with definition defaults and instance overrides
- Nested subflows (subflow instance inside another subflow)
- Internal node retrieval via `engine.get_node`
- Subflow status badge propagation and CatchNode handling
"""

import asyncio
import pytest
from red_fastapi.runtime.engine import FlowEngine


@pytest.mark.asyncio
async def test_simple_subflow():
    """ Tests a basic subflow taking payload, incrementing it via internal function,
    and outputting to downstream outer node.
    """
    engine = FlowEngine()

    flows = [
        # Subflow Template Definition
        {
            "id": "subflow_math",
            "type": "subflow",
            "name": "Math Incrementer",
            "in": [{"wires": [{"id": "internal_calc"}]}],
            "out": [{"wires": [{"id": "internal_calc", "port": 0}]}],
        },
        # Internal Node inside subflow_math
        {
            "id": "internal_calc",
            "type": "function",
            "z": "subflow_math",
            "func": "msg['payload'] = msg.get('payload', 0) + 10\nreturn msg",
            "wires": [[]],
        },
        # Outer Flow Tab
        {"id": "tab1", "type": "tab", "label": "Tab 1"},
        # Inject Node
        {
            "id": "n_inject",
            "type": "inject",
            "z": "tab1",
            "payload": 5,
            "payloadType": "num",
            "wires": [["n_subflow_inst"]],
        },
        # Subflow Instance
        {
            "id": "n_subflow_inst",
            "type": "subflow:subflow_math",
            "z": "tab1",
            "wires": [["n_debug"]],
        },
        # Debug Node
        {
            "id": "n_debug",
            "type": "debug",
            "z": "tab1",
            "wires": [],
        },
    ]

    await engine.start(flows)

    inject_node = engine.get_node("n_inject")
    assert inject_node is not None

    received = []
    debug_node = engine.get_node("n_debug")
    original_on_input = debug_node.on_input

    async def mock_debug_input(msg):
        received.append(msg)
        await original_on_input(msg)

    debug_node.on_input = mock_debug_input

    # Inject message: 5 + 10 -> 15
    await inject_node.trigger({"payload": 5})
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["payload"] == 15

    # Test engine.get_node finds internal node
    internal_node = engine.get_node("internal_calc")
    assert internal_node is not None

    await engine.stop()


@pytest.mark.asyncio
async def test_multi_output_subflow():
    """ Tests a subflow that has multiple output ports routing to different outer wires.
    """
    engine = FlowEngine()

    flows = [
        # Subflow Definition with 2 outputs
        {
            "id": "sf_router",
            "type": "subflow",
            "name": "Odd/Even Splitter",
            "in": [{"wires": [{"id": "sf_switch"}]}],
            "out": [
                {"wires": [{"id": "sf_switch", "port": 0}]},
                {"wires": [{"id": "sf_switch", "port": 1}]},
            ],
        },
        # Internal Switch Node
        {
            "id": "sf_switch",
            "type": "switch",
            "z": "sf_router",
            "property": "payload",
            "propertyType": "msg",
            "checkall": "true",
            "rules": [
                {"t": "lt", "v": "10", "vt": "num"},
                {"t": "gte", "v": "10", "vt": "num"},
            ],
            "wires": [[], []],
        },
        # Outer Subflow Instance
        {
            "id": "inst_router",
            "type": "subflow:sf_router",
            "z": "tab1",
            "wires": [["dest_port0"], ["dest_port1"]],
        },
        {"id": "dest_port0", "type": "function", "z": "tab1", "wires": []},
        {"id": "dest_port1", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    p0_msgs = []
    p1_msgs = []

    d0 = engine.get_node("dest_port0")
    d1 = engine.get_node("dest_port1")

    async def m0(msg):
        p0_msgs.append(msg)

    async def m1(msg):
        p1_msgs.append(msg)

    d0.on_input = m0
    d1.on_input = m1

    inst = engine.get_node("inst_router")

    # Send 5 (< 10) -> Should go to port 0
    await inst.on_input({"payload": 5})
    await asyncio.sleep(0.05)
    assert len(p0_msgs) == 1
    assert p0_msgs[0]["payload"] == 5
    assert len(p1_msgs) == 0

    # Send 15 (>= 10) -> Should go to port 1
    await inst.on_input({"payload": 15})
    await asyncio.sleep(0.05)
    assert len(p0_msgs) == 1
    assert len(p1_msgs) == 1
    assert p1_msgs[0]["payload"] == 15

    await engine.stop()


@pytest.mark.asyncio
async def test_subflow_env_variables():
    """ Tests subflow environment variable inheritance and instance overrides.
    """
    engine = FlowEngine()

    flows = [
        # Subflow Definition with default env
        {
            "id": "sf_env_test",
            "type": "subflow",
            "name": "Env Subflow",
            "env": [
                {"name": "BASE_URL", "type": "str", "value": "https://api.default.com"},
                {"name": "TIMEOUT", "type": "num", "value": 30},
                {"name": "RETRY", "type": "bool", "value": "true"},
            ],
            "in": [{"wires": [{"id": "func_env"}]}],
            "out": [{"wires": [{"id": "func_env", "port": 0}]}],
        },
        # Internal Function Node accessing env
        {
            "id": "func_env",
            "type": "function",
            "z": "sf_env_test",
            "func": (
                "msg['url'] = env.get('BASE_URL')\n"
                "msg['timeout'] = env.get('TIMEOUT')\n"
                "msg['retry'] = env.get('RETRY')\n"
                "return msg"
            ),
            "wires": [[]],
        },
        # Instance 1: Uses defaults
        {
            "id": "inst_default",
            "type": "subflow:sf_env_test",
            "z": "tab1",
            "wires": [["out1"]],
        },
        # Instance 2: Overrides BASE_URL and TIMEOUT
        {
            "id": "inst_override",
            "type": "subflow:sf_env_test",
            "z": "tab1",
            "env": [
                {"name": "BASE_URL", "type": "str", "value": "https://custom.override.com"},
                {"name": "TIMEOUT", "type": "num", "value": 99},
            ],
            "wires": [["out2"]],
        },
        {"id": "out1", "type": "function", "z": "tab1", "wires": []},
        {"id": "out2", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    res1 = []
    res2 = []

    o1 = engine.get_node("out1")
    o2 = engine.get_node("out2")

    async def cb1(msg):
        res1.append(msg)

    async def cb2(msg):
        res2.append(msg)

    o1.on_input = cb1
    o2.on_input = cb2

    inst1 = engine.get_node("inst_default")
    inst2 = engine.get_node("inst_override")

    await inst1.on_input({})
    await inst2.on_input({})
    await asyncio.sleep(0.05)

    assert len(res1) == 1
    assert res1[0]["url"] == "https://api.default.com"
    assert res1[0]["timeout"] == 30
    assert res1[0]["retry"] is True

    assert len(res2) == 1
    assert res2[0]["url"] == "https://custom.override.com"
    assert res2[0]["timeout"] == 99
    assert res2[0]["retry"] is True  # preserved default

    await engine.stop()


@pytest.mark.asyncio
async def test_nested_subflows():
    """ Tests a subflow instance placed inside another subflow definition.
    """
    engine = FlowEngine()

    flows = [
        # Child Subflow: Adds 5
        {
            "id": "sf_child",
            "type": "subflow",
            "name": "Child Add 5",
            "in": [{"wires": [{"id": "child_func"}]}],
            "out": [{"wires": [{"id": "child_func", "port": 0}]}],
        },
        {
            "id": "child_func",
            "type": "function",
            "z": "sf_child",
            "func": "msg['payload'] = msg.get('payload', 0) + 5\nreturn msg",
            "wires": [[]],
        },
        # Parent Subflow: Instantiates sf_child and doubles the result
        {
            "id": "sf_parent",
            "type": "subflow",
            "name": "Parent Workflow",
            "in": [{"wires": [{"id": "nested_child_inst"}]}],
            "out": [{"wires": [{"id": "parent_func", "port": 0}]}],
        },
        # Inside Parent: child subflow instance wired to parent_func
        {
            "id": "nested_child_inst",
            "type": "subflow:sf_child",
            "z": "sf_parent",
            "wires": [["parent_func"]],
        },
        {
            "id": "parent_func",
            "type": "function",
            "z": "sf_parent",
            "func": "msg['payload'] = msg.get('payload', 0) * 2\nreturn msg",
            "wires": [[]],
        },
        # Root Canvas Instance of Parent Subflow
        {
            "id": "root_parent_inst",
            "type": "subflow:sf_parent",
            "z": "tab1",
            "wires": [["root_result"]],
        },
        {"id": "root_result", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    root_received = []
    root_node = engine.get_node("root_result")

    async def root_cb(msg):
        root_received.append(msg)

    root_node.on_input = root_cb

    parent_inst = engine.get_node("root_parent_inst")
    # (10 + 5) * 2 = 30
    await parent_inst.on_input({"payload": 10})
    await asyncio.sleep(0.05)

    assert len(root_received) == 1
    assert root_received[0]["payload"] == 30

    await engine.stop()


@pytest.mark.asyncio
async def test_subflow_status_and_errors():
    """ Tests error bubbling and status propagation from subflow instances.
    """
    engine = FlowEngine()

    flows = [
        # Subflow Definition
        {
            "id": "sf_err",
            "type": "subflow",
            "name": "Error Subflow",
            "in": [{"wires": [{"id": "sf_err_func"}]}],
            "out": [{"wires": []}],
        },
        {
            "id": "sf_err_func",
            "type": "function",
            "z": "sf_err",
            "func": "raise ValueError('Critical failure inside subflow')",
            "wires": [[]],
        },
        # Root flow
        {
            "id": "inst_err",
            "type": "subflow:sf_err",
            "z": "tab1",
            "wires": [],
        },
        # Root CatchNode to catch error from subflow
        {
            "id": "root_catch",
            "type": "catch",
            "z": "tab1",
            "scope": None,  # catch all errors
            "wires": [["catch_dest"]],
        },
        {"id": "catch_dest", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    caught_errors = []
    cd = engine.get_node("catch_dest")

    async def cb(msg):
        caught_errors.append(msg)

    cd.on_input = cb

    sf_inst = engine.get_node("inst_err")
    await sf_inst.on_input({"payload": "test"})
    await asyncio.sleep(0.05)

    assert len(caught_errors) == 1
    assert "Critical failure inside subflow" in caught_errors[0]["error"]["message"]

    await engine.stop()
