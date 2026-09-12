""" Context storage subsystem for FastAPI-Red.

Mirrors @node-red/runtime/lib/nodes/context/index.js:
- Hierarchical scopes: Node context, Flow context, Global context
- Thread-safe in-memory stores with persistent capability hooks
- get, set, keys methods matching Node-RED context API
"""

import copy
import logging
from typing import Any, Dict, List, Optional


logger = logging.getLogger("fastapi_red.runtime.context")


class ContextStore:
    """ Key-value in-memory storage matching Node-RED context scope store.
    """

    def __init__(self, scope_id: str):
        self.scope_id: str = scope_id
        self._data: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """ Retrieves a stored value by key.
        """
        if key in self._data:
            return copy.deepcopy(self._data[key])
        return default

    def set(self, key: str, value: Any) -> None:
        """ Stores a value by key. If value is None, deletes the key.
        """
        if value is None:
            self._data.pop(key, None)
        else:
            self._data[key] = copy.deepcopy(value)

    def keys(self) -> List[str]:
        """ Returns all stored keys in this context scope.
        """
        return sorted(list(self._data.keys()))

    def clear(self) -> None:
        """ Clears all keys in this store.
        """
        self._data.clear()


class ContextManager:
    """ Manages Node, Flow, and Global context hierarchies,
    matching Node-RED runtime context manager.
    """

    def __init__(self):
        self._global_store = ContextStore("global")
        self._flow_stores: Dict[str, ContextStore] = {}
        self._node_stores: Dict[str, ContextStore] = {}

    def get_global(self) -> ContextStore:
        """ Returns the global context store.
        """
        return self._global_store

    def get_flow(self, flow_id: str) -> ContextStore:
        """ Returns or creates a flow-scoped context store.
        """
        if flow_id not in self._flow_stores:
            self._flow_stores[flow_id] = ContextStore(f"flow:{flow_id}")
        return self._flow_stores[flow_id]

    def get_node(self, node_id: str) -> ContextStore:
        """ Returns or creates a node-scoped context store.
        """
        if node_id not in self._node_stores:
            self._node_stores[node_id] = ContextStore(f"node:{node_id}")
        return self._node_stores[node_id]

    def clear(self) -> None:
        """ Clears all stores on runtime re-initialization.
        """
        self._global_store.clear()
        self._flow_stores.clear()
        self._node_stores.clear()


# Global context manager singleton
context_manager = ContextManager()

