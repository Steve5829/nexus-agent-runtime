import asyncio
import inspect
import json
import logging
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional


logger = logging.getLogger("NexusMCP")

JSONRPC_VERSION = "2.0"
SUPPORTED_METHODS = frozenset(
    {
        "initialize",
        "list_tools",
        "call_tool",
        "tools/list",
        "tools/call",
        "shutdown",
    }
)
SCHEMA_TYPE_MAP = {
    "string": str,
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class MCPError(Exception):
    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_payload(self) -> Dict[str, Any]:
        payload = {"code": self.code, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        return payload


class NexusServer:
    """
    Minimal MCP-style JSON-RPC server with schema validation and stdio support.
    """

    def __init__(self, name: str = "Nexus Agent Runtime", version: str = "0.1.0"):
        self.name = name
        self.version = version
        self.tools = {}  # type: Dict[str, MCPTool]
        self._running = False

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator used to register a tool exposed over JSON-RPC."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            tool_desc = description or inspect.getdoc(func) or "No description provided."
            tool_schema = self._normalize_schema(input_schema)
            self.tools[tool_name] = MCPTool(
                name=tool_name,
                description=tool_desc,
                input_schema=tool_schema,
                handler=func,
            )
            logger.info("Registered tool: %s", tool_name)
            return func

        return decorator

    async def handle_request(self, request_data: str) -> str:
        """Parse a single JSON-RPC request and return a serialized response."""
        try:
            request = json.loads(request_data)
        except json.JSONDecodeError:
            return json.dumps(self._error_response(None, -32700, "Parse error"))

        try:
            response = await self.handle_message(request)
        except MCPError as exc:
            response = self._error_response(request.get("id"), exc.code, exc.message, exc.data)
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("Unexpected server error")
            response = self._error_response(request.get("id"), -32603, "Internal error", str(exc))

        return json.dumps(response)

    async def handle_message(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(request, Mapping):
            raise MCPError(-32600, "Invalid Request", "Top-level request must be an object.")

        jsonrpc = request.get("jsonrpc")
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if jsonrpc != JSONRPC_VERSION:
            raise MCPError(-32600, "Invalid Request", "Only JSON-RPC 2.0 is supported.")
        if not isinstance(method, str):
            raise MCPError(-32600, "Invalid Request", "Request method must be a string.")
        if method not in SUPPORTED_METHODS:
            raise MCPError(-32601, "Method not found", method)
        if params is not None and not isinstance(params, Mapping):
            raise MCPError(-32602, "Invalid params", "Request params must be an object.")

        if method == "initialize":
            return self._success_response(
                req_id,
                {
                    "server": {"name": self.name, "version": self.version},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            )

        if method in ("list_tools", "tools/list"):
            return self._success_response(
                req_id,
                {"tools": [tool.to_public_dict() for tool in self.tools.values()]},
            )

        if method in ("call_tool", "tools/call"):
            return await self._handle_tool_call(req_id, params)

        self._running = False
        return self._success_response(req_id, {"ok": True})

    async def serve_stdio(self) -> None:
        """
        Run a newline-delimited JSON-RPC loop over stdio.

        This is intentionally small and dependency-free so the repository stays
        easy to inspect and run in a public demo setting.
        """
        self._running = True
        loop = asyncio.get_running_loop()
        logger.info("Starting stdio loop for %s", self.name)
        while self._running:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            payload = line.strip()
            if not payload:
                continue

            response = await self.handle_request(payload)
            sys.stdout.write(response + "\n")
            sys.stdout.flush()

    async def run(self) -> None:
        await self.serve_stdio()

    async def _handle_tool_call(self, req_id: Any, params: Mapping[str, Any]) -> Dict[str, Any]:
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not isinstance(tool_name, str) or not tool_name:
            raise MCPError(-32602, "Invalid params", "Tool name must be a non-empty string.")
        if not isinstance(arguments, Mapping):
            raise MCPError(-32602, "Invalid params", "Tool arguments must be an object.")
        if tool_name not in self.tools:
            raise MCPError(-32601, "Method not found", "Unknown tool: %s" % tool_name)

        tool = self.tools[tool_name]
        validated_arguments = self._validate_arguments(tool.input_schema, arguments)
        logger.info("Executing tool '%s' with args: %s", tool_name, validated_arguments)

        try:
            result = tool.handler(**validated_arguments)
            if inspect.isawaitable(result):
                result = await result
        except MCPError:
            raise
        except Exception as exc:
            logger.exception("Tool '%s' raised an exception", tool_name)
            raise MCPError(-32000, "Tool execution failed", str(exc))

        return self._success_response(req_id, {"content": self._coerce_content(result)})

    def _normalize_schema(self, schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        base = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        if not schema:
            return base
        merged = dict(base)
        merged.update(schema)
        merged["properties"] = dict(schema.get("properties", {}))
        merged["required"] = list(schema.get("required", []))
        return merged

    def _validate_arguments(self, schema: Mapping[str, Any], arguments: Mapping[str, Any]) -> Dict[str, Any]:
        if schema.get("type") != "object":
            raise MCPError(-32603, "Internal error", "Tool schema must describe an object.")

        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        validated = {}

        missing = [name for name in required if name not in arguments]
        if missing:
            raise MCPError(-32602, "Invalid params", "Missing required arguments: %s" % ", ".join(sorted(missing)))

        if not schema.get("additionalProperties", False):
            unknown = [name for name in arguments if name not in properties]
            if unknown:
                raise MCPError(-32602, "Invalid params", "Unknown arguments: %s" % ", ".join(sorted(unknown)))

        for name, value in arguments.items():
            property_schema = properties.get(name)
            if property_schema is not None:
                self._validate_value(name, value, property_schema)
            validated[name] = value

        return validated

    def _validate_value(self, name: str, value: Any, schema: Mapping[str, Any]) -> None:
        expected_type = schema.get("type")
        if expected_type is None:
            return

        if expected_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MCPError(-32602, "Invalid params", "Argument '%s' must be numeric." % name)
            return

        if expected_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise MCPError(-32602, "Invalid params", "Argument '%s' must be an integer." % name)
            return

        python_type = SCHEMA_TYPE_MAP.get(expected_type)
        if python_type is None:
            return

        if not isinstance(value, python_type):
            raise MCPError(-32602, "Invalid params", "Argument '%s' must be of type %s." % (name, expected_type))

        if expected_type == "array":
            item_schema = schema.get("items")
            if item_schema:
                for index, item in enumerate(value):
                    self._validate_value("%s[%d]" % (name, index), item, item_schema)
            return

        if expected_type == "object":
            nested_properties = schema.get("properties")
            if nested_properties:
                nested_required = set(schema.get("required", []))
                missing = [key for key in nested_required if key not in value]
                if missing:
                    raise MCPError(
                        -32602,
                        "Invalid params",
                        "Argument '%s' is missing keys: %s" % (name, ", ".join(sorted(missing))),
                    )
                for key, nested_value in value.items():
                    nested_schema = nested_properties.get(key)
                    if nested_schema:
                        self._validate_value("%s.%s" % (name, key), nested_value, nested_schema)

    def _coerce_content(self, result: Any) -> Any:
        if isinstance(result, dict) and "content" in result:
            return result["content"]
        if isinstance(result, str):
            text = result
        else:
            text = json.dumps(result, sort_keys=True)
        return [{"type": "text", "text": text}]

    def _success_response(self, req_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": result}

    def _error_response(
        self,
        req_id: Any,
        code: int,
        message: str,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        payload = {"code": code, "message": message}
        if data is not None:
            payload["data"] = data
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "error": payload}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    server = NexusServer()

    @server.tool(
        name="echo",
        description="Echo a string back to the caller.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )
    async def echo_tool(text: str) -> str:
        return "Nexus says: %s" % text

    asyncio.run(server.run())
