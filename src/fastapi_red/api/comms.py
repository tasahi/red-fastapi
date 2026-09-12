""" WebSocket /comms API router.

Mirrors @node-red/editor-api/lib/editor/comms.js:
- WebSocket /comms connection lifecycle
- Client authentication handling
- Topic subscription handling ({"subscribe": "topic"})
- Keep-alive heartbeat loop
"""

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi_red.runtime.comms import CommsClient, add_connection, remove_connection


router = APIRouter()
logger = logging.getLogger("fastapi_red.api.comms")


@router.websocket("/comms")
async def comms_websocket(websocket: WebSocket):
    """ WebSocket endpoint for real-time editor communication,
    matching wsServer.on('connection') in @node-red/editor-api/lib/editor/comms.js.
    """
    await websocket.accept()
    client = CommsClient(websocket)
    await add_connection(client)

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                if not isinstance(msg, dict):
                    continue

                # Handle subscription requests: {"subscribe": "debug"}
                if "subscribe" in msg:
                    topic = msg.get("subscribe")
                    if isinstance(topic, str):
                        client.subscribe(topic)

                # Handle authentication requests (if sent)
                elif "auth" in msg:
                    await websocket.send_text(json.dumps({"auth": "ok"}))

            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as err:
        logger.debug(f"comms_websocket error: {err}")
    finally:
        await remove_connection(client)

