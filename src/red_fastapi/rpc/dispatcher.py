""" JSON-RPC 2.0 Dispatcher Implementation.\n
Supports async method registration (decorator & function call),
request validation, single/batch execution, notifications, and error mapping.
Maintains full signature and naming parity with standard Option B / C libraries.
"""

import asyncio
import inspect
import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from pydantic import ValidationError

from red_fastapi.rpc.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    InternalError,
    InvalidParams,
    InvalidRequest,
    JSONRPCError,
    MethodNotFound,
    ParseError,
)
from red_fastapi.rpc.models import (
    JSONRPCErrorData,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)

logger = logging.getLogger("red_fastapi.rpc")


class JSONRPCDispatcher:
    """ High-performance Async JSON-RPC 2.0 Dispatcher.\n
    Maintains signature compatibility with Option B (jsonrpc-async) and Option C (mcp Server)
    methods such as add_method, register, and dispatch.
    """

    def __init__(self):
        self._methods: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

    def add_method( self,
            name_or_func: Union[str, Callable],
            func: Optional[Callable] = None,
        ) -> Any:
        """ Register an async RPC method.

        Can be used as a standard method call:
            dispatcher.add_method("echo", my_func)
        Or as a decorator:
            @dispatcher.add_method("echo")
            async def my_func(...): ...
            # or
            @dispatcher.add_method
            async def echo(...): ...
        """
        if func is None:
            if callable(name_or_func):
                # Decorator with no arguments: @dispatcher.add_method
                method_name = name_or_func.__name__
                self._methods[method_name] = name_or_func
                return name_or_func
            elif isinstance(name_or_func, str):
                # Decorator with name: @dispatcher.add_method("custom_name")
                def decorator(target_func: Callable):
                    self._methods[name_or_func] = target_func
                    return target_func
                return decorator

        if not callable(func):
            raise ValueError(f"RPC method handler must be callable, got {type(func)}")

        self._methods[str(name_or_func)] = func
        return func

    # Alias for Option B compatibility
    register = add_method

    def has_method(self, name: str) -> bool:
        """ Check if a method name is registered."""
        return name in self._methods

    def list_methods(self) -> List[str]:
        """ Return list of all registered method names."""
        return list(self._methods.keys())

    async def _invoke_handler(self, handler: Callable, params: Optional[Union[Dict[str, Any], List[Any]]]) -> Any:
        """ Execute the method handler with positional or keyword params."""
        try:
            if params is None:
                if inspect.iscoroutinefunction(handler):
                    return await handler()
                return handler()
            elif isinstance(params, dict):
                if inspect.iscoroutinefunction(handler):
                    return await handler(**params)
                return handler(**params)
            elif isinstance(params, list):
                if inspect.iscoroutinefunction(handler):
                    return await handler(*params)
                return handler(*params)
            else:
                raise InvalidParams(message="Parameters must be a list or object dictionary")
        except TypeError as err:
            # Inspection check for argument mismatch
            logger.warning("Handler argument error for %s: %s", getattr(handler, '__name__', str(handler)), err)
            raise InvalidParams(message=str(err))
        except JSONRPCError:
            raise
        except Exception as err:
            logger.exception("Internal error during RPC execution: %s", err)
            raise InternalError(data=str(err))

    async def _handle_single( self, req_data: Any ) -> Optional[JSONRPCResponse]:
        """ Processes a single JSON-RPC message dictionary or object."""
        if not isinstance(req_data, dict):
            return JSONRPCResponse(
                id=None,
                error=JSONRPCErrorData(code=INVALID_REQUEST, message="Invalid Request: payload must be a JSON object")
            )

        # Check for JSON-RPC 2.0 version specifier
        if req_data.get("jsonrpc") != "2.0":
            return JSONRPCResponse(
                id=req_data.get("id"),
                error=JSONRPCErrorData(code=INVALID_REQUEST, message="Invalid Request: 'jsonrpc' must be exactly '2.0'")
            )

        is_notification = "id" not in req_data
        msg_id = req_data.get("id")
        method_name = req_data.get("method")
        params = req_data.get("params")

        if not isinstance(method_name, str):
            if is_notification:
                return None
            return JSONRPCResponse(
                id=msg_id,
                error=JSONRPCErrorData(code=INVALID_REQUEST, message="Invalid Request: 'method' must be a string")
            )

        handler = self._methods.get(method_name)
        if not handler:
            if is_notification:
                return None
            return JSONRPCResponse(
                id=msg_id,
                error=JSONRPCErrorData(code=METHOD_NOT_FOUND, message=f"Method not found: '{method_name}'")
            )

        try:
            result = await self._invoke_handler(handler, params)
            if is_notification:
                return None
            return JSONRPCResponse(id=msg_id, result=result)
        except JSONRPCError as err:
            if is_notification:
                return None
            return JSONRPCResponse(
                id=msg_id,
                error=JSONRPCErrorData(code=err.code, message=err.message, data=err.data)
            )
        except Exception as err:
            if is_notification:
                return None
            return JSONRPCResponse(
                id=msg_id,
                error=JSONRPCErrorData(code=INTERNAL_ERROR, message="Internal error", data=str(err))
            )

    async def dispatch( self,
            payload: Union[Dict[str, Any], List[Dict[str, Any]], str, bytes],
        ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """ Dispatch a single request, a batch of requests, or raw JSON.\n
        Returns:
            Dict or List of Dicts conforming to JSON-RPC 2.0 response format,
            or None if all requests were notifications.
        """
        if isinstance(payload, (str, bytes)):
            try:
                payload = json.loads(payload)
            except Exception as err:
                return JSONRPCResponse(
                    id=None,
                    error=JSONRPCErrorData(code=PARSE_ERROR, message="Parse error", data=str(err))
                ).to_dict()

        if isinstance(payload, list):
            if len(payload) == 0:
                return JSONRPCResponse(
                    id=None,
                    error=JSONRPCErrorData(code=INVALID_REQUEST, message="Invalid Request: empty batch")
                ).to_dict()

            responses = await asyncio.gather(*(self._handle_single(item) for item in payload))
            non_null = [resp.to_dict() for resp in responses if resp is not None]
            return non_null if non_null else None

        resp = await self._handle_single(payload)
        return resp.to_dict() if resp is not None else None
