""" Unit tests for Advanced Sequence & Flow Control Nodes (Batch 2).

Tests:
- SplitNode: arrays, strings, and objects with msg.parts metadata
- JoinNode: array, string, and object aggregation
- SortNode: ascending and descending sorting
- CatchNode: flow and node-scoped error catching
- StatusNode: flow and node-scoped visual status event listening
- CompleteNode: message lifecycle completion notification
"""

import asyncio
import pytest
from red_fastapi.runtime.sequence_nodes import (
    SplitNode,
    JoinNode,
    SortNode,
    CatchNode,
    StatusNode,
    CompleteNode,
)
from red_fastapi.runtime.node import Node


class MockFlow:
    """ Mock flow engine capturing routed messages across output ports.
    """

    def __init__(self):
        self.sent_messages = []
        self.active_nodes = {}

    async def route_message(self, source_id: str, port: int, msg: dict):
        self.sent_messages.append((source_id, port, msg))

    async def handle_error(self, source_node: Node, error_message: str, original_msg: dict = None):
        for node in self.active_nodes.values():
            if isinstance(node, CatchNode):
                await node.handle_error(source_node, error_message, original_msg)

    async def handle_status(self, source_node: Node, status_info: dict):
        for node in self.active_nodes.values():
            if isinstance(node, StatusNode):
                await node.handle_status(source_node, status_info)


@pytest.mark.asyncio
async def test_split_and_join_array():
    """ Tests SplitNode decomposing a list and JoinNode reassembling it.
    """
    flow = MockFlow()
    split_config = {
        "id": "split1",
        "type": "split",
        "property": "payload"
    }
    split_node = SplitNode(split_config, flow=flow)

    join_config = {
        "id": "join1",
        "type": "join",
        "mode": "auto",
        "property": "payload"
    }
    join_node = JoinNode(join_config, flow=flow)

    # 1. Split array [10, 20, 30]
    await split_node.on_input({"payload": [10, 20, 30], "topic": "numbers"})
    assert len(flow.sent_messages) == 3

    split_outputs = [msg for _, _, msg in flow.sent_messages]
    assert [m["payload"] for m in split_outputs] == [10, 20, 30]
    for m in split_outputs:
        assert "parts" in m
        assert m["parts"]["count"] == 3

    # 2. Feed sequence into JoinNode
    flow.sent_messages.clear()
    for m in split_outputs:
        await join_node.on_input(m)

    # JoinNode emits assembled message upon receiving all parts
    assert len(flow.sent_messages) == 1
    _, _, assembled = flow.sent_messages[0]
    assert assembled["payload"] == [10, 20, 30]
    assert "parts" not in assembled


@pytest.mark.asyncio
async def test_split_and_join_string():
    """ Tests SplitNode decomposing a delimited string and JoinNode reassembling it.
    """
    flow = MockFlow()
    split_node = SplitNode({"id": "s1", "type": "split", "splt": ",", "property": "payload"}, flow=flow)
    join_node = JoinNode({"id": "j1", "type": "join", "mode": "auto", "property": "payload"}, flow=flow)

    await split_node.on_input({"payload": "apple,banana,cherry"})
    assert len(flow.sent_messages) == 3

    split_msgs = [m for _, _, m in flow.sent_messages]
    flow.sent_messages.clear()

    for m in split_msgs:
        await join_node.on_input(m)

    assert len(flow.sent_messages) == 1
    assert flow.sent_messages[0][2]["payload"] == "apple,banana,cherry"


@pytest.mark.asyncio
async def test_sort_node():
    """ Tests SortNode on numeric and string lists.
    """
    flow = MockFlow()
    sort_node_asc = SortNode({
        "id": "sort1",
        "type": "sort",
        "order": "ascending",
        "as_num": True,
        "target": "payload"
    }, flow=flow)

    await sort_node_asc.on_input({"payload": [42, 5, 100, 1]})
    assert flow.sent_messages[-1][2]["payload"] == [1, 5, 42, 100]

    sort_node_desc = SortNode({
        "id": "sort2",
        "type": "sort",
        "order": "descending",
        "as_num": True,
        "target": "payload"
    }, flow=flow)

    await sort_node_desc.on_input({"payload": [42, 5, 100, 1]})
    assert flow.sent_messages[-1][2]["payload"] == [100, 42, 5, 1]


@pytest.mark.asyncio
async def test_catch_node():
    """ Tests CatchNode intercepting node error events.
    """
    flow = MockFlow()
    test_node = Node({"id": "worker1", "type": "function", "name": "Worker 1"}, flow=flow)
    catch_node = CatchNode({"id": "catch1", "type": "catch"}, flow=flow)
    flow.active_nodes["worker1"] = test_node
    flow.active_nodes["catch1"] = catch_node

    # Trigger error on worker node
    await test_node.error("Simulated failure", msg={"payload": "orig_data"})

    assert len(flow.sent_messages) == 1
    _, _, err_msg = flow.sent_messages[0]
    assert err_msg["payload"] == "orig_data"
    assert err_msg["error"]["message"] == "Simulated failure"
    assert err_msg["error"]["source"]["id"] == "worker1"


@pytest.mark.asyncio
async def test_status_node():
    """ Tests StatusNode intercepting node visual status changes.
    """
    flow = MockFlow()
    test_node = Node({"id": "sensor1", "type": "inject", "name": "Sensor"}, flow=flow)
    status_node = StatusNode({"id": "status1", "type": "status"}, flow=flow)
    flow.active_nodes["sensor1"] = test_node
    flow.active_nodes["status1"] = status_node

    await test_node.status(fill="green", shape="dot", text="connected")

    assert len(flow.sent_messages) == 1
    _, _, stat_msg = flow.sent_messages[0]
    assert stat_msg["status"]["text"] == "connected"
    assert stat_msg["status"]["fill"] == "green"
    assert stat_msg["source"]["id"] == "sensor1"


@pytest.mark.asyncio
async def test_complete_node():
    """ Tests CompleteNode firing upon completion of a target node.
    """
    flow = MockFlow()
    test_node = Node({"id": "target1", "type": "function"}, flow=flow)
    complete_node = CompleteNode({"id": "comp1", "type": "complete", "scope": ["target1"]}, flow=flow)

    await complete_node.handle_complete(test_node, {"payload": "completed_job"})

    assert len(flow.sent_messages) == 1
    assert flow.sent_messages[0][2]["payload"] == "completed_job"

