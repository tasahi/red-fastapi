""" Network Node implementations for Red-Fastapi.

Mirrors upstream Node-RED core nodes:
- HTTPInNode: Serves incoming HTTP requests
- HTTPResponseNode: Emits response back to waiting HTTP client
- HTTPRequestNode: Outbound non-blocking HTTP requests using httpx
"""

import asyncio
import copy
import logging
import uuid
from typing import Any, Dict, List, Optional
import httpx
from red_fastapi.runtime.node import Node
from red_fastapi.runtime.eval import get_property, set_property


logger = logging.getLogger("red_fastapi.runtime.network_nodes")


class HTTPInNode(Node):
    """ Listens for incoming HTTP requests matching a method and URL path,
    matching HTTPIn in @node-red/nodes/core/network/21-httpin.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.url: str = str(config.get("url", "/"))
        self.method: str = str(config.get("method", "get")).lower()

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Passes received HTTP request message along wires.
        """
        await self.send(msg)


class HTTPResponseNode(Node):
    """ Resolves and sends the HTTP response for an in-flight HTTP request,
    matching HTTPResponse in @node-red/nodes/core/network/21-httpin.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.status_code: Optional[int] = (
            int(config["statusCode"]) if config.get("statusCode") else None
        )
        self.headers: Dict[str, str] = config.get("headers", {})

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Dispatches response back to the waiting HTTP connection.
        """
        from red_fastapi.api.http_in import complete_response

        res_id = msg.get("_res_id") or msg.get("res", {}).get("_res_id")
        if not res_id:
            await self.warn("HTTP Response node received message without _res_id")
            return

        if self.status_code and "statusCode" not in msg:
            msg["statusCode"] = self.status_code

        if self.headers:
            if "headers" not in msg:
                msg["headers"] = {}
            for k, v in self.headers.items():
                if k not in msg["headers"]:
                    msg["headers"][k] = v

        complete_response(str(res_id), copy.deepcopy(msg))


class HTTPRequestNode(Node):
    """ Makes outbound HTTP requests using asynchronous httpx client,
    matching HTTPRequest in @node-red/nodes/core/network/21-httprequest.js.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.url: str = str(config.get("url", ""))
        self.method: str = str(config.get("method", "GET")).upper()
        self.ret: str = config.get("ret", "txt")  # "txt", "bin", "obj"
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """ Initializes reusable connection client.
        """
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def on_input(self, msg: Dict[str, Any]) -> None:
        """ Dispatches asynchronous HTTP request and forwards response.
        """
        target_url = msg.get("url") or self.url
        if not target_url:
            await self.error("No URL specified for HTTP Request node", msg)
            return

        target_method = (msg.get("method") or self.method or "GET").upper()
        req_headers = copy.deepcopy(msg.get("headers", {}))

        # Payload to send
        payload = msg.get("payload")
        req_body = None
        req_json = None

        if target_method in ("POST", "PUT", "PATCH", "DELETE") and payload is not None:
            if isinstance(payload, (dict, list)):
                req_json = payload
            else:
                req_body = str(payload)

        if not self.client:
            self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

        try:
            resp = await self.client.request(
                target_method,
                target_url,
                headers=req_headers,
                data=req_body,
                json=req_json,
            )

            out_msg = copy.deepcopy(msg)
            out_msg["statusCode"] = resp.status_code
            out_msg["headers"] = dict(resp.headers)

            if self.ret == "bin":
                out_msg["payload"] = resp.content
            elif self.ret == "obj":
                try:
                    out_msg["payload"] = resp.json()
                except Exception:
                    out_msg["payload"] = resp.text
            else:
                out_msg["payload"] = resp.text

            out_msg["responseUrl"] = str(resp.url)
            await self.send(out_msg)

        except Exception as err:
            await self.error(f"HTTP Request failed: {err}", msg)

    async def close(self) -> None:
        """ Closes httpx client pool.
        """
        await super().close()
        if self.client:
            await self.client.aclose()
            self.client = None

