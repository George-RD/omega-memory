# jit-proxy Daemon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Daemonize jit-proxy so all Claude Code sessions share a single process on port 8378, eliminating ~450 MB of redundant memory.

**Architecture:** Add HTTP transport to `jit_proxy.py` using the same `StreamableHTTPSessionManager` + uvicorn + starlette pattern as `mcp_server.py`. Manage the daemon via launchd plist. Extend `omega serve` CLI with `--target jit-proxy` subcommands.

**Tech Stack:** Python 3.11, MCP SDK (StreamableHTTPSessionManager), uvicorn, starlette, launchd

---

### Task 1: Add HTTP transport to jit_proxy.py

**Files:**
- Modify: `src/omega/server/jit_proxy.py`

**Step 1: Add transport configuration constants**

At the top of `jit_proxy.py`, after the existing imports and before `_configure_logging`, add:

```python
# --- Transport configuration ---
_TRANSPORT = os.environ.get("JIT_PROXY_TRANSPORT", "stdio").lower()
_HTTP_HOST = os.environ.get("JIT_PROXY_HTTP_HOST", "127.0.0.1")
_HTTP_PORT = int(os.environ.get("JIT_PROXY_HTTP_PORT", "8378"))
_start_time = time.monotonic()
```

Add `signal` and `socket` to the existing imports at the top of the file.

**Step 2: Add `_check_port_available` helper**

After `_configure_logging`, add:

```python
def _check_port_available(host: str, port: int) -> bool:
    """Check if a TCP port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def _get_current_rss_bytes() -> int:
    """Get current process RSS in bytes (macOS/Linux)."""
    try:
        import resource
        # resource.getrusage returns ru_maxrss in bytes on macOS, KB on Linux
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return rss  # Already bytes on macOS
        return rss * 1024  # KB to bytes on Linux
    except Exception:
        return 0
```

**Step 3: Add `_run_http_transport` method**

After the `JitProxy.run` method (which becomes the stdio path), add a new async function:

```python
async def _run_http_transport(proxy: JitProxy) -> None:
    """Run jit-proxy as a Streamable HTTP daemon via uvicorn."""
    try:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    except ImportError as e:
        print(
            f"Error: HTTP transport requires additional packages: {e}\n"
            "Install with: pip install mcp starlette uvicorn",
            file=sys.stderr,
        )
        sys.exit(1)

    if not _check_port_available(_HTTP_HOST, _HTTP_PORT):
        print(
            f"Error: Port {_HTTP_PORT} already in use on {_HTTP_HOST}.\n"
            f"Another jit-proxy daemon may be running. Check: curl http://{_HTTP_HOST}:{_HTTP_PORT}/health",
            file=sys.stderr,
        )
        sys.exit(1)

    session_manager = StreamableHTTPSessionManager(
        app=proxy.server,
        json_response=False,
        stateless=False,
    )

    async def health(request):
        rss = _get_current_rss_bytes()
        backend_status = {}
        for name, backend in proxy.backends.items():
            backend_status[name] = {
                "connected": backend.connected,
                "last_activity_ago_s": round(time.monotonic() - backend.last_activity, 1) if backend.last_activity > 0 else None,
            }
        return JSONResponse({
            "status": "ok",
            "pid": os.getpid(),
            "rss_mb": round(rss / 1024**2, 1),
            "uptime_s": round(time.monotonic() - _start_time, 1),
            "tool_count": len(proxy.tool_to_backend),
            "backend_count": len(proxy.backends),
            "backends": backend_status,
            "transport": "http",
        })

    import contextlib

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            logger.info(
                "jit-proxy daemon listening on http://%s:%d/mcp",
                _HTTP_HOST, _HTTP_PORT,
            )
            yield
        # Disconnect all backends on shutdown
        for backend in proxy.backends.values():
            try:
                await backend.disconnect()
            except Exception:
                pass

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/mcp", app=session_manager.handle_request),
        ],
        lifespan=lifespan,
    )

    config = uvicorn.Config(
        app,
        host=_HTTP_HOST,
        port=_HTTP_PORT,
        log_level="warning",
        timeout_graceful_shutdown=5,
    )
    uv_server = uvicorn.Server(config)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(uv_server.shutdown()))

    await uv_server.serve()
```

**Step 4: Update `_main` to branch on transport**

Replace the existing `_main` function:

```python
async def _main():
    _configure_logging()

    if "--cache-manifest" in sys.argv:
        await cache_manifest()
        return

    config = load_config()
    manifest = load_manifest()
    proxy = JitProxy(config, manifest)

    if _TRANSPORT == "http":
        # Start idle watchdog as background task
        watchdog = asyncio.create_task(proxy._idle_watchdog())
        try:
            await _run_http_transport(proxy)
        finally:
            watchdog.cancel()
    else:
        await proxy.run()
```

Note: The idle watchdog needs to run alongside the HTTP transport. Currently `proxy.run()` starts the watchdog internally for stdio mode. For HTTP mode, we start it externally since `_run_http_transport` replaces `proxy.run()`.

**Step 5: Verify the proxy still works in stdio mode**

Run: `echo '{}' | python3.11 -c "import sys; print('stdio check')"` — just a sanity check. The real test is restarting a Claude Code session.

**Step 6: Commit**

```bash
git add src/omega/server/jit_proxy.py
git commit -m "feat(jit-proxy): add HTTP transport with StreamableHTTPSessionManager

Supports JIT_PROXY_TRANSPORT=http env var to run as daemon on port 8378.
Includes /health endpoint with backend connection status."
```

---

### Task 2: Create launchd plist template

**Files:**
- Create: `src/omega/data/com.omega.jit-proxy-daemon.plist`

**Step 1: Create the plist template**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.omega.jit-proxy-daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>__PYTHON_PATH__</string>
        <string>-m</string>
        <string>omega.server.jit_proxy</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OMEGA_HOME</key>
        <string>__OMEGA_HOME__</string>
        <key>JIT_PROXY_TRANSPORT</key>
        <string>http</string>
        <key>PYTHONPATH</key>
        <string>__PYTHONPATH__</string>
        <key>PATH</key>
        <string>__PATH__</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>__OMEGA_HOME__/logs/jit-proxy-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>__OMEGA_HOME__/logs/jit-proxy-daemon.log</string>
</dict>
</plist>
```

Note: The `PATH` env var is critical — jit-proxy backends use `npx` (playwright), `uvx` (email), and `x-twitter-mcp-server` which all need to be on PATH. launchd has a minimal PATH by default. The template includes `__PATH__` which gets replaced with the current user's PATH at install time.

**Step 2: Commit**

```bash
git add src/omega/data/com.omega.jit-proxy-daemon.plist
git commit -m "feat(jit-proxy): add launchd plist template for daemon mode"
```

---

### Task 3: Extend `omega serve` CLI for jit-proxy

**Files:**
- Modify: `src/omega/cli.py`

**Step 1: Add jit-proxy constants**

After the existing `_PLIST_LABEL` / `_PLIST_DEST` / `_DEFAULT_HTTP_PORT` / `_DEFAULT_HTTP_HOST` constants (around line 1561), add:

```python
_JP_PLIST_LABEL = "com.omega.jit-proxy-daemon"
_JP_PLIST_DEST = Path.home() / "Library" / "LaunchAgents" / f"{_JP_PLIST_LABEL}.plist"
_JP_HTTP_PORT = 8378
_JP_HTTP_HOST = "127.0.0.1"
```

**Step 2: Add `_jp_install` function**

After `_serve_restore_config` (around line 1741), add:

```python
def _jp_install(args):
    """Install jit-proxy launchd daemon."""
    plist_template = (DATA_DIR / "com.omega.jit-proxy-daemon.plist").read_text()

    python_path = _resolve_python_path()
    omega_home = str(OMEGA_DIR)

    try:
        import omega
        pythonpath = str(Path(omega.__file__).parent.parent)
    except Exception:
        pythonpath = ""

    # Capture current PATH so backends (npx, uvx, x-twitter-mcp-server) are findable
    current_path = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")

    log_dir = OMEGA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    plist_content = (
        plist_template
        .replace("__PYTHON_PATH__", python_path)
        .replace("__OMEGA_HOME__", omega_home)
        .replace("__PYTHONPATH__", pythonpath)
        .replace("__PATH__", current_path)
    )

    _JP_PLIST_DEST.parent.mkdir(parents=True, exist_ok=True)
    _JP_PLIST_DEST.write_text(plist_content)
    print(f"Plist written to {_JP_PLIST_DEST}")

    result = subprocess.run(
        ["launchctl", "load", str(_JP_PLIST_DEST)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("jit-proxy daemon loaded. It will start automatically on login.")
        print(f"\nVerify: curl http://{_JP_HTTP_HOST}:{_JP_HTTP_PORT}/health")
        print("\nTo use with Claude Code, run: omega proxy migrate-config")
    else:
        print(f"launchctl load failed: {result.stderr.strip()}")
        sys.exit(1)
```

**Step 3: Add `_jp_uninstall` function**

```python
def _jp_uninstall(args):
    """Unload and remove jit-proxy daemon."""
    if _JP_PLIST_DEST.exists():
        subprocess.run(
            ["launchctl", "unload", str(_JP_PLIST_DEST)],
            capture_output=True, text=True,
        )
        _JP_PLIST_DEST.unlink()
        print("jit-proxy daemon unloaded and plist removed.")
        print("\nTo restore stdio config, run: omega proxy restore-config")
    else:
        print("No jit-proxy daemon plist found. Nothing to uninstall.")
```

**Step 4: Add `_jp_status` function**

```python
def _jp_status(args):
    """Check jit-proxy daemon status."""
    import urllib.request
    import urllib.error

    result = subprocess.run(
        ["launchctl", "list", _JP_PLIST_LABEL],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("Daemon: not loaded")
    else:
        print("Daemon: loaded")
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                print(f"  {line.strip()}")

    url = f"http://{_JP_HTTP_HOST}:{_JP_HTTP_PORT}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            print(f"\nHealth: OK")
            print(f"  PID: {data.get('pid')}")
            print(f"  RSS: {data.get('rss_mb')} MB")
            print(f"  Uptime: {data.get('uptime_s')}s")
            print(f"  Tools: {data.get('tool_count')}")
            backends = data.get("backends", {})
            for name, status in backends.items():
                connected = "connected" if status.get("connected") else "idle"
                print(f"  Backend {name}: {connected}")
    except Exception:
        print(f"\nHealth: unreachable ({url})")
```

**Step 5: Add `_jp_migrate_config` function**

This is the key difference from the OMEGA daemon — jit-proxy is a **global** MCP server (top-level `mcpServers` in `~/.claude.json`), not per-project.

```python
def _jp_migrate_config(args):
    """Migrate ~/.claude.json jit-proxy entry from stdio to http."""
    claude_json = Path.home() / ".claude.json"
    if not claude_json.exists():
        print("No ~/.claude.json found.")
        return

    content = claude_json.read_text()
    config = json.loads(content)

    # Backup
    backup = claude_json.with_suffix(".json.bak")
    backup.write_text(content)
    print(f"Backup saved to {backup}")

    url = f"http://{_JP_HTTP_HOST}:{_JP_HTTP_PORT}/mcp"
    changed = 0

    # Global mcpServers (top-level)
    servers = config.get("mcpServers", {})
    if "jit-proxy" in servers:
        entry = servers["jit-proxy"]
        if entry.get("type") == "stdio":
            servers["jit-proxy"] = {
                "type": "http",
                "url": url,
            }
            changed += 1

    # Also check per-project entries (in case user moved it)
    projects = config.get("projects", {})
    for proj_path, proj_config in projects.items():
        proj_servers = proj_config.get("mcpServers", {})
        if "jit-proxy" in proj_servers:
            entry = proj_servers["jit-proxy"]
            if entry.get("type") == "stdio":
                proj_servers["jit-proxy"] = {
                    "type": "http",
                    "url": url,
                }
                changed += 1

    if changed > 0:
        claude_json.write_text(json.dumps(config, indent=2) + "\n")
        print(f"Migrated {changed} jit-proxy entry/entries from stdio to http.")
        print(f"MCP endpoint: {url}")
        print("\nRestart Claude Code terminals to use the daemon.")
    else:
        print("No stdio jit-proxy entries found to migrate.")
```

**Step 6: Add `_jp_restore_config` function**

```python
def _jp_restore_config(args):
    """Restore ~/.claude.json from backup."""
    claude_json = Path.home() / ".claude.json"
    backup = claude_json.with_suffix(".json.bak")

    if not backup.exists():
        print("No backup found at ~/.claude.json.bak")
        return

    backup_content = backup.read_text()
    claude_json.write_text(backup_content)
    print("Restored ~/.claude.json from backup.")
    print("Restart Claude Code terminals to apply.")
```

**Step 7: Add `cmd_proxy` command handler**

```python
def cmd_proxy(args):
    """Manage jit-proxy daemon."""
    subcmd = getattr(args, "proxy_command", None)

    if subcmd == "install":
        _jp_install(args)
    elif subcmd == "uninstall":
        _jp_uninstall(args)
    elif subcmd == "status":
        _jp_status(args)
    elif subcmd == "migrate-config":
        _jp_migrate_config(args)
    elif subcmd == "restore-config":
        _jp_restore_config(args)
    else:
        print("Usage: omega proxy {install|uninstall|status|migrate-config|restore-config}")
```

**Step 8: Add argparse registration**

In the argparse setup section (after the `serve_sub` block, around line 2516), add:

```python
proxy_parser = subparsers.add_parser("proxy", help="Manage jit-proxy daemon")
proxy_sub = proxy_parser.add_subparsers(dest="proxy_command", help="Proxy daemon management")
proxy_sub.add_parser("install", help="Install jit-proxy launchd daemon")
proxy_sub.add_parser("uninstall", help="Unload and remove jit-proxy daemon")
proxy_sub.add_parser("status", help="Check jit-proxy daemon status and health")
proxy_sub.add_parser("migrate-config", help="Migrate ~/.claude.json jit-proxy from stdio to http")
proxy_sub.add_parser("restore-config", help="Restore ~/.claude.json from backup")
```

And in the command dispatch dict (find where `"serve": cmd_serve` is registered), add:

```python
"proxy": cmd_proxy,
```

**Step 9: Commit**

```bash
git add src/omega/cli.py
git commit -m "feat(cli): add 'omega proxy' subcommand for jit-proxy daemon management

Supports: install, uninstall, status, migrate-config, restore-config.
Same pattern as 'omega serve' but for the jit-proxy daemon on port 8378."
```

---

### Task 4: Deploy and verify

**Step 1: Install the daemon**

Run: `python3.11 -m omega proxy install`

Expected output:
```
Plist written to ~/Library/LaunchAgents/com.omega.jit-proxy-daemon.plist
jit-proxy daemon loaded. It will start automatically on login.

Verify: curl http://127.0.0.1:8378/health
```

**Step 2: Verify health endpoint**

Run: `curl -s http://127.0.0.1:8378/health | python3.11 -m json.tool`

Expected: JSON with `status: "ok"`, pid, tool_count, backends with `connected: false` (none spawned yet).

**Step 3: Migrate config**

Run: `python3.11 -m omega proxy migrate-config`

Expected:
```
Backup saved to ~/.claude.json.bak
Migrated 1 jit-proxy entry/entries from stdio to http.
MCP endpoint: http://127.0.0.1:8378/mcp
```

**Step 4: Verify in a new Claude Code session**

Open a new terminal, start Claude Code, use a jit-proxy tool (e.g. search twitter). Confirm it works.

**Step 5: Verify only 1 jit-proxy process exists**

Run: `ps aux | grep jit_proxy | grep -v grep`

Expected: exactly 1 process (the daemon). No more per-terminal spawns.

**Step 6: Kill old jit-proxy processes**

Close stale terminals, or if needed:
Run: `pkill -f "omega.server.jit_proxy"` then verify the daemon restarts (launchd KeepAlive).

**Step 7: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix(jit-proxy): deployment fixups for daemon mode"
```
