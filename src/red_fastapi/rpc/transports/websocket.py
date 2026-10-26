""" WebSocket Bidirectional JSON-RPC 2.0 Transport.\n
Provides full duplex JSON-RPC 2.0 messaging:
- Request/Response processing over persistent connection.
- Batch processing and client-to-server notifications.
- Server-to-client JSON-RPC notifications (streaming events, debug messages, status changes).
- Topic-based subscriptions (e.g. "debug", "status", "notification/*") compatible with red-fastapi comms.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect

from red_fastapi.rpc.dispatcher import JSONRPCDispatcher
from red_fastapi.rpc.models import JSONRPCNotification

logger = logging.getLogger("red_fastapi.rpc.websocket")


class RPCWebSocketSession:
    """ Represents a connected bidirectional JSON-RPC WebSocket client."""

    def __init__(self, websocket: WebSocket, dispatcher: JSONRPCDispatcher):
        self.websocket = websocket
        self.dispatcher = dispatcher
        self.subscriptions: Set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue()
        self._sender_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """ Start the background send worker."""
        self._sender_task = asyncio.create_task(self._sender_loop())

    async def stop(self) -> None:
        """ Stop background worker and clean up."""
        if self._sender_task:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass

    async def notify(self, method: str, params: Optional[Any] = None) -> None:
        """ Queue a JSON-RPC 2.0 notification from server to this client."""
        notification = JSONRPCNotification(method=method, params=params)
        await self.queue.put(notification.model_dump(exclude_none=True))

    async def _sender_loop(self) -> None:
        """ Continuously dequeues outbound messages and writes to WebSocket."""
        try:
            while True:
                msg = await self.queue.get()
                await self.websocket.send_text(json.dumps(msg))
                self.queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.debug(f"RPCWebSocketSession sender error: {err}")


class RPCWebSocketManager:
    """ Tracks active JSON-RPC WebSocket sessions and handles broadcasts."""

    def __init__(self):
        self.active_sessions: Set[RPCWebSocketSession] = set()

    async def connect(self, websocket: WebSocket, dispatcher: JSONRPCDispatcher) -> RPCWebSocketSession:
        await websocket.accept()
        session = RPCWebSocketSession(websocket, dispatcher)
        await session.start()
        self.active_sessions.add(session)
        logger.info(f"RPC WebSocket client connected. Active sessions: {len(self.active_sessions)}")
        return session

    async def disconnect(self, session: RPCWebSocketSession) -> None:
        self.active_sessions.discard(session)
        await session.stop()
        logger.info(f"RPC WebSocket client disconnected. Active sessions: {len(self.active_sessions)}")

    async def broadcast_notification(self, method: str, params: Optional[Any] = None) -> None:
        """ Broadcasts a JSON-RPC notification to all connected sessions."""
        for session in list(self.active_sessions):
            await session.notify(method, params)

    async def broadcast_to_subscribers(self, topic: str, method: str, params: Optional[Any] = None) -> None:
        """ Broadcasts to sessions subscribed to the topic (or wildcard '*')."""
        for session in list(self.active_sessions):
            if "*" in session.subscriptions or topic in session.subscriptions:
                await session.notify(method, params)


# Global manager for RPC WebSockets
rpc_ws_manager = RPCWebSocketManager()


async def handle_rpc_websocket(websocket: WebSocket, dispatcher: JSONRPCDispatcher) -> None:
    """ Manages full lifecycle of an active JSON-RPC WebSocket connection."""
    session = await rpc_ws_manager.connect(websocket, dispatcher)

    # Attach session to dispatcher context if needed
    try:
        while True:
            text = await websocket.receive_text()
            # Process incoming RPC request or batch
            response = await dispatcher.dispatch(text)
            if response is not None:
                await websocket.send_text(json.dumps(response))
    except WebSocketDisconnect:
        await rpc_ws_manager.disconnect(session)
    except Exception as err:
        logger.warning(f"Error in RPC WebSocket connection: {err}")
        await rpc_ws_manager.disconnect(session)
