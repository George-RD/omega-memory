# Remote MCP Server for Claude Mobile

**Date**: 2026-02-23
**Status**: Design approved, pending implementation

## Problem

OMEGA is a local-only MCP server (stdio transport). Claude Mobile (Android/iOS) only supports remote MCP servers via Streamable HTTP + OAuth 2.1. There is no way to access OMEGA memories from Claude Mobile.

## Goal

Deploy OMEGA as a remote MCP server accessible from Claude Mobile as a Custom Connector, exposing a curated subset of tools for on-the-go use.

## Architecture

```
Claude Mobile  ──HTTPS──▶  Remote Host (Docker)
                              │
                              ├── FastMCP HTTP Server (remote_server.py)
                              │     5 tools: store, query, memory, remind, profile
                              │     │
                              │     ▼
                              ├── Existing OMEGA Handlers (handlers.py, bridge.py)
                              │     │
                              │     ▼
                              ├── SQLite + sqlite-vec (persistent volume)
                              │
Auth0 (OAuth 2.1 + DCR) ◀──── /.well-known/oauth-protected-resource
```

### Key Decisions

1. **Two separate entry points**: `mcp_server.py` (stdio, local, unchanged) and `remote_server.py` (HTTP, cloud). Share handlers and storage.
2. **FastMCP v3 for HTTP transport**: Built-in Streamable HTTP, ASGI, OAuth support. New dependency.
3. **5 mobile tools only**: omega_store, omega_query, omega_memory, omega_remind, omega_profile. No coordination/entity/oracle.
4. **Auth0 free tier for OAuth 2.1**: Supports Dynamic Client Registration (DCR) required by Claude Mobile. Free up to 25K MAU.
5. **SQLite on persistent volume**: No storage rewrite. Copy of local omega.db uploaded to remote host.
6. **Hosting TBD**: Design is hosting-agnostic (Docker container). Candidates: Fly.io (~$0.50-2/mo), Oracle Cloud (free), self-hosted VPS.

## Components

### New Files

| File | Purpose |
|------|---------|
| `src/omega/server/remote_server.py` | FastMCP HTTP entry point. Registers 5 tools, wraps existing handlers. |
| `src/omega/server/auth.py` | Auth0 OAuth 2.1 integration. JWT validation, well-known endpoints, selective auth. |
| `Dockerfile` | Python 3.11, sqlite-vec, ONNX runtime, Uvicorn. |
| `scripts/sync-db.sh` | Upload/download omega.db to/from remote host. |

### Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | Add `remote` extra: fastmcp>=3.0.0, pyjwt, httpx |

### Unchanged Files

- `src/omega/server/mcp_server.py` (local stdio server)
- `src/omega/server/handlers.py` (all handler logic)
- `src/omega/sqlite_store.py` (storage layer)

## Tool Registration Pattern

Each mobile tool is a thin FastMCP wrapper around the existing handler:

```python
from fastmcp import FastMCP
from omega.server.handlers import HANDLERS

mcp = FastMCP("OMEGA Mobile")

@mcp.tool
async def omega_store(content: str, event_type: str = "general") -> str:
    result = await HANDLERS["omega_store"]({"content": content, "event_type": event_type})
    return result

@mcp.tool
async def omega_query(query: str, mode: str = "semantic") -> str:
    result = await HANDLERS["omega_query"]({"query": query, "mode": mode})
    return result

# omega_memory, omega_remind, omega_profile similarly
```

## Auth Flow

1. Claude Mobile queries `/.well-known/oauth-protected-resource` on OMEGA server
2. Claude auto-registers via RFC 7591 DCR with Auth0
3. User authenticates via Auth0 UI (browser redirect)
4. Auth0 issues JWT; Claude sends Bearer token on subsequent requests
5. Selective auth: `initialize` unauthenticated, `tools/list` and `tools/call` require JWT

## Database Sync

Manual push/pull workflow:

```bash
./scripts/sync-db.sh push   # local omega.db -> remote
./scripts/sync-db.sh pull   # remote omega.db -> local backup
```

No automated sync. Mobile writes accumulate remotely; periodic manual merge if needed.

## Hosting Candidates

| Platform | Cost | SQLite Support | Notes |
|----------|------|----------------|-------|
| Fly.io | ~$0.50-2/mo | Persistent volumes | Auto-stop, fly mcp wrap |
| Oracle Cloud | Free forever | Full VM with disk | ARM, manual setup |
| Self-hosted VPS | ~$5-10/mo | Full disk | Full control |
| Render | Free tier | No persistent disk | Would need Turso |
| Google Cloud Run | ~$15/mo | Ephemeral | Would need Turso |

## What This Does NOT Include

- Automated database sync between local and remote
- Coordination/entity/oracle tools on mobile
- Hook server on remote (not needed for 5-tool subset)
- Embedding daemon on remote (in-process ONNX fallback)
- Pro license enforcement on remote (tools are hardcoded, not dynamic)

## MCP Spec Requirements

- Protocol version: 2025-06-18
- Transport: Streamable HTTP (not SSE)
- Session management: Mcp-Session-Id headers
- HEAD method support for protocol discovery

## References

- [Claude Help: Custom Connectors](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [The Missing MCP Playbook](https://medium.com/@george.vetticaden/the-missing-mcp-playbook-deploying-custom-agents-on-claude-ai-and-claude-mobile-05274f60a970)
- [FastMCP HTTP Deployment](https://gofastmcp.com/deployment/http)
- [Fly.io Remote MCP Servers](https://fly.io/docs/blueprints/remote-mcp-servers/)
- [FederalRunner Reference Implementation](https://github.com/georgevetticaden/multi-agent-federal-form-automation-system)
