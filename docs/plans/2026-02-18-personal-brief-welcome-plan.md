# Personal Brief Welcome Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure session_start welcome from system diagnostic to warm personal briefing so users feel OMEGA's memory working.

**Architecture:** Single-file rewrite of output formatting in `handle_session_start()` in `hook_server.py`. Add two small helper functions for user name and last session info. No new DB tables, tools, or dependencies. Existing data queries stay, only output layout changes.

**Tech Stack:** Python 3.11, SQLite (existing omega.db), existing profile engine

**Design doc:** `docs/plans/2026-02-18-personal-brief-welcome-design.md`

---

### Task 1: Add `_get_user_name()` helper

**Files:**
- Modify: `src/omega/server/hook_server.py` (add helper before `handle_session_start`, around line 460)

**Step 1: Write the helper function**

Add this helper before `handle_session_start()`:

```python
def _get_user_name() -> str:
    """Try to get the user's display name from the profile engine."""
    try:
        from omega.profile.engine import get_profile_engine
        pe = get_profile_engine()
        # Try common field names
        for field in ("display_name", "name", "first_name"):
            try:
                val = pe.get_field("identity", field)
                if val and not val.startswith("Error") and not val.startswith("No field"):
                    # Extract just the first name if it's a full name
                    return val.split()[0]
            except Exception:
                continue
    except Exception:
        pass
    return ""
```

**Step 2: Verify no import issues**

Run: `cd /Users/singularityjason/Projects/omega && python3 -c "from omega.server.hook_server import _get_user_name; print(repr(_get_user_name()))"`
Expected: Either a name string or empty string, no crash.

---

### Task 2: Add `_get_last_session_info()` helper

**Files:**
- Modify: `src/omega/server/hook_server.py` (add helper after `_get_user_name`)

**Step 1: Write the helper function**

```python
def _get_last_session_info(current_session_id: str) -> dict:
    """Get info about the most recently ended session for the personal greeting.

    Returns dict with keys: agent_name, task, ended_ago, checkpoint_text.
    All values are strings, empty string if unavailable.
    """
    result = {"agent_name": "", "task": "", "ended_ago": "", "checkpoint_text": ""}
    try:
        db_path = Path.home() / ".omega" / "omega.db"
        if not db_path.exists():
            return result
        import sqlite3
        conn = sqlite3.connect(str(db_path), timeout=2)
        conn.row_factory = sqlite3.Row
        try:
            # Most recent ended session (not current)
            row = conn.execute(
                "SELECT session_id, task, last_heartbeat FROM coord_sessions "
                "WHERE status = 'ended' AND session_id != ? "
                "ORDER BY last_heartbeat DESC LIMIT 1",
                (current_session_id,),
            ).fetchone()
            if row:
                sid = row["session_id"] or ""
                result["agent_name"] = _agent_name_from_sid(sid)
                task_text = row["task"] or ""
                if task_text and task_text not in ("idle", "no task", "null", "New session"):
                    result["task"] = task_text
                # Compute ended_ago
                if row["last_heartbeat"]:
                    try:
                        ended_dt = datetime.fromisoformat(row["last_heartbeat"].replace("Z", "+00:00"))
                        if ended_dt.tzinfo is None:
                            ended_dt = ended_dt.replace(tzinfo=timezone.utc)
                        delta = datetime.now(timezone.utc) - ended_dt
                        secs = delta.total_seconds()
                        if secs < 60:
                            result["ended_ago"] = f"{int(secs)}s ago"
                        elif secs < 3600:
                            result["ended_ago"] = f"{int(secs/60)}m ago"
                        elif secs < 86400:
                            result["ended_ago"] = f"{int(secs/3600)}h ago"
                        else:
                            result["ended_ago"] = f"{int(secs/86400)}d ago"
                    except Exception:
                        pass

            # Most recent checkpoint (any session)
            ckpt_row = conn.execute(
                "SELECT content FROM memories "
                "WHERE event_type = 'checkpoint' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()
            if ckpt_row:
                content = ckpt_row["content"] or ""
                # Extract first line or first 120 chars
                first_line = content.split("\n")[0].strip()
                if first_line.startswith("CHECKPOINT: "):
                    first_line = first_line[12:]
                result["checkpoint_text"] = first_line[:120]
        finally:
            conn.close()
    except Exception:
        pass
    return result
```

Note: `_agent_name_from_sid` needs to reference the existing `_AGENT_NAMES` list already in hook_server.py. Check if there's already a function for this. If the statusline has `_agent_name()` but hook_server.py doesn't, add a minimal version:

```python
def _agent_name_from_sid(session_id: str) -> str:
    """Derive a human-friendly agent name from session ID hash."""
    if not session_id:
        return ""
    import hashlib
    h = hashlib.md5(session_id.encode()).hexdigest()
    idx = int(h[:8], 16) % len(_AGENT_NAMES)
    return _AGENT_NAMES[idx]
```

Check if `_AGENT_NAMES` already exists in hook_server.py. If yes, reuse. If not, add the list.

**Step 2: Verify no import issues**

Run: `cd /Users/singularityjason/Projects/omega && python3 -c "from omega.server.hook_server import _get_last_session_info; print(_get_last_session_info('test'))"`
Expected: Dict with string values, no crash.

---

### Task 3: Rewrite `handle_session_start()` output formatting

**Files:**
- Modify: `src/omega/server/hook_server.py` :: `handle_session_start()` (lines ~625-1070)

This is the main change. Replace the output building section (after all the data gathering is done) with the 5-layer personal brief format.

**Step 1: Rewrite Layer 1 (Personal Greeting) - replace lines 625-658**

Replace the current header section:
```python
    # --- Layer 1: Personal Greeting ---
    user_name = _get_user_name()
    last_session = _get_last_session_info(session_id)

    # Time of day greeting
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        tod = "morning"
    elif 12 <= current_hour < 17:
        tod = "afternoon"
    elif 17 <= current_hour < 22:
        tod = "evening"
    else:
        tod = "night"

    # Streak
    streak_str = ""
    try:
        from omega.milestones import get_streak
        from omega.bridge import _get_store as _gs_streak
        _store_streak = _gs_streak()
        streak = get_streak(_store_streak)
        if streak["current"] >= 3:
            streak_str = f" {streak['current']}-day streak."
    except Exception:
        pass

    # Build greeting line
    name_part = f", {user_name}" if user_name else ""
    greeting = f"Good {tod}{name_part}.{streak_str}"

    lines = [greeting, ""]

    # First-time user onboarding (keep unchanged)
    if memory_count == 0:
        lines.append("OMEGA captures decisions, lessons, and errors automatically as you work.")
        lines.append("Next session, it surfaces relevant context when you edit the same files.")
        lines.append("")
        lines.append("**Quick start:**")
        lines.append('- Say "remember that we always use TypeScript strict mode" to store a preference')
        lines.append("- Make a decision and OMEGA captures it automatically")
        lines.append("- Encounter an error, and OMEGA stores the pattern for future recall")
        lines.append("")
        lines.append("After this session ends, you'll see exactly what was captured.")
    elif memory_count <= 10:
        lines.append(f"OMEGA has {memory_count} memories from your first sessions. These will surface when you edit related files.")
        # ... keep existing type_stats code for early users ...
    else:
        # Last session context
        if last_session["ended_ago"]:
            task_part = ""
            if last_session["task"]:
                task_part = f" working on: {last_session['task'][:60]}"
            agent_part = last_session["agent_name"] or "Previous session"
            lines.append(f"Last session ended {last_session['ended_ago']}.{task_part}")
        if last_session["checkpoint_text"]:
            lines.append(f"You left off at: {last_session['checkpoint_text']}")
```

**Step 2: Rewrite Layer 2 (What's Ahead) - replace task/reminder sections**

Replace the current `[TASKS]`, `[REMINDER]` sections with natural language:

```python
    # --- Layer 2: What's Ahead ---
    ahead_parts = []

    # Tasks (reuse existing task query code, just reformat output)
    if pending_tasks:
        top = pending_tasks[0]
        top_title = top["content"]
        if top_title.startswith("TASK: "):
            top_title = top_title[6:]
        top_title = top_title.split("\n")[0].split("STATUS:")[0].strip()[:60]
        entity_tag = f" [{top['entity']}]" if top["entity"] else ""
        ahead_parts.append(
            f"{len(pending_tasks)} task{'s' if len(pending_tasks) != 1 else ''} pending"
            f" — top: {top_title} (P{top['priority']}){entity_tag}."
        )

    # Reminders (reuse existing reminder query, just reformat)
    # ... due_count already computed ...
    if due_count > 0:
        ahead_parts.append(f"{due_count} reminder{'s' if due_count != 1 else ''} due.")

    # Active peers
    try:
        import sqlite3 as _sq_peers
        _peer_conn = _sq_peers.connect(str(Path.home() / ".omega" / "omega.db"), timeout=2)
        _peer_conn.row_factory = _sq_peers.Row
        peer_rows = _peer_conn.execute(
            "SELECT session_id, task FROM coord_sessions "
            "WHERE status = 'active' AND session_id != ?",
            (session_id,),
        ).fetchall()
        _peer_conn.close()
        if peer_rows:
            peer_parts = []
            for pr in peer_rows[:2]:
                pname = _agent_name_from_sid(pr["session_id"])
                ptask = pr["task"] or "idle"
                if ptask not in ("idle", "no task", "null", "New session"):
                    ptask = ptask[:40]
                else:
                    ptask = "idle"
                peer_parts.append(f"{pname} ({ptask})")
            ahead_parts.append(f"Active peers: {', '.join(peer_parts)}.")
    except Exception:
        pass

    if ahead_parts:
        lines.append("")
        for part in ahead_parts:
            lines.append(part)
```

**Step 3: Keep Layer 3 (Agent Context) unchanged**

The `[CONTEXT]` section stays exactly as-is. No changes needed.

**Step 4: Rewrite Layer 4 (Nudges) - remove bracket prefixes**

Replace `[NUDGE]` prefix with plain sentences:

```python
    # --- Layer 4: Nudges (natural language, no brackets) ---
    if nudges:
        lines.append("")
        for nudge in nudges[:2]:  # Cap at 2
            lines.append(nudge)
```

Remove the `[NUDGE]` prefix from the nudge generation code too (around lines 984, 996, 998).

**Step 5: Rewrite Layer 5 (System Footer) - compress to 1 line**

Replace the multi-line health/graph/profile/maintenance sections:

```python
    # --- Layer 5: System Footer (compact single line) ---
    footer = f"OMEGA: {memory_count} memories | {health_status} | capture: {last_capture}"
    if footer_parts:
        footer += f" | {', '.join(footer_parts)}"
    lines.append(f"\n{footer}")
```

Remove the separate `**Health:**`, `**Graph:**`, `**Profile:**` lines.

**Step 6: Remove deleted sections**

Delete these output sections (the data queries can stay, just remove the lines.append calls):
- `## Welcome back! OMEGA ready` header (line 628)
- `**Health:**` line (line 661)
- `**Graph:**` line (line 683)
- `**Profile:**` line (line 696)
- `[MAINTENANCE]` line (line 703)
- `[ACTION]` line (lines 858-861)

Keep the `[!]` alert lines (subsystem degradation warnings) - these are important and should stay between Layer 2 and Layer 3.

---

### Task 4: Update existing tests

**Files:**
- Modify: `tests/test_hook_ux_outputs.py` :: `TestHookServerSessionStart` (lines 527-585)

**Step 1: Update test assertions to match new format**

```python
def test_header_with_memories(self):
    """Personal greeting shown for returning users."""
    from omega.server.hook_server import handle_session_start
    mock_ctx = {
        "memory_count": 5, "health_status": "ok",
        "last_capture_ago": "5m ago", "context_items": [],
    }
    with patch("omega.bridge.get_session_context", return_value=mock_ctx), \
         patch("omega.bridge.consolidate"), \
         patch("omega.bridge.compact"):
        result = handle_session_start({"session_id": "s1", "project": "/p"})
    output = result["output"]
    # Personal greeting present
    assert any(tod in output for tod in ("Good morning", "Good afternoon", "Good evening", "Good night"))
    # Footer has memory count
    assert "5 memories" in output

def test_context_items_in_output(self):
    from omega.server.hook_server import handle_session_start
    mock_ctx = {
        "memory_count": 42, "health_status": "ok",
        "last_capture_ago": "5m ago",
        "context_items": [
            {"tag": "DECISION", "text": "Use SQLite WAL mode"},
            {"tag": "LESSON", "text": "Lock is non-reentrant"},
        ],
    }
    with patch("omega.bridge.get_session_context", return_value=mock_ctx), \
         patch("omega.bridge.consolidate"), \
         patch("omega.bridge.compact"):
        result = handle_session_start({"session_id": "s1", "project": "/p"})
    # Context items unchanged
    assert "[CONTEXT]" in result["output"]
    assert "DECISION: Use SQLite WAL mode" in result["output"]
    assert "LESSON: Lock is non-reentrant" in result["output"]

def test_first_session_greeting(self):
    from omega.server.hook_server import handle_session_start
    mock_ctx = {
        "memory_count": 0, "health_status": "ok",
        "last_capture_ago": "unknown", "context_items": [],
    }
    with patch("omega.bridge.get_session_context", return_value=mock_ctx), \
         patch("omega.bridge.consolidate"), \
         patch("omega.bridge.compact"):
        result = handle_session_start({"session_id": "s1", "project": "/p"})
    output = result["output"]
    # Still shows first-time onboarding
    assert "OMEGA captures decisions" in output
    assert "Quick start" in output

def test_no_error_on_success(self):
    # Unchanged
    ...
```

**Step 2: Run tests**

Run: `cd /Users/singularityjason/Projects/omega && pytest tests/test_hook_ux_outputs.py::TestHookServerSessionStart -v`
Expected: All 4 tests PASS.

---

### Task 5: Add new tests for personal greeting

**Files:**
- Modify: `tests/test_hook_ux_outputs.py` (add to `TestHookServerSessionStart`)

**Step 1: Add test for streak in greeting**

```python
def test_streak_in_greeting(self):
    from omega.server.hook_server import handle_session_start
    mock_ctx = {
        "memory_count": 100, "health_status": "ok",
        "last_capture_ago": "5m ago", "context_items": [],
    }
    mock_streak = {"current": 7, "longest": 10}
    with patch("omega.bridge.get_session_context", return_value=mock_ctx), \
         patch("omega.bridge.consolidate"), \
         patch("omega.bridge.compact"), \
         patch("omega.milestones.get_streak", return_value=mock_streak):
        result = handle_session_start({"session_id": "s1", "project": "/p"})
    assert "7-day streak" in result["output"]
```

**Step 2: Add test for compact footer**

```python
def test_compact_footer(self):
    from omega.server.hook_server import handle_session_start
    mock_ctx = {
        "memory_count": 730, "health_status": "ok",
        "last_capture_ago": "12m ago", "context_items": [],
    }
    with patch("omega.bridge.get_session_context", return_value=mock_ctx), \
         patch("omega.bridge.consolidate"), \
         patch("omega.bridge.compact"):
        result = handle_session_start({"session_id": "s1", "project": "/p"})
    output = result["output"]
    # Footer is compact single line
    assert "OMEGA: 730 memories" in output
    assert "capture: 12m ago" in output
```

**Step 3: Run all tests**

Run: `cd /Users/singularityjason/Projects/omega && pytest tests/test_hook_ux_outputs.py::TestHookServerSessionStart -v`
Expected: All tests PASS.

---

### Task 6: Run full test suite and commit

**Step 1: Run full hook UX tests**

Run: `cd /Users/singularityjason/Projects/omega && pytest tests/test_hook_ux_outputs.py -v`
Expected: All tests PASS.

**Step 2: Run broader test suite for regressions**

Run: `cd /Users/singularityjason/Projects/omega && pytest tests/test_hook_server.py -x -v`
Expected: PASS, no regressions.

**Step 3: Commit**

```bash
cd /Users/singularityjason/Projects/omega
git add src/omega/server/hook_server.py tests/test_hook_ux_outputs.py docs/plans/2026-02-18-personal-brief-welcome-design.md docs/plans/2026-02-18-personal-brief-welcome-plan.md
git commit -m "feat: personal brief welcome - warm greeting replaces system diagnostic

Restructure session_start welcome output so users feel OMEGA's memory
working. Greeting uses time-of-day, user name, streak, last session
context. System diagnostics compressed to single footer line. Agent
context ([CONTEXT] blocks) preserved unchanged.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```
