# jit-proxy Daemonization (Phase 4)

**Date**: 2026-03-05
**Status**: Approved
**Context**: Phase 1-3 daemonized the OMEGA MCP server (port 8377). Phase 4 applies the same pattern to jit-proxy, eliminating 6+ duplicate processes (~450 MB).

## Problem

Each Claude Code terminal spawns its own jit-proxy process via stdio. With 7 terminals open, that's 7 identical proxy processes (~65 MB each), each capable of spawning up to 3 backends (playwright, email, x-twitter). Total waste: ~450 MB of redundant proxy processes.

## Solution

Run a single jit-proxy daemon on port 8378 via launchd. All Claude Code sessions connect over HTTP.

## Architecture

Same pattern as the OMEGA MCP daemon (Phase 1-3):

1. **Transport toggle in jit_proxy.py** — `JIT_PROXY_TRANSPORT=http` env var switches from `stdio_server()` to `StreamableHTTPSessionManager` + uvicorn on port 8378
2. **Health endpoint** — `GET /health` returns pid, rss, uptime, backend status, tool count
3. **Graceful shutdown** — SIGTERM handler for launchd unload, disconnects all backends
4. **launchd plist** — `com.omega.jit-proxy-daemon.plist`, KeepAlive, RunAtLoad
5. **CLI commands** — extend `omega serve` with jit-proxy target
6. **Config migration** — update top-level `mcpServers.jit-proxy` in `~/.claude.json` from stdio to `{"type": "http", "url": "http://127.0.0.1:8378/mcp"}`

## Files

| File | Change |
|------|--------|
| `src/omega/server/jit_proxy.py` | Add `_run_http_transport()`, env var toggle, health endpoint, signal handlers |
| `src/omega/cli.py` | Add jit-proxy install/uninstall/status/migrate-config commands under `omega serve` |
| `src/omega/data/com.omega.jit-proxy-daemon.plist` | New launchd plist template |

## Key differences from OMEGA daemon

- Port 8378 (not 8377)
- Global MCP server (top-level `mcpServers` in `~/.claude.json`) vs per-project
- No hook server integration
- No Pro license check or plugin discovery
- Simpler health endpoint (includes backend connection status)

## Rollback

`omega serve restore-config` restores `~/.claude.json.bak`.
