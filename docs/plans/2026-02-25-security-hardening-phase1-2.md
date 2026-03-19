# Security Hardening (Phases 1-2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the two highest-value security gaps: incomplete write-tool rate limiting and missing input validation in coordination handlers.

**Architecture:** Phase 1 rebuilds `_WRITE_TOOLS` in `mcp_server.py` as a comprehensive set covering all mutation tools, with a guard test to prevent future drift. Phase 2 adds `_validate_session_id` calls to all coord handlers that accept `session_id`, reusing the existing validator from `handlers.py`.

**Tech Stack:** Python 3.11, pytest, SQLite

---

### Task 1: Add drift-detection test for `_WRITE_TOOLS`

**Files:**
- Modify: `tests/test_security_hardening.py` (append to existing `TestRateLimiting` class)

**Step 1: Write the failing test**

Add this test to the end of `TestRateLimiting` in `tests/test_security_hardening.py`:

```python
def test_all_write_tools_are_rate_limited(self):
    """Every mutation tool must be in _WRITE_TOOLS. Prevents drift."""
    from omega.server.mcp_server import _WRITE_TOOLS

    # Exhaustive list of read-only tools (safe to exclude from write limiting)
    READ_ONLY_TOOLS = frozenset({
        # Core read tools
        "omega_query", "omega_welcome", "omega_protocol", "omega_lessons",
        "omega_resume_task", "omega_stats", "omega_profile",
        # Coord read tools
        "omega_sessions_list", "omega_file_check", "omega_intent_check",
        "omega_coord_status", "omega_session_recover", "omega_task_next",
        "omega_tasks_list", "omega_audit", "omega_inbox",
        "omega_find_agents", "omega_git_events", "omega_branch_check",
        "omega_coord_metrics", "omega_action_check", "omega_drift_check",
        "omega_smart_route", "omega_compare_agents", "omega_decision_query",
    })

    # Get all registered tool names
    from omega.server.tool_schemas import TOOLS as core_tools
    from omega.server.coord_schemas import TOOLS as coord_tools
    all_tool_names = {t["name"] for t in core_tools} | {t["name"] for t in coord_tools}

    # Every tool must be classified as either read-only or write
    unclassified = all_tool_names - _WRITE_TOOLS - READ_ONLY_TOOLS
    assert not unclassified, (
        f"Tools not classified as read or write (add to _WRITE_TOOLS or READ_ONLY_TOOLS): "
        f"{sorted(unclassified)}"
    )
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_security_hardening.py::TestRateLimiting::test_all_write_tools_are_rate_limited -v`
Expected: FAIL listing all unclassified tools

---

### Task 2: Rebuild `_WRITE_TOOLS` with all mutation tools

**Files:**
- Modify: `src/omega/server/mcp_server.py:149-158`

**Step 1: Replace `_WRITE_TOOLS` with comprehensive set**

Replace the existing `_WRITE_TOOLS` frozenset (lines 149-158) with:

```python
_WRITE_TOOLS = frozenset({
    # Core write tools (handlers.py)
    "omega_store", "omega_checkpoint", "omega_remind",
    "omega_memory", "omega_maintain", "omega_reflect",
    # Coord session lifecycle
    "omega_session_register", "omega_session_heartbeat",
    "omega_session_deregister", "omega_session_snapshot",
    # Coord file/branch claims
    "omega_file_claim", "omega_file_release",
    "omega_branch_claim", "omega_branch_release",
    # Coord intents
    "omega_intent_announce",
    # Coord tasks
    "omega_task_create", "omega_task_claim", "omega_task_complete",
    "omega_task_fail", "omega_task_cancel", "omega_task_progress",
    "omega_task_deps", "omega_update_task",
    # Coord messaging
    "omega_send_message", "omega_handoff",
    # Coord actions
    "omega_action_claim", "omega_action_complete",
    # Coord goals & decisions
    "omega_goal", "omega_goal_link",
    "omega_decision_register", "omega_decision_revoke",
    # Pro features
    "omega_profile_set", "omega_entity_create", "omega_entity_update",
    "omega_ingest_document",
    "omega_oracle_record", "omega_oracle_resolve",
    "omega_track_statement", "omega_resolve_outcome",
})
```

**Step 2: Run the drift-detection test**

Run: `python3.11 -m pytest tests/test_security_hardening.py::TestRateLimiting::test_all_write_tools_are_rate_limited -v`
Expected: PASS (all tools now classified)

**Step 3: Run all rate limiting tests**

Run: `python3.11 -m pytest tests/test_security_hardening.py::TestRateLimiting -v`
Expected: All 5 tests PASS

**Step 4: Commit**

```bash
git add src/omega/server/mcp_server.py tests/test_security_hardening.py
git commit -m "fix(security): complete _WRITE_TOOLS coverage with drift-detection test"
```

---

### Task 3: Extract validators into shared module

**Files:**
- Create: `src/omega/server/validation.py`
- Modify: `src/omega/server/handlers.py:106-141`

**Step 1: Create shared validation module**

Create `src/omega/server/validation.py`:

```python
"""Shared input validation helpers for MCP handlers.

Prevents path traversal and injection via session_id, entity_id,
and other user-supplied identifiers.
"""

import logging
import re

logger = logging.getLogger("omega.server.validation")

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def validate_session_id(session_id: str | None) -> str | None:
    """Validate session_id to prevent path traversal.

    Returns cleaned session_id or None if invalid.
    """
    if not session_id:
        return session_id
    if ".." in session_id or "/" in session_id or "\\" in session_id:
        logger.warning("Rejected session_id with path traversal: %s", session_id[:50])
        return None
    if not _SAFE_ID_RE.match(session_id):
        logger.warning("Rejected session_id with invalid chars: %s", session_id[:50])
        return None
    return session_id


def validate_entity_id(entity_id: str | None) -> str | None:
    """Validate entity_id format (alphanumeric, hyphens, dots, underscores).

    Returns cleaned entity_id or None if invalid.
    """
    if not entity_id:
        return entity_id
    if not _SAFE_ID_RE.match(entity_id):
        logger.warning("Rejected entity_id with invalid chars: %s", entity_id[:50])
        return None
    return entity_id
```

**Step 2: Update handlers.py to import from shared module**

Replace lines 106-141 in `handlers.py` (the validation section) with:

```python
from omega.server.validation import validate_session_id as _validate_session_id
from omega.server.validation import validate_entity_id as _validate_entity_id
```

Keep the `_SAFE_EXPORT_DIR` line (103) and the comment block (106-108) intact. Only remove the regex definitions and the two function definitions.

**Step 3: Run existing tests**

Run: `python3.11 -m pytest tests/test_security_hardening.py -v`
Expected: All existing tests PASS (refactor is behavior-preserving)

**Step 4: Commit**

```bash
git add src/omega/server/validation.py src/omega/server/handlers.py
git commit -m "refactor(security): extract input validators into shared module"
```

---

### Task 4: Write validation tests for coord handlers

**Files:**
- Modify: `tests/test_security_hardening.py` (add new test class)

**Step 1: Write the failing tests**

Append to `tests/test_security_hardening.py`:

```python
# ---------------------------------------------------------------------------
# Phase 7: Coordination handler input validation
# ---------------------------------------------------------------------------


class TestCoordHandlerValidation:
    """Test that coord handlers reject malicious session_ids."""

    @pytest.mark.asyncio
    async def test_session_register_rejects_path_traversal(self):
        from omega.server.coord_handlers import handle_session_register

        result = await handle_session_register({"session_id": "../../../etc/passwd"})
        assert result.get("isError"), f"Should reject path traversal, got: {result}"

    @pytest.mark.asyncio
    async def test_file_claim_rejects_path_traversal(self):
        from omega.server.coord_handlers import handle_file_claim

        result = await handle_file_claim({
            "session_id": "valid-session",
            "file_path": "/tmp/test.py",
        })
        # This should work with valid session_id (may fail for other reasons)
        # But a bad session_id should fail with validation error
        result_bad = await handle_file_claim({
            "session_id": "../../etc/shadow",
            "file_path": "/tmp/test.py",
        })
        assert result_bad.get("isError"), f"Should reject path traversal, got: {result_bad}"

    @pytest.mark.asyncio
    async def test_send_message_rejects_invalid_chars(self):
        from omega.server.coord_handlers import handle_send_message

        result = await handle_send_message({
            "session_id": "valid",
            "to_session_id": "$(whoami)",
            "content": "hello",
        })
        assert result.get("isError"), f"Should reject shell metachar, got: {result}"

    @pytest.mark.asyncio
    async def test_task_create_rejects_path_traversal(self):
        from omega.server.coord_handlers import handle_task_create

        result = await handle_task_create({
            "session_id": "/etc/passwd\x00",
            "title": "test",
        })
        assert result.get("isError"), f"Should reject null byte, got: {result}"

    @pytest.mark.asyncio
    async def test_valid_session_id_passes(self):
        from omega.server.coord_handlers import handle_session_register

        # Valid session_ids should not be rejected by validation
        # (they may fail for other reasons like missing coordination manager)
        result = await handle_session_register({"session_id": "abc-123.test_session"})
        # Should either succeed or fail for non-validation reasons
        if result.get("isError"):
            assert "session_id" not in result["content"][0]["text"].lower() or \
                   "invalid" not in result["content"][0]["text"].lower()
```

**Step 2: Run tests to verify they fail**

Run: `python3.11 -m pytest tests/test_security_hardening.py::TestCoordHandlerValidation -v`
Expected: FAIL (coord handlers don't validate yet)

---

### Task 5: Add validation to coord handlers

**Files:**
- Modify: `src/omega/server/coord_handlers.py` (add import + validation to all handlers with session_id)

**Step 1: Add import at top of coord_handlers.py**

After the existing imports (line 10), add:

```python
from omega.server.validation import validate_session_id as _validate_session_id
```

**Step 2: Add validation guard to each handler that takes session_id**

In every handler that does `session_id = arguments.get("session_id", "").strip()`, add immediately after the existing `if not session_id:` check:

```python
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
```

Apply this pattern to all handlers that accept session_id:
- `handle_session_register` (line 48)
- `handle_session_heartbeat` (line 90)
- `handle_session_deregister` (line 114)
- `handle_file_claim` (line 178)
- `handle_file_release` (line 227)
- `handle_file_check` (line 255)
- `handle_branch_claim` (line 286)
- `handle_branch_release` (line 329)
- `handle_intent_announce` (line 360)
- `handle_intent_check` (line 425)
- `handle_session_snapshot` (line 542)
- `handle_session_recover` (line 570)
- `handle_task_create` (line 618)
- `handle_task_claim` (line 676)
- `handle_task_resolve` (line 747) — also has `result` from arguments
- `handle_audit` (line 860)
- `handle_send_message` (line 898) — also validate `to_session_id`
- `handle_inbox` (line 986)
- `handle_task_fail` (line 1039)
- `handle_task_cancel` (line 1073)
- `handle_task_progress` (line 1102)
- `handle_handoff` (line 1346)
- `handle_action_claim` (line 1463)
- `handle_action_complete` (line 1524)
- `handle_decision_register` (line 1881)

For `handle_send_message`, also validate `to_session_id`:

```python
    to_session_id = arguments.get("to_session_id", "").strip()
    if not to_session_id:
        return mcp_error("to_session_id is required")
    to_session_id = _validate_session_id(to_session_id)
    if not to_session_id:
        return mcp_error("Invalid to_session_id")
```

**Step 3: Run validation tests**

Run: `python3.11 -m pytest tests/test_security_hardening.py::TestCoordHandlerValidation -v`
Expected: All 5 tests PASS

**Step 4: Run full security test suite**

Run: `python3.11 -m pytest tests/test_security_hardening.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/omega/server/coord_handlers.py tests/test_security_hardening.py
git commit -m "fix(security): add session_id validation to all coordination handlers"
```

---

### Task 6: Run full test suite and final verification

**Step 1: Run full test suite**

Run: `python3.11 -m pytest tests/ -x --timeout=30 -q`
Expected: All tests PASS (no regressions)

**Step 2: Verify no hardcoded tool names were missed**

Run: `python3.11 -m pytest tests/test_security_hardening.py -v`
Expected: All tests PASS including drift detection

**Step 3: Final commit (if any fixups needed)**

Only if tests revealed issues that needed fixing.
