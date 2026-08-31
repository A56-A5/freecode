"""
freecode.mcp.endpoint - JSON-RPC transport layer for MCP server.

Implements the MCP protocol over stdio (JSON-RPC 2.0).
This allows the server to be used as an MCP server by Claude, cursor, or other MCP clients.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Callable

from freecode.config.logging import get_logger
from freecode.mcp.server import MCPServer

log = get_logger(__name__)


class JSONRPCError(Exception):
    """JSON-RPC error with error code."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data


class MCPEndpoint:
    """
    JSON-RPC 2.0 endpoint for MCP server.

    Reads JSON-RPC requests from stdin, dispatches to MCPServer,
    writes JSON-RPC responses to stdout.
    """

    # JSON-RPC error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    def __init__(self, server: MCPServer) -> None:
        self.server = server
        self.request_id_counter = 0
        self.handlers: dict[str, Callable] = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "ping": self._handle_ping,
        }

    async def run(self) -> None:
        """Run the endpoint — read requests from stdin, write responses to stdout."""
        loop = asyncio.get_event_loop()

        # Run stdin reading in executor to avoid blocking
        while True:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                request = json.loads(line)
                response = await self.dispatch(request)
                if response:
                    sys.stdout.write(json.dumps(response, default=str) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError as e:
                error_response = self._error_response(
                    None,
                    self.PARSE_ERROR,
                    f"JSON parse error: {e}",
                )
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()
            except Exception as e:
                log.exception("Unexpected error in endpoint loop")
                error_response = self._error_response(
                    None,
                    self.INTERNAL_ERROR,
                    str(e),
                )
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """
        Dispatch a JSON-RPC request to the appropriate handler.

        Args:
            request: JSON-RPC 2.0 request object

        Returns:
            JSON-RPC 2.0 response object, or None for notifications
        """
        try:
            # Validate request structure
            if not isinstance(request, dict):
                return self._error_response(None, self.INVALID_REQUEST, "Request must be an object")

            jsonrpc = request.get("jsonrpc")
            method = request.get("method")
            req_id = request.get("id")
            params = request.get("params", {})

            if jsonrpc != "2.0":
                return self._error_response(req_id, self.INVALID_REQUEST, "jsonrpc must be '2.0'")

            if not isinstance(method, str):
                return self._error_response(req_id, self.INVALID_REQUEST, "method must be a string")

            # Dispatch to handler
            if method not in self.handlers:
                return self._error_response(req_id, self.METHOD_NOT_FOUND, f"Method not found: {method}")

            handler = self.handlers[method]
            result = await handler(params)

            # Notifications don't get responses
            if req_id is None:
                return None

            return self._success_response(req_id, result)

        except JSONRPCError as e:
            return self._error_response(req_id, e.code, e.message, e.data)
        except TypeError as e:
            return self._error_response(req_id, self.INVALID_PARAMS, str(e))
        except Exception as e:
            log.exception(f"Error handling request: {request}")
            return self._error_response(req_id, self.INTERNAL_ERROR, str(e))

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
            },
            "serverInfo": {
                "name": "freecode",
                "version": "0.1.0",
            },
        }

    async def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/list request."""
        return {"tools": self.server.list_tools()}

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/call request."""
        if "name" not in params:
            raise JSONRPCError(self.INVALID_PARAMS, "name is required")
        if "arguments" not in params:
            raise JSONRPCError(self.INVALID_PARAMS, "arguments is required")

        name = params["name"]
        arguments = params["arguments"]

        if not isinstance(arguments, dict):
            raise JSONRPCError(self.INVALID_PARAMS, "arguments must be an object")

        return await self.server.call_tool(name, arguments)

    async def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle resources/list request."""
        return {"resources": self.server.get_resources()}

    async def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle resources/read request."""
        if "uri" not in params:
            raise JSONRPCError(self.INVALID_PARAMS, "uri is required")

        uri = params["uri"]
        content = await self.server.read_resource(uri)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": content,
                }
            ]
        }

    async def _handle_ping(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ping request."""
        return {"ok": True}

    def _success_response(self, req_id: Any, result: Any) -> dict[str, Any]:
        """Create a JSON-RPC success response."""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }

    def _error_response(self, req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
        """Create a JSON-RPC error response."""
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if data is not None:
            response["error"]["data"] = data
        return response


async def run_mcp_server(project_root: str = ".") -> None:
    """
    Launch the MCP server.

    Args:
        project_root: Path to the FreeCode project root
    """
    try:
        server = MCPServer(project_root)
        endpoint = MCPEndpoint(server)
        await endpoint.run()
    except KeyboardInterrupt:
        log.info("MCP server interrupted")
    except Exception as e:
        log.exception("MCP server error")
        sys.exit(1)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from freecode.config import load_config, setup_logging

    # Setup logging
    config = load_config()
    setup_logging(config)

    # Determine project root
    root = Path.cwd()
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])

    # Run server
    asyncio.run(run_mcp_server(str(root)))
