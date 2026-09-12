""" Storage nodes implementation for FastAPI-Red.

Mirrors @node-red/nodes/core/storage/ and integrates Cloud Blob Storage:
- FileNode: Writes, appends, or deletes files on the filesystem.
- FileInNode: Reads files into memory as string (utf8), lines, or binary buffer.
- S3ConfigNode: Configuration node for AWS S3 and MinIO credentials & endpoints.
- S3InNode: Downloads / retrieves blobs from AWS S3 or MinIO bucket.
- S3OutNode: Uploads / writes or deletes blobs in AWS S3 or MinIO bucket.
"""

import asyncio
import copy
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import aiofiles
import aiofiles.os
from fastapi_red.runtime.node import Node
from fastapi_red.runtime.eval import evaluate_value, get_property, set_property


logger = logging.getLogger("fastapi_red.nodes.storage")


class FileNode(Node):
    """ Writes, appends, or deletes files from disk.
    Mirrors @node-red/nodes/core/storage/10-file.js (FileNode).
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.filename: str = config.get("filename", "")
        self.filename_type: str = config.get("filenameType", "str" if self.filename else "msg")
        self.append_newline: bool = config.get("appendNewline", True)
        self.overwrite_file: str = str(config.get("overwriteFile", "false")).lower()
        self.create_dir: bool = config.get("createDir", False)
        self.encoding: str = config.get("encoding", "none")

    async def on_input(self, msg: Dict[str, Any]) -> None:
        target_file = ""
        if self.filename_type == "msg":
            prop = self.filename or "filename"
            target_file = str(get_property(msg, prop) or "")
        elif self.filename:
            target_file = str(evaluate_value(self.filename_type, self.filename, msg=msg, node=self) or "")

        if not target_file:
            await self.error("No filename specified", msg)
            return

        path = Path(target_file)

        # Delete operation
        if self.overwrite_file == "delete":
            try:
                if await aiofiles.os.path.exists(path):
                    await aiofiles.os.remove(path)
                    await self.status(fill="grey", shape="dot", text=f"deleted: {path.name}")
                    await self.send(msg)
                else:
                    await self.warn(f"File to delete does not exist: {path}")
            except Exception as err:
                await self.error(f"Failed to delete file: {err}", msg)
            return

        # Write or append operation
        payload = msg.get("payload")
        if payload is None:
            await self.send(msg)
            return

        if self.create_dir:
            try:
                parent = path.parent
                if not parent.exists():
                    parent.mkdir(parents=True, exist_ok=True)
            except Exception as err:
                await self.error(f"Failed to create directory: {err}", msg)
                return

        mode = "w" if self.overwrite_file in ("true", "1") else "a"
        data_to_write: Union[str, bytes]

        if isinstance(payload, bytes):
            mode += "b"
            data_to_write = payload
        elif isinstance(payload, (dict, list)):
            import json
            data_to_write = json.dumps(payload)
            if self.append_newline:
                data_to_write += "\n"
        else:
            data_to_write = str(payload)
            if self.append_newline:
                data_to_write += "\n"

        try:
            encoding = None if "b" in mode else ("utf-8" if self.encoding in ("none", "utf8", "") else self.encoding)
            async with aiofiles.open(path, mode=mode, encoding=encoding) as f:
                await f.write(data_to_write)

            await self.status(fill="green", shape="dot", text=f"wrote {path.name}")
            await self.send(msg)
        except Exception as err:
            await self.error(f"Write file failed: {err}", msg)


class FileInNode(Node):
    """ Reads files from disk as utf8 string, split lines, or binary buffer.
    Mirrors @node-red/nodes/core/storage/10-file.js (FileInNode).
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.filename: str = config.get("filename", "")
        self.filename_type: str = config.get("filenameType", "str" if self.filename else "msg")
        self.format: str = config.get("format", "utf8")  # "utf8", "lines", "", "stream"
        self.encoding: str = config.get("encoding", "none")

    async def on_input(self, msg: Dict[str, Any]) -> None:
        target_file = ""
        if self.filename_type == "msg":
            prop = self.filename or "filename"
            target_file = str(get_property(msg, prop) or "")
        elif self.filename:
            target_file = str(evaluate_value(self.filename_type, self.filename, msg=msg, node=self) or "")

        if not target_file:
            await self.error("No filename specified", msg)
            return

        path = Path(target_file)
        if not await aiofiles.os.path.exists(path):
            await self.error(f"File not found: {target_file}", msg)
            return

        try:
            if self.format == "lines":
                # Output line by line
                encoding = "utf-8" if self.encoding in ("none", "utf8", "") else self.encoding
                async with aiofiles.open(path, mode="r", encoding=encoding) as f:
                    lines = await f.readlines()
                total = len(lines)
                for idx, line in enumerate(lines):
                    line_msg = copy.deepcopy(msg)
                    line_msg["payload"] = line.rstrip("\r\n")
                    line_msg["parts"] = {
                        "id": msg.get("_msgid", "file"),
                        "index": idx,
                        "count": total,
                        "type": "string"
                    }
                    await self.send(line_msg)
            elif self.format in ("utf8", "str"):
                encoding = "utf-8" if self.encoding in ("none", "utf8", "") else self.encoding
                async with aiofiles.open(path, mode="r", encoding=encoding) as f:
                    content = await f.read()
                out_msg = copy.deepcopy(msg)
                out_msg["payload"] = content
                await self.send(out_msg)
            else:
                # Binary buffer
                async with aiofiles.open(path, mode="rb") as f:
                    content_bytes = await f.read()
                out_msg = copy.deepcopy(msg)
                out_msg["payload"] = content_bytes
                await self.send(out_msg)

        except Exception as err:
            await self.error(f"File read error: {err}", msg)


class S3ConfigNode(Node):
    """ Configuration node for AWS S3 and MinIO blob storage.
    Holds endpoint URL, region, access key, and secret key.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.endpoint_url: Optional[str] = config.get("endpoint") or None
        self.region_name: str = config.get("region", "us-east-1")
        self.aws_access_key_id: Optional[str] = config.get("accessKey") or os.environ.get("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key: Optional[str] = config.get("secretKey") or os.environ.get("AWS_SECRET_ACCESS_KEY")
        self._client = None

    def get_client(self):
        """ Returns an authenticated boto3 S3 client.
        """
        if self._client is None:
            import boto3
            kwargs: Dict[str, Any] = {
                "region_name": self.region_name,
            }
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            if self.aws_access_key_id and self.aws_secret_access_key:
                kwargs["aws_access_key_id"] = self.aws_access_key_id
                kwargs["aws_secret_access_key"] = self.aws_secret_access_key

            self._client = boto3.client("s3", **kwargs)
        return self._client


class S3InNode(Node):
    """ Downloads or fetches blob objects from AWS S3 or MinIO.
    Payload can be returned as string, JSON parsed, or raw bytes.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.bucket: str = config.get("bucket", "")
        self.key: str = config.get("key", "")
        self.s3_config_id: str = config.get("s3Config", "")
        self.format: str = config.get("format", "utf8")  # "utf8", "buffer", "json"

    async def on_input(self, msg: Dict[str, Any]) -> None:
        bucket = self.bucket or str(msg.get("bucket", ""))
        key = self.key or str(msg.get("key", "") or msg.get("filename", ""))

        if not bucket or not key:
            await self.error("Missing S3 bucket or object key", msg)
            return

        # Resolve S3 client
        client = None
        if self.s3_config_id and self.flow:
            config_node = self.flow.get_node(self.s3_config_id)
            if config_node and hasattr(config_node, "get_client"):
                client = config_node.get_client()

        if client is None:
            import boto3
            client = boto3.client("s3")

        try:
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, lambda: client.get_object(Bucket=bucket, Key=key))
            body_stream = resp["Body"]
            raw_data = await loop.run_in_executor(None, body_stream.read)

            out_msg = copy.deepcopy(msg)
            out_msg["bucket"] = bucket
            out_msg["key"] = key
            out_msg["contentType"] = resp.get("ContentType", "")

            if self.format == "utf8":
                out_msg["payload"] = raw_data.decode("utf-8")
            elif self.format == "json":
                import json
                out_msg["payload"] = json.loads(raw_data.decode("utf-8"))
            else:
                out_msg["payload"] = raw_data

            await self.send(out_msg)
            await self.status(fill="green", shape="dot", text=f"downloaded {key}")
        except Exception as err:
            await self.error(f"S3 get_object error: {err}", msg)


class S3OutNode(Node):
    """ Uploads, writes, or deletes blob objects in AWS S3 or MinIO.
    """

    def __init__(self, config: Dict[str, Any], flow: Optional[Any] = None):
        super().__init__(config, flow)
        self.bucket: str = config.get("bucket", "")
        self.key: str = config.get("key", "")
        self.s3_config_id: str = config.get("s3Config", "")
        self.action: str = config.get("action", "upload")  # "upload" or "delete"

    async def on_input(self, msg: Dict[str, Any]) -> None:
        bucket = self.bucket or str(msg.get("bucket", ""))
        key = self.key or str(msg.get("key", "") or msg.get("filename", ""))
        action = str(msg.get("action", self.action)).lower()

        if not bucket or not key:
            await self.error("Missing S3 bucket or object key", msg)
            return

        client = None
        if self.s3_config_id and self.flow:
            config_node = self.flow.get_node(self.s3_config_id)
            if config_node and hasattr(config_node, "get_client"):
                client = config_node.get_client()

        if client is None:
            import boto3
            client = boto3.client("s3")

        loop = asyncio.get_running_loop()

        try:
            if action == "delete":
                await loop.run_in_executor(None, lambda: client.delete_object(Bucket=bucket, Key=key))
                await self.status(fill="grey", shape="dot", text=f"deleted {key}")
                await self.send(msg)
            else:
                payload = msg.get("payload")
                if payload is None:
                    payload = b""

                if isinstance(payload, str):
                    body_bytes = payload.encode("utf-8")
                elif isinstance(payload, (dict, list)):
                    import json
                    body_bytes = json.dumps(payload).encode("utf-8")
                elif isinstance(payload, bytes):
                    body_bytes = payload
                else:
                    body_bytes = str(payload).encode("utf-8")

                content_type = msg.get("contentType", "application/octet-stream")
                await loop.run_in_executor(
                    None,
                    lambda: client.put_object(
                        Bucket=bucket,
                        Key=key,
                        Body=body_bytes,
                        ContentType=content_type,
                    ),
                )
                await self.status(fill="green", shape="dot", text=f"uploaded {key}")
                await self.send(msg)
        except Exception as err:
            await self.error(f"S3 put/delete error: {err}", msg)

