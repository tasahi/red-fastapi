""" Flows API endpoints for flow retrieval, deployment, and lifecycle state.

Mirrors @node-red/editor-api/lib/admin/flows.js and flow.js:
- GET /flows
- POST /flows
- GET /flows/state
- POST /flows/state
- GET /flow/{id}
- POST /flow
- PUT /flow/{id}
- DELETE /flow/{id}
"""

from typing import Any, Dict, List, Union
from fastapi import APIRouter, Header, HTTPException, Request, Response
from red_fastapi.runtime import flows as runtime_flows
from red_fastapi.runtime import comms as runtime_comms


router = APIRouter()


@router.get("/flows")
async def get_flows(node_red_api_version: str = Header(default="v2", alias="Node-RED-API-Version")):
    """ Returns the current flows and revision,
    matching get in @node-red/editor-api/lib/admin/flows.js.
    """
    result = runtime_flows.get_flows()
    if node_red_api_version == "v1":
        return result.get("flows", [])
    return result


@router.post("/flows")
async def set_flows(
    request: Request,
    node_red_api_version: str = Header(default="v2", alias="Node-RED-API-Version"),
    node_red_deployment_type: str = Header(default="full", alias="Node-RED-Deployment-Type")
):
    """ Deploys updated flow configurations from the editor,
    matching post in @node-red/editor-api/lib/admin/flows.js.
    """
    if node_red_deployment_type == "reload":
        # Reload existing flows from disk without modification
        result = runtime_flows.get_flows()
        return {"rev": result.get("rev", "")}

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    deploy_res = await runtime_flows.set_flows(data, deployment_type=node_red_deployment_type)

    # Broadcast runtime-deploy event over /comms to synchronize connected clients
    new_rev = deploy_res.get("rev", "")
    await runtime_comms.publish_notification("runtime-deploy", {"revision": new_rev}, retain=True)

    if node_red_api_version == "v1":
        return Response(status_code=204)
    return deploy_res


@router.get("/flows/state")
async def get_flows_state():
    """ Returns the current flow execution state ('start' or 'stop'),
    matching getState in @node-red/editor-api/lib/admin/flows.js.
    """
    return runtime_flows.get_state()


@router.post("/flows/state")
async def set_flows_state(request: Request):
    """ Sets the runtime flow execution state ('start' or 'stop'),
    matching postState in @node-red/editor-api/lib/admin/flows.js.
    """
    try:
        data = await request.json()
        state_val = data.get("state", "start")
    except Exception:
        state_val = "start"

    result = await runtime_flows.set_state(state_val)
    # Broadcast runtime-state event over /comms
    await runtime_comms.publish_notification("runtime-state", {"state": state_val}, retain=True)
    return result


@router.get("/flow/{flow_id}")
async def get_flow(flow_id: str):
    """ Retrieves an individual flow or workspace definition by ID,
    matching get in @node-red/editor-api/lib/admin/flow.js.
    """
    flow = runtime_flows.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow


@router.post("/flow")
async def add_flow(request: Request):
    """ Appends an individual flow/workspace,
    matching post in @node-red/editor-api/lib/admin/flow.js.
    """
    try:
        flow_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    new_id = await runtime_flows.add_flow(flow_data)
    return {"id": new_id}


@router.put("/flow/{flow_id}")
async def update_flow(flow_id: str, request: Request):
    """ Updates an individual flow/workspace,
    matching put in @node-red/editor-api/lib/admin/flow.js.
    """
    try:
        flow_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    updated_id = await runtime_flows.update_flow(flow_id, flow_data)
    return {"id": updated_id}


@router.delete("/flow/{flow_id}")
async def delete_flow(flow_id: str):
    """ Deletes an individual flow/workspace,
    matching delete in @node-red/editor-api/lib/admin/flow.js.
    """
    await runtime_flows.delete_flow(flow_id)
    return Response(status_code=204)
