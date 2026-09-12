""" MQTT and Sockets (TCP, UDP, WebSocket) node implementations for Red-Fastapi.

Mirrors upstream Node-RED network nodes:
- MQTTBrokerNode: Configuration node managing client connections to MQTT brokers
- MQTTInNode: Subscribes to MQTT topics and dispatches incoming messages
- MQTTOutNode: Publishes messages to MQTT broker topics
- TCPInNode: TCP server / client ingress
- TCPOutNode: TCP client egress / response
- UDPInNode: UDP listener
- UDPOutNode: UDP datagram transmitter
- WebSocketInNode: Custom flow-level WebSocket server/client ingress
- WebSocketOutNode: Custom flow-level WebSocket egress
"""

import asyncio
import copy
import json
import logging
import socket
from typing import Any, Dict, List, Optional
import paho.mqtt.client as paho_mqtt
from red_fastapi.runtime.node import Node
from red_fastapi.runtime.eval import get_property, set_property


logger = logging.getLogger("red_fastapi.runtime.socket_nodes")


class MQTTBrokerNode(Node):
    """ Configuration node managing the client connection to an external MQTT broker,
    matching mqtt-broker in @node-red/nodes/core/network/10-mqtt.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.broker: str = str(config.get("broker", "localhost"))
        self.port: int = int(config.get("port", 1883))
        self.client_id: str = str(config.get("clientid", ""))
        self.keepalive: int = int(config.get("keepalive", 60))
        self.cleansession: bool = config.get("cleansession", True)
        self.username: str = str(config.get("user", ""))
        self.password: str = str(config.get("password", ""))

        self.client: Optional[paho_mqtt.Client] = None
        self._subscribers: List[Any] = []
        self._connected: bool = False
        self._loop = None

    def register_subscriber(self, sub_node: Any) -> None:
        """ Registers an MQTTInNode subscriber to receive matching messages.
        """
        if sub_node not in self._subscribers:
            self._subscribers.append(sub_node)
            if self._connected and hasattr(sub_node, "topic") and sub_node.topic:
                if self.client:
                    self.client.subscribe(sub_node.topic, qos=int(getattr(sub_node, "qos", 0)))

    def deregister_subscriber(self, sub_node: Any) -> None:
        """ Deregisters an MQTTInNode subscriber.
        """
        if sub_node in self._subscribers:
            self._subscribers.remove(sub_node)

    async def start(self) -> None:
        """ Connects to the MQTT broker in background thread.
        """
        self._loop = asyncio.get_running_loop()
        client_id = self.client_id or f"red_fastapi_{self.id[:8]}"
        try:
            self.client = paho_mqtt.Client(paho_mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=self.cleansession)
        except Exception:
            self.client = paho_mqtt.Client(client_id=client_id, clean_session=self.cleansession)

        if self.username:
            self.client.username_pw_set(self.username, self.password)

        def on_connect(client, userdata, flags, reason_code, properties=None):
            self._connected = True
            logger.info(f"MQTT Broker {self.broker}:{self.port} connected")
            # Subscribe for all active subscribers
            for sub in self._subscribers:
                if hasattr(sub, "topic") and sub.topic:
                    client.subscribe(sub.topic, qos=int(getattr(sub, "qos", 0)))

        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
            self._connected = False
            logger.info(f"MQTT Broker {self.broker}:{self.port} disconnected")

        def on_message(client, userdata, message):
            topic = message.topic
            raw_payload = message.payload
            # Dispatch to subscribers on asyncio loop
            if self._loop and self._loop.is_running():
                for sub in self._subscribers:
                    asyncio.run_coroutine_threadsafe(sub.handle_mqtt_message(topic, raw_payload, message.qos, message.retain), self._loop)

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message = on_message

        try:
            self.client.connect_async(self.broker, self.port, self.keepalive)
            self.client.loop_start()
        except Exception as err:
            logger.warning(f"Could not initiate connection to MQTT broker {self.broker}:{self.port}: {err}")

    async def publish(self, topic: str, payload: Any, qos: int = 0, retain: bool = False) -> None:
        """ Publishes a message via the broker connection.
        """
        if not self.client:
            return
        data = payload if isinstance(payload, (bytes, bytearray)) else str(payload)
        self.client.publish(topic, data, qos=qos, retain=retain)

    async def close(self) -> None:
        """ Clean up broker connection.
        """
        await super().close()
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None


class MQTTInNode(Node):
    """ Subscribes to an MQTT topic and passes received messages into the flow,
    matching MQTTIn in @node-red/nodes/core/network/10-mqtt.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.broker_id: str = str(config.get("broker", ""))
        self.topic: str = str(config.get("topic", "#"))
        self.qos: int = int(config.get("qos", 0))
        self.datatype: str = config.get("datatype", "auto")

    async def start(self) -> None:
        """ Registers with the target MQTTBrokerNode.
        """
        if self.flow:
            broker_node = self.flow.get_node(self.broker_id)
            if broker_node and hasattr(broker_node, "register_subscriber"):
                broker_node.register_subscriber(self)

    async def handle_mqtt_message(self, topic: str, raw_payload: bytes, qos: int, retain: bool) -> None:
        """ Called when a message matching subscription arrives from the broker.
        """
        if self._closed:
            return

        payload_parsed: Any = raw_payload
        if self.datatype in ("auto", "utf-8", "json"):
            try:
                text = raw_payload.decode("utf-8")
                if self.datatype == "json":
                    payload_parsed = json.loads(text)
                elif self.datatype == "auto":
                    try:
                        payload_parsed = json.loads(text)
                    except Exception:
                        payload_parsed = text
                else:
                    payload_parsed = text
            except Exception:
                payload_parsed = raw_payload

        msg = {
            "topic": topic,
            "payload": payload_parsed,
            "qos": qos,
            "retain": retain,
        }
        await self.send(msg)

    async def close(self) -> None:
        """ Deregister on node close.
        """
        await super().close()
        if self.flow:
            broker_node = self.flow.get_node(self.broker_id)
            if broker_node and hasattr(broker_node, "deregister_subscriber"):
                broker_node.deregister_subscriber(self)


class MQTTOutNode(Node):
    """ Publishes incoming messages to an MQTT topic,
    matching MQTTOut in @node-red/nodes/core/network/10-mqtt.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.broker_id: str = str(config.get("broker", ""))
        self.topic: str = str(config.get("topic", ""))
        self.qos: int = int(config.get("qos", 0))
        self.retain: bool = config.get("retain", False)

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Publishes payload to target topic.
        """
        target_topic = self.topic or msg.get("topic", "")
        if not target_topic:
            await self.warn("MQTT Out received message with no topic")
            return

        payload = msg.get("payload", "")
        qos = int(msg.get("qos", self.qos))
        retain = bool(msg.get("retain", self.retain))

        if self.flow:
            broker_node = self.flow.get_node(self.broker_id)
            if broker_node and hasattr(broker_node, "publish"):
                await broker_node.publish(target_topic, payload, qos=qos, retain=retain)


class TCPInNode(Node):
    """ Listens for incoming TCP connections or connects as TCP client,
    matching TCPIn in @node-red/nodes/core/network/31-tcpin.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.server: bool = config.get("server", "server") == "server" or config.get("server") is True
        self.host: str = str(config.get("host", "127.0.0.1"))
        self.port: int = int(config.get("port", 3000))
        self._server = None

    async def start(self) -> None:
        """ Starts TCP server listener if in server mode.
        """
        if self.server:
            try:
                self._server = await asyncio.start_server(self._handle_client, host=self.host, port=self.port)
                logger.info(f"TCP server listening on {self.host}:{self.port}")
            except Exception as err:
                logger.error(f"TCPIn error binding to {self.host}:{self.port}: {err}")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """ Handles client TCP stream.
        """
        peer = writer.get_extra_info("peername")
        while not self._closed:
            data = await reader.read(4096)
            if not data:
                break
            msg = {
                "payload": data,
                "ip": peer[0] if peer else "",
                "port": peer[1] if peer else 0,
            }
            await self.send(msg)
        writer.close()
        await writer.wait_closed()

    async def close(self) -> None:
        """ Closes TCP server.
        """
        await super().close()
        if self._server is not None:
            try:
                self._server.close()
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None


class TCPOutNode(Node):
    """ Sends TCP packets to a host and port,
    matching TCPOut in @node-red/nodes/core/network/31-tcpin.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.host: str = str(config.get("host", "127.0.0.1"))
        self.port: int = int(config.get("port", 3000))

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Transmits message payload to TCP server.
        """
        target_host = msg.get("host", self.host)
        target_port = int(msg.get("port", self.port))
        payload = msg.get("payload", b"")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        try:
            reader, writer = await asyncio.open_connection(target_host, target_port)
            writer.write(payload)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        except Exception as err:
            await self.error(f"TCP send failed: {err}", msg)


class UDPInNode(Node):
    """ Listens for UDP datagrams on a given port,
    matching UDPin in @node-red/nodes/core/network/32-udp.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.port: int = int(config.get("port", 5000))
        self.ipv: str = config.get("ipv", "udp4")
        self._transport = None

    class _DatagramProtocol(asyncio.DatagramProtocol):
        def __init__(self, outer_node):
            self.outer = outer_node

        def datagram_received(self, data, addr):
            msg = {"payload": data, "ip": addr[0], "port": addr[1]}
            asyncio.create_task(self.outer.send(msg))

    async def start(self) -> None:
        """ Starts UDP listener.
        """
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: self._DatagramProtocol(self),
                local_addr=("0.0.0.0", self.port)
            )
            self._transport = transport
            logger.info(f"UDP listener active on port {self.port}")
        except Exception as err:
            logger.error(f"UDPIn bind failed on port {self.port}: {err}")

    async def close(self) -> None:
        """ Closes UDP listener.
        """
        await super().close()
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None


class UDPOutNode(Node):
    """ Sends UDP datagrams to a remote host and port,
    matching UDPout in @node-red/nodes/core/network/32-udp.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.addr: str = str(config.get("addr", "127.0.0.1"))
        self.port: int = int(config.get("port", 5000))

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Transmits UDP packet.
        """
        target_addr = msg.get("ip") or msg.get("addr") or self.addr
        target_port = int(msg.get("port") or self.port)
        payload = msg.get("payload", b"")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            await loop.sock_sendto(sock, payload, (target_addr, target_port))
        except Exception as err:
            await self.error(f"UDP send failed: {err}", msg)
        finally:
            sock.close()


class WebSocketInNode(Node):
    """ Custom flow-level WebSocket server/client ingress,
    matching WebSocketIn in @node-red/nodes/core/network/22-websocket.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.path: str = str(config.get("path", "/ws"))

    async def handle_message(self, client_id: str, data: Any) -> None:
        """ Called when a client sends a message on the flow websocket endpoint.
        """
        msg = {"payload": data, "_session": {"id": client_id}}
        await self.send(msg)


class WebSocketOutNode(Node):
    """ Custom flow-level WebSocket server/client egress,
    matching WebSocketOut in @node-red/nodes/core/network/22-websocket.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.path: str = str(config.get("path", "/ws"))
        self._clients: set = set()

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Broadcasts payload or sends to designated session.
        """
        payload = msg.get("payload", "")
        if isinstance(payload, (dict, list)):
            payload_str = json.dumps(payload)
        else:
            payload_str = str(payload)

        for client in list(self._clients):
            try:
                await client.send_text(payload_str)
            except Exception:
                self._clients.discard(client)


