""" Unit tests for MQTT & Sockets (TCP, UDP, WebSocket) nodes.

Tests:
- TCPInNode and TCPOutNode: local TCP socket server & client communication
- UDPInNode and UDPOutNode: local UDP datagram transmission and reception
- MQTTBrokerNode, MQTTInNode, and MQTTOutNode: broker registration and mock message routing
- WebSocketInNode and WebSocketOutNode: flow-level WebSocket message handling
"""

import asyncio
import json
import pytest
from unittest.mock import MagicMock
from fastapi_red.runtime.engine import engine
from fastapi_red.runtime.socket_nodes import (
    TCPInNode,
    TCPOutNode,
    UDPInNode,
    UDPOutNode,
    MQTTBrokerNode,
    MQTTInNode,
    MQTTOutNode,
    WebSocketInNode,
    WebSocketOutNode,
)


@pytest.mark.asyncio
async def test_tcp_in_and_tcp_out_pipeline():
    """ Tests TCP In server receiving payload sent by TCP Out client.
    """
    received_messages = []

    class CollectNode(TCPInNode):
        """ Test collector node.
        """

        async def receive(self, msg):
            received_messages.append(msg)

    engine.register_type("collector-tcp", CollectNode)

    port = 19876
    flow_configs = [
        {
            "id": "tcp_server",
            "type": "tcp in",
            "server": "server",
            "port": port,
            "wires": [["coll_1"]],
        },
        {
            "id": "coll_1",
            "type": "collector-tcp",
            "wires": [],
        },
        {
            "id": "tcp_client",
            "type": "tcp out",
            "beserver": "client",
            "host": "127.0.0.1",
            "port": port,
            "wires": [],
        },
    ]

    await engine.start(flow_configs)
    await asyncio.sleep(0.1)

    tcp_client = engine.get_node("tcp_client")
    assert tcp_client is not None

    # Send message through tcp out
    await tcp_client.receive({"payload": "Hello TCP Socket!"})
    await asyncio.sleep(0.2)

    assert len(received_messages) >= 1
    raw = received_messages[0].get("payload", b"")
    payload_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    assert "Hello TCP Socket!" in payload_str
    assert received_messages[0].get("port") is not None

    await engine.stop()


@pytest.mark.asyncio
async def test_udp_in_and_udp_out_pipeline():
    """ Tests UDP In listener receiving datagram sent by UDP Out node.
    """
    received_messages = []

    class CollectUDPNode(UDPInNode):
        """ Test collector node for UDP.
        """

        async def receive(self, msg):
            received_messages.append(msg)

    engine.register_type("collector-udp", CollectUDPNode)

    port = 19877
    flow_configs = [
        {
            "id": "udp_listener",
            "type": "udp in",
            "port": port,
            "datatype": "utf8",
            "wires": [["coll_udp"]],
        },
        {
            "id": "coll_udp",
            "type": "collector-udp",
            "wires": [],
        },
        {
            "id": "udp_sender",
            "type": "udp out",
            "addr": "127.0.0.1",
            "port": port,
            "wires": [],
        },
    ]

    await engine.start(flow_configs)
    await asyncio.sleep(0.1)

    udp_sender = engine.get_node("udp_sender")
    assert udp_sender is not None

    await udp_sender.receive({"payload": "Hello UDP Datagram!"})
    await asyncio.sleep(0.2)

    assert len(received_messages) >= 1
    raw = received_messages[0].get("payload", b"")
    payload_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    assert "Hello UDP Datagram!" in payload_str

    await engine.stop()


@pytest.mark.asyncio
async def test_mqtt_broker_subscriber_and_publish():
    """ Tests MQTTInNode and MQTTOutNode interaction via MQTTBrokerNode subscriber mechanism.
    """
    received_messages = []

    class CollectMQTTNode(MQTTInNode):
        """ Test collector node for MQTT.
        """

        async def receive(self, msg):
            received_messages.append(msg)

    engine.register_type("collector-mqtt", CollectMQTTNode)

    flow_configs = [
        {
            "id": "broker_1",
            "type": "mqtt-broker",
            "broker": "localhost",
            "port": 1883,
            "wires": [],
        },
        {
            "id": "mqtt_in_1",
            "type": "mqtt in",
            "broker": "broker_1",
            "topic": "sensors/temperature",
            "datatype": "json",
            "wires": [["coll_mqtt"]],
        },
        {
            "id": "coll_mqtt",
            "type": "collector-mqtt",
            "wires": [],
        },
        {
            "id": "mqtt_out_1",
            "type": "mqtt out",
            "broker": "broker_1",
            "topic": "sensors/temperature",
            "wires": [],
        },
    ]

    await engine.start(flow_configs)

    broker = engine.get_node("broker_1")
    mqtt_in = engine.get_node("mqtt_in_1")
    mqtt_out = engine.get_node("mqtt_out_1")

    assert broker is not None
    assert mqtt_in is not None
    assert mqtt_out is not None

    # Simulate incoming broker message directly dispatching to registered subscribers
    test_payload = json.dumps({"temp": 22.5, "unit": "C"}).encode("utf-8")
    await mqtt_in.handle_mqtt_message("sensors/temperature", test_payload, qos=0, retain=False)
    await asyncio.sleep(0.1)

    assert len(received_messages) == 1
    assert received_messages[0]["topic"] == "sensors/temperature"
    assert received_messages[0]["payload"] == {"temp": 22.5, "unit": "C"}

    # Mock client publish on MQTTOutNode
    broker.client = MagicMock()
    await mqtt_out.receive({"payload": {"command": "fan_on"}})
    broker.client.publish.assert_called_once()

    await engine.stop()


@pytest.mark.asyncio
async def test_websocket_in_and_out():
    """ Tests flow-level WebSocket in and out node handling.
    """
    received_messages = []

    class CollectWSNode(WebSocketInNode):
        """ Test collector node for WebSockets.
        """

        async def receive(self, msg):
            received_messages.append(msg)

    engine.register_type("collector-ws", CollectWSNode)

    flow_configs = [
        {
            "id": "ws_in_1",
            "type": "websocket in",
            "path": "/ws/telemetry",
            "wires": [["coll_ws"]],
        },
        {
            "id": "coll_ws",
            "type": "collector-ws",
            "wires": [],
        },
        {
            "id": "ws_out_1",
            "type": "websocket out",
            "path": "/ws/telemetry",
            "wires": [],
        },
    ]

    await engine.start(flow_configs)

    ws_in = engine.get_node("ws_in_1")
    ws_out = engine.get_node("ws_out_1")

    assert ws_in is not None
    assert ws_out is not None

    # Mock an active websocket connection
    mock_ws = MagicMock()
    mock_send = MagicMock()
    mock_ws.send_text = mock_send
    ws_out._clients.add(mock_ws)

    # Deliver message to ws_in
    await ws_in.handle_message("client-123", "ping-frame")
    await asyncio.sleep(0.1)

    assert len(received_messages) == 1
    assert received_messages[0]["payload"] == "ping-frame"

    # Send outgoing frame through ws_out
    await ws_out.receive({"payload": "pong-frame"})
    mock_ws.send_text.assert_called_with("pong-frame")

    await engine.stop()
