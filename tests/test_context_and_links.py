""" Unit tests for Context Hierarchy and Link Cross-Flow Routing.

Tests:
- ContextStore & ContextManager: global, flow, and node-level isolation
- ChangeNode: setting and deleting values in flow and global contexts
- FunctionNode: accessing flow_ctx and global_ctx inside Python code blocks
- LinkInNode & LinkOutNode: cross-workspace link forwarding
- LinkCallNode & LinkOutNode(return): subflow calling, timeout, and response resolution
"""

import asyncio
import pytest
from red_fastapi.runtime.context import context_manager
from red_fastapi.runtime.node import Node
from red_fastapi.runtime.core_nodes import FunctionNode
from red_fastapi.runtime.logic_nodes import ChangeNode
from red_fastapi.runtime.sequence_nodes import LinkInNode, LinkOutNode, LinkCallNode


class MockFlow:
    """ Mock flow engine supporting active nodes lookup and message dispatch.
    """

    def __init__(self):
        self.active_nodes = {}
        self.sent_messages = []

    def get_node(self, node_id: str):
        return self.active_nodes.get(node_id)

    async def route_message(self, source_id: str, port: int, msg: dict):
        self.sent_messages.append((source_id, port, msg))


def test_context_hierarchy_isolation():
    """ Tests that global, flow, and node contexts maintain strict isolation.
    """
    context_manager.clear()
    g = context_manager.get_global()
    f1 = context_manager.get_flow("flow1")
    f2 = context_manager.get_flow("flow2")
    n1 = context_manager.get_node("node1")

    g.set("counter", 100)
    f1.set("counter", 200)
    f2.set("counter", 300)
    n1.set("counter", 400)

    assert g.get("counter") == 100
    assert f1.get("counter") == 200
    assert f2.get("counter") == 300
    assert n1.get("counter") == 400

    assert g.keys() == ["counter"]
    assert f1.keys() == ["counter"]

    g.set("counter", None)
    assert g.get("counter") is None
    assert "counter" not in g.keys()


@pytest.mark.asyncio
async def test_change_node_with_context():
    """ Tests ChangeNode writing and reading flow and global contexts.
    """
    context_manager.clear()
    flow = MockFlow()

    # Node configured to store payload into global context and read flow context
    set_node = ChangeNode({
        "id": "c1",
        "type": "change",
        "z": "flow_a",
        "rules": [
            {"t": "set", "p": "shared_var", "pt": "global", "to": "payload", "tot": "msg"},
            {"t": "set", "p": "flow_var", "pt": "flow", "to": "FlowSpecific", "tot": "str"},
        ]
    }, flow=flow)

    await set_node.on_input({"payload": "GlobalValue"})

    assert context_manager.get_global().get("shared_var") == "GlobalValue"
    assert context_manager.get_flow("flow_a").get("flow_var") == "FlowSpecific"


@pytest.mark.asyncio
async def test_function_node_with_context():
    """ Tests FunctionNode Python code reading and mutating flow and global contexts.
    """
    context_manager.clear()
    context_manager.get_global().set("app_version", "1.0.0")

    flow = MockFlow()
    func_code = (
        "current_ver = global_ctx.get('app_version')\n"
        "flow_ctx.set('invoked', True)\n"
        "msg['version'] = current_ver\n"
        "return msg"
    )

    func_node = FunctionNode({
        "id": "fn1",
        "type": "function",
        "z": "test_flow",
        "func": func_code
    }, flow=flow)

    await func_node.on_input({"payload": "hello"})

    assert len(flow.sent_messages) == 1
    _, _, out_msg = flow.sent_messages[0]
    assert out_msg["version"] == "1.0.0"
    assert context_manager.get_flow("test_flow").get("invoked") is True


@pytest.mark.asyncio
async def test_link_in_and_link_out():
    """ Tests LinkOut forwarding messages across links to a LinkIn node.
    """
    flow = MockFlow()
    link_in = LinkInNode({"id": "link_in_1", "type": "link in"}, flow=flow)
    link_out = LinkOutNode({
        "id": "link_out_1",
        "type": "link out",
        "mode": "link",
        "links": ["link_in_1"]
    }, flow=flow)

    flow.active_nodes["link_in_1"] = link_in
    flow.active_nodes["link_out_1"] = link_out

    await link_out.on_input({"payload": "cross_link_data"})

    # LinkIn should have received the message and forwarded it along its wires
    assert len(flow.sent_messages) == 1
    assert flow.sent_messages[0][0] == "link_in_1"
    assert flow.sent_messages[0][2]["payload"] == "cross_link_data"


@pytest.mark.asyncio
async def test_link_call_and_return():
    """ Tests LinkCall dispatching to a LinkIn, processing, and receiving a return from LinkOut.
    """
    flow = MockFlow()

    link_call = LinkCallNode({
        "id": "caller1",
        "type": "link call",
        "links": ["target_in"],
        "timeout": 2
    }, flow=flow)

    link_in = LinkInNode({"id": "target_in", "type": "link in"}, flow=flow)

    link_return = LinkOutNode({
        "id": "target_out",
        "type": "link out",
        "mode": "return"
    }, flow=flow)

    flow.active_nodes["caller1"] = link_call
    flow.active_nodes["target_in"] = link_in
    flow.active_nodes["target_out"] = link_return

    # Simulate link_in wired to a worker that passes msg to link_return
    async def simulate_worker():
        while len(flow.sent_messages) == 0:
            await asyncio.sleep(0.01)
        # Message arrived at link_in
        _, _, arrived_msg = flow.sent_messages.pop(0)
        arrived_msg["payload"] = arrived_msg["payload"].upper()
        # Return via link_return
        await link_return.on_input(arrived_msg)

    worker_task = asyncio.create_task(simulate_worker())

    # Trigger call from link_call
    await link_call.on_input({"payload": "call_subflow"})
    await worker_task

    # Caller receives the return message
    assert len(flow.sent_messages) == 1
    assert flow.sent_messages[0][0] == "caller1"
    assert flow.sent_messages[0][2]["payload"] == "CALL_SUBFLOW"
    assert "_linkSource" not in flow.sent_messages[0][2]
    await link_call.close()

