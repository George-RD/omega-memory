# Feedback Loops Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automated procedural learning extraction at session stop — the only remaining feedback loop from the expanded spec (1.6 retrieval feedback and 1.8 mid-session context push are already implemented).

**Architecture:** New function `_extract_procedural_learnings(session_id)` in session.py, called from `handle_session_stop()` after the existing `_auto_feedback_on_retrieval()`. Scans `coord_audit` for error→recovery and stuck patterns, stores as `lesson_learned` memories.

**Tech Stack:** Python 3.11, SQLite (coord_audit table), OMEGA bridge (auto_capture).

**Spec:** `docs/superpowers/specs/2026-03-14-omega-utilization-gaps-design.md` (Section 1.7)

**Already implemented (verified by codebase exploration):**
- **1.6 Retrieval Quality Feedback:** `_auto_feedback_on_retrieval()` at session.py:1575-1600, with `_compute_retrieval_feedback()` at 1539-1572
- **1.8 Mid-Session Context Push:** `_memory_context_push()` at insights.py:58-129, called at line 153

---

## Chunk 1: Procedural Learning Extraction

### Task 1: Implement `_extract_procedural_learnings()` helper functions

**Files:**
- Modify: `src/omega/server/hook_server/session.py` (add functions before `handle_session_stop()`)
- Test: `tests/test_procedural_learnings.py` (new)

**Key APIs:**
- `CoordinationManager.query_audit(session_id=session_id, limit=500)` → `List[Dict]` with `tool_name`, `result_status` ("ok"/"error"/"timeout"), `call_index`, `result_summary`. Returns ORDER BY created_at DESC — **must re-sort by call_index ASC**.
- `auto_capture(content, event_type="lesson_learned", metadata={...})` → str. Dedup threshold for lesson_learned is 0.85 Jaccard.

- [ ] **Step 1: Write failing test for recovery pattern detection**

Create `tests/test_procedural_learnings.py`:

```python
"""Tests for automated procedural learning extraction."""
from unittest.mock import patch, MagicMock


def _make_audit_row(call_index, tool_name, result_status, result_summary=""):
    """Helper to create a coord_audit row dict."""
    return {
        "id": call_index,
        "session_id": "test-session",
        "tool_name": tool_name,
        "arguments": None,
        "result_summary": result_summary[:200],
        "created_at": f"2026-03-14T00:00:{call_index:02d}Z",
        "call_index": call_index,
        "result_status": result_status,
        "input_size": 100,
    }


def test_detects_recovery_pattern():
    """Should detect error -> success on same tool_name within 10 calls."""
    from omega.server.hook_server.session import _detect_procedural_patterns

    rows = [
        _make_audit_row(1, "Bash", "ok"),
        _make_audit_row(2, "Bash", "error", "command not found: pytest"),
        _make_audit_row(3, "Read", "ok"),
        _make_audit_row(4, "Bash", "error", "command not found: pytest"),
        _make_audit_row(5, "Bash", "ok", "all tests passed"),
    ]

    recoveries, stuck = _detect_procedural_patterns(rows)

    assert len(recoveries) >= 1
    assert recoveries[0]["tool_name"] == "Bash"
    assert recoveries[0]["error_count"] >= 1
    assert "command not found" in recoveries[0]["first_error"]
    assert "all tests passed" in recoveries[0]["success_summary"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_procedural_learnings.py::test_detects_recovery_pattern -v`
Expected: FAIL — `_detect_procedural_patterns` doesn't exist

- [ ] **Step 3: Write failing test for stuck pattern detection**

```python
def test_detects_stuck_pattern():
    """Should detect 5+ consecutive errors on same tool_name."""
    from omega.server.hook_server.session import _detect_procedural_patterns

    rows = [
        _make_audit_row(1, "Edit", "ok"),
        _make_audit_row(2, "Edit", "error", "syntax error line 42"),
        _make_audit_row(3, "Edit", "error", "syntax error line 42"),
        _make_audit_row(4, "Edit", "error", "syntax error line 43"),
        _make_audit_row(5, "Edit", "error", "indentation error"),
        _make_audit_row(6, "Edit", "error", "name error"),
        _make_audit_row(7, "Read", "ok"),
    ]

    recoveries, stuck = _detect_procedural_patterns(rows)

    assert len(stuck) >= 1
    assert stuck[0]["tool_name"] == "Edit"
    assert stuck[0]["consecutive_errors"] >= 5
```

- [ ] **Step 4: Write failing test for gate conditions**

```python
def test_no_learnings_below_20_tool_calls():
    """Should not extract learnings from short sessions."""
    from omega.server.hook_server.session import _detect_procedural_patterns

    # Only 10 rows — below the 20-call threshold
    rows = [
        _make_audit_row(i, "Bash", "error" if i % 2 == 0 else "ok")
        for i in range(1, 11)
    ]

    recoveries, stuck = _detect_procedural_patterns(rows)

    assert len(recoveries) == 0
    assert len(stuck) == 0


def test_max_3_learnings_per_session():
    """Should cap at 3 learnings even if more patterns exist."""
    from omega.server.hook_server.session import _detect_procedural_patterns

    # Create 5 recovery patterns
    rows = []
    for batch in range(5):
        base = batch * 10
        rows.append(_make_audit_row(base + 1, f"Tool{batch}", "error", f"err {batch}"))
        rows.append(_make_audit_row(base + 2, f"Tool{batch}", "ok", f"fixed {batch}"))
    # Pad to 20+ rows
    for i in range(len(rows), 25):
        rows.append(_make_audit_row(i + 1, "Read", "ok"))

    recoveries, stuck = _detect_procedural_patterns(rows)

    # Total patterns should be capped at 3
    assert len(recoveries) + len(stuck) <= 3
```

- [ ] **Step 5: Implement `_detect_procedural_patterns()`**

In `src/omega/server/hook_server/session.py`, add before `handle_session_stop()` (near the other helper functions ~line 1530):

```python
def _detect_procedural_patterns(
    audit_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Detect recovery and stuck patterns from sorted audit rows.

    Args:
        audit_rows: List of coord_audit row dicts, sorted by call_index ASC.

    Returns:
        Tuple of (recovery_patterns, stuck_patterns), each capped so total <= 3.
        Recovery: error on tool_name followed by success within 10 calls.
        Stuck: 5+ consecutive errors on same tool_name.
    """
    if len(audit_rows) < 20:
        return [], []

    recoveries = []
    stuck_patterns = []

    # --- Detect recovery patterns ---
    # Track last error per tool_name
    last_error: dict[str, dict] = {}  # tool_name -> {index, summary, count}

    for row in audit_rows:
        tool = row.get("tool_name", "")
        status = row.get("result_status", "ok")
        idx = row.get("call_index", 0)
        summary = row.get("result_summary", "") or ""

        if status == "error":
            if tool not in last_error:
                last_error[tool] = {
                    "first_index": idx,
                    "first_error": summary[:100],
                    "count": 0,
                }
            last_error[tool]["count"] += 1
            last_error[tool]["last_index"] = idx

        elif status == "ok" and tool in last_error:
            err = last_error[tool]
            # Recovery: success within 10 calls of last error
            if idx - err["last_index"] <= 10:
                recoveries.append({
                    "tool_name": tool,
                    "error_count": err["count"],
                    "first_error": err["first_error"],
                    "success_summary": summary[:100],
                })
            del last_error[tool]

    # --- Detect stuck patterns ---
    consecutive_count = 0
    consecutive_tool = ""
    consecutive_last_summary = ""

    for row in audit_rows:
        tool = row.get("tool_name", "")
        status = row.get("result_status", "ok")
        summary = row.get("result_summary", "") or ""

        if status == "error" and tool == consecutive_tool:
            consecutive_count += 1
            consecutive_last_summary = summary[:100]
        elif status == "error":
            # Check if previous streak qualifies
            if consecutive_count >= 5:
                stuck_patterns.append({
                    "tool_name": consecutive_tool,
                    "consecutive_errors": consecutive_count,
                    "last_error": consecutive_last_summary,
                })
            consecutive_tool = tool
            consecutive_count = 1
            consecutive_last_summary = summary[:100]
        else:
            if consecutive_count >= 5:
                stuck_patterns.append({
                    "tool_name": consecutive_tool,
                    "consecutive_errors": consecutive_count,
                    "last_error": consecutive_last_summary,
                })
            consecutive_count = 0
            consecutive_tool = ""

    # Final check for streak at end of list
    if consecutive_count >= 5:
        stuck_patterns.append({
            "tool_name": consecutive_tool,
            "consecutive_errors": consecutive_count,
            "last_error": consecutive_last_summary,
        })

    # Cap total learnings at 3
    total = recoveries[:3]
    remaining = 3 - len(total)
    if remaining > 0:
        total_stuck = stuck_patterns[:remaining]
    else:
        total_stuck = []

    return total, total_stuck
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_procedural_learnings.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/hook_server/session.py tests/test_procedural_learnings.py
git commit -m "feat(hooks): add procedural pattern detection for session learning

Detects recovery patterns (error -> success on same tool within 10 calls)
and stuck patterns (5+ consecutive errors). Capped at 3 total, gated on
20+ tool calls."
```

---

### Task 2: Implement `_extract_procedural_learnings()` and wire into session stop

**Files:**
- Modify: `src/omega/server/hook_server/session.py` (add function, wire into handle_session_stop)
- Test: `tests/test_procedural_learnings.py`

- [ ] **Step 1: Write failing test for the full extraction function**

Add to `tests/test_procedural_learnings.py`:

```python
def test_extract_procedural_learnings_stores_recovery():
    """Full extraction should store recovery as lesson_learned via auto_capture."""
    from omega.server.hook_server.session import _extract_procedural_learnings

    mock_rows = [_make_audit_row(i, "Read", "ok") for i in range(1, 21)]
    # Inject a recovery pattern
    mock_rows[5] = _make_audit_row(6, "Bash", "error", "pytest: command not found")
    mock_rows[6] = _make_audit_row(7, "Bash", "error", "pytest: command not found")
    mock_rows[7] = _make_audit_row(8, "Bash", "ok", "3 tests passed")

    with patch("omega.server.hook_server.session.get_manager") as mock_gm, \
         patch("omega.server.hook_server.session.auto_capture") as mock_capture:

        mock_mgr = MagicMock()
        mock_mgr.query_audit.return_value = mock_rows
        mock_gm.return_value = mock_mgr

        _extract_procedural_learnings("test-session")

        # Verify auto_capture was called with lesson_learned
        assert mock_capture.called
        call_args = mock_capture.call_args
        assert call_args.kwargs.get("event_type") == "lesson_learned" or \
               (len(call_args.args) >= 2 and call_args.args[1] == "lesson_learned")
        metadata = call_args.kwargs.get("metadata", {})
        assert metadata.get("source") == "auto_procedural"
        assert metadata.get("polarity") == "positive"


def test_extract_procedural_learnings_stores_stuck():
    """Full extraction should store stuck pattern as lesson_learned."""
    from omega.server.hook_server.session import _extract_procedural_learnings

    mock_rows = [_make_audit_row(i, "Read", "ok") for i in range(1, 21)]
    # Inject a stuck pattern: 6 consecutive Edit errors
    for i in range(5, 11):
        mock_rows[i] = _make_audit_row(i + 1, "Edit", "error", f"syntax error {i}")

    with patch("omega.server.hook_server.session.get_manager") as mock_gm, \
         patch("omega.server.hook_server.session.auto_capture") as mock_capture:

        mock_mgr = MagicMock()
        mock_mgr.query_audit.return_value = mock_rows
        mock_gm.return_value = mock_mgr

        _extract_procedural_learnings("test-session")

        assert mock_capture.called
        content = mock_capture.call_args.kwargs.get("content", "") or mock_capture.call_args.args[0]
        assert "Anti-pattern" in content or "failed" in content.lower()
        metadata = mock_capture.call_args.kwargs.get("metadata", {})
        assert metadata.get("source") == "auto_procedural"
        assert metadata.get("polarity") == "negative"


def test_extract_procedural_learnings_skips_short_sessions():
    """Should not run for sessions with < 20 tool calls."""
    from omega.server.hook_server.session import _extract_procedural_learnings

    mock_rows = [_make_audit_row(i, "Bash", "error") for i in range(1, 10)]

    with patch("omega.server.hook_server.session.get_manager") as mock_gm, \
         patch("omega.server.hook_server.session.auto_capture") as mock_capture:

        mock_mgr = MagicMock()
        mock_mgr.query_audit.return_value = mock_rows
        mock_gm.return_value = mock_mgr

        _extract_procedural_learnings("test-session")

        mock_capture.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_procedural_learnings.py -v -k "extract_procedural"`
Expected: FAIL — `_extract_procedural_learnings` doesn't exist

- [ ] **Step 3: Implement `_extract_procedural_learnings()`**

In `src/omega/server/hook_server/session.py`, add after `_detect_procedural_patterns()`:

```python
def _extract_procedural_learnings(session_id: str) -> None:
    """Extract procedural learnings from session audit trail.

    Detects recovery patterns (error -> success) and stuck patterns
    (5+ consecutive errors). Stores as lesson_learned memories.

    Gates: 20+ tool calls, max 3 learnings, dedup via auto_capture threshold.
    """
    if not session_id:
        return

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        if mgr is None:
            return

        raw_rows = mgr.query_audit(session_id=session_id, limit=500)
        # query_audit returns ORDER BY created_at DESC — re-sort chronologically
        audit_rows = sorted(raw_rows, key=lambda r: r.get("call_index", 0))

        recoveries, stuck = _detect_procedural_patterns(audit_rows)

        if not recoveries and not stuck:
            return

        from omega.bridge import auto_capture

        stored = 0

        for rec in recoveries:
            if stored >= 3:
                break
            content = (
                f"Approach that worked: {rec['tool_name']} error resolved after "
                f"{rec['error_count']} attempts. Error context: {rec['first_error']}. "
                f"Success context: {rec['success_summary']}"
            )
            auto_capture(
                content=content,
                event_type="lesson_learned",
                metadata={
                    "source": "auto_procedural",
                    "polarity": "positive",
                    "memory_type": "procedural",
                },
                session_id=session_id,
            )
            stored += 1

        for stk in stuck:
            if stored >= 3:
                break
            content = (
                f"Anti-pattern: {stk['tool_name']} failed {stk['consecutive_errors']} "
                f"consecutive times. Error: {stk['last_error']}"
            )
            auto_capture(
                content=content,
                event_type="lesson_learned",
                metadata={
                    "source": "auto_procedural",
                    "polarity": "negative",
                    "memory_type": "procedural",
                },
                session_id=session_id,
            )
            stored += 1

        if stored > 0:
            logger.info(
                f"Procedural learnings: {stored} patterns extracted "
                f"({len(recoveries)} recoveries, {len(stuck)} stuck)"
            )

    except Exception as e:
        _log_hook_error("extract_procedural_learnings", e)
```

- [ ] **Step 4: Wire into handle_session_stop()**

In `handle_session_stop()`, add after the `_auto_feedback_on_retrieval(session_id)` call (currently ~line 1964):

```python
# --- Cross-session procedural learning extraction ---
_extract_procedural_learnings(session_id)
```

- [ ] **Step 5: Run all tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_procedural_learnings.py -v`
Expected: All PASS

- [ ] **Step 6: Run lint**

Run: `cd ~/Projects/omega && ruff check src/omega/server/hook_server/session.py`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/hook_server/session.py tests/test_procedural_learnings.py
git commit -m "feat(hooks): add procedural learning extraction at session stop

Extracts recovery patterns (error->success) and stuck patterns (5+
consecutive errors) from coord_audit. Stores as lesson_learned with
source=auto_procedural. Capped at 3 per session, gated on 20+ tool calls."
```

---

### Task 3: Verify existing implementations (1.6 and 1.8)

**Files:** None (verification only)

- [ ] **Step 1: Verify 1.6 retrieval feedback has tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -v -k "retrieval_feedback or compute_retrieval" --no-header -q 2>&1 | tail -10`

If no tests exist, note this as a gap but don't block — the implementation is already live.

- [ ] **Step 2: Verify 1.8 mid-session context push has tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -v -k "memory_context_push or memory_push" --no-header -q 2>&1 | tail -10`

If no tests exist, note this as a gap but don't block.

- [ ] **Step 3: Run full related test suite**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_procedural_learnings.py tests/test_protocol.py tests/test_maintenance_pipeline.py tests/server/hook_server/test_auto_checkpoint.py tests/test_welcome_briefing_enhancements.py -v --no-header -q 2>&1 | tail -5`
Expected: All PASS

- [ ] **Step 4: Final lint**

Run: `cd ~/Projects/omega && ruff check src/omega/server/hook_server/session.py src/omega/server/hook_server/insights.py`
Expected: No errors
