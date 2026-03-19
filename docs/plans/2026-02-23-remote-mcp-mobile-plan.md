# Remote MCP Server for Claude Mobile -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy OMEGA as a remote HTTP MCP server accessible from Claude Mobile via Custom Connectors, exposing 5 curated tools (store, query, memory, remind, profile).

**Architecture:** New `remote_server.py` using FastMCP v3 with Streamable HTTP transport wraps existing OMEGA handlers. Auth0 provides OAuth 2.1 with DCR for Claude Mobile. SQLite stays on persistent volume. Existing local stdio server (`mcp_server.py`) is untouched.

**Tech Stack:** FastMCP v3, Auth0 (OAuth 2.1), PyJWT, Uvicorn, Docker

**Design Doc:** `docs/plans/2026-02-23-remote-mcp-mobile-design.md`

---

## Task 1: Add `remote` optional dependency to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add the `remote` extra**

In `pyproject.toml`, add a new optional dependency group after the existing `bridge` extra (line 42):

```toml
remote = ["fastmcp>=3.0.0", "pyjwt[crypto]>=2.8.0", "httpx>=0.27.0"]
```

Also add it to the `full` extra so `pip install omega-memory[full]` includes remote:

```toml
full = [
    "omega-memory[server]",
    "omega-memory[router]",
    "omega-memory[encrypt]",
    "omega-memory[bridge]",
    "omega-memory[remote]",
    "omega-memory[knowledge]",
    "omega-memory[entity]",
    "omega-memory[cloud]",
]
```

**Step 2: Install the new dependencies locally**

Run: `cd ~/Projects/omega && python3.11 -m pip install -e ".[remote,server,dev]"`
Expected: FastMCP 3.x, PyJWT, httpx installed successfully

**Step 3: Verify FastMCP is importable**

Run: `python3.11 -c "import fastmcp; print(fastmcp.__version__)"`
Expected: `3.x.x`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add remote optional dependency (fastmcp, pyjwt, httpx)"
```

---

## Task 2: Create `remote_server.py` with 5 tool wrappers (no auth yet)

**Files:**
- Create: `src/omega/server/remote_server.py`
- Test: `tests/test_remote_server.py`

**Step 1: Write the failing test**

Create `tests/test_remote_server.py`:

```python
"""Tests for the remote MCP server (FastMCP HTTP transport)."""

import pytest


@pytest.fixture
def _set_omega_home(tmp_path, monkeypatch):
    """Isolate OMEGA_HOME for each test."""
    monkeypatch.setenv("OMEGA_HOME", str(tmp_path / ".omega"))


@pytest.mark.usefixtures("_set_omega_home")
class TestRemoteServerTools:
    """Test that remote_server tool wrappers correctly delegate to handlers."""

    async def test_omega_store_delegates_to_handler(self):
        """omega_store wrapper should call the handler and return text."""
        from omega.server.remote_server import mcp

        # FastMCP provides a test client
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool(
                "omega_store", {"content": "test memory from mobile"}
            )
            assert result is not None
            # Handler returns text containing the stored content confirmation
            text = result[0].text if hasattr(result[0], "text") else str(result[0])
            assert "test memory from mobile" in text.lower() or "stored" in text.lower() or "node" in text.lower()

    async def test_omega_query_delegates_to_handler(self):
        """omega_query wrapper should search memories."""
        from omega.server.remote_server import mcp
        from fastmcp import Client

        # Store something first
        async with Client(mcp) as client:
            await client.call_tool(
                "omega_store", {"content": "the quick brown fox jumps"}
            )
            result = await client.call_tool(
                "omega_query", {"query": "quick brown fox", "mode": "semantic"}
            )
            assert result is not None

    async def test_omega_profile_read(self):
        """omega_profile read should return profile or empty message."""
        from omega.server.remote_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool(
                "omega_profile", {"action": "read"}
            )
            text = result[0].text if hasattr(result[0], "text") else str(result[0])
            # Either returns profile JSON or "No profile found" message
            assert len(text) > 0

    async def test_omega_remind_set(self):
        """omega_remind set should create a reminder."""
        from omega.server.remote_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool(
                "omega_remind",
                {"action": "set", "text": "test reminder", "duration": "1h"},
            )
            text = result[0].text if hasattr(result[0], "text") else str(result[0])
            assert "reminder" in text.lower()

    async def test_omega_memory_flagged(self):
        """omega_memory flagged action should work."""
        from omega.server.remote_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool(
                "omega_memory", {"action": "flagged"}
            )
            assert result is not None

    async def test_only_5_tools_exposed(self):
        """Remote server should expose exactly 5 tools."""
        from omega.server.remote_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == {
                "omega_store",
                "omega_query",
                "omega_memory",
                "omega_remind",
                "omega_profile",
            }

    async def test_tool_descriptions_present(self):
        """Each tool should have a description."""
        from omega.server.remote_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.description, f"{tool.name} missing description"
```

**Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_remote_server.py -x -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'omega.server.remote_server'`

**Step 3: Write the remote server implementation**

Create `src/omega/server/remote_server.py`:

```python
"""
OMEGA Remote MCP Server -- FastMCP HTTP transport for Claude Mobile.

Exposes 5 curated tools (store, query, memory, remind, profile) over
Streamable HTTP. Wraps existing OMEGA handlers; shares the same
SQLite storage layer as the local stdio server.

Usage:
    # Development
    python -m omega.server.remote_server

    # Production (ASGI)
    uvicorn omega.server.remote_server:app --host 0.0.0.0 --port 8000
"""

import logging
import os
from typing import Optional

from fastmcp import FastMCP

logger = logging.getLogger("omega.server.remote")

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "OMEGA Mobile",
    instructions=(
        "OMEGA is a persistent memory system. "
        "Use omega_store to save thoughts, omega_query to search memories, "
        "omega_memory to manage individual memories, omega_remind for reminders, "
        "and omega_profile to read/update your profile."
    ),
)


# ---------------------------------------------------------------------------
# Helper: extract text from handler response dict
# ---------------------------------------------------------------------------

def _extract_text(result: dict) -> str:
    """Extract text string from OMEGA handler response dict.

    Handlers return {"content": [{"type": "text", "text": "..."}]}.
    On error: {"content": [...], "isError": True}.
    """
    if result.get("isError"):
        content = result.get("content", [{}])
        msg = content[0].get("text", "Unknown error") if content else "Unknown error"
        raise ValueError(msg)
    content = result.get("content", [{}])
    return content[0].get("text", str(result)) if content else str(result)


# ---------------------------------------------------------------------------
# Tool wrappers -- thin delegation to existing handlers
# ---------------------------------------------------------------------------

@mcp.tool
async def omega_store(
    content: str,
    event_type: str = "general",
    metadata: Optional[dict] = None,
    project: Optional[str] = None,
    priority: Optional[int] = None,
    entity_id: Optional[str] = None,
) -> str:
    """Store a memory. Use for saving thoughts, decisions, lessons, or any information to remember later."""
    from omega.server.handlers import HANDLERS

    args = {"content": content, "event_type": event_type}
    if metadata is not None:
        args["metadata"] = metadata
    if project is not None:
        args["project"] = project
    if priority is not None:
        args["priority"] = priority
    if entity_id is not None:
        args["entity_id"] = entity_id
    result = await HANDLERS["omega_store"](args)
    return _extract_text(result)


@mcp.tool
async def omega_query(
    query: str = "",
    mode: str = "semantic",
    limit: int = 10,
    event_type: Optional[str] = None,
    project: Optional[str] = None,
    entity_id: Optional[str] = None,
    days: int = 7,
) -> str:
    """Search memories. Modes: semantic (default), phrase, timeline, browse."""
    from omega.server.handlers import HANDLERS

    args = {"query": query, "mode": mode, "limit": limit, "days": days}
    if event_type is not None:
        args["event_type"] = event_type
    if project is not None:
        args["project"] = project
    if entity_id is not None:
        args["entity_id"] = entity_id
    result = await HANDLERS["omega_query"](args)
    return _extract_text(result)


@mcp.tool
async def omega_memory(
    action: str,
    memory_id: Optional[str] = None,
    new_content: Optional[str] = None,
    rating: Optional[str] = None,
    reason: Optional[str] = None,
    target_id: Optional[str] = None,
    edge_type: str = "related",
    limit: int = 5,
) -> str:
    """Manage a memory. Actions: edit, delete, feedback, similar, traverse, link, flagged, check_contradictions, supersede."""
    from omega.server.handlers import HANDLERS

    args = {"action": action, "limit": limit, "edge_type": edge_type}
    if memory_id is not None:
        args["memory_id"] = memory_id
    if new_content is not None:
        args["new_content"] = new_content
    if rating is not None:
        args["rating"] = rating
    if reason is not None:
        args["reason"] = reason
    if target_id is not None:
        args["target_id"] = target_id
    result = await HANDLERS["omega_memory"](args)
    return _extract_text(result)


@mcp.tool
async def omega_remind(
    action: str = "set",
    text: Optional[str] = None,
    duration: Optional[str] = None,
    context: Optional[str] = None,
    reminder_id: Optional[str] = None,
    status: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> str:
    """Manage reminders. Actions: set (default), list, dismiss."""
    from omega.server.handlers import HANDLERS

    args = {"action": action}
    if text is not None:
        args["text"] = text
    if duration is not None:
        args["duration"] = duration
    if context is not None:
        args["context"] = context
    if reminder_id is not None:
        args["reminder_id"] = reminder_id
    if status is not None:
        args["status"] = status
    if entity_id is not None:
        args["entity_id"] = entity_id
    result = await HANDLERS["omega_remind"](args)
    return _extract_text(result)


@mcp.tool
async def omega_profile(
    action: str = "read",
    update: Optional[dict] = None,
) -> str:
    """Read or update your persistent profile. Actions: read (default), update, list_preferences."""
    from omega.server.handlers import HANDLERS

    args = {"action": action}
    if update is not None:
        args["update"] = update
    result = await HANDLERS["omega_profile"](args)
    return _extract_text(result)


# ---------------------------------------------------------------------------
# ASGI app for production deployment (uvicorn omega.server.remote_server:app)
# ---------------------------------------------------------------------------

app = mcp.http_app(path="/mcp")


# ---------------------------------------------------------------------------
# CLI entry point for development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport="http", host="0.0.0.0", port=port)
```

**Step 4: Run the tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_remote_server.py -x -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add src/omega/server/remote_server.py tests/test_remote_server.py
git commit -m "feat: add remote MCP server with 5 mobile tools (FastMCP HTTP)"
```

---

## Task 3: Create `auth.py` for Auth0 OAuth 2.1

**Files:**
- Create: `src/omega/server/auth.py`
- Modify: `src/omega/server/remote_server.py`
- Test: `tests/test_remote_auth.py`

**Context:** Claude Mobile requires OAuth 2.1 with Dynamic Client Registration (DCR). Auth0 handles DCR; the server needs to:
1. Serve `/.well-known/oauth-protected-resource` pointing to Auth0
2. Validate JWT tokens on `tools/list` and `tools/call`
3. Allow `initialize` without authentication

**Step 1: Write the failing test**

Create `tests/test_remote_auth.py`:

```python
"""Tests for remote server Auth0 OAuth integration."""

import pytest
from unittest.mock import patch, AsyncMock


class TestAuthConfig:
    """Test auth configuration and well-known endpoint."""

    def test_auth_config_from_env(self, monkeypatch):
        """Auth config should read from environment variables."""
        monkeypatch.setenv("AUTH0_DOMAIN", "test.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://omega.example.com")

        from omega.server.auth import get_auth_config

        config = get_auth_config()
        assert config["domain"] == "test.auth0.com"
        assert config["audience"] == "https://omega.example.com"
        assert config["issuer"] == "https://test.auth0.com/"
        assert config["jwks_uri"] == "https://test.auth0.com/.well-known/jwks.json"

    def test_auth_config_missing_domain_raises(self, monkeypatch):
        """Should raise if AUTH0_DOMAIN is not set."""
        monkeypatch.delenv("AUTH0_DOMAIN", raising=False)
        monkeypatch.delenv("AUTH0_AUDIENCE", raising=False)

        from omega.server.auth import get_auth_config

        with pytest.raises(ValueError, match="AUTH0_DOMAIN"):
            get_auth_config()

    def test_well_known_response_format(self, monkeypatch):
        """Well-known endpoint should return correct RFC 9470 format."""
        monkeypatch.setenv("AUTH0_DOMAIN", "test.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://omega.example.com")

        from omega.server.auth import build_well_known_response

        response = build_well_known_response()
        assert response["resource"] == "https://omega.example.com"
        assert "https://test.auth0.com/" in response["authorization_servers"]


class TestJWTValidation:
    """Test JWT token validation."""

    def test_missing_token_raises(self):
        """Should raise on missing Authorization header."""
        from omega.server.auth import validate_token

        with pytest.raises(ValueError, match="[Mm]issing"):
            validate_token(None)

    def test_malformed_token_raises(self):
        """Should raise on malformed Bearer token."""
        from omega.server.auth import validate_token

        with pytest.raises(ValueError, match="[Ii]nvalid"):
            validate_token("NotBearer xyz")

    def test_bearer_prefix_extracted(self):
        """Should extract token after 'Bearer ' prefix."""
        from omega.server.auth import extract_bearer_token

        assert extract_bearer_token("Bearer abc123") == "abc123"
        assert extract_bearer_token("bearer abc123") == "abc123"
```

**Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_remote_auth.py -x -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'omega.server.auth'`

**Step 3: Write the auth module**

Create `src/omega/server/auth.py`:

```python
"""
Auth0 OAuth 2.1 integration for OMEGA Remote MCP Server.

Provides:
- Auth config from environment variables (AUTH0_DOMAIN, AUTH0_AUDIENCE)
- JWT validation using Auth0 JWKS
- RFC 9470 well-known endpoint response builder
- Bearer token extraction
"""

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("omega.server.auth")


def get_auth_config() -> dict:
    """Read Auth0 configuration from environment variables.

    Required env vars:
        AUTH0_DOMAIN: Auth0 tenant domain (e.g., 'myapp.auth0.com')
        AUTH0_AUDIENCE: API identifier / audience (e.g., 'https://omega.example.com')

    Returns dict with: domain, audience, issuer, jwks_uri, algorithms
    """
    domain = os.environ.get("AUTH0_DOMAIN", "").strip()
    audience = os.environ.get("AUTH0_AUDIENCE", "").strip()

    if not domain:
        raise ValueError("AUTH0_DOMAIN environment variable is required")
    if not audience:
        raise ValueError("AUTH0_AUDIENCE environment variable is required")

    return {
        "domain": domain,
        "audience": audience,
        "issuer": f"https://{domain}/",
        "jwks_uri": f"https://{domain}/.well-known/jwks.json",
        "algorithms": ["RS256"],
    }


def build_well_known_response() -> dict:
    """Build RFC 9470 OAuth Protected Resource Metadata response.

    Claude Mobile queries this endpoint to discover the auth server.
    """
    config = get_auth_config()
    return {
        "resource": config["audience"],
        "authorization_servers": [config["issuer"]],
    }


def extract_bearer_token(authorization: str) -> str:
    """Extract token from 'Bearer <token>' header value."""
    if not authorization:
        raise ValueError("Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ValueError("Invalid Authorization header format. Expected: Bearer <token>")
    return parts[1].strip()


def validate_token(authorization: Optional[str]) -> dict:
    """Validate a JWT Bearer token against Auth0 JWKS.

    Args:
        authorization: Full Authorization header value ('Bearer <token>')

    Returns:
        Decoded JWT payload dict on success.

    Raises:
        ValueError: On missing, malformed, or invalid token.
    """
    if not authorization:
        raise ValueError("Missing Authorization header")

    token = extract_bearer_token(authorization)
    config = get_auth_config()

    try:
        import jwt
        from jwt import PyJWKClient

        jwks_client = _get_jwks_client(config["jwks_uri"])
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=config["algorithms"],
            audience=config["audience"],
            issuer=config["issuer"],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")


@lru_cache(maxsize=1)
def _get_jwks_client(jwks_uri: str):
    """Cache the JWKS client (key rotation is handled internally by PyJWKClient)."""
    from jwt import PyJWKClient

    return PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)
```

**Step 4: Run the tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_remote_auth.py -x -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/omega/server/auth.py tests/test_remote_auth.py
git commit -m "feat: add Auth0 OAuth 2.1 module for remote server"
```

---

## Task 4: Wire auth into remote_server.py

**Files:**
- Modify: `src/omega/server/remote_server.py`
- Test: `tests/test_remote_auth.py` (add integration tests)

**Step 1: Write the failing test**

Add to `tests/test_remote_auth.py`:

```python
class TestWellKnownEndpoint:
    """Test the well-known endpoint on the remote server ASGI app."""

    async def test_well_known_returns_json(self, monkeypatch):
        """GET /.well-known/oauth-protected-resource should return RFC 9470 JSON."""
        monkeypatch.setenv("AUTH0_DOMAIN", "test.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://omega.example.com")

        from starlette.testclient import TestClient
        from omega.server.remote_server import create_app

        test_app = create_app()
        client = TestClient(test_app)
        resp = client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resource"] == "https://omega.example.com"
        assert "https://test.auth0.com/" in body["authorization_servers"]

    async def test_health_endpoint(self, monkeypatch):
        """GET /health should return 200."""
        monkeypatch.setenv("AUTH0_DOMAIN", "test.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://omega.example.com")

        from starlette.testclient import TestClient
        from omega.server.remote_server import create_app

        test_app = create_app()
        client = TestClient(test_app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
```

**Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_remote_auth.py::TestWellKnownEndpoint -x -v`
Expected: FAIL (`create_app` not found)

**Step 3: Refactor remote_server.py to add auth endpoints**

Update `src/omega/server/remote_server.py`. Replace the bottom section (ASGI app + CLI) with:

```python
# ---------------------------------------------------------------------------
# ASGI app factory with auth endpoints
# ---------------------------------------------------------------------------

def create_app():
    """Create the full ASGI app with MCP + auth + health endpoints.

    Mounts:
        /mcp -- FastMCP Streamable HTTP endpoint
        /.well-known/oauth-protected-resource -- RFC 9470 discovery
        /health -- Health check
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def well_known(request):
        """RFC 9470 OAuth Protected Resource Metadata."""
        try:
            from omega.server.auth import build_well_known_response
            return JSONResponse(build_well_known_response())
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    async def health(request):
        """Health check endpoint."""
        return JSONResponse({"status": "ok"})

    mcp_app = mcp.http_app(path="/mcp")

    routes = [
        Route("/.well-known/oauth-protected-resource", well_known, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
    ]

    outer_app = Starlette(routes=routes)
    outer_app.mount("/", mcp_app)
    return outer_app


app = create_app()


# ---------------------------------------------------------------------------
# CLI entry point for development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("omega.server.remote_server:app", host="0.0.0.0", port=port, reload=True)
```

Remove the old `app = mcp.http_app(path="/mcp")` line and the old `if __name__` block.

**Step 4: Run the tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_remote_auth.py -x -v`
Expected: All tests PASS

**Step 5: Also run the tool tests to make sure nothing broke**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_remote_server.py -x -v`
Expected: All 7 tests still PASS

**Step 6: Commit**

```bash
git add src/omega/server/remote_server.py tests/test_remote_auth.py
git commit -m "feat: wire Auth0 well-known + health endpoints into remote server"
```

---

## Task 5: Create Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Test: manual `docker build` + `docker run`

**Step 1: Create .dockerignore**

Create `.dockerignore`:

```
.git
.venv
__pycache__
*.pyc
.pytest_cache
.ruff_cache
website/
node_modules/
docs/
tests/
*.egg-info
.env
```

**Step 2: Create Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for sqlite-vec and ONNX
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install with remote + server extras
RUN pip install --no-cache-dir -e ".[remote,server]"

# Create data directory for persistent volume mount
RUN mkdir -p /data/omega

# OMEGA_HOME points to persistent volume
ENV OMEGA_HOME=/data/omega
ENV PORT=8000

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run with uvicorn
CMD ["uvicorn", "omega.server.remote_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 3: Build the Docker image**

Run: `cd ~/Projects/omega && docker build -t omega-remote:test .`
Expected: Build succeeds

**Step 4: Test the container**

Run: `docker run --rm -p 8000:8000 -e AUTH0_DOMAIN=placeholder.auth0.com -e AUTH0_AUDIENCE=https://placeholder omega-remote:test`

In another terminal:
Run: `curl http://localhost:8000/health`
Expected: `{"status":"ok"}`

Run: `curl http://localhost:8000/.well-known/oauth-protected-resource`
Expected: `{"resource":"https://placeholder","authorization_servers":["https://placeholder.auth0.com/"]}`

Stop the container (Ctrl+C).

**Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile for remote MCP server deployment"
```

---

## Task 6: Create database sync script

**Files:**
- Create: `scripts/sync-db.sh`

**Step 1: Create the sync script**

Create `scripts/sync-db.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# OMEGA Database Sync -- push/pull omega.db to/from remote host
#
# Usage:
#   ./scripts/sync-db.sh push          # local -> remote
#   ./scripts/sync-db.sh pull          # remote -> local backup
#
# Configuration (environment variables):
#   OMEGA_REMOTE_HOST  -- SSH host (e.g., user@host or fly machine name)
#   OMEGA_REMOTE_PATH  -- Remote DB path (default: /data/omega/omega.db)
#   OMEGA_LOCAL_DB     -- Local DB path (default: ~/.omega/omega.db)

REMOTE_HOST="${OMEGA_REMOTE_HOST:?Set OMEGA_REMOTE_HOST (e.g., user@myhost)}"
REMOTE_PATH="${OMEGA_REMOTE_PATH:-/data/omega/omega.db}"
LOCAL_DB="${OMEGA_LOCAL_DB:-$HOME/.omega/omega.db}"
BACKUP_DIR="$HOME/.omega/backups"

case "${1:-}" in
    push)
        echo "Pushing local DB to remote..."
        if [ ! -f "$LOCAL_DB" ]; then
            echo "Error: Local DB not found at $LOCAL_DB"
            exit 1
        fi
        # WAL checkpoint before copying to ensure consistency
        python3.11 -c "
import sqlite3
conn = sqlite3.connect('$LOCAL_DB')
conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
conn.close()
print('WAL checkpoint done')
"
        rsync -avz --progress "$LOCAL_DB" "$REMOTE_HOST:$REMOTE_PATH"
        echo "Done. Pushed $(du -h "$LOCAL_DB" | cut -f1) to $REMOTE_HOST:$REMOTE_PATH"
        ;;
    pull)
        echo "Pulling remote DB to local backup..."
        mkdir -p "$BACKUP_DIR"
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        DEST="$BACKUP_DIR/omega-remote-$TIMESTAMP.db"
        rsync -avz --progress "$REMOTE_HOST:$REMOTE_PATH" "$DEST"
        echo "Done. Saved to $DEST ($(du -h "$DEST" | cut -f1))"
        ;;
    *)
        echo "Usage: $0 {push|pull}"
        echo ""
        echo "  push  -- Upload local omega.db to remote host"
        echo "  pull  -- Download remote omega.db to local backup"
        exit 1
        ;;
esac
```

**Step 2: Make it executable**

Run: `chmod +x ~/Projects/omega/scripts/sync-db.sh`

**Step 3: Commit**

```bash
git add scripts/sync-db.sh
git commit -m "feat: add database sync script for remote OMEGA deployment"
```

---

## Task 7: End-to-end local verification

**Files:** None new -- this is a verification task.

**Step 1: Run the full test suite to verify nothing is broken**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_remote_server.py tests/test_remote_auth.py -v`
Expected: All tests PASS

**Step 2: Run existing tests to confirm no regressions**

Run: `cd ~/Projects/omega && python3.11 -m pytest -x --timeout=120`
Expected: Existing test suite still passes

**Step 3: Run ruff lint**

Run: `cd ~/Projects/omega && python3.11 -m ruff check src/omega/server/remote_server.py src/omega/server/auth.py`
Expected: No lint errors

**Step 4: Test HTTP server locally (manual smoke test)**

Run:
```bash
cd ~/Projects/omega
AUTH0_DOMAIN=placeholder.auth0.com AUTH0_AUDIENCE=https://placeholder \
    python3.11 -m omega.server.remote_server
```

In another terminal:
```bash
# Health check
curl http://localhost:8000/health

# Well-known endpoint
curl http://localhost:8000/.well-known/oauth-protected-resource

# MCP endpoint (should return method not allowed or protocol info)
curl -X POST http://localhost:8000/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

Expected: Health returns 200, well-known returns Auth0 config, MCP returns initialize response.

**Step 5: Stop the server and document results**

Stop with Ctrl+C. Note any issues for follow-up.

---

## Task 8: Auth0 tenant setup (manual, not code)

**This task is manual configuration, not code.**

**Step 1: Create Auth0 account and tenant**

1. Go to https://auth0.com and sign up (free tier)
2. Create a new tenant (e.g., `omega-memory`)
3. Note the domain (e.g., `omega-memory.auth0.com`)

**Step 2: Create an API in Auth0**

1. Go to Applications > APIs > Create API
2. Name: "OMEGA Remote MCP"
3. Identifier (audience): `https://omega-remote.example.com` (use your actual domain)
4. Signing Algorithm: RS256

**Step 3: Enable Dynamic Client Registration**

1. Go to Settings > Advanced > Enable Dynamic Client Registration
2. This allows Claude Mobile to auto-register as an OAuth client

**Step 4: Test auth config locally**

Run:
```bash
AUTH0_DOMAIN=omega-memory.auth0.com \
AUTH0_AUDIENCE=https://omega-remote.example.com \
    python3.11 -c "from omega.server.auth import get_auth_config; print(get_auth_config())"
```

Expected: Config dict with correct domain, audience, issuer, jwks_uri

**Step 5: Update environment variables for deployment**

Set `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` in your deployment platform's secrets/env config.

---

## Task 9: Deploy to hosting platform

**This task depends on hosting choice (revisited later per design). Below is the Fly.io path as reference.**

**Step 1: Install Fly CLI (if not already)**

Run: `curl -L https://fly.io/install.sh | sh`

**Step 2: Create Fly app**

Run:
```bash
cd ~/Projects/omega
fly launch --no-deploy --name omega-remote
```

**Step 3: Create persistent volume**

Run: `fly volumes create omega_data --size 1 --region sjc`

**Step 4: Configure fly.toml**

The `fly launch` creates `fly.toml`. Ensure it includes:

```toml
[mounts]
  source = "omega_data"
  destination = "/data/omega"

[env]
  OMEGA_HOME = "/data/omega"
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  path = "/health"
  timeout = "5s"
```

**Step 5: Set Auth0 secrets**

Run:
```bash
fly secrets set AUTH0_DOMAIN=omega-memory.auth0.com
fly secrets set AUTH0_AUDIENCE=https://omega-remote.yourdomain.com
```

**Step 6: Push local DB to volume**

Run: `./scripts/sync-db.sh push` (after configuring OMEGA_REMOTE_HOST)

**Step 7: Deploy**

Run: `fly deploy`

**Step 8: Verify deployment**

Run:
```bash
curl https://omega-remote.fly.dev/health
curl https://omega-remote.fly.dev/.well-known/oauth-protected-resource
```

---

## Task 10: Register as Claude Custom Connector

**This task is manual UI configuration.**

**Step 1: Add Custom Connector on claude.ai**

1. Go to https://claude.ai > Settings > Connectors
2. Click "Add custom connector"
3. Enter URL: `https://omega-remote.fly.dev/mcp` (or your domain)
4. Claude will discover the OAuth endpoint and start the DCR flow
5. Authenticate via Auth0 when prompted

**Step 2: Verify on Claude Mobile**

1. Open Claude Mobile (Android)
2. Tap (+) > Manage Connectors
3. Enable "OMEGA Mobile"
4. Start a new conversation
5. Test: "What do you remember about me?" (should trigger omega_query)
6. Test: "Remember that I prefer dark mode" (should trigger omega_store)

**Step 3: Document the working setup**

Store the successful configuration details for reference.

---

## Summary

| Task | Type | Effort | Dependencies |
|------|------|--------|-------------|
| 1. Add `remote` dependency | Code | 5 min | None |
| 2. Create `remote_server.py` | Code + Test | 30 min | Task 1 |
| 3. Create `auth.py` | Code + Test | 20 min | Task 1 |
| 4. Wire auth into remote server | Code + Test | 15 min | Tasks 2, 3 |
| 5. Create Dockerfile | Code | 15 min | Task 4 |
| 6. Create sync script | Code | 10 min | None |
| 7. E2E local verification | Test | 15 min | Tasks 1-6 |
| 8. Auth0 tenant setup | Manual | 15 min | None |
| 9. Deploy to host | Manual | 30 min | Tasks 7, 8 |
| 10. Register Claude connector | Manual | 10 min | Task 9 |

**Total estimated code work: Tasks 1-7 (~2 hours)**
**Total including manual setup: Tasks 1-10 (~3 hours)**
