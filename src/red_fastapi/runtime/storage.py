""" Storage layer for flows, credentials, and settings.

Supports pluggable backends:
1. Local filesystem ('local'): Default storage in `storage/flows.json` and `storage/flows_cred.json`
2. AWS S3 / MinIO ('s3'): Cloud object storage in S3/MinIO bucket.

Mirrors @node-red/runtime/lib/storage/localfilesystem/index.js and pluggable storageModule contract:
- init
- getFlows
- saveFlows
- getCredentials
- saveCredentials
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from red_fastapi.config import settings

logger = logging.getLogger("red_fastapi.runtime.storage")

DEFAULT_INITIAL_FLOWS: List[Dict[str, Any]] = [
    {
        "type": "tab",
        "id": "flow1",
        "label": "Flow 1",
        "disabled": False,
        "info": "",
        "env": []
    }
]


def compute_rev(flows: List[Dict[str, Any]]) -> str:
    """ Computes an MD5 revision identifier from the serialized flow content,
    matching flow revision tracking in Node-RED.
    """
    serialized = json.dumps(flows, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()


class BaseStorageDriver(ABC):
    """ Abstract base class for storage drivers.
    """

    @abstractmethod
    def init(self) -> None:
        pass

    @abstractmethod
    def get_flows(self) -> Tuple[List[Dict[str, Any]], str]:
        pass

    @abstractmethod
    def save_flows(self, flows: List[Dict[str, Any]]) -> str:
        pass

    @abstractmethod
    def get_credentials(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def save_credentials(self, credentials: Dict[str, Any]) -> None:
        pass


class LocalFileStorageDriver(BaseStorageDriver):
    """ Local filesystem storage driver.
    """

    def __init__(self):
        self._cached_flows: Optional[List[Dict[str, Any]]] = None
        self._cached_rev: Optional[str] = None
        self._cached_credentials: Dict[str, Any] = {}

    def init(self) -> None:
        settings.user_dir.mkdir(parents=True, exist_ok=True)
        if not settings.flows_file.exists():
            self.save_flows(DEFAULT_INITIAL_FLOWS)

    def get_flows(self) -> Tuple[List[Dict[str, Any]], str]:
        if self._cached_flows is not None and self._cached_rev is not None:
            return self._cached_flows, self._cached_rev

        if settings.flows_file.is_file():
            try:
                with open(settings.flows_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            self._cached_flows = data
                            self._cached_rev = compute_rev(data)
                            return self._cached_flows, self._cached_rev
            except Exception as e:
                logger.warning(f"Error reading flows from local file: {e}")

        # Default fallback
        self._cached_flows = list(DEFAULT_INITIAL_FLOWS)
        self._cached_rev = compute_rev(self._cached_flows)
        self.save_flows(self._cached_flows)
        return self._cached_flows, self._cached_rev

    def save_flows(self, flows: List[Dict[str, Any]]) -> str:
        settings.user_dir.mkdir(parents=True, exist_ok=True)
        rev = compute_rev(flows)

        temp_file = settings.flows_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(flows, f, indent=4, ensure_ascii=False)
        temp_file.replace(settings.flows_file)

        self._cached_flows = list(flows)
        self._cached_rev = rev
        return rev

    def get_credentials(self) -> Dict[str, Any]:
        if settings.credentials_file.is_file():
            try:
                with open(settings.credentials_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._cached_credentials = data
                        return self._cached_credentials
            except Exception as e:
                logger.warning(f"Error reading credentials from local file: {e}")
        return self._cached_credentials

    def save_credentials(self, credentials: Dict[str, Any]) -> None:
        settings.user_dir.mkdir(parents=True, exist_ok=True)
        temp_file = settings.credentials_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(credentials, f, indent=4, ensure_ascii=False)
        temp_file.replace(settings.credentials_file)
        self._cached_credentials = dict(credentials)


class S3StorageDriver(BaseStorageDriver):
    """ AWS S3 / MinIO Object Storage Driver.
    Stores flows and credentials as objects in a designated S3 bucket.
    """

    def __init__(self):
        self._cached_flows: Optional[List[Dict[str, Any]]] = None
        self._cached_rev: Optional[str] = None
        self._cached_credentials: Dict[str, Any] = {}
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            kwargs: Dict[str, Any] = {
                "region_name": settings.s3_region_name,
            }
            if settings.s3_endpoint_url:
                kwargs["endpoint_url"] = settings.s3_endpoint_url
            if settings.s3_access_key_id and settings.s3_secret_access_key:
                kwargs["aws_access_key_id"] = settings.s3_access_key_id
                kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def _ensure_bucket(self) -> None:
        client = self._get_client()
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            try:
                if settings.s3_region_name and settings.s3_region_name != "us-east-1":
                    client.create_bucket(
                        Bucket=settings.s3_bucket,
                        CreateBucketConfiguration={"LocationConstraint": settings.s3_region_name}
                    )
                else:
                    client.create_bucket(Bucket=settings.s3_bucket)
                logger.info(f"Created S3 bucket '{settings.s3_bucket}'")
            except Exception as err:
                logger.warning(f"Could not verify or create bucket '{settings.s3_bucket}': {err}")

    def init(self) -> None:
        self._ensure_bucket()
        client = self._get_client()
        try:
            client.head_object(Bucket=settings.s3_bucket, Key=settings.s3_flows_key)
        except Exception:
            # Initialize with default initial flows if object not found
            self.save_flows(DEFAULT_INITIAL_FLOWS)

    def get_flows(self) -> Tuple[List[Dict[str, Any]], str]:
        if self._cached_flows is not None and self._cached_rev is not None:
            return self._cached_flows, self._cached_rev

        client = self._get_client()
        try:
            resp = client.get_object(Bucket=settings.s3_bucket, Key=settings.s3_flows_key)
            raw = resp["Body"].read().decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                self._cached_flows = data
                self._cached_rev = compute_rev(data)
                return self._cached_flows, self._cached_rev
        except Exception as err:
            logger.warning(f"Failed to read flows from S3 bucket '{settings.s3_bucket}': {err}")

        # Fallback to default
        self._cached_flows = list(DEFAULT_INITIAL_FLOWS)
        self._cached_rev = compute_rev(self._cached_flows)
        self.save_flows(self._cached_flows)
        return self._cached_flows, self._cached_rev

    def save_flows(self, flows: List[Dict[str, Any]]) -> str:
        client = self._get_client()
        rev = compute_rev(flows)
        payload = json.dumps(flows, indent=4, ensure_ascii=False).encode("utf-8")

        client.put_object(
            Bucket=settings.s3_bucket,
            Key=settings.s3_flows_key,
            Body=payload,
            ContentType="application/json"
        )
        self._cached_flows = list(flows)
        self._cached_rev = rev
        return rev

    def get_credentials(self) -> Dict[str, Any]:
        client = self._get_client()
        try:
            resp = client.get_object(Bucket=settings.s3_bucket, Key=settings.s3_credentials_key)
            raw = resp["Body"].read().decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                self._cached_credentials = data
                return self._cached_credentials
        except Exception:
            pass
        return self._cached_credentials

    def save_credentials(self, credentials: Dict[str, Any]) -> None:
        client = self._get_client()
        payload = json.dumps(credentials, indent=4, ensure_ascii=False).encode("utf-8")
        client.put_object(
            Bucket=settings.s3_bucket,
            Key=settings.s3_credentials_key,
            Body=payload,
            ContentType="application/json"
        )
        self._cached_credentials = dict(credentials)


def _get_driver() -> BaseStorageDriver:
    """ Resolves the configured storage driver.
    """
    driver_type = (settings.storage_type or "local").lower().strip()
    if driver_type in ("s3", "minio"):
        return S3StorageDriver()
    return LocalFileStorageDriver()


# Active singleton storage driver
_active_driver: BaseStorageDriver = _get_driver()


def init() -> None:
    """ Initialises the active storage subsystem.
    """
    global _active_driver
    _active_driver = _get_driver()
    _active_driver.init()


def get_flows() -> Tuple[List[Dict[str, Any]], str]:
    """ Reads flows from the active storage driver.
    """
    return _active_driver.get_flows()


def save_flows(flows: List[Dict[str, Any]]) -> str:
    """ Saves flows to the active storage driver.
    """
    return _active_driver.save_flows(flows)


def get_credentials() -> Dict[str, Any]:
    """ Reads credentials from the active storage driver.
    """
    return _active_driver.get_credentials()


def save_credentials(credentials: Dict[str, Any]) -> None:
    """ Saves credentials to the active storage driver.
    """
    _active_driver.save_credentials(credentials)
