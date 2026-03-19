# Security Policy

## Scope

Nexus Agent Runtime is a prototype repository for secure tool execution patterns. It is not advertised as a production-grade multi-tenant sandbox.

## Threat model

The current repository aims to reduce accidental misuse and demonstrate a credible hardening direction:

- JSON-RPC requests are validated before tool execution.
- Tool arguments are checked against declared schemas.
- Linux launcher mode applies resource caps and a seccomp allowlist.
- Descriptor-backed telemetry avoids trivial instance-dictionary tampering.

The repository does not currently guarantee:

- full filesystem isolation
- cross-platform kernel hardening
- protection against determined local attackers
- a complete seccomp profile for arbitrary payloads

## Reporting

If you find a security issue, open a private advisory or contact the maintainer directly before filing a public issue.

When reporting, include:

- affected file and commit
- reproduction steps
- expected and actual behavior
- impact assessment
