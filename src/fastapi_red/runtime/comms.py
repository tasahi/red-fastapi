""" Runtime communication layer for WebSocket events.

Mirrors @node-red/runtime/lib/api/comms.js:
- publish
- publish_status
- publish_notification
- add_connection
- remove_connection
- get_retained
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket


logger = logging.getLogger("fastapi_red.runtime.comms")

# Retained messages map (topic -> data) for new connections
_retained: Dict[str, Any] = {}

# Active WebSocket connections
_active_connections: Set["CommsClient"] = set()


class CommsClient:
    """ Represents an active editor WebSocket connection,
    matching CommsConnection in @node-red/editor-api/lib/editor/comms.js.
    """

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.subscriptions: Set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue()
        self._sender_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """ Starts background sender worker for this connection.
        """
        self._sender_task = asyncio.create_task(self._sender_loop())

    async def stop(self) -> None:
        """ Cancels the sender worker when connection closes.
        """
        if self._sender_task:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass

    def subscribe(self, topic: str) -> None:
        """ Adds a topic subscription for this client.
        """
        self.subscriptions.add(topic)

    def unsubscribe(self, topic: str) -> None:
        """ Removes a topic subscription.
        """
        self.subscriptions.discard(topic)

    async def send(self, topic: str, data: Any) -> None:
        """ Enqueues a message to be sent to this client.
        """
        await self.queue.put({"topic": topic, "data": data})

    async def _sender_loop(self) -> None:
        """ Batches and sends messages over the WebSocket in the standard array format,
        matching CommsConnection.prototype._queueSend() in comms.js.
        """
        try:
            while True:
                # Wait for first message
                first_msg = await self.queue.get()
                batch = [first_msg]
                self.queue.task_done()

                # Collect any pending messages without blocking (up to 50)
                while not self.queue.empty() and len(batch) < 50:
                    batch.append(self.queue.get_nowait())
                    self.queue.task_done()

                # Send batch as JSON array
                await self.websocket.send_text(json.dumps(batch))
        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.debug(f"CommsClient sender error: {err}")


def init() -> None:
    """ Initialises the comms subsystem,
    matching init() in @node-red/runtime/lib/api/comms.js.
    """
    global _retained, _active_connections
    _retained = {}
    _active_connections.clear()


async def add_connection(client: CommsClient) -> None:
    """ Registers a newly connected client and delivers retained messages,
    matching addConnection() in @node-red/runtime/lib/api/comms.js.
    """
    _active_connections.add(client)
    await client.start()

    # Deliver retained messages (e.g., node status badges, runtime state)
    for topic, data in list(_retained.items()):
        await client.send(topic, data)


async def remove_connection(client: CommsClient) -> None:
    """ Unregisters a disconnected client,
    matching removeConnection() in @node-red/runtime/lib/api/comms.js.
    """
    _active_connections.discard(client)
    await client.stop()


async def publish(topic: str, data: Any, retain: bool = False) -> None:
    """ Broadcasts a message on a given topic to all active clients,
    matching publish() in @node-red/runtime/lib/api/comms.js.
    """
    if retain:
        _retained[topic] = data
    elif topic in _retained:
        del _retained[topic]

    for client in list(_active_connections):
        await client.send(topic, data)


async def publish_status(node_id: str, fill: str = "", shape: str = "", text: str = "") -> None:
    """ Broadcasts a node status badge update,
    matching handleStatusEvent() in @node-red/runtime/lib/api/comms.js.
    """
    topic = f"status/{node_id}"
    if not fill and not shape and not text:
        # Clear status
        if topic in _retained:
            del _retained[topic]
        await publish(topic, {}, retain=False)
    else:
        status_data = {"fill": fill, "shape": shape, "text": text}
        await publish(topic, status_data, retain=True)


async def publish_notification(notification_id: str, payload: Dict[str, Any], retain: bool = False) -> None:
    """ Broadcasts a runtime notification (e.g., deploy completion, warnings),
    matching handleRuntimeEvent() in @node-red/runtime/lib/api/comms.js.
    """
    topic = f"notification/{notification_id}"
    await publish(topic, payload, retain=retain)


async def publish_debug(node_id: str, name: str, msg: Dict[str, Any]) -> None:
    """ Broadcasts a debug message to the editor's Debug sidebar,
    matching debug node output handling.
    """
    debug_packet = {
        "id": node_id,
        "name": name,
        "msg": msg
    }
    await publish("debug", debug_packet, retain=False)


def get_active_connection_count() -> int:
    """ Returns the number of connected editor WebSocket clients.
    """
    return len(_active_connections)


def get_retained() -> Dict[str, Any]:
    """ Returns the currently retained messages dictionary.
    """
    return dict(_retained)
