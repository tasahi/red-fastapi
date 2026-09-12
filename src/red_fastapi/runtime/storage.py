""" Local filesystem storage layer for flows, credentials, and settings.

Mirrors @node-red/runtime/lib/storage/localfilesystem/index.js and util.js:
- init
- getFlows
- saveFlows
- getCredentials
- saveCredentials
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from red_fastapi.config import settings


# In-memory storage state cache
_cached_flows: Optional[List[Dict[str, Any]]] = None
_cached_rev: Optional[str] = None
_cached_credentials: Dict[str, Any] = {}

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


def _compute_rev(flows: List[Dict[str, Any]]) -> str:
    """ Computes an MD5 revision identifier from the serialized flow content,
    matching flow revision tracking in Node-RED.
    """
    serialized = json.dumps(flows, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()


def init() -> None:
    """ Initialises the storage subsystem, ensuring storage directory exists,
    matching init() in @node-red/runtime/lib/storage/localfilesystem/index.js.
    """
    settings.user_dir.mkdir(parents=True, exist_ok=True)
    if not settings.flows_file.exists():
        save_flows(DEFAULT_INITIAL_FLOWS)


def get_flows() -> Tuple[List[Dict[str, Any]], str]:
    """ Reads flows from disk or cache, returning (flows, rev),
    matching getFlows() in @node-red/runtime/lib/storage/localfilesystem/index.js.
    """
    global _cached_flows, _cached_rev

    if _cached_flows is not None and _cached_rev is not None:
        return _cached_flows, _cached_rev

    if settings.flows_file.is_file():
        try:
            with open(settings.flows_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    if isinstance(data, list):
                        _cached_flows = data
                        _cached_rev = _compute_rev(data)
                        return _cached_flows, _cached_rev
        except Exception:
            pass

    # Default fallback
    _cached_flows = list(DEFAULT_INITIAL_FLOWS)
    _cached_rev = _compute_rev(_cached_flows)
    save_flows(_cached_flows)
    return _cached_flows, _cached_rev


def save_flows(flows: List[Dict[str, Any]]) -> str:
    """ Writes the flows array to flows.json and returns the updated revision string,
    matching saveFlows() in @node-red/runtime/lib/storage/localfilesystem/index.js.
    """
    global _cached_flows, _cached_rev

    settings.user_dir.mkdir(parents=True, exist_ok=True)
    rev = _compute_rev(flows)

    temp_file = settings.flows_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(flows, f, indent=4, ensure_ascii=False)
    temp_file.replace(settings.flows_file)

    _cached_flows = list(flows)
    _cached_rev = rev
    return rev


def get_credentials() -> Dict[str, Any]:
    """ Reads credentials from flows_cred.json,
    matching getCredentials() in @node-red/runtime/lib/storage/localfilesystem/index.js.
    """
    global _cached_credentials
    if settings.credentials_file.is_file():
        try:
            with open(settings.credentials_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _cached_credentials = data
                    return _cached_credentials
        except Exception:
            pass
    return _cached_credentials


def save_credentials(credentials: Dict[str, Any]) -> None:
    """ Writes credentials to flows_cred.json,
    matching saveCredentials() in @node-red/runtime/lib/storage/localfilesystem/index.js.
    """
    global _cached_credentials
    settings.user_dir.mkdir(parents=True, exist_ok=True)
    temp_file = settings.credentials_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=4, ensure_ascii=False)
    temp_file.replace(settings.credentials_file)
    _cached_credentials = dict(credentials)

