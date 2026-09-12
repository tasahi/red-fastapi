""" Node execution endpoints:
- POST /inject/{id}
- POST /debug/{id}/enable and /disable
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Request, Response
from red_fastapi.runtime import flows as runtime_flows
from red_fastapi.runtime.core_nodes import InjectNode, DebugNode


router = APIRouter()


@router.post("/inject/{node_id}")
async def trigger_inject(node_id: str, request: Request):
    """ Triggers an inject node execution,
    matching POST /inject/:id in @node-red/nodes/core/common/20-inject.js.
    """
    node = runtime_flows.get_node(node_id)
    if node is None or not isinstance(node, InjectNode):
        raise HTTPException(status_code=404, detail="Inject node not found or not deployed")

    custom_payload: Optional[Dict[str, Any]] = None
    try:
        data = await request.json()
        if isinstance(data, dict):
            custom_payload = data
    except Exception:
        pass

    await node.trigger(custom_payload)
    return {"status": "ok"}


@router.post("/debug/{node_id}/{action}")
async def toggle_debug(node_id: str, action: str):
    """ Enables or disables a debug node,
    matching POST /debug/:id/:action in @node-red/nodes/core/common/21-debug.js.
    """
    node = runtime_flows.get_node(node_id)
    if node is None or not isinstance(node, DebugNode):
        raise HTTPException(status_code=404, detail="Debug node not found or not deployed")

    if action == "enable":
        node.active = True
    elif action == "disable":
        node.active = False
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    return {"status": "ok", "active": node.active}
