import asyncio
import json
from pathlib import Path

import pytest

from core.mcp_adapter import NexusServer
from core.sandbox.runtime import SandboxRuntime
from sdk.secure_api import AgentTelemetry


def test_secure_metric_validation_and_storage_isolation():
    telemetry = AgentTelemetry("test-agent")
    telemetry.cpu_usage = 50.0

    assert telemetry.cpu_usage == 50.0

    telemetry.__dict__["cpu_usage"] = "shadowed"
    telemetry.__dict__["_nexus_cpu_usage"] = "tampered"
    assert telemetry.cpu_usage == 50.0

    with pytest.raises(TypeError):
        telemetry.cpu_usage = "high"

    with pytest.raises(ValueError):
        telemetry.cpu_usage = -10


def test_secure_metric_cannot_be_deleted():
    telemetry = AgentTelemetry("test-agent")
    with pytest.raises(AttributeError):
        del telemetry.cpu_usage


def test_mcp_echo_tool_and_schema_validation():
    server = NexusServer()

    @server.tool(
        name="echo",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )
    async def echo(text):
        return {"content": [{"type": "text", "text": text.upper()}]}

    request = {
        "jsonrpc": "2.0",
        "id": "123",
        "method": "call_tool",
        "params": {"name": "echo", "arguments": {"text": "GSoC-2026"}},
    }

    response_json = asyncio.run(server.handle_request(json.dumps(request)))
    response = json.loads(response_json)

    assert response["id"] == "123"
    assert response["result"]["content"][0]["text"] == "GSOC-2026"

    invalid_request = dict(request)
    invalid_request["params"] = {"name": "echo", "arguments": {"text": 42}}
    invalid_response = json.loads(asyncio.run(server.handle_request(json.dumps(invalid_request))))
    assert invalid_response["error"]["code"] == -32602


def test_mcp_initialize_and_list_tools():
    server = NexusServer()

    @server.tool(name="calc", description="Performs math")
    def calc(x, y):
        return x + y

    initialize_response = json.loads(
        asyncio.run(server.handle_request(json.dumps({"jsonrpc": "2.0", "id": "1", "method": "initialize"})))
    )
    assert initialize_response["result"]["server"]["name"] == "Nexus Agent Runtime"

    list_response = json.loads(
        asyncio.run(server.handle_request(json.dumps({"jsonrpc": "2.0", "id": "2", "method": "tools/list"})))
    )
    tool = list_response["result"]["tools"][0]
    assert tool["name"] == "calc"
    assert tool["description"] == "Performs math"
    assert "handler" not in tool


def test_readme_import_path_is_public():
    from core.mcp_adapter import NexusServer as ExportedNexusServer

    assert ExportedNexusServer.__name__ == "NexusServer"


def test_sandbox_runtime_falls_back_when_launcher_is_missing(tmp_path):
    runtime = SandboxRuntime(launcher=tmp_path / "missing-launcher")
    script = Path(__file__).resolve().parent.parent / "sdk" / "secure_api.py"
    result = runtime.run(["python3", str(script)], timeout=5.0)

    assert result.command[0] == "python3"
    assert result.returncode == 0
