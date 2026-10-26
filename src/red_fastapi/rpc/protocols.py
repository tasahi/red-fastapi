""" JSON-RPC Protocol Definitions and Abstract Base Classes.\n
Provides standard protocols to ensure seamless swapping between Option A (internal)
and Options B/C (third-party packages such as jsonrpc-async or mcp SDK).
"""

from typing import Any, Callable, Coroutine, Dict, List, Optional, Protocol, Union, runtime_checkable
from red_fastapi.rpc.models import JSONRPCRequest, JSONRPCResponse


@runtime_checkable
class BaseDispatcherProtocol(Protocol):
    """ Protocol matching standard JSON-RPC dispatchers."""

    def add_method( self,
            name_or_func: Union[str, Callable],
            func: Optional[Callable] = None,
        ) -> Any:
        """ Register a method with the dispatcher."""
        ...

    async def dispatch( self,
            payload: Union[Dict[str, Any], List[Dict[str, Any]], str],
        ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """ Dispatch a JSON-RPC request or batch of requests."""
        ...
