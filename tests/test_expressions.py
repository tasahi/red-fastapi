""" Unit tests for the Expression Evaluator (JSONata and Python Expressions) in FastAPI-Red.

Validates:
- Direct JSONata expression evaluation: object projection, arithmetic, string concatenation, and array filtering
- evaluate_value with val_type="jsonata"
- evaluate_value with val_type="py" (Python expressions)
- ChangeNode with tot="jsonata" and tot="py"
- SwitchNode with rule op="jsonata_exp" and op="py"
"""

import asyncio
import pytest
from fastapi_red.runtime.eval import evaluate_jsonata_expression, evaluate_value
from fastapi_red.runtime.engine import FlowEngine


def test_jsonata_direct_evaluations():
    """ Tests standalone JSONata expressions with various structures.
    """
    msg = {
        "payload": {
            "order": {
                "id": "ord_100",
                "customer": {"first": "Alice", "last": "Smith"},
                "items": [
                    {"sku": "A1", "price": 10, "qty": 2},
                    {"sku": "B2", "price": 25, "qty": 1},
                ],
            }
        }
    }

    # 1. Path lookup
    res_id = evaluate_jsonata_expression("payload.order.id", msg)
    assert res_id == "ord_100"

    # 2. String concatenation
    res_name = evaluate_jsonata_expression("payload.order.customer.first & ' ' & payload.order.customer.last", msg)
    assert res_name == "Alice Smith"

    # 3. Arithmetic operations
    res_math = evaluate_jsonata_expression("payload.order.items[0].price * payload.order.items[0].qty", msg)
    assert res_math == 20

    # 4. Filtering expression
    res_filtered = evaluate_jsonata_expression("payload.order.items[price > 15].sku", msg)
    assert res_filtered == "B2"


def test_evaluate_value_jsonata_and_py():
    """ Tests evaluate_value handling jsonata and py types.
    """
    msg = {"payload": 50, "ratio": 0.2}

    # evaluate_value with jsonata
    res_jsonata = evaluate_value("jsonata", "payload * ratio", msg=msg)
    assert res_jsonata == 10.0

    # evaluate_value with py
    res_py = evaluate_value("py", "payload * ratio", msg=msg)
    assert res_py == 10.0


@pytest.mark.asyncio
async def test_change_node_with_jsonata():
    """ Tests ChangeNode rule using JSONata expression to compute payload property.
    """
    engine = FlowEngine()

    flows = [
        {"id": "tab1", "type": "tab", "label": "Tab 1"},
        {
            "id": "change_jsonata",
            "type": "change",
            "z": "tab1",
            "rules": [
                {
                    "t": "set",
                    "p": "summary.total",
                    "pt": "msg",
                    "to": "items[0].cost + items[1].cost",
                    "tot": "jsonata",
                },
                {
                    "t": "set",
                    "p": "summary.fullName",
                    "pt": "msg",
                    "to": "user.fname & ' ' & user.lname",
                    "tot": "jsonata",
                },
            ],
            "wires": [["out_dest"]],
        },
        {"id": "out_dest", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    results = []
    engine.get_node("out_dest").on_input = lambda m: results.append(m) or asyncio.sleep(0)

    node = engine.get_node("change_jsonata")
    input_msg = {
        "user": {"fname": "Grace", "lname": "Hopper"},
        "items": [{"cost": 15}, {"cost": 45}],
    }
    await node.on_input(input_msg)
    await asyncio.sleep(0.02)

    assert len(results) == 1
    res = results[0]
    assert res["summary"]["total"] == 60
    assert res["summary"]["fullName"] == "Grace Hopper"

    await engine.stop()


@pytest.mark.asyncio
async def test_switch_node_with_jsonata_exp():
    """ Tests SwitchNode conditional branching using jsonata_exp rules.
    """
    engine = FlowEngine()

    flows = [
        {"id": "tab1", "type": "tab", "label": "Tab 1"},
        {
            "id": "switch_exp",
            "type": "switch",
            "z": "tab1",
            "checkall": "true",
            "rules": [
                {"t": "jsonata_exp", "v": "score >= 80"},
                {"t": "jsonata_exp", "v": "score < 80"},
            ],
            "wires": [["pass_dest"], ["fail_dest"]],
        },
        {"id": "pass_dest", "type": "function", "z": "tab1", "wires": []},
        {"id": "fail_dest", "type": "function", "z": "tab1", "wires": []},
    ]

    await engine.start(flows)

    passes = []
    fails = []
    engine.get_node("pass_dest").on_input = lambda m: passes.append(m) or asyncio.sleep(0)
    engine.get_node("fail_dest").on_input = lambda m: fails.append(m) or asyncio.sleep(0)

    node = engine.get_node("switch_exp")

    # Message 1: score 95 -> pass
    await node.on_input({"score": 95})
    await asyncio.sleep(0.02)
    assert len(passes) == 1
    assert len(fails) == 0

    # Message 2: score 60 -> fail
    await node.on_input({"score": 60})
    await asyncio.sleep(0.02)
    assert len(passes) == 1
    assert len(fails) == 1

    await engine.stop()

