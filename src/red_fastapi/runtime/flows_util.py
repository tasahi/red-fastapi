""" Utility functions for flow configuration parsing and diffing.

Mirrors @node-red/runtime/lib/flows/util.js:
- parse_config
- diff_configs
"""

import copy
from typing import Any, Dict, List, Optional


def parse_config(config: List[Dict[str, Any]]) -> Dict[str, Any]:
    """ Parses a raw flow array into structured maps (allNodes, flows, subflows, configs),
    matching parseConfig() in @node-red/runtime/lib/flows/util.js.
    """
    flow: Dict[str, Any] = {
        "allNodes": {},
        "subflows": {},
        "configs": {},
        "flows": {},
        "missingTypes": []
    }

    for n in config:
        node_id = str(n.get("id", ""))
        if not node_id:
            continue
        node_copy = copy.deepcopy(n)
        flow["allNodes"][node_id] = node_copy

        node_type = n.get("type")
        if node_type == "tab":
            flow["flows"][node_id] = node_copy
            node_copy["subflows"] = {}
            node_copy["configs"] = {}
            node_copy["nodes"] = {}
            node_copy["groups"] = {}
        elif node_type == "subflow":
            flow["subflows"][node_id] = node_copy
            node_copy["configs"] = {}
            node_copy["nodes"] = {}
            node_copy["groups"] = {}
            node_copy["instances"] = []

    for n in config:
        node_type = n.get("type")
        node_id = str(n.get("id", ""))
        if node_type not in ("subflow", "tab", "group"):
            container = None
            parent_z = n.get("z")
            if parent_z in flow["flows"]:
                container = flow["flows"][parent_z]
            elif parent_z in flow["subflows"]:
                container = flow["subflows"][parent_z]

            if "x" in n and "y" in n:
                if container is not None:
                    container["nodes"][node_id] = n
            else:
                if container is not None:
                    container["configs"][node_id] = n
                else:
                    flow["configs"][node_id] = n
                    flow["configs"][node_id]["_users"] = []

    return flow


def diff_nodes(old_node: Optional[Dict[str, Any]], new_node: Optional[Dict[str, Any]]) -> bool:
    """ Checks if a node configuration has changed between deployments,
    ignoring position (x, y) and wires, matching diffNodes() in @node-red/runtime/lib/flows/util.js.
    """
    if old_node is None:
        return True
    if new_node is None:
        return True

    # Filter out x, y, wires for diff
    ignored_keys = {"x", "y", "wires"}
    old_filtered = {k: v for k, v in old_node.items() if k not in ignored_keys}
    new_filtered = {k: v for k, v in new_node.items() if k not in ignored_keys}

    return old_filtered != new_filtered


def diff_configs(old_config: Optional[Dict[str, Any]], new_config: Dict[str, Any]) -> Dict[str, Any]:
    """ Generates a diff identifying added, changed, and deleted nodes,
    matching diffConfigs() in @node-red/runtime/lib/flows/util.js.
    """
    diff: Dict[str, Any] = {
        "added": [],
        "changed": [],
        "deleted": [],
        "wiring_changed": []
    }

    if not old_config:
        diff["added"] = list(new_config.get("allNodes", {}).keys())
        return diff

    old_nodes = old_config.get("allNodes", {})
    new_nodes = new_config.get("allNodes", {})

    for nid, new_node in new_nodes.items():
        if nid not in old_nodes:
            diff["added"].append(nid)
        else:
            old_node = old_nodes[nid]
            if diff_nodes(old_node, new_node):
                diff["changed"].append(nid)
            elif old_node.get("wires") != new_node.get("wires"):
                diff["wiring_changed"].append(nid)

    for nid in old_nodes:
        if nid not in new_nodes:
            diff["deleted"].append(nid)

    return diff
