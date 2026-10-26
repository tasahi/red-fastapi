""" JSON-RPC Streaming and Bridge to red-fastapi Comms.\n
Bridges internal red-fastapi events (node status, runtime debug messages,
lifecycle notifications) into JSON-RPC 2.0 notifications streamed over WebSocket:
- stream.subscribe: Subscribe this session to topics ("debug", "status/*", "*")
- stream.unsubscribe: Unsubscribe from topics
- stream.publish: Publish custom event to other connected clients
"""

from typing import Any, Dict, List, Optional
from red_fastapi.rpc.dispatcher import JSONRPCDispatcher
from red_fastapi.rpc.errors import InvalidParams
from red_fastapi.rpc.transports.websocket import rpc_ws_manager
from red_fastapi.runtime import comms as runtime_comms


def register_streaming_methods(dispatcher: JSONRPCDispatcher) -> None:
    """ Register streaming and subscription RPC methods."""

    @dispatcher.add_method("stream.subscribe")
    async def stream_subscribe(topic: str = "*") -> Dict[str, Any]:
        """ Subscribe to server event streams.
        
        Topics include:
        - '*' : All events
        - 'debug' : Debug node messages
        - 'status' : Status updates
        - 'notification' : Runtime notifications
        """
        if not topic:
            raise InvalidParams(message="Parameter 'topic' cannot be empty")
        # Add to all active sessions (or per-session context)
        for s in rpc_ws_manager.active_sessions:
            s.subscriptions.add(topic)
        return {"subscribed": True, "topic": topic}

    @dispatcher.add_method("stream.unsubscribe")
    async def stream_unsubscribe(topic: str = "*") -> Dict[str, Any]:
        """ Unsubscribe from server event streams."""
        for s in rpc_ws_manager.active_sessions:
            s.subscriptions.discard(topic)
        return {"unsubscribed": True, "topic": topic}

    @dispatcher.add_method("stream.broadcast")
    async def stream_broadcast(event: str, data: Optional[Any] = None) -> Dict[str, Any]:
        """ Broadcast a custom server-side notification to all connected clients."""
        if not event:
            raise InvalidParams(message="Parameter 'event' is required")
        await rpc_ws_manager.broadcast_notification(event, data)
        return {"broadcasted": True, "event": event, "recipient_count": len(rpc_ws_manager.active_sessions)}


# Optional: Hook to forward runtime_comms debug and status events into RPC WebSocket manager
async def forward_comms_to_rpc(topic: str, data: Any) -> None:
    """ Helper to convert internal comms publish events into JSON-RPC notifications."""
    method_name = f"red.{topic.replace('/', '.')}"
    await rpc_ws_manager.broadcast_to_subscribers(topic, method_name, data)
