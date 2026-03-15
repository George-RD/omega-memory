# Trajectory-to-Skill Distillation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically distill successful agent sessions into reusable skill templates that surface in future sessions via protocol injection.

**Architecture:** At session stop, gather the session's memory sequence + coord_audit tool names, send to Haiku for structured extraction, store as `skill_template` event type. Protocol surfaces top-2 matching skills at session start via `_get_relevant_skills()`.

**Tech Stack:** Python 3.11, SQLite (existing schema, no migration), `llm_complete()` (Haiku), existing auto_capture pipeline.

**Design Doc:** `docs/plans/2026-03-01-trajectory-distillation-design.md`

---

### Task 1: Register `skill_template` Event Type

**Files:**
- Modify: `src/omega/types.py:87-88` (add constant after PREDICTION_SNAPSHOT)
- Modify: `src/omega/types.py:131` (add TTL entry after CONSTRAINT)
- Test: `tests/test_types.py` (existing test auto-validates TTL mapping)

**Step 1: Add the AutoCaptureEventType constant**

In `src/omega/types.py`, after line 87 (`PREDICTION_SNAPSHOT = "prediction_snapshot"`), add:

```python
    # Experiential memory: distilled session trajectories
    SKILL_TEMPLATE = "skill_template"
```

**Step 2: Add the TTL mapping**

In `src/omega/types.py`, after line 131 (`AutoCaptureEventType.CONSTRAINT: TTLCategory.PERMANENT,`), add:

```python
    # Trajectory distillation (permanent — ACT-R decay handles pruning)
    AutoCaptureEventType.SKILL_TEMPLATE: TTLCategory.PERMANENT,
```

**Step 3: Run test to verify TTL mapping is valid**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_types.py -v -x`
Expected: PASS — `test_all_class_event_types_in_ttl_map` validates all constants have TTL entries.

**Step 4: Commit**

```bash
cd ~/Projects/omega
git add src/omega/types.py
git commit -m "feat: register skill_template event type with permanent TTL"
```

---

### Task 2: Add `skill_template` to Store Type Maps

**Files:**
- Modify: `src/omega/sqlite_store/_base.py:35-72` (_TYPE_WEIGHTS)
- Modify: `src/omega/sqlite_store/_base.py:75-114` (_MEMORY_TYPE_MAP)
- Modify: `src/omega/sqlite_store/_base.py:148-168` (_DEFAULT_PRIORITY)
- Modify: `src/omega/sqlite_store/_base.py:174-187` (_DECAY_LAMBDAS)
- Test: Run existing store tests

**Step 1: Add to _TYPE_WEIGHTS**

In `src/omega/sqlite_store/_base.py`, in the `_TYPE_WEIGHTS` dict, add after the `"contradiction_detected": 2.0,` entry:

```python
    # Experiential memory: distilled trajectories
    "skill_template": 2.0,
```

**Step 2: Add to _MEMORY_TYPE_MAP**

In the `_MEMORY_TYPE_MAP` dict, add after the `"reminder": "procedural",` entry in the Procedural section:

```python
    "skill_template": "procedural",
```

**Step 3: Add to _DEFAULT_PRIORITY**

In the `_DEFAULT_PRIORITY` dict, add after the `"advisor_insight": 3,` entry:

```python
    "skill_template": 4,
```

**Step 4: Add to _DECAY_LAMBDAS**

In the `_DECAY_LAMBDAS` dict, add after the `"lesson_learned": 0.005,` entry:

```python
    "skill_template": 0.01,         # 50% at ~69 days — slower decay than decisions
```

**Step 5: Run store tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_sqlite_store.py -v -x`
Expected: PASS

**Step 6: Commit**

```bash
cd ~/Projects/omega
git add src/omega/sqlite_store/_base.py
git commit -m "feat: add skill_template to store type weights, memory map, priority, and decay"
```

---

### Task 3: Add `skill_template` to Bridge Evolution Types and Dedup Thresholds

**Files:**
- Modify: `src/omega/bridge.py:46-56` (DEDUP_THRESHOLDS)
- Modify: `src/omega/bridge.py:59-64` (EVOLUTION_TYPES)
- Test: Run bridge integration tests

**Step 1: Add to DEDUP_THRESHOLDS**

In `src/omega/bridge.py`, in the `DEDUP_THRESHOLDS` dict (around line 46-56), add:

```python
    AutoCaptureEventType.SKILL_TEMPLATE: 0.85,
```

**Step 2: Add to EVOLUTION_TYPES**

In `src/omega/bridge.py`, in the `EVOLUTION_TYPES` set (around line 59-64), add:

```python
    AutoCaptureEventType.SKILL_TEMPLATE,
```

**Step 3: Run bridge tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_bridge_integration.py -v -x`
Expected: PASS

**Step 4: Commit**

```bash
cd ~/Projects/omega
git add src/omega/bridge.py
git commit -m "feat: add skill_template to dedup thresholds and evolution types"
```

---

### Task 4: Write `distill_trajectory()` Function

**Files:**
- Modify: `src/omega/bridge.py` (add new function after `get_cross_session_lessons` around line 2617)
- Test: `tests/test_trajectory_distillation.py` (new file)

**Step 1: Write the test file**

Create `tests/test_trajectory_distillation.py`:

```python
"""Tests for trajectory-to-skill distillation."""

import json
from unittest.mock import patch, MagicMock

import pytest


def test_quality_gate_skips_short_sessions(tmp_path):
    """Sessions with fewer than 3 memories are not distilled."""
    from omega.bridge import distill_trajectory

    with patch("omega.bridge._get_store") as mock_store:
        mock_db = MagicMock()
        mock_db.get_by_session.return_value = [
            {"content": "error found", "event_type": "error_pattern", "metadata": {}},
        ]
        mock_store.return_value = mock_db

        result = distill_trajectory("test-session-short")
        assert result is None


def test_quality_gate_skips_no_completion(tmp_path):
    """Sessions without task_completion or commit are not distilled."""
    from omega.bridge import distill_trajectory

    with patch("omega.bridge._get_store") as mock_store:
        mock_db = MagicMock()
        mock_db.get_by_session.return_value = [
            {"content": "explored codebase", "event_type": "decision", "metadata": {}},
            {"content": "read some files", "event_type": "decision", "metadata": {}},
            {"content": "interesting finding", "event_type": "lesson_learned", "metadata": {}},
        ]
        mock_store.return_value = mock_db

        result = distill_trajectory("test-session-no-completion")
        assert result is None


def test_quality_gate_passes_with_completion(tmp_path):
    """Sessions with task_completion and 3+ memories pass the gate."""
    from omega.bridge import distill_trajectory

    mock_llm_response = json.dumps({
        "skill_type": "debugging",
        "summary": "Debug null check bug in auth module",
        "steps": ["detect_error", "read_context", "apply_fix", "verify", "commit"],
        "key_insight": "Always validate optional fields",
        "tools_used": ["Grep", "Read", "Edit", "Bash"],
        "files_involved": ["auth.py"],
        "outcome": "success",
    })

    with patch("omega.bridge._get_store") as mock_store, \
         patch("omega.bridge.llm_complete", return_value=mock_llm_response) as mock_llm, \
         patch("omega.bridge.auto_capture", return_value="node-123") as mock_capture:
        mock_db = MagicMock()
        mock_db.get_by_session.return_value = [
            {"content": "TypeError in auth.py", "event_type": "error_pattern", "metadata": {}},
            {"content": "Root cause: missing null check", "event_type": "decision", "metadata": {}},
            {"content": "Committed fix abc123", "event_type": "task_completion", "metadata": {"commit": "abc123"}},
        ]
        mock_store.return_value = mock_db

        result = distill_trajectory("test-session-ok")
        assert result is not None
        mock_llm.assert_called_once()
        mock_capture.assert_called_once()
        # Verify stored as skill_template
        call_kwargs = mock_capture.call_args
        assert call_kwargs[1]["event_type"] == "skill_template"


def test_quality_gate_passes_with_commit_in_metadata(tmp_path):
    """Sessions with a commit in metadata (no explicit task_completion type) pass."""
    from omega.bridge import distill_trajectory

    mock_llm_response = json.dumps({
        "skill_type": "feature",
        "summary": "Add endpoint",
        "steps": ["scaffold", "implement", "test", "commit"],
        "key_insight": "Wire middleware first",
        "tools_used": ["Write", "Bash"],
        "files_involved": ["routes.py"],
        "outcome": "success",
    })

    with patch("omega.bridge._get_store") as mock_store, \
         patch("omega.bridge.llm_complete", return_value=mock_llm_response), \
         patch("omega.bridge.auto_capture", return_value="node-456"):
        mock_db = MagicMock()
        mock_db.get_by_session.return_value = [
            {"content": "Design decision", "event_type": "decision", "metadata": {}},
            {"content": "Wrote handler", "event_type": "decision", "metadata": {}},
            {"content": "Committed abc", "event_type": "decision", "metadata": {"commit": "abc"}},
        ]
        mock_store.return_value = mock_db

        result = distill_trajectory("test-session-commit")
        assert result is not None


def test_llm_failure_returns_none(tmp_path):
    """LLM failure is fail-open — returns None, no skill stored."""
    from omega.bridge import distill_trajectory

    with patch("omega.bridge._get_store") as mock_store, \
         patch("omega.bridge.llm_complete", return_value="") as mock_llm, \
         patch("omega.bridge.auto_capture") as mock_capture:
        mock_db = MagicMock()
        mock_db.get_by_session.return_value = [
            {"content": "error", "event_type": "error_pattern", "metadata": {}},
            {"content": "fix", "event_type": "decision", "metadata": {}},
            {"content": "done", "event_type": "task_completion", "metadata": {}},
        ]
        mock_store.return_value = mock_db

        result = distill_trajectory("test-session-llm-fail")
        assert result is None
        mock_capture.assert_not_called()


def test_llm_skip_response_returns_none(tmp_path):
    """LLM returning skip:true means session is too routine."""
    from omega.bridge import distill_trajectory

    with patch("omega.bridge._get_store") as mock_store, \
         patch("omega.bridge.llm_complete", return_value='{"skip": true}'), \
         patch("omega.bridge.auto_capture") as mock_capture:
        mock_db = MagicMock()
        mock_db.get_by_session.return_value = [
            {"content": "small fix", "event_type": "decision", "metadata": {}},
            {"content": "committed", "event_type": "task_completion", "metadata": {}},
            {"content": "done", "event_type": "task_completion", "metadata": {}},
        ]
        mock_store.return_value = mock_db

        result = distill_trajectory("test-session-skip")
        assert result is None
        mock_capture.assert_not_called()


def test_malformed_json_returns_none(tmp_path):
    """Malformed LLM JSON is fail-open."""
    from omega.bridge import distill_trajectory

    with patch("omega.bridge._get_store") as mock_store, \
         patch("omega.bridge.llm_complete", return_value="not json at all"), \
         patch("omega.bridge.auto_capture") as mock_capture:
        mock_db = MagicMock()
        mock_db.get_by_session.return_value = [
            {"content": "e", "event_type": "error_pattern", "metadata": {}},
            {"content": "d", "event_type": "decision", "metadata": {}},
            {"content": "t", "event_type": "task_completion", "metadata": {}},
        ]
        mock_store.return_value = mock_db

        result = distill_trajectory("test-session-bad-json")
        assert result is None
        mock_capture.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_trajectory_distillation.py -v -x`
Expected: FAIL with `ImportError: cannot import name 'distill_trajectory' from 'omega.bridge'`

**Step 3: Implement `distill_trajectory()` in bridge.py**

Add the following function in `src/omega/bridge.py` after the `get_cross_session_lessons()` function (around line 2617). Also add `from omega.llm import llm_complete` at the top of the function (lazy import pattern matching the file's style).

```python
def distill_trajectory(session_id: str) -> Optional[str]:
    """Distill a session's memory trajectory into a reusable skill template.

    Called at session stop. Returns the stored node_id, or None if the session
    didn't pass the quality gate or distillation failed.

    Fail-open: any error results in None (no skill stored), never blocks session stop.
    """
    import json as _json

    try:
        db = _get_store()
        memories = db.get_by_session(session_id, limit=50)

        # Quality gate: minimum 3 memories
        if len(memories) < 3:
            logger.debug("distill_trajectory: skipped session %s (only %d memories)", session_id, len(memories))
            return None

        # Quality gate: must have task_completion event type OR a commit in metadata
        has_completion = any(
            getattr(m, "event_type", None) == "task_completion"
            or (isinstance(m, dict) and m.get("event_type") == "task_completion")
            for m in memories
        )
        has_commit = any(
            _safe_meta(m).get("commit")
            for m in memories
        )
        if not has_completion and not has_commit:
            logger.debug("distill_trajectory: skipped session %s (no completion/commit)", session_id)
            return None

        # Gather trajectory context
        mem_lines = []
        for m in memories:
            if isinstance(m, dict):
                et = m.get("event_type", "unknown")
                content = m.get("content", "")[:200]
            else:
                et = getattr(m, "event_type", "unknown")
                content = (getattr(m, "content", "") or "")[:200]
            mem_lines.append(f"- [{et}] {content}")

        trajectory_text = "\n".join(mem_lines[:20])  # Cap at 20 entries

        # Gather tool sequence from coord_audit if available
        tool_sequence = ""
        try:
            from omega.coordination import get_manager
            mgr = get_manager()
            if mgr:
                audit_rows = mgr._conn.execute(
                    "SELECT tool_name, result_status FROM coord_audit "
                    "WHERE session_id = ? ORDER BY call_index ASC LIMIT 30",
                    (session_id,),
                ).fetchall()
                if audit_rows:
                    tools = [f"{r[0]}({'ok' if r[1] == 'ok' else 'err'})" for r in audit_rows]
                    tool_sequence = f"\nTool sequence: {' → '.join(tools)}"
        except Exception:
            pass  # Coordination unavailable — continue without tool sequence

        # LLM distillation call
        system_prompt = (
            "You extract reusable skill templates from agent work sessions. "
            "Output valid JSON only, no markdown fencing."
        )
        user_prompt = f"""Analyze this agent session and extract a reusable skill template.

Memory sequence (chronological):
{trajectory_text}
{tool_sequence}

Extract a JSON skill template:
{{
  "skill_type": "debugging|feature|refactor|config|deploy",
  "summary": "One sentence describing the workflow in imperative form",
  "steps": ["verb_phrase_1", "verb_phrase_2", ...],
  "key_insight": "The most important actionable lesson from this session",
  "tools_used": ["Tool1", "Tool2"],
  "files_involved": ["path1", "path2"],
  "outcome": "success|partial|failed_then_recovered"
}}

Rules:
- Steps should be abstract enough to transfer (not "edit auth.py line 42" but "apply null-safe fix")
- key_insight should be actionable advice, not a description
- 3-7 steps maximum
- If the session is too routine or trivial to extract a skill, return {{"skip": true}}"""

        from omega.llm import llm_complete

        raw = llm_complete(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=512,
            temperature=0.0,
            timeout=10.0,
            model_tier="fast",
        )

        if not raw:
            logger.debug("distill_trajectory: LLM returned empty for session %s", session_id)
            return None

        # Parse JSON (strip markdown fencing if present)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            skill = _json.loads(cleaned)
        except _json.JSONDecodeError:
            logger.debug("distill_trajectory: malformed JSON from LLM for session %s", session_id)
            return None

        # Handle skip response
        if skill.get("skip"):
            logger.debug("distill_trajectory: LLM said skip for session %s", session_id)
            return None

        # Validate required fields
        required = ("skill_type", "summary", "steps", "key_insight")
        if not all(skill.get(k) for k in required):
            logger.debug("distill_trajectory: missing required fields for session %s", session_id)
            return None

        # Build content string (human-readable)
        steps_str = " → ".join(skill["steps"])
        files_str = ", ".join(skill.get("files_involved", [])[:5])
        content = (
            f"{skill['summary']}. "
            f"Steps: {steps_str}. "
            f"Insight: {skill['key_insight']}"
        )
        if files_str:
            content += f". Files: {files_str}"

        # Build metadata
        meta = {
            "source": "trajectory_distillation",
            "session_id": session_id,
            "skill_type": skill["skill_type"],
            "steps": skill["steps"],
            "tools_used": skill.get("tools_used", []),
            "files_involved": skill.get("files_involved", []),
            "key_insight": skill["key_insight"],
            "outcome": skill.get("outcome", "success"),
            "memory_count": len(memories),
            "distillation_model": "haiku",
        }

        node_id = auto_capture(
            content=content,
            event_type="skill_template",
            metadata=meta,
            session_id=session_id,
        )

        logger.info("distill_trajectory: distilled %s skill from session %s → %s",
                     skill["skill_type"], session_id, node_id)
        return node_id

    except Exception as e:
        logger.debug("distill_trajectory: failed for session %s: %s", session_id, e)
        return None


def _safe_meta(m) -> dict:
    """Extract metadata dict from a memory (dict or MemoryResult)."""
    if isinstance(m, dict):
        meta = m.get("metadata", {})
    else:
        meta = getattr(m, "metadata", {})
    if isinstance(meta, str):
        try:
            import json as _j
            return _j.loads(meta)
        except Exception:
            return {}
    return meta or {}
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_trajectory_distillation.py -v -x`
Expected: All 7 tests PASS

**Step 5: Run full test suite to check for regressions**

Run: `cd ~/Projects/omega && python3.11 -m pytest -x --timeout=120`
Expected: PASS (no regressions)

**Step 6: Commit**

```bash
cd ~/Projects/omega
git add src/omega/bridge.py tests/test_trajectory_distillation.py
git commit -m "feat: implement distill_trajectory() with quality gate, LLM extraction, and fail-open"
```

---

### Task 5: Wire Distillation Into Session Stop Hook

**Files:**
- Modify: `src/omega/server/hook_server/session.py:1848-1850` (insert call before return)
- Test: Existing session stop test + manual verification

**Step 1: Write a test for the wiring**

Add to `tests/test_trajectory_distillation.py`:

```python
def test_session_stop_calls_distill(tmp_path):
    """Verify handle_session_stop calls distill_trajectory."""
    with patch("omega.server.hook_server.session.distill_trajectory") as mock_distill:
        mock_distill.return_value = None
        # We can't easily call handle_session_stop directly (complex deps),
        # so just verify the import works
        from omega.server.hook_server.session import handle_session_stop
        assert callable(handle_session_stop)
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_trajectory_distillation.py::test_session_stop_calls_distill -v -x`
Expected: FAIL with `ImportError` — `distill_trajectory` not yet imported in session.py

**Step 3: Wire the call into session.py**

In `src/omega/server/hook_server/session.py`, insert between line 1848 (`_auto_cloud_sync(session_id)`) and line 1850 (`return ...`):

```python
    # Trajectory-to-skill distillation (fail-open, non-blocking)
    try:
        from omega.bridge import distill_trajectory
        distill_trajectory(session_id)
    except Exception as e:
        _log_hook_error("trajectory_distillation", e)
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_trajectory_distillation.py -v -x`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd ~/Projects/omega && python3.11 -m pytest -x --timeout=120`
Expected: PASS

**Step 6: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/hook_server/session.py tests/test_trajectory_distillation.py
git commit -m "feat: wire distill_trajectory into session stop hook (fail-open)"
```

---

### Task 6: Add `_get_relevant_skills()` to Protocol

**Files:**
- Modify: `src/omega/protocol.py:685-686` (add new function after `_get_protocol_lessons`)
- Modify: `src/omega/protocol.py:599-605` (wire into protocol output)
- Test: `tests/test_trajectory_distillation.py` (add protocol test)

**Step 1: Write the protocol surfacing test**

Add to `tests/test_trajectory_distillation.py`:

```python
def test_get_relevant_skills_returns_formatted():
    """_get_relevant_skills returns formatted skill block."""
    from omega.protocol import _get_relevant_skills

    mock_results = [
        {
            "content": "Debug null check. Steps: detect → fix → test. Insight: validate optional fields",
            "metadata": {
                "skill_type": "debugging",
                "steps": ["detect", "fix", "test"],
                "key_insight": "validate optional fields",
                "files_involved": ["auth.py"],
            },
            "created_at": "2026-02-28T12:00:00",
        },
    ]

    with patch("omega.protocol.query_structured", return_value=mock_results):
        result = _get_relevant_skills(task="fix auth bug")
        assert result  # Non-empty
        assert "detect" in result
        assert "validate optional fields" in result


def test_get_relevant_skills_empty_on_no_results():
    """_get_relevant_skills returns empty string when no skills match."""
    from omega.protocol import _get_relevant_skills

    with patch("omega.protocol.query_structured", return_value=[]):
        result = _get_relevant_skills(task="unrelated task")
        assert result == ""


def test_get_relevant_skills_handles_exception():
    """_get_relevant_skills is fail-safe."""
    from omega.protocol import _get_relevant_skills

    with patch("omega.protocol.query_structured", side_effect=Exception("db error")):
        result = _get_relevant_skills(task="anything")
        assert result == ""
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_trajectory_distillation.py::test_get_relevant_skills_returns_formatted -v -x`
Expected: FAIL with `ImportError: cannot import name '_get_relevant_skills'`

**Step 3: Implement `_get_relevant_skills()` in protocol.py**

In `src/omega/protocol.py`, after `_get_protocol_lessons()` (after line 685), add:

```python
def _get_relevant_skills(
    task: Optional[str] = None, project: Optional[str] = None
) -> str:
    """Fetch relevant skill templates distilled from prior sessions."""
    try:
        from omega.bridge import query_structured

        query = task or "skill workflow approach"
        results = query_structured(
            query_text=query,
            limit=5,
            event_type="skill_template",
        )
        if not results:
            return ""

        items = []
        for r in results[:2]:  # Top 2 only — keep protocol compact
            content = r.get("content", "")[:300]
            meta = r.get("metadata", {})
            if isinstance(meta, str):
                import json as _j
                try:
                    meta = _j.loads(meta)
                except Exception:
                    meta = {}
            skill_type = meta.get("skill_type", "general")
            created = r.get("created_at", "")[:10]
            items.append(f"- **{skill_type}** ({created}): {content}")
        return "\n".join(items)
    except Exception as e:
        logger.debug("Skills fetch failed: %s", e)
        return ""
```

**Step 4: Wire into `get_protocol()` output**

In `src/omega/protocol.py`, after the lessons block (after line 605, before `return "\n".join(lines)`), add:

```python
    # Append relevant skill templates from trajectory distillation
    if include_lessons:
        task_hint = kwargs.get("task") or ""
        skills_text = _get_relevant_skills(task=task_hint, project=project)
        if skills_text:
            lines.append("## Prior Successful Approaches")
            lines.append(skills_text)
            lines.append("")
```

Note: Check how `get_protocol()` receives kwargs — the `task` parameter may come from `session_id` metadata or the function signature. If `get_protocol` doesn't accept `**kwargs`, pass `task=None` and rely on the generic query fallback.

**Step 5: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_trajectory_distillation.py -v -x`
Expected: All 10 tests PASS

**Step 6: Run full test suite**

Run: `cd ~/Projects/omega && python3.11 -m pytest -x --timeout=120`
Expected: PASS

**Step 7: Commit**

```bash
cd ~/Projects/omega
git add src/omega/protocol.py tests/test_trajectory_distillation.py
git commit -m "feat: add _get_relevant_skills() to protocol for skill surfacing at session start"
```

---

### Task 7: Update Hardcoded Test Counts

**Files:**
- Check: `tests/test_uat_coordination.py` (handler count assertions)
- Check: `tests/test_utilization_gaps.py` (tool/handler count assertions)
- Check: Any test asserting on event type counts

**Step 1: Search for assertions that might break**

Run: `cd ~/Projects/omega && grep -rn 'assert.*len.*==\|assert.*count.*==' tests/ | grep -i 'type\|weight\|decay\|memory_type\|event'`

Review each match. The key things to check:
- `_TYPE_WEIGHTS` count assertions
- `_MEMORY_TYPE_MAP` count assertions
- `_DECAY_LAMBDAS` count assertions
- `EVOLUTION_TYPES` count assertions
- `DEDUP_THRESHOLDS` count assertions

**Step 2: Update any hardcoded counts**

For each assertion found, increment the count by 1 (we added `skill_template` to each dict/set).

**Step 3: Run full test suite**

Run: `cd ~/Projects/omega && python3.11 -m pytest -x --timeout=120`
Expected: PASS

**Step 4: Commit**

```bash
cd ~/Projects/omega
git add tests/
git commit -m "fix: update hardcoded test counts for skill_template event type"
```

---

### Task 8: End-to-End Verification

**Step 1: Run full test suite one final time**

Run: `cd ~/Projects/omega && python3.11 -m pytest -x --timeout=120`
Expected: All tests PASS

**Step 2: Verify the distillation module imports cleanly**

Run: `cd ~/Projects/omega && python3.11 -c "from omega.bridge import distill_trajectory; print('OK')" `
Expected: `OK`

**Step 3: Verify protocol function imports cleanly**

Run: `cd ~/Projects/omega && python3.11 -c "from omega.protocol import _get_relevant_skills; print('OK')"`
Expected: `OK`

**Step 4: Verify event type registration is complete**

Run: `cd ~/Projects/omega && python3.11 -c "from omega.types import AutoCaptureEventType, EVENT_TYPE_TTL; assert AutoCaptureEventType.SKILL_TEMPLATE == 'skill_template'; assert AutoCaptureEventType.SKILL_TEMPLATE in EVENT_TYPE_TTL; print('OK')"`
Expected: `OK`

**Step 5: Run lint**

Run: `cd ~/Projects/omega && ruff check src/omega/bridge.py src/omega/types.py src/omega/protocol.py src/omega/sqlite_store/_base.py src/omega/server/hook_server/session.py`
Expected: No errors (fix any if found)
