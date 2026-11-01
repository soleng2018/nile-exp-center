# nile-lab

Python CLI that reconciles a Windows and macOS client VM lab on this server (see `README.md` and `docs/specs/0001-stack-architecture/index.md`). Full conventions are captured later by `/audit` (scope feature 2).

## Stack

Python 3.13 (uv, `uv sync --locked`), Typer CLI, pydantic v2 config models over YAML, Docker and `docker compose` through `subprocess`, systemd and udev on the host, pytest. Source of truth: the `## Proposed stack` table in `docs/specs/0001-stack-architecture/index.md`.

## Build approach

Tracer Bullet: prove one real path end to end first (config to VM to browser login), then thicken it one strand at a time. Source: `docs/scope/scope.md` header.

## README rule (always)

`README.md` is the operator's guide to this repo and must stay current. After every change that touches setup, commands, config keys, secrets, prerequisites, or behavior, update `README.md` in the same turn, before you finish. If nothing usage related changed, say so instead.

The README must keep this order:
1. **Prerequisites** first: every package, service, hardware, and access the server needs, with a way to check each one. Mark items not needed yet as *(later)*.
2. **Secrets and values** next: every secret and required value, whether it is secret, where to get it, and its config key. Never put real secret values in the README.
3. Then **Get started** steps, tests, exit codes, and links.

## Agent skills

MCP servers: cloudflare (recommended, official `cloudflare/mcp-server-cloudflare`, connect before feature 6)
Declined: `vm0-ai/vm0-skills` `cloudflare-tunnel`, `deploying-cloudflare-access-for-zero-trust` (flagged by their security audits)
