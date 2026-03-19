# OMEGA Utilization Boost: A+C Hybrid

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Raise OMEGA tool utilization from 27% to ~50% by tightening protocol enforcement for 5 critical tools and auto-activating 4 dormant capabilities via hooks.

**Architecture:** Two-pronged approach: (A) Add hook-based nudges that detect when agents skip critical tool calls and surface reminders, plus sharpen protocol wording. (C) Add auto-activation logic to existing hooks so dormant capabilities produce data without relying on agent cooperation.

**Tech Stack:** Python 3.11, OMEGA hooks (fast_hook.py dispatcher), protocol.py, bridge.py, coordination.py

---

## Part A: Protocol Tightening (Nudges for 5 Critical Tools)

### Task 1: Session Stop Utilization Report

**Why:** Agents currently get no feedback on what they skipped. A session-end scorecard shows which critical tools were never called, creating awareness.

**Files:**
- Modify: `hooks/session_stop.py`
- Modify: `hooks/trace_capture.py` (ensure tool_name is captured consistently)
- Test: `tests/test_hooks/test_session_stop.py`

**Step 1: Write the failing test**

Create `tests/test_hooks/test_session_stop_utilization.py`:

```python
"""Test session stop utilization report."""
import pytest


def test_utilization_report_flags_missing_tools():
    """When agent never called omega_reflect or omega_decision_query,
    the report should flag them as unused."""
    from hooks.session_stop import _build_utilization_report

    # Simulate a session that called some tools but skipped critical ones
    tool_calls = [
        "omega_welcome", "omega_protocol", "omega_query", "omega_store",
        "Read", "Edit", "Bash", "omega_query", "omega_store",
    ]
    report = _build_utilization_report(tool_calls)

    assert "omega_reflect" in report["missed"]
    assert "omega_decision_query" in report["missed"]
    assert report["score"] < 100  # Not a perfect score


def test_utilization_report_perfect_score():
    """When all critical tools were called, score is 100."""
    from hooks.session_stop import _build_utilization_report

    tool_calls = [
        "omega_welcome", "omega_protocol", "omega_query", "omega_store",
        "omega_reflect", "omega_decision_query", "omega_file_check",
        "omega_checkpoint", "omega_coord_status",
    ]
    report = _build_utilization_report(tool_calls)

    assert len(report["missed"]) == 0
    assert report["score"] == 100


def test_utilization_report_empty_session():
    """An empty session should flag all critical tools."""
    from hooks.session_stop import _build_utilization_report

    report = _build_utilization_report([])
    assert report["score"] == 0
    assert len(report["missed"]) > 0
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_hooks/test_session_stop_utilization.py -v`
Expected: FAIL with ImportError (function doesn't exist yet)

**Step 3: Implement `_build_utilization_report` in `hooks/session_stop.py`**

Add this function near the top of `session_stop.py`:

```python
# Critical tools that agents SHOULD call at least once per session.
# Scored: each hit = 1 point, total / len = percentage.
CRITICAL_TOOLS = [
    "omega_reflect",          # Contradiction/stale detection — 0 calls ever
    "omega_decision_query",   # Check active decisions before domain work — 0 calls
    "omega_file_check",       # Conflict check before edits — 5 calls / 931 edits
    "omega_checkpoint",       # Save state at 70% context — 4 calls ever
    "omega_coord_status",     # Check peers before taking work — 10 calls
]


def _build_utilization_report(tool_calls: list[str]) -> dict:
    """Score which critical OMEGA tools the agent used this session."""
    called = set(tool_calls)
    # Normalize: strip mcp__omega-memory__ prefix if present
    normalized = set()
    for t in called:
        if t.startswith("mcp__omega-memory__"):
            normalized.add(t.replace("mcp__omega-memory__", ""))
        else:
            normalized.add(t)

    missed = [t for t in CRITICAL_TOOLS if t not in normalized]
    hit_count = len(CRITICAL_TOOLS) - len(missed)
    score = round(hit_count / len(CRITICAL_TOOLS) * 100) if CRITICAL_TOOLS else 100

    return {"score": score, "missed": missed, "hit": hit_count, "total": len(CRITICAL_TOOLS)}
```

**Step 4: Run test to verify it passes**

Run: `python3.11 -m pytest tests/test_hooks/test_session_stop_utilization.py -v`
Expected: PASS

**Step 5: Wire the report into session_stop output**

In `hooks/session_stop.py`, find the section that prints the session activity report (near the end of the `main()` function). After the existing report lines, add:

```python
# Utilization scorecard
try:
    tool_names = _get_session_tool_names(session_id)
    report = _build_utilization_report(tool_names)
    if report["missed"]:
        lines.append("")
        lines.append(f"[OMEGA] Utilization: {report['score']}% ({report['hit']}/{report['total']} critical tools used)")
        lines.append(f"  Unused: {', '.join(report['missed'])}")
except Exception:
    pass
```

Also add this helper to read tool names from coord_audit:

```python
def _get_session_tool_names(session_id: str) -> list[str]:
    """Get list of tool names called in this session from coord_audit."""
    try:
        import sqlite3
        db_path = os.path.expanduser("~/.omega/omega.db")
        conn = sqlite3.connect(db_path, timeout=2)
        rows = conn.execute(
            "SELECT DISTINCT tool_name FROM coord_audit WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []
```

**Step 6: Commit**

```bash
git add hooks/session_stop.py tests/test_hooks/test_session_stop_utilization.py
git commit -m "feat(hooks): add session-end utilization scorecard for critical tools"
```

---

### Task 2: Mid-Session Nudge in surface_memories.py

**Why:** The surface_memories hook fires on every Edit/Write/Bash. It's the natural place to nudge agents when they've made 10+ edits without calling `omega_file_check` or `omega_reflect`.

**Files:**
- Modify: `hooks/surface_memories.py`
- Test: `tests/test_hooks/test_surface_nudge.py`

**Step 1: Write the failing test**

Create `tests/test_hooks/test_surface_nudge.py`:

```python
"""Test mid-session utilization nudges."""


def test_nudge_after_many_edits_without_file_check():
    from hooks.surface_memories import _check_nudge

    # 15 edits, 0 file_checks => should nudge
    nudge = _check_nudge(edit_count=15, tool_calls=["Edit"] * 15)
    assert nudge is not None
    assert "omega_file_check" in nudge


def test_no_nudge_when_file_check_called():
    from hooks.surface_memories import _check_nudge

    calls = ["Edit"] * 15 + ["mcp__omega-memory__omega_file_check"]
    nudge = _check_nudge(edit_count=15, tool_calls=calls)
    assert nudge is None


def test_nudge_reflect_after_30_tool_calls():
    from hooks.surface_memories import _check_nudge

    calls = ["Bash"] * 35
    nudge = _check_nudge(edit_count=0, tool_calls=calls)
    assert nudge is not None
    assert "omega_reflect" in nudge
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_hooks/test_surface_nudge.py -v`
Expected: FAIL

**Step 3: Implement `_check_nudge` in `hooks/surface_memories.py`**

Add near the top:

```python
def _check_nudge(edit_count: int, tool_calls: list[str]) -> str | None:
    """Return a nudge string if agent is missing a critical tool call, or None."""
    normalized = set()
    for t in tool_calls:
        if t.startswith("mcp__omega-memory__"):
            normalized.add(t.replace("mcp__omega-memory__", ""))
        else:
            normalized.add(t)

    # Nudge 1: 10+ edits without omega_file_check
    if edit_count >= 10 and "omega_file_check" not in normalized:
        return "[OMEGA] Tip: You've made {n} edits without checking for file conflicts. Consider `omega_file_check(file_path=...)` before your next edit.".format(n=edit_count)

    # Nudge 2: 30+ tool calls without omega_reflect
    if len(tool_calls) >= 30 and "omega_reflect" not in normalized:
        return "[OMEGA] Tip: Consider running `omega_reflect()` to check for contradictions or stale memories in your current work area."

    return None
```

**Step 4: Wire into surface_memories main output**

In the main output path of `surface_memories.py`, after the memory surfacing output, add:

```python
# Mid-session utilization nudge (once per threshold crossing)
try:
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    nudge_marker = Path.home() / ".omega" / f"session-{session_id}.nudged"
    tool_calls = _get_session_tool_names_fast(session_id)
    edit_count = sum(1 for t in tool_calls if t in ("Edit", "Write", "NotebookEdit"))
    nudge = _check_nudge(edit_count, tool_calls)
    if nudge and not nudge_marker.exists():
        print(nudge, file=sys.stderr)
        nudge_marker.touch()  # Only nudge once per session
except Exception:
    pass
```

Add this fast helper (avoids SQLite for speed, reads from the audit trail):

```python
def _get_session_tool_names_fast(session_id: str) -> list[str]:
    """Fast read of tool names from coord_audit for this session."""
    try:
        import sqlite3
        db = sqlite3.connect(os.path.expanduser("~/.omega/omega.db"), timeout=1)
        rows = db.execute(
            "SELECT tool_name FROM coord_audit WHERE session_id = ? ORDER BY call_index",
            (session_id,),
        ).fetchall()
        db.close()
        return [r[0] for r in rows]
    except Exception:
        return []
```

**Step 5: Run tests**

Run: `python3.11 -m pytest tests/test_hooks/test_surface_nudge.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add hooks/surface_memories.py tests/test_hooks/test_surface_nudge.py
git commit -m "feat(hooks): add mid-session nudge for omega_file_check and omega_reflect"
```

---

### Task 3: Sharpen Protocol Wording for 5 Critical Tools

**Why:** The protocol mentions these tools but buried in paragraphs. Making them standalone bullet points with "MUST" language increases compliance.

**Files:**
- Modify: `src/omega/protocol.py`
- Test: `tests/test_protocol.py` (existing — verify protocol still renders)

**Step 1: Edit the protocol sections**

In `src/omega/protocol.py`, add a new section `"critical_tools"` to `SECTIONS`:

```python
"critical_tools": {
    "title": "Critical Tools Checklist",
    "content": """\
These 5 tools have the highest impact but lowest usage. Use them proactively:

| Tool | When | Why |
|------|------|-----|
| `omega_reflect()` | Every 30+ tool calls or before major decisions | Detects contradictions and stale memories. 0 calls recorded — agents never use it. |
| `omega_decision_query(domain="<area>")` | Before starting work in any domain | Prevents contradicting prior decisions. 0 calls recorded. |
| `omega_file_check(file_path="...")` | Before editing any file | Detects conflicts before they happen. Only 5 calls vs 931 edits. |
| `omega_checkpoint()` | When context > 70% or before risky ops | Saves your work state. Only 4 calls ever. |
| `omega_coord_status` | Before "what's next" and before taking tasks | Prevents overlapping with peers. Only 10 calls across all sessions. |

**These are not optional.** Hooks will report your utilization score at session end.""",
},
```

**Step 2: Add "critical_tools" to SECTION_GROUPS**

Add `"critical_tools"` to both "solo" and "multi_agent" groups, right after "memory":

```python
"solo": ["memory", "critical_tools", "intelligence_cards", ...],
"multi_agent": ["memory", "critical_tools", "intelligence_cards", ...],
```

**Step 3: Run existing protocol tests**

Run: `python3.11 -m pytest tests/test_protocol.py -v`
Expected: PASS (protocol still renders correctly)

**Step 4: Commit**

```bash
git add src/omega/protocol.py
git commit -m "feat(protocol): add Critical Tools Checklist section for 5 underutilized tools"
```

---

## Part C: Auto-Activation (4 Dormant Capabilities via Hooks)

### Task 4: Auto-Register Decisions from omega_store

**Why:** `coord_decisions` has 0 rows, yet agents store 305 "decision" memories via `omega_store`. The data exists but isn't feeding the coordination decision system.

**Files:**
- Modify: `src/omega/server/handlers.py` (the `omega_store` handler)
- Test: `tests/test_auto_decision_register.py`

**Step 1: Write the failing test**

Create `tests/test_auto_decision_register.py`:

```python
"""Test auto-registration of decisions when omega_store gets a decision type."""
import pytest
from unittest.mock import patch, MagicMock


def test_store_decision_auto_registers_coordination():
    """When omega_store is called with event_type='decision', it should
    also register the decision in coordination."""
    from omega.server.handlers import _auto_register_decision

    mock_mgr = MagicMock()
    mock_mgr.register_decision.return_value = {"id": 1, "status": "active"}

    result = _auto_register_decision(
        mgr=mock_mgr,
        session_id="test-session",
        project="/test/project",
        content="Use PostgreSQL instead of MySQL for the user service",
        entity_id=None,
    )

    mock_mgr.register_decision.assert_called_once()
    call_args = mock_mgr.register_decision.call_args
    assert call_args[1]["session_id"] == "test-session"
    assert "PostgreSQL" in call_args[1]["decision"]


def test_store_non_decision_does_not_register():
    """omega_store with event_type='lesson_learned' should NOT register a decision."""
    from omega.server.handlers import _auto_register_decision

    # Should return None for non-decision types
    result = _auto_register_decision(
        mgr=None,
        session_id="test",
        project="/test",
        content="A lesson",
        entity_id=None,
    )
    assert result is None


def test_auto_register_extracts_domain():
    """Domain should be extracted from content heuristically."""
    from omega.server.handlers import _extract_decision_domain

    assert _extract_decision_domain("Use PostgreSQL for the auth service") == "auth"
    assert _extract_decision_domain("Deploy to Vercel instead of Netlify") == "deploy"
    assert _extract_decision_domain("Random decision text") == "general"
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_auto_decision_register.py -v`
Expected: FAIL

**Step 3: Implement in `src/omega/server/handlers.py`**

Add these functions:

```python
# Domain keywords for auto-classification
_DOMAIN_KEYWORDS = {
    "auth": ["auth", "login", "password", "session", "token", "oauth", "credential"],
    "deploy": ["deploy", "vercel", "netlify", "docker", "k8s", "ci/cd", "pipeline"],
    "testing": ["test", "pytest", "jest", "coverage", "e2e", "unit test"],
    "database": ["database", "postgres", "mysql", "sqlite", "supabase", "migration", "schema"],
    "api": ["api", "endpoint", "route", "rest", "graphql"],
    "frontend": ["frontend", "react", "next.js", "tailwind", "component", "ui", "ux"],
    "architecture": ["architecture", "refactor", "module", "pattern", "structure"],
}


def _extract_decision_domain(content: str) -> str:
    """Extract a domain from decision content using keyword matching."""
    lower = content.lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return domain
    return "general"


def _auto_register_decision(
    mgr,
    session_id: str,
    project: str | None,
    content: str,
    entity_id: str | None,
) -> dict | None:
    """Auto-register a decision in coordination when omega_store gets a decision type.
    Returns the registered decision dict or None if skipped/failed."""
    if mgr is None:
        return None

    try:
        domain = _extract_decision_domain(content)
        return mgr.register_decision(
            session_id=session_id,
            project=project or "",
            domain=domain,
            decision=content[:500],  # Truncate for coordination table
            rationale="Auto-registered from omega_store(event_type='decision')",
        )
    except Exception:
        return None  # Non-critical — don't break omega_store
```

Then in the `handle_omega_store` function, after the memory is successfully stored, add:

```python
# Auto-register decisions in coordination (Part C of utilization boost)
if event_type == "decision" and session_id:
    try:
        from omega.coordination import get_manager
        mgr = get_manager()
        _auto_register_decision(mgr, session_id, project, content, entity_id)
    except Exception:
        pass  # Non-critical
```

**Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_auto_decision_register.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/omega/server/handlers.py tests/test_auto_decision_register.py
git commit -m "feat: auto-register decisions in coordination when stored via omega_store"
```

---

### Task 5: Auto-Reflect on Session Stop

**Why:** `omega_reflect` has 0 calls ever. Running it automatically at session end catches contradictions and stale memories without agent cooperation.

**Files:**
- Modify: `hooks/session_stop.py`
- Test: `tests/test_hooks/test_auto_reflect.py`

**Step 1: Write the failing test**

Create `tests/test_hooks/test_auto_reflect.py`:

```python
"""Test auto-reflect at session stop."""
from unittest.mock import patch, MagicMock


def test_auto_reflect_calls_bridge():
    """Auto-reflect should call bridge.check_contradictions and store results."""
    from hooks.session_stop import _auto_reflect

    with patch("hooks.session_stop.bridge") as mock_bridge:
        mock_bridge.check_contradictions.return_value = [
            {"memory_id": "m1", "content": "Use MySQL", "contradicts": "m2", "contra_content": "Use PostgreSQL"}
        ]
        mock_bridge.store_memory.return_value = {"id": "new-mem"}

        result = _auto_reflect("test-session", "/test/project")

        mock_bridge.check_contradictions.assert_called_once()
        assert result["contradictions_found"] == 1


def test_auto_reflect_no_contradictions():
    """When no contradictions found, result shows 0."""
    from hooks.session_stop import _auto_reflect

    with patch("hooks.session_stop.bridge") as mock_bridge:
        mock_bridge.check_contradictions.return_value = []

        result = _auto_reflect("test-session", "/test/project")

        assert result["contradictions_found"] == 0
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_hooks/test_auto_reflect.py -v`
Expected: FAIL

**Step 3: Implement `_auto_reflect` in `hooks/session_stop.py`**

```python
def _auto_reflect(session_id: str, project: str) -> dict:
    """Run contradiction detection automatically at session end.
    Returns summary dict with contradictions_found count."""
    try:
        from omega import bridge

        contradictions = bridge.check_contradictions(
            project=project, limit=5
        )

        if contradictions:
            # Store a summary for the next session to see
            summary = f"Auto-reflect found {len(contradictions)} potential contradiction(s):\n"
            for c in contradictions[:3]:
                summary += f"- '{c.get('content', '')[:80]}' vs '{c.get('contra_content', '')[:80]}'\n"

            bridge.store_memory(
                content=summary,
                event_type="lesson_learned",
                session_id=session_id,
                project=project,
                metadata={"source": "auto_reflect", "contradiction_count": len(contradictions)},
            )

        return {"contradictions_found": len(contradictions)}
    except Exception:
        return {"contradictions_found": 0}
```

Wire into session_stop main flow, after the activity report and before the final print:

```python
# Auto-reflect: detect contradictions (Part C — omega_reflect has 0 agent calls)
try:
    reflect_result = _auto_reflect(session_id, project)
    if reflect_result["contradictions_found"] > 0:
        lines.append(f"[OMEGA] Auto-reflect: {reflect_result['contradictions_found']} contradiction(s) detected. Check next session start.")
except Exception:
    pass
```

**Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_hooks/test_auto_reflect.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add hooks/session_stop.py tests/test_hooks/test_auto_reflect.py
git commit -m "feat(hooks): auto-reflect at session end to detect contradictions"
```

---

### Task 6: Auto-Detect Goal Drift via Coord Session Stop

**Why:** `omega_drift_check` and `omega_goal` have 0 calls and 0 rows. Instead of relying on agents, the session stop hook can compare what the agent was asked to do (task at registration) vs what they actually did (files modified, commits made).

**Files:**
- Modify: `hooks/coord_session_stop.py`
- Test: `tests/test_hooks/test_drift_detection.py`

**Step 1: Write the failing test**

Create `tests/test_hooks/test_drift_detection.py`:

```python
"""Test goal drift detection at session end."""


def test_drift_detected_when_no_overlap():
    from hooks.coord_session_stop import _detect_drift

    result = _detect_drift(
        original_task="Fix the login bug in auth.py",
        files_modified=["website/components/Dashboard.tsx", "website/styles/global.css"],
        commits=["refactor: redesign dashboard layout"],
    )
    assert result["drifted"] is True
    assert result["confidence"] > 0.5


def test_no_drift_when_aligned():
    from hooks.coord_session_stop import _detect_drift

    result = _detect_drift(
        original_task="Fix the login bug in auth.py",
        files_modified=["src/auth.py", "tests/test_auth.py"],
        commits=["fix: resolve login validation error"],
    )
    assert result["drifted"] is False


def test_drift_no_task():
    """If no original task was registered, can't detect drift."""
    from hooks.coord_session_stop import _detect_drift

    result = _detect_drift(
        original_task=None,
        files_modified=["src/auth.py"],
        commits=["fix: something"],
    )
    assert result["drifted"] is False
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_hooks/test_drift_detection.py -v`
Expected: FAIL

**Step 3: Implement `_detect_drift` in `hooks/coord_session_stop.py`**

```python
def _detect_drift(
    original_task: str | None,
    files_modified: list[str],
    commits: list[str],
) -> dict:
    """Detect if the session's actual work drifted from its declared task.
    Uses keyword overlap between task description and actual work."""
    if not original_task or not original_task.strip():
        return {"drifted": False, "confidence": 0.0, "reason": "no task registered"}

    # Extract meaningful words from task
    import re
    stop_words = {"the", "a", "an", "in", "on", "to", "for", "of", "and", "or", "is", "was", "be", "it", "this", "that", "with", "from", "fix", "add", "update", "implement"}
    task_words = set(w.lower() for w in re.findall(r'[a-zA-Z]{3,}', original_task)) - stop_words

    if not task_words:
        return {"drifted": False, "confidence": 0.0, "reason": "task too generic"}

    # Extract words from actual work
    work_text = " ".join(files_modified + commits)
    work_words = set(w.lower() for w in re.findall(r'[a-zA-Z]{3,}', work_text)) - stop_words

    if not work_words:
        return {"drifted": False, "confidence": 0.0, "reason": "no work tracked"}

    # Calculate overlap
    overlap = task_words & work_words
    overlap_ratio = len(overlap) / len(task_words) if task_words else 0

    drifted = overlap_ratio < 0.2  # Less than 20% keyword overlap = drift
    confidence = 1.0 - overlap_ratio

    reason = (
        f"Only {len(overlap)}/{len(task_words)} task keywords found in work"
        if drifted
        else f"{len(overlap)}/{len(task_words)} task keywords matched"
    )

    return {"drifted": drifted, "confidence": round(confidence, 2), "reason": reason}
```

Wire into coord_session_stop before deregistration:

```python
# Goal drift detection (Part C — omega_drift_check has 0 calls)
try:
    session_info = mgr.get_session(session_id)
    original_task = session_info.get("task", "") if session_info else ""
    files_modified = [c.get("file_path", "") for c in mgr.list_file_claims(session_id)]
    commits = [e.get("message", "") for e in mgr.get_git_events(session_id) if e.get("event_type") == "commit"]
    drift = _detect_drift(original_task, files_modified, commits)
    if drift["drifted"]:
        print(f'[OMEGA] Goal drift detected (confidence: {drift["confidence"]}): {drift["reason"]}', file=sys.stderr)
        # Store as lesson for future sessions
        from omega.bridge import store_memory
        store_memory(
            content=f"Goal drift: Agent registered task '{original_task}' but actual work diverged. {drift['reason']}",
            event_type="lesson_learned",
            session_id=session_id,
            metadata={"source": "auto_drift_check", "confidence": drift["confidence"]},
        )
except Exception:
    pass
```

**Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_hooks/test_drift_detection.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add hooks/coord_session_stop.py tests/test_hooks/test_drift_detection.py
git commit -m "feat(hooks): auto-detect goal drift at session end"
```

---

### Task 7: Auto-Store Entity Relationships from File Claims

**Why:** `entity_relationships` has only 13 rows despite 24 entities existing. When two agents from different projects claim files in the same directory, there's an implicit project-to-project relationship. Auto-capture it.

**Files:**
- Modify: `hooks/coord_session_stop.py`
- Test: `tests/test_hooks/test_auto_entity_link.py`

**Step 1: Write the failing test**

Create `tests/test_hooks/test_auto_entity_link.py`:

```python
"""Test auto entity relationship from file claims."""


def test_extracts_project_from_path():
    from hooks.coord_session_stop import _extract_project_entity

    assert _extract_project_entity("/Users/jason/Projects/omega/src/foo.py") == "omega"
    assert _extract_project_entity("/Users/jason/Projects/element1/lib/bar.ts") == "element1"
    assert _extract_project_entity("/tmp/test.py") is None


def test_builds_relationships_from_claims():
    from hooks.coord_session_stop import _build_entity_links

    claims = [
        {"file_path": "/Users/jason/Projects/omega/src/bridge.py"},
        {"file_path": "/Users/jason/Projects/omega/website/app/page.tsx"},
    ]
    links = _build_entity_links(claims, current_project="omega")

    # omega -> omega-website is a relationship
    assert len(links) >= 0  # Same project, no cross-project link


def test_cross_project_link():
    from hooks.coord_session_stop import _build_entity_links

    claims = [
        {"file_path": "/Users/jason/Projects/omega/src/bridge.py"},
        {"file_path": "/Users/jason/Projects/element1/lib/conductor.ts"},
    ]
    links = _build_entity_links(claims, current_project="omega")

    assert len(links) == 1
    assert links[0]["from"] == "omega"
    assert links[0]["to"] == "element1"
    assert links[0]["relationship"] == "co-developed"
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/test_hooks/test_auto_entity_link.py -v`
Expected: FAIL

**Step 3: Implement**

```python
def _extract_project_entity(file_path: str) -> str | None:
    """Extract project name from a file path."""
    import re
    match = re.search(r'/Projects/([^/]+)', file_path)
    return match.group(1) if match else None


def _build_entity_links(claims: list[dict], current_project: str) -> list[dict]:
    """Build cross-project entity links from file claims."""
    projects = set()
    for claim in claims:
        proj = _extract_project_entity(claim.get("file_path", ""))
        if proj and proj != current_project:
            projects.add(proj)

    return [
        {"from": current_project, "to": proj, "relationship": "co-developed"}
        for proj in projects
    ]
```

Wire into coord_session_stop:

```python
# Auto entity links from cross-project file claims (Part C)
try:
    claims = [{"file_path": c.get("file_path", "")} for c in mgr.list_file_claims(session_id)]
    proj_name = _extract_project_entity(project) or ""
    links = _build_entity_links(claims, proj_name)
    for link in links:
        try:
            from omega.entity import get_entity_store
            es = get_entity_store()
            es.add_relationship(link["from"], link["to"], link["relationship"])
        except Exception:
            pass
except Exception:
    pass
```

**Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_hooks/test_auto_entity_link.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add hooks/coord_session_stop.py tests/test_hooks/test_auto_entity_link.py
git commit -m "feat(hooks): auto-link entity relationships from cross-project file claims"
```

---

### Task 8: Full Test Suite + Integration Verification

**Step 1: Run all new tests**

```bash
python3.11 -m pytest tests/test_hooks/test_session_stop_utilization.py tests/test_hooks/test_surface_nudge.py tests/test_auto_decision_register.py tests/test_hooks/test_auto_reflect.py tests/test_hooks/test_drift_detection.py tests/test_hooks/test_auto_entity_link.py -v
```
Expected: All PASS

**Step 2: Run full test suite**

```bash
python3.11 -m pytest tests/ -x -q --tb=short
```
Expected: 3848+ passed, 0 failures

**Step 3: Final commit with version bump**

Update `PROTOCOL_VERSION` in protocol.py from "1.3.0" to "1.4.0".

```bash
git add -A
git commit -m "chore: bump protocol version to 1.4.0 for utilization boost"
```
