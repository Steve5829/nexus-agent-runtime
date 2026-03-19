# Architecture Notes

Nexus Agent Runtime is split into three layers so each part can be reviewed on its own.

## 1. Protocol edge

`core/mcp_adapter/server.py` handles:

- tool registration
- JSON-RPC 2.0 request validation
- minimal MCP-style methods
- argument schema checking
- stdio request/response serving

The goal is to keep the protocol surface explicit and easy to test.

## 2. Execution boundary

`core/sandbox/runtime.py` is the Python boundary for subprocess execution.

- On Linux, it prepends the compiled `sandbox_kernel` launcher.
- On non-Linux hosts or when the launcher is missing, it falls back to direct execution.
- This keeps local development easy while still showcasing a realistic split between protocol handling and payload execution.

## 3. Telemetry and object model

`sdk/secure_api.py` demonstrates data descriptor behavior:

- values are validated on assignment
- storage lives in the descriptor, not in `instance.__dict__`
- deletion is blocked
- access and writes are recorded into an audit log

## Security stance

This repository is a prototype, not a hardened multi-tenant sandbox. Current guarantees are intentionally narrow:

- Linux resource limits are enforced in the launcher.
- Seccomp is best understood here as a prototype allowlist, not a production profile.
- Namespace isolation is best-effort because unprivileged host capabilities vary.
- Non-Linux systems run without kernel-level isolation.

That tradeoff is deliberate for a public showcase repository: the code stays small enough to audit while still proving the implementation direction.
