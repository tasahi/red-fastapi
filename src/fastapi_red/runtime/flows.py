""" Runtime flow management engine.

Mirrors @node-red/runtime/lib/flows/index.js:
- init
- loadFlows
- getFlows
- setFlows
- getFlow
- addFlow
- updateFlow
- deleteFlow
- getState
- setState
- getNode
"""

from typing import Any, Dict, List, Optional
from fastapi_red.runtime import flows_util
from fastapi_red.runtime import storage
from fastapi_red.runtime.engine import engine


# Runtime flow state tracking
_active_flows: List[Dict[str, Any]] = []
_active_rev: str = "initial-rev-1"
_active_parsed_config: Optional[Dict[str, Any]] = None
_runtime_state: str = "start"


def init() -> None:
    """ Initialises the flows subsystem and loads current flows from storage,
    matching init() in @node-red/runtime/lib/flows/index.js.
    """
    storage.init()
    load_flows()


def load_flows() -> Dict[str, Any]:
    """ Loads flows from storage and parses the flow configuration,
    matching loadFlows() in @node-red/runtime/lib/flows/index.js.
    """
    global _active_flows, _active_rev, _active_parsed_config

    flows, rev = storage.get_flows()
    _active_flows = flows
    _active_rev = rev
    _active_parsed_config = flows_util.parse_config(flows)
    return {"flows": _active_flows, "rev": _active_rev}


async def start_flows() -> None:
    """ Starts the runtime flow execution engine with the active flows.
    """
    global _active_flows
    if _runtime_state == "start":
        await engine.start(_active_flows)


async def stop_flows() -> None:
    """ Stops the runtime flow execution engine.
    """
    await engine.stop()


def get_flows() -> Dict[str, Any]:
    """ Returns the currently active flows and revision,
    matching getFlows() in @node-red/runtime/lib/flows/index.js.
    """
    global _active_flows, _active_rev
    if not _active_flows:
        load_flows()
    return {"flows": _active_flows, "rev": _active_rev}


async def set_flows(flows_data: Any, deployment_type: str = "full") -> Dict[str, str]:
    """ Updates and persists flows, performing diffing and returning the new revision,
    matching setFlows() in @node-red/runtime/lib/flows/index.js.
    """
    global _active_flows, _active_rev, _active_parsed_config

    # Handle both { "flows": [...], "rev": "..." } and raw list [...]
    new_flows: List[Dict[str, Any]]
    if isinstance(flows_data, dict) and "flows" in flows_data:
        new_flows = flows_data["flows"]
    elif isinstance(flows_data, list):
        new_flows = flows_data
    else:
        new_flows = []

    # Parse and diff
    new_parsed = flows_util.parse_config(new_flows)
    diff = flows_util.diff_configs(_active_parsed_config, new_parsed)

    # Persist to disk
    new_rev = storage.save_flows(new_flows)
    _active_flows = new_flows
    _active_rev = new_rev
    _active_parsed_config = new_parsed

    # Restart flow engine with updated configuration
    if _runtime_state == "start":
        await engine.start(new_flows)

    return {"rev": new_rev}


def get_flow(flow_id: str) -> Optional[Dict[str, Any]]:
    """ Retrieves a single tab or subflow by its ID,
    matching getFlow() in @node-red/runtime/lib/flows/index.js.
    """
    if not _active_parsed_config:
        load_flows()
    if _active_parsed_config and flow_id in _active_parsed_config["allNodes"]:
        return _active_parsed_config["allNodes"][flow_id]
    return None


def get_node(node_id: str):
    """ Retrieves an active running node instance by ID,
    matching RED.nodes.getNode(id) in Node-RED.
    """
    return engine.get_node(node_id)


async def add_flow(flow_node: Dict[str, Any]) -> str:
    """ Appends a new workspace tab/subflow to the current flow set,
    matching addFlow() in @node-red/runtime/lib/flows/index.js.
    """
    global _active_flows
    flow_id = str(flow_node.get("id", ""))
    if not flow_id:
        import uuid
        flow_id = uuid.uuid4().hex[:16]
        flow_node["id"] = flow_id

    updated_flows = list(_active_flows)
    updated_flows.append(flow_node)
    await set_flows(updated_flows, deployment_type="nodes")
    return flow_id


async def update_flow(flow_id: str, flow_node: Dict[str, Any]) -> str:
    """ Updates an existing tab or subflow in the flow set,
    matching updateFlow() in @node-red/runtime/lib/flows/index.js.
    """
    global _active_flows
    updated_flows = []
    found = False
    for n in _active_flows:
        if n.get("id") == flow_id:
            flow_node["id"] = flow_id
            updated_flows.append(flow_node)
            found = True
        else:
            updated_flows.append(n)

    if not found:
        flow_node["id"] = flow_id
        updated_flows.append(flow_node)

    await set_flows(updated_flows, deployment_type="nodes")
    return flow_id


async def delete_flow(flow_id: str) -> None:
    """ Deletes a flow and all nodes belonging to that workspace (z == flow_id),
    matching deleteFlow() in @node-red/runtime/lib/flows/index.js.
    """
    global _active_flows
    updated_flows = [n for n in _active_flows if n.get("id") != flow_id and n.get("z") != flow_id]
    await set_flows(updated_flows, deployment_type="full")


def get_state() -> Dict[str, str]:
    """ Returns runtime flow execution state ('start' or 'stop'),
    matching getState() in @node-red/runtime/lib/flows/index.js.
    """
    return {"state": _runtime_state}


async def set_state(state: str) -> Dict[str, str]:
    """ Starts or stops flow execution in the runtime,
    matching setState() in @node-red/runtime/lib/flows/index.js.
    """
    global _runtime_state
    if state in ("start", "stop"):
        _runtime_state = state
        if _runtime_state == "start":
            await start_flows()
        else:
            await stop_flows()
    return {"state": _runtime_state}
