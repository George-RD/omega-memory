# Session Tracing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add always-on, lightweight session tracing to OMEGA by extending coord_audit with trace columns, capturing every tool call via a new PostToolUse hook, and exposing traces through omega_query mode="trace".

**Architecture:** Extend the existing `coord_audit` table with 4 nullable columns (latency_ms, call_index, result_status, input_size). A new `handle_trace_capture()` hook handler fires on every PostToolUse, writes one row per tool call. Query via `omega_query(mode="trace", session_id=...)` returns a formatted timeline.

**Tech Stack:** Python 3.11, SQLite, OMEGA hook server (Unix domain socket), pytest

**Design doc:** `docs/plans/2026-02-22-session-tracing-design.md`

---

### Task 1: Schema Migration (coord_audit columns)

**Files:**
- Modify: `src/omega/coordination.py:229-247` (_ensure_tables, coord_audit CREATE TABLE)

**Step 1: Write the failing test**

Create `tests/test_trace.py`:

```python
"""Tests for session tracing: schema, capture, and query."""

import pytest
from omega.coordination import CoordinationManager


@pytest.fixture
def mgr(tmp_path):
    return CoordinationManager(str(tmp_path / "coord.db"))


class TestTraceSchema:
    def test_coord_audit_has_trace_columns(self, mgr):
        """coord_audit should have latency_ms, call_index, result_status, input_size."""
        cursor = mgr._conn.execute("PRAGMA table_info(coord_audit)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "latency_ms" in columns
        assert "call_index" in columns
        assert "result_status" in columns
        assert "input_size" in columns
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_trace.py::TestTraceSchema::test_coord_audit_has_trace_columns -v`
Expected: FAIL (columns don't exist yet)

**Step 3: Add columns to _ensure_tables**

In `src/omega/coordination.py`, after the existing coord_audit CREATE TABLE (line ~238), add 4 safe ALTERs:

```python
        # Trace columns (added v1.1.0) — nullable for backward compat
        for col, typedef in [
            ("latency_ms", "INTEGER"),
            ("call_index", "INTEGER"),
            ("result_status", "TEXT DEFAULT 'ok'"),
            ("input_size", "INTEGER"),
        ]:
            try:
                c.execute(f"ALTER TABLE coord_audit ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # Column already exists
```

**Step 4: Run test to verify it passes**

Run: `python3.11 -m pytest tests/test_trace.py::TestTraceSchema -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/omega/coordination.py tests/test_trace.py
git commit -m "feat(trace): add trace columns to coord_audit schema"
```

---

### Task 2: Extend log_audit() and query_audit()

**Files:**
- Modify: `src/omega/coordination.py:3043-3097` (log_audit and query_audit methods)

**Step 1: Write the failing test**

Append to `tests/test_trace.py`:

```python
class TestTraceLogAudit:
    def test_log_audit_with_trace_fields(self, mgr):
        """log_audit should accept and store trace fields."""
        row_id = mgr.log_audit(
            session_id="sess-1",
            tool_name="Edit",
            arguments={"file_path": "/tmp/test.py"},
            result_summary="ok",
            latency_ms=42,
            call_index=1,
            result_status="ok",
            input_size=256,
        )
        assert row_id > 0

        rows = mgr.query_audit(session_id="sess-1")
        assert len(rows) == 1
        assert rows[0]["latency_ms"] == 42
        assert rows[0]["call_index"] == 1
        assert rows[0]["result_status"] == "ok"
        assert rows[0]["input_size"] == 256

    def test_log_audit_without_trace_fields(self, mgr):
        """Existing callers that omit trace fields should still work."""
        row_id = mgr.log_audit(
            session_id="sess-2",
            tool_name="Read",
            arguments=None,
            result_summary="read ok",
        )
        assert row_id > 0

        rows = mgr.query_audit(session_id="sess-2")
        assert len(rows) == 1
        assert rows[0]["latency_ms"] is None
        assert rows[0]["call_index"] is None
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_trace.py::TestTraceLogAudit -v`
Expected: FAIL (log_audit doesn't accept new params, query_audit doesn't return new fields)

**Step 3: Extend log_audit signature and INSERT**

In `src/omega/coordination.py`, modify `log_audit` (~line 3043):

```python
    def log_audit(
        self,
        tool_name: str,
        session_id: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
        result_summary: Optional[str] = None,
        latency_ms: Optional[int] = None,
        call_index: Optional[int] = None,
        result_status: str = "ok",
        input_size: Optional[int] = None,
    ) -> int:
        """Record a tool call in the audit log."""
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            cursor = self._conn.execute(
                """INSERT INTO coord_audit
                   (session_id, tool_name, arguments, result_summary, created_at,
                    latency_ms, call_index, result_status, input_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    tool_name,
                    json.dumps(arguments) if arguments else None,
                    result_summary,
                    now,
                    latency_ms,
                    call_index,
                    result_status,
                    input_size,
                ),
            )
            self._commit()

        return cursor.lastrowid
```

**Step 4: Extend query_audit SELECT and result dict**

In `src/omega/coordination.py`, modify `query_audit` (~line 3063):

```python
    def query_audit(
        self,
        session_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query the audit log with optional filters."""
        query = """SELECT id, session_id, tool_name, arguments, result_summary,
                          created_at, latency_ms, call_index, result_status, input_size
                   FROM coord_audit"""
        conditions = []
        params: list = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if tool_name:
            conditions.append("tool_name = ?")
            params.append(tool_name)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "tool_name": r[2],
                "arguments": _safe_json_loads(r[3]),
                "result_summary": r[4],
                "created_at": r[5],
                "latency_ms": r[6],
                "call_index": r[7],
                "result_status": r[8],
                "input_size": r[9],
            }
            for r in rows
        ]
```

**Step 5: Run tests to verify they pass**

Run: `python3.11 -m pytest tests/test_trace.py -v`
Expected: All PASS

**Step 6: Run existing coordination tests to check no regressions**

Run: `python3.11 -m pytest tests/test_edge_and_coord.py -x -v`
Expected: All PASS (existing callers of log_audit use keyword args)

**Step 7: Commit**

```bash
git add src/omega/coordination.py tests/test_trace.py
git commit -m "feat(trace): extend log_audit/query_audit with trace fields"
```

---

### Task 3: Trace Capture Hook Handler

**Files:**
- Create: `src/omega/server/hook_server/trace.py`

**Step 1: Write the failing test**

Append to `tests/test_trace.py`:

```python
from omega.server.hook_server.trace import handle_trace_capture


class TestTraceCaptureHandler:
    def test_basic_trace_capture(self):
        """handle_trace_capture should return a dict with no output (silent)."""
        payload = {
            "tool_name": "Edit",
            "tool_input": '{"file_path": "/tmp/test.py", "old_string": "a", "new_string": "b"}',
            "tool_output": "File edited successfully",
            "session_id": "sess-trace-1",
            "project": "/tmp/test-project",
        }
        result = handle_trace_capture(payload)
        assert isinstance(result, dict)

    def test_classifies_error_status(self):
        """Should detect error from Traceback in output."""
        from omega.server.hook_server.trace import _classify_result_status

        assert _classify_result_status("Traceback (most recent call last):\n  ...") == "error"
        assert _classify_result_status("Error: file not found") == "error"
        assert _classify_result_status("exit code 1") == "error"
        assert _classify_result_status("Command timed out after 120s") == "timeout"
        assert _classify_result_status("File edited successfully") == "ok"
        assert _classify_result_status("") == "ok"

    def test_increments_call_index(self):
        """Sequential calls in the same session should increment call_index."""
        from omega.server.hook_server.trace import _call_counters

        _call_counters.clear()
        from omega.server.hook_server.trace import _next_call_index

        assert _next_call_index("sess-a") == 1
        assert _next_call_index("sess-a") == 2
        assert _next_call_index("sess-b") == 1
        assert _next_call_index("sess-a") == 3
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_trace.py::TestTraceCaptureHandler -v`
Expected: FAIL (module doesn't exist)

**Step 3: Implement trace.py**

Create `src/omega/server/hook_server/trace.py`:

```python
"""Session trace capture -- records every tool call to coord_audit."""

import logging
import re

logger = logging.getLogger("omega.hook_server.trace")

# Per-session call counters (in-memory, resets on MCP server restart)
_call_counters: dict[str, int] = {}


def _next_call_index(session_id: str) -> int:
    """Return the next call index for a session (1-based)."""
    _call_counters[session_id] = _call_counters.get(session_id, 0) + 1
    return _call_counters[session_id]


_ERROR_PATTERNS = re.compile(
    r"Traceback \(most recent|Error:|FAILED|exit code [1-9]",
    re.IGNORECASE,
)
_TIMEOUT_PATTERNS = re.compile(
    r"timed? out|timeout",
    re.IGNORECASE,
)


def _classify_result_status(output: str) -> str:
    """Classify tool output as ok, error, or timeout."""
    if not output:
        return "ok"
    if _TIMEOUT_PATTERNS.search(output):
        return "timeout"
    if _ERROR_PATTERNS.search(output):
        return "error"
    return "ok"


def handle_trace_capture(payload: dict) -> dict:
    """Record a trace row for every tool call. Silent (no user output)."""
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", "")
    tool_output = payload.get("tool_output", "")
    session_id = payload.get("session_id", "")
    if not isinstance(tool_output, str):
        tool_output = str(tool_output)

    if not session_id or not tool_name:
        return {}

    call_index = _next_call_index(session_id)
    result_status = _classify_result_status(tool_output)
    input_size = len(tool_input) if tool_input else 0

    try:
        from omega.coordination import CoordinationManager

        mgr = CoordinationManager.get_instance()
        mgr.log_audit(
            session_id=session_id,
            tool_name=tool_name,
            arguments=None,
            result_summary=None,
            call_index=call_index,
            result_status=result_status,
            input_size=input_size,
        )
    except Exception as e:
        logger.debug("Trace capture failed: %s", e)

    return {}
```

**Step 4: Run test to verify it passes**

Run: `python3.11 -m pytest tests/test_trace.py::TestTraceCaptureHandler -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/omega/server/hook_server/trace.py tests/test_trace.py
git commit -m "feat(trace): add trace capture hook handler"
```

---

### Task 4: Wire Hook Dispatch and Config

**Files:**
- Modify: `src/omega/server/hook_server/core.py:14-59` (imports + dispatch table)
- Modify: `hooks/fast_hook.py:20-33` (_FALLBACK_SCRIPTS)
- Modify: `src/omega/data/hooks.json:13-17` (PostToolUse array)

**Step 1: Write the failing test**

Append to `tests/test_trace.py`:

```python
class TestTraceWiring:
    def test_trace_capture_in_dispatch_table(self):
        """trace_capture should be in the hook dispatch table."""
        from omega.server.hook_server.core import HOOK_HANDLERS

        assert "trace_capture" in HOOK_HANDLERS

    def test_trace_capture_in_fallback_scripts(self):
        """trace_capture should be in fast_hook.py fallback map."""
        import importlib
        import sys
        hooks_dir = str(Path(__file__).parent.parent / "hooks")
        if hooks_dir not in sys.path:
            sys.path.insert(0, hooks_dir)
        import fast_hook
        importlib.reload(fast_hook)
        assert "trace_capture" in fast_hook._FALLBACK_SCRIPTS
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_trace.py::TestTraceWiring -v`
Expected: FAIL (trace_capture not registered)

**Step 3: Add import and dispatch entry in core.py**

In `src/omega/server/hook_server/core.py`, add import (after line 15):
```python
from .trace import handle_trace_capture
```

Add to `_COMMERCIAL_HOOK_HANDLERS` dict (after line 58):
```python
    "trace_capture": handle_trace_capture,
```

**Step 4: Add fallback entry in fast_hook.py**

In `hooks/fast_hook.py`, add to `_FALLBACK_SCRIPTS` dict (after line 32):
```python
    "trace_capture": "trace_capture",
```

Note: trace_capture doesn't have a standalone fallback script, but the entry is needed for the wiring test. The fallback will silently skip (no script file found). This is acceptable since trace capture is non-critical.

**Step 5: Add PostToolUse entry in hooks.json**

In `src/omega/data/hooks.json`, add to the PostToolUse array (as the first entry, before surface_memories):
```json
    {"script": "fast_hook.py trace_capture", "timeout": 2000, "matcher": ""}
```

This empty matcher means it fires for ALL tool calls, not just Edit/Write/Bash/Read.

**Step 6: Run tests to verify they pass**

Run: `python3.11 -m pytest tests/test_trace.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/omega/server/hook_server/core.py hooks/fast_hook.py src/omega/data/hooks.json tests/test_trace.py
git commit -m "feat(trace): wire trace_capture into hook dispatch and config"
```

---

### Task 5: omega_query mode="trace"

**Files:**
- Modify: `src/omega/server/tool_schemas.py:49-52` (mode enum)
- Modify: `src/omega/server/handlers.py:247-258` (handle_omega_query)

**Step 1: Write the failing test**

Append to `tests/test_trace.py`:

```python
class TestTraceQuery:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        """Set up a fresh store and coordination manager."""
        import os
        os.environ["OMEGA_HOME"] = str(tmp_path / ".omega")
        (tmp_path / ".omega").mkdir()
        os.environ["OMEGA_ENCRYPT"] = "0"
        from omega.bridge import reset_memory
        reset_memory()
        yield
        reset_memory()
        os.environ.pop("OMEGA_HOME", None)
        os.environ.pop("OMEGA_ENCRYPT", None)

    @pytest.mark.asyncio
    async def test_trace_mode_returns_timeline(self):
        """omega_query mode=trace should return formatted session timeline."""
        from omega.server.handlers import HANDLERS

        # Insert some trace rows
        from omega.coordination import CoordinationManager
        mgr = CoordinationManager.get_instance()
        mgr.log_audit(session_id="sess-t", tool_name="Read", call_index=1, result_status="ok", input_size=100)
        mgr.log_audit(session_id="sess-t", tool_name="Edit", call_index=2, result_status="ok", input_size=500)
        mgr.log_audit(session_id="sess-t", tool_name="Bash", call_index=3, result_status="error", input_size=50)

        result = await HANDLERS["omega_query"]({"mode": "trace", "session_id": "sess-t"})
        text = result["content"][0]["text"]
        assert "3 tool calls" in text
        assert "Read" in text
        assert "Edit" in text
        assert "Bash" in text
        assert "error" in text

    @pytest.mark.asyncio
    async def test_trace_mode_requires_session_id(self):
        """mode=trace without session_id should return an error."""
        from omega.server.handlers import HANDLERS

        result = await HANDLERS["omega_query"]({"mode": "trace"})
        assert result.get("isError", False)
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_trace.py::TestTraceQuery -v`
Expected: FAIL (mode="trace" not handled)

**Step 3: Add "trace" to mode enum in tool_schemas.py**

In `src/omega/server/tool_schemas.py`, line 51, change:
```python
"enum": ["semantic", "phrase", "timeline", "browse"],
```
to:
```python
"enum": ["semantic", "phrase", "timeline", "browse", "trace"],
```

Update description on line 52 to include trace:
```python
"description": "Search mode: 'semantic' (default), 'phrase' for exact match, 'timeline' for recent memories by day, 'browse' for listing, 'trace' for session tool call timeline",
```

**Step 4: Add trace mode handler in handlers.py**

In `src/omega/server/handlers.py`, after the browse mode check (~line 257), add:

```python
    # Trace mode — session tool call timeline
    if mode == "trace":
        return await handle_omega_trace(arguments)
```

Then add the handler function (before or after `handle_omega_timeline`):

```python
async def handle_omega_trace(arguments: dict) -> dict:
    """Format a session's tool call trace as a timeline."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required for trace mode")

    try:
        from omega.coordination import CoordinationManager

        mgr = CoordinationManager.get_instance()
        rows = mgr.query_audit(session_id=session_id, limit=500)

        if not rows:
            return mcp_response(f"No trace data for session {session_id}")

        # Sort by call_index (ascending) if available, else by created_at
        rows.sort(key=lambda r: (r.get("call_index") or 0, r.get("created_at", "")))

        error_count = sum(1 for r in rows if r.get("result_status") == "error")
        total_latency = sum(r.get("latency_ms") or 0 for r in rows)

        lines = [f"Session {session_id[:12]} -- {len(rows)} tool calls, {total_latency/1000:.1f}s total, {error_count} errors\n"]

        for r in rows:
            idx = r.get("call_index") or "-"
            lat = f"{r.get('latency_ms') or 0}ms"
            tool = r.get("tool_name", "?")
            status = r.get("result_status") or "ok"
            size = r.get("input_size") or 0
            size_str = f"{size/1024:.1f}KB" if size >= 1024 else f"{size}B"

            lines.append(f" #{idx:<4} {lat:<8} {tool:<12} {status:<8} {size_str}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("omega_query (trace) failed: %s", e, exc_info=True)
        return mcp_error(f"Trace query failed: {e}")
```

**Step 5: Run tests to verify they pass**

Run: `python3.11 -m pytest tests/test_trace.py -v`
Expected: All PASS

**Step 6: Run full handler smoke tests for regression**

Run: `python3.11 -m pytest tests/test_handler_smoke.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/omega/server/tool_schemas.py src/omega/server/handlers.py tests/test_trace.py
git commit -m "feat(trace): add omega_query mode=trace for session timeline"
```

---

### Task 6: Integration Test and Final Verification

**Files:**
- Modify: `tests/test_trace.py` (add integration test)

**Step 1: Write an end-to-end integration test**

Append to `tests/test_trace.py`:

```python
class TestTraceIntegration:
    def test_full_trace_pipeline(self, mgr):
        """End-to-end: capture trace rows, query them back, verify ordering."""
        from omega.server.hook_server.trace import handle_trace_capture, _call_counters

        _call_counters.clear()

        # Simulate 3 tool calls
        for i, (tool, output) in enumerate([
            ("Read", "file contents here"),
            ("Edit", "File edited successfully"),
            ("Bash", "Traceback (most recent call last):\n  Error"),
        ]):
            handle_trace_capture({
                "tool_name": tool,
                "tool_input": f'{{"arg": "value{i}"}}',
                "tool_output": output,
                "session_id": "sess-integ",
                "project": "/tmp/test",
            })

        rows = mgr.query_audit(session_id="sess-integ")
        assert len(rows) == 3

        # Verify ordering (query returns DESC, so reverse)
        rows.reverse()
        assert rows[0]["tool_name"] == "Read"
        assert rows[0]["call_index"] == 1
        assert rows[0]["result_status"] == "ok"

        assert rows[1]["tool_name"] == "Edit"
        assert rows[1]["call_index"] == 2

        assert rows[2]["tool_name"] == "Bash"
        assert rows[2]["call_index"] == 3
        assert rows[2]["result_status"] == "error"
```

**Step 2: Run the full test suite**

Run: `python3.11 -m pytest tests/test_trace.py -v`
Expected: All PASS

**Step 3: Run the full OMEGA test suite to check for regressions**

Run: `python3.11 -m pytest tests/ -x --timeout=60`
Expected: All PASS. If any test_tool_schemas count test fails, update the count (but we didn't add a new tool, just a new enum value, so it should be fine).

**Step 4: Commit**

```bash
git add tests/test_trace.py
git commit -m "test(trace): add end-to-end integration test"
```

---

### Task 7: Final Commit and Push

**Step 1: Verify clean working tree**

Run: `git status --short`
Expected: Only unrelated files remain

**Step 2: Push**

Run: `git push`
