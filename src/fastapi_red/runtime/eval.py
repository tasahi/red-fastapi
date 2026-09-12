""" Property evaluation and manipulation utilities for FastAPI-Red.

Provides robust dotted/indexed path resolution and evaluation matching
RED.util.getMessageProperty, setMessageProperty, and evaluateNodeProperty
in @node-red/util/lib/util.js.
"""

import copy
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union


logger = logging.getLogger("fastapi_red.runtime.eval")


def parse_property_expr(expr: str) -> List[Union[str, int]]:
    """ Parses a property expression string like 'payload.users[0].name' or 'a["b.c"]'
    into a list of traversal keys (str or int).
    """
    if not expr:
        return []

    # Clean leading msg. or payload prefix if given explicitly
    if expr.startswith("msg."):
        expr = expr[4:]

    parts: List[Union[str, int]] = []
    # Tokenize by dot or bracket indexing: [123] or ["key"] or ['key'] or .key
    token_pattern = re.compile(r'\[(?:(?:"([^"]*)")|(?:\'([^\']*)\')|([0-9]+))\]|\.?([^.\[\]]+)')
    for match in token_pattern.finditer(expr):
        d_quoted, s_quoted, num_idx, prop = match.groups()
        if d_quoted is not None:
            parts.append(d_quoted)
        elif s_quoted is not None:
            parts.append(s_quoted)
        elif num_idx is not None:
            parts.append(int(num_idx))
        elif prop is not None and prop != "":
            parts.append(prop)

    return parts


def get_property(obj: Any, prop_path: str) -> Any:
    """ Retrieves a nested property from a dictionary/list/object hierarchy.
    Returns None if any intermediate segment does not exist.
    """
    if not prop_path or obj is None:
        return obj

    keys = parse_property_expr(prop_path)
    curr = obj
    for key in keys:
        if isinstance(curr, dict):
            if key in curr:
                curr = curr[key]
            else:
                return None
        elif isinstance(curr, list) and isinstance(key, int):
            if 0 <= key < len(curr):
                curr = curr[key]
            else:
                return None
        else:
            return None

    return curr


def set_property(obj: Any, prop_path: str, value: Any, create_missing: bool = True) -> bool:
    """ Sets a nested property in a dictionary/list structure, dynamically
    creating intermediate dictionaries or lists if needed.
    """
    if not prop_path or obj is None:
        return False

    keys = parse_property_expr(prop_path)
    if not keys:
        return False

    curr = obj
    for i in range(len(keys) - 1):
        key = keys[i]
        next_key = keys[i + 1]

        if isinstance(curr, dict):
            if key not in curr or not isinstance(curr[key], (dict, list)):
                if not create_missing:
                    return False
                curr[key] = [] if isinstance(next_key, int) else {}
            curr = curr[key]
        elif isinstance(curr, list) and isinstance(key, int):
            if key >= len(curr):
                if not create_missing:
                    return False
                while len(curr) <= key:
                    curr.append(None)
            if curr[key] is None or not isinstance(curr[key], (dict, list)):
                if not create_missing:
                    return False
                curr[key] = [] if isinstance(next_key, int) else {}
            curr = curr[key]
        else:
            return False

    final_key = keys[-1]
    if isinstance(curr, dict):
        curr[str(final_key)] = value
        return True
    elif isinstance(curr, list) and isinstance(final_key, int):
        if final_key >= len(curr):
            while len(curr) <= final_key:
                curr.append(None)
        curr[final_key] = value
        return True

    return False


def delete_property(obj: Any, prop_path: str) -> bool:
    """ Deletes a nested property from a dictionary or list hierarchy.
    """
    if not prop_path or obj is None:
        return False

    keys = parse_property_expr(prop_path)
    if not keys:
        return False

    curr = obj
    for i in range(len(keys) - 1):
        key = keys[i]
        if isinstance(curr, dict) and key in curr:
            curr = curr[key]
        elif isinstance(curr, list) and isinstance(key, int) and 0 <= key < len(curr):
            curr = curr[key]
        else:
            return False

    final_key = keys[-1]
    if isinstance(curr, dict) and final_key in curr:
        del curr[final_key]
        return True
    elif isinstance(curr, list) and isinstance(final_key, int) and 0 <= final_key < len(curr):
        curr.pop(final_key)
        return True

    return False


def evaluate_jsonata_expression(expr_str: str, msg: Optional[Dict[str, Any]] = None, node: Optional[Any] = None) -> Any:
    """ Evaluates a JSONata expression against a message or context hierarchy,
    matching RED.util.evaluateJSONataExpression.
    """
    if not expr_str:
        return None

    import jsonata

    # Context evaluation scope for JSONata
    scope_data = copy.deepcopy(msg) if msg is not None else {}

    try:
        compiled = jsonata.Jsonata(expr_str)
        return compiled.evaluate(scope_data)
    except Exception as err:
        # If JSONata fails, fallback to Python eval if suitable
        logger.debug(f"JSONata eval error on '{expr_str}': {err}")
        return None


def evaluate_value(val_type: str, val_value: Any, msg: Optional[Dict[str, Any]] = None, node: Optional[Any] = None) -> Any:
    """ Evaluates a typed property value matching RED.util.evaluateNodeProperty.
    Supports str, num, bool, json, bin, date, msg, env, jsonata, py, global, flow.
    """
    if val_type == "str":
        return str(val_value) if val_value is not None else ""
    elif val_type == "num":
        try:
            if "." in str(val_value):
                return float(val_value)
            return int(val_value)
        except (ValueError, TypeError):
            return 0
    elif val_type == "bool":
        if isinstance(val_value, bool):
            return val_value
        return str(val_value).lower() in ("true", "1")
    elif val_type == "json":
        if isinstance(val_value, (dict, list)):
            return val_value
        try:
            return json.loads(str(val_value))
        except Exception:
            return val_value
    elif val_type == "bin":
        try:
            parsed = json.loads(str(val_value))
            return bytes(parsed)
        except Exception:
            return b""
    elif val_type == "date":
        return int(time.time() * 1000)
    elif val_type == "msg":
        if msg is not None:
            return get_property(msg, str(val_value))
        return None
    elif val_type == "env":
        if node and hasattr(node, "get_env"):
            return node.get_env(str(val_value))
        return os.environ.get(str(val_value), "")
    elif val_type == "jsonata":
        return evaluate_jsonata_expression(str(val_value), msg=msg, node=node)
    elif val_type in ("py", "expr"):
        # Safe Python expression evaluation with msg and its top-level keys available
        try:
            env_scope: Dict[str, Any] = {"msg": msg, "node": node}
            if isinstance(msg, dict):
                for k, v in msg.items():
                    if k.isidentifier():
                        env_scope[k] = v
            return eval(str(val_value), {"__builtins__": {}}, env_scope)
        except Exception as err:
            logger.error(f"Expression evaluation error: {err}")
            return None
    elif val_type == "global":
        from fastapi_red.runtime.context import context_manager
        return context_manager.get_global().get(str(val_value))
    elif val_type == "flow":
        from fastapi_red.runtime.context import context_manager
        flow_id = node.z if node and hasattr(node, "z") else "default"
        return context_manager.get_flow(flow_id).get(str(val_value))
    elif val_type == "prev":
        if node and hasattr(node, "previous_value"):
            return getattr(node, "previous_value")
        return None
    elif val_type == "null":
        return None

    return val_value
