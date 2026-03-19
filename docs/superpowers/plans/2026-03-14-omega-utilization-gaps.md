# OMEGA Utilization Gap Fixes — Implementation Plan (v2)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between OMEGA's 25 tools and the ~40% agents actively use, by adding 3 automated feedback loops (retrieval quality, procedural learning, mid-session context push), enriching auto-checkpoints, adding protocol guidance, and reinforcing via CLAUDE.md.

**Architecture:** Hybrid — hooks enforce mechanical tasks (feedback loops at session stop, context push at edit time), protocol teaches judgment calls (graph linking, cross-model consultation). Two hook files modified (`session.py`, `insights.py`), one protocol file, one config file.

**Tech Stack:** Python 3.11, SQLite (omega store + coord_audit), OMEGA hook server, OMEGA protocol system.

**Spec:** `docs/superpowers/specs/2026-03-14-omega-utilization-gaps-design.md`

**Already implemented** (verified in code, NOT in this plan):
- 1.1 auto-checkpoint trigger logic (session.py lines 1780-1827)
- 1.2 stale maintenance pipeline stage (maintenance.py lines 557-588, 659-665)
- 1.2 stale welcome surfacing (session.py lines 705-727)
- 1.3 habit confirmation prompt with IDs (session.py lines 1038-1068)
- 1.4 advisor_insight in compact pipeline (maintenance.py line 472)
- 1.5 dead memory surfacing (session.py lines 670-703)
- 2.1 graph linking in protocol memory section (protocol.py line 44)
- 2.2 store-result in consultation section (protocol.py line 416)
- 2.3 reflect(evolution) in HIGH-risk gate (protocol.py line 97)
- 2.4 profile loading in memory section (protocol.py line 31)

---

## Chunk 1: Enrich Auto-Checkpoint Content

### Task 1: Add files_touched and next_steps to auto-checkpoint

**Files:**
- Modify: `src/omega/server/hook_server/session.py:1807-1827`

- [ ] **Step 1: Write the failing test**

Create `tests/server/hook_server/test_session_checkpoint_enrichment.py`:

```python
"""Tests for enriched auto-checkpoint content at session stop."""
import re


def test_checkpoint_includes_files_touched(tmp_path):
    """Auto-checkpoint should include files from coord_audit Edit/Write entries."""
    from omega.server.hook_server.session import _enrich_checkpoint_content

    # Simulate coord_audit rows with Edit/Write tool calls
    audit_rows = [
        {"tool_name": "Edit", "result_summary": "Updated /tmp/foo.py successfully", "call_index": 1, "result_status": "ok"},
        {"tool_name": "Write", "result_summary": "Created /tmp/bar.py successfully", "call_index": 2, "result_status": "ok"},
        {"tool_name": "Bash", "result_summary": "pytest passed", "call_index": 3, "result_status": "ok"},
    ]

    result = _enrich_checkpoint_content("Base checkpoint", audit_rows, handoff_content=None)
    assert "files_touched" in result.lower() or "foo.py" in result or "bar.py" in result


def test_checkpoint_includes_next_steps_from_handoff(tmp_path):
    """Auto-checkpoint should include next_steps from handoff content."""
    from omega.server.hook_server.session import _enrich_checkpoint_content

    handoff = "## Open issues\n- Fix auth bug in login flow\n- Update tests for new API"

    result = _enrich_checkpoint_content("Base checkpoint", [], handoff_content=handoff)
    assert "next_steps" in result.lower() or "auth bug" in result.lower()


def test_checkpoint_graceful_with_no_enrichment(tmp_path):
    """Checkpoint should return base content when no enrichment data available."""
    from omega.server.hook_server.session import _enrich_checkpoint_content

    result = _enrich_checkpoint_content("Base checkpoint", [], handoff_content=None)
    assert result == "Base checkpoint"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/test_session_checkpoint_enrichment.py -v`
Expected: FAIL — `_enrich_checkpoint_content` doesn't exist

- [ ] **Step 3: Implement _enrich_checkpoint_content helper**

In `src/omega/server/hook_server/session.py`, add before `handle_session_stop()` (around line 1420):

```python
def _enrich_checkpoint_content(
    base_content: str,
    audit_rows: list[dict],
    handoff_content: str | None,
) -> str:
    """Enrich checkpoint content with files touched and next steps."""
    parts = [base_content]

    # Extract files from Edit/Write audit entries
    edit_tools = [r for r in audit_rows if r.get("tool_name") in ("Edit", "Write")]
    if edit_tools:
        # Extract file paths from result_summary (best-effort)
        import re as _re_enrich
        file_paths: list[str] = []
        for row in edit_tools:
            summary = row.get("result_summary", "") or ""
            # Match common path patterns in result summaries
            matches = _re_enrich.findall(r"(/[^\s,]+\.\w+)", summary)
            file_paths.extend(matches)
        if file_paths:
            unique_files = list(dict.fromkeys(file_paths))[:10]  # Dedup, max 10
            parts.append(f"files_touched={', '.join(unique_files)}")

    # Extract next steps from handoff content
    if handoff_content:
        # Look for "Open issues" or "Blocked" sections
        for section_header in ("## Open issues", "## Blocked", "## Next"):
            idx = handoff_content.find(section_header)
            if idx >= 0:
                section = handoff_content[idx:idx + 200].strip()
                # Take first 2 items
                lines = [l.strip() for l in section.split("\n")[1:3] if l.strip().startswith("- ")]
                if lines:
                    parts.append(f"next_steps: {'; '.join(l.lstrip('- ') for l in lines)}")
                break

    return " | ".join(parts) if len(parts) > 1 else base_content
```

- [ ] **Step 4: Wire enrichment into auto-checkpoint block**

In `src/omega/server/hook_server/session.py`, replace lines 1807-1827. The existing checkpoint block builds `checkpoint_content` as a string. Replace the content-building with:

```python
    if _should_checkpoint:
        try:
            from omega.bridge import auto_capture as _ac_checkpoint

            checkpoint_content = f"Auto-checkpoint: {summary[:200]}"
            if git_files_summary:
                checkpoint_content += f" | {git_files_summary}"
            checkpoint_content += f" | tool_calls={_tool_call_count}, stores={captured}"

            # Enrich with files_touched and next_steps
            _enrich_audit: list[dict] = []
            _enrich_handoff: str | None = None
            try:
                from omega.coordination import get_manager as _gm_enrich
                _enrich_mgr = _gm_enrich()
                _enrich_audit = _enrich_mgr.query_audit(session_id=session_id, limit=200)
            except Exception:
                pass
            try:
                from omega.bridge import _get_store as _gs_enrich
                _enrich_store = _gs_enrich()
                _handoff_row = _enrich_store._conn.execute(
                    "SELECT content FROM memories WHERE event_type = 'handoff' "
                    "AND session_id = ? ORDER BY created_at DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
                if _handoff_row:
                    _enrich_handoff = _handoff_row[0]
            except Exception:
                pass
            checkpoint_content = _enrich_checkpoint_content(
                checkpoint_content, _enrich_audit, _enrich_handoff
            )

            _ac_checkpoint(
                content=checkpoint_content,
                event_type="checkpoint",
                metadata={"source": "session_stop_auto_checkpoint", "project": project,
                           "tool_calls": _tool_call_count, "stores": captured},
                session_id=session_id,
                project=project,
                entity_id=entity_id,
                agent_type=_client,
                ttl_override=604800,  # 7 days
            )
        except Exception as e:
            _log_hook_error("session_stop_auto_checkpoint", e)
```

- [ ] **Step 5: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/test_session_checkpoint_enrichment.py -v`
Expected: PASS

- [ ] **Step 6: Run full session hook tests for regressions**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/ -v --timeout=60`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/hook_server/session.py tests/server/hook_server/test_session_checkpoint_enrichment.py
git commit -m "feat(hooks): enrich auto-checkpoint with files_touched and next_steps

Extracts file paths from coord_audit Edit/Write entries and pulls
next_steps from handoff content when available."
```

---

## Chunk 2: Retrieval Quality Feedback Loop

### Task 2: Implement _auto_feedback_on_retrieval

**Files:**
- Modify: `src/omega/server/hook_server/session.py` (add function + wire into handle_session_stop after auto-checkpoint ~line 1828)
- Test: `tests/server/hook_server/test_retrieval_feedback.py`

- [ ] **Step 1: Write the failing test**

Create `tests/server/hook_server/test_retrieval_feedback.py`:

```python
"""Tests for retrieval quality feedback at session stop."""
import re


def test_extracts_memory_ids_from_result_summary():
    """Should extract mem-xxxxxxxxxxxx IDs from result_summary."""
    from omega.server.hook_server.session import _extract_retrieved_ids

    summary = "## 1. [decision] `mem-5d5ef8d37340` (str: 1.00)\nSome content\n## 2. [lesson] `mem-abc123def456`"
    ids = _extract_retrieved_ids(summary)
    assert "mem-5d5ef8d37340" in ids
    assert "mem-abc123def456" in ids


def test_no_ids_from_empty_summary():
    """Should return empty set from None or empty summary."""
    from omega.server.hook_server.session import _extract_retrieved_ids

    assert _extract_retrieved_ids(None) == set()
    assert _extract_retrieved_ids("") == set()


def test_feedback_records_helpful_for_reused_ids():
    """Should call record_feedback('helpful') for IDs that reappear later."""
    from omega.server.hook_server.session import _compute_retrieval_feedback

    # omega_query at call_index 5 returned mem-aaa, mem-bbb
    # Later tool at call_index 10 references mem-aaa in its result_summary
    audit_rows = [
        {"tool_name": "omega_query", "result_summary": "## 1. `mem-aaa111222333` content\n## 2. `mem-bbb444555666`", "call_index": 5, "result_status": "ok"},
        {"tool_name": "Bash", "result_summary": "using mem-aaa111222333 in output", "call_index": 10, "result_status": "ok"},
        {"tool_name": "Edit", "result_summary": "edited file successfully", "call_index": 15, "result_status": "ok"},
    ]

    feedback = _compute_retrieval_feedback(audit_rows)
    assert ("mem-aaa111222333", "helpful", "retrieval_used") in feedback
    # mem-bbb should NOT get negative feedback (positive-only)
    assert not any(f[0] == "mem-bbb444555666" for f in feedback)


def test_no_feedback_without_omega_query():
    """Should return empty list when no omega_query calls in session."""
    from omega.server.hook_server.session import _compute_retrieval_feedback

    audit_rows = [
        {"tool_name": "Edit", "result_summary": "edited foo.py", "call_index": 1, "result_status": "ok"},
        {"tool_name": "Bash", "result_summary": "pytest passed", "call_index": 2, "result_status": "ok"},
    ]

    feedback = _compute_retrieval_feedback(audit_rows)
    assert feedback == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/test_retrieval_feedback.py -v`
Expected: FAIL — functions don't exist

- [ ] **Step 3: Implement retrieval feedback functions**

In `src/omega/server/hook_server/session.py`, add before `handle_session_stop()`:

```python
_MEM_ID_PATTERN = re.compile(r"mem-[a-f0-9]{12}")


def _extract_retrieved_ids(result_summary: str | None) -> set[str]:
    """Extract memory IDs from a result_summary string."""
    if not result_summary:
        return set()
    return set(_MEM_ID_PATTERN.findall(result_summary))


def _compute_retrieval_feedback(
    audit_rows: list[dict],
) -> list[tuple[str, str, str]]:
    """Compute positive-only retrieval feedback from audit trail.

    Returns list of (memory_id, "helpful", "retrieval_used") tuples.
    audit_rows must be sorted by call_index ASC.
    """
    # Find all omega_query calls and their retrieved IDs
    query_results: list[tuple[int, set[str]]] = []
    for row in audit_rows:
        tool = row.get("tool_name", "")
        if "omega_query" not in tool:
            continue
        ids = _extract_retrieved_ids(row.get("result_summary"))
        if ids:
            query_results.append((row.get("call_index", 0), ids))

    if not query_results:
        return []

    # For each query, check if any returned IDs appear in subsequent tool calls
    feedback: list[tuple[str, str, str]] = []
    seen_helpful: set[str] = set()

    for query_idx, retrieved_ids in query_results:
        for row in audit_rows:
            if row.get("call_index", 0) <= query_idx:
                continue
            later_ids = _extract_retrieved_ids(row.get("result_summary"))
            for mid in retrieved_ids & later_ids:
                if mid not in seen_helpful:
                    feedback.append((mid, "helpful", "retrieval_used"))
                    seen_helpful.add(mid)

    return feedback


def _auto_feedback_on_retrieval(session_id: str) -> None:
    """Auto-record positive feedback for memories reused after retrieval."""
    if not session_id:
        return
    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        # query_audit returns ORDER BY created_at DESC — re-sort by call_index ASC
        raw_rows = mgr.query_audit(session_id=session_id, limit=500)
        audit_rows = sorted(raw_rows, key=lambda r: r.get("call_index", 0))

        feedback = _compute_retrieval_feedback(audit_rows)
        if not feedback:
            return

        from omega.bridge import record_feedback

        for memory_id, rating, reason in feedback:
            try:
                record_feedback(memory_id, rating, reason)
            except Exception:
                pass  # Individual feedback failures are non-critical

        logger.info(f"Retrieval feedback: {len(feedback)} helpful signals recorded")
    except Exception as e:
        _log_hook_error("auto_feedback_retrieval", e)
```

Also add `import re` at the top of `session.py` if not already present.

- [ ] **Step 4: Wire into handle_session_stop**

In `src/omega/server/hook_server/session.py`, add after the auto-checkpoint block (after line ~1828, before the Intelligence Card format block):

```python
    # --- Retrieval quality feedback ---
    _auto_feedback_on_retrieval(session_id)
```

- [ ] **Step 5: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/test_retrieval_feedback.py -v`
Expected: PASS

- [ ] **Step 6: Run full session hook tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/ -v --timeout=60`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/hook_server/session.py tests/server/hook_server/test_retrieval_feedback.py
git commit -m "feat(hooks): add retrieval quality feedback loop at session stop

Scans coord_audit for omega_query calls, extracts returned memory IDs,
checks if they reappear in subsequent tool calls. Records 'helpful'
feedback for reused memories. Positive-only (no negative signal)."
```

---

## Chunk 3: Cross-Session Procedural Learning Extraction

### Task 3: Implement _extract_procedural_learnings

**Files:**
- Modify: `src/omega/server/hook_server/session.py` (add function + wire after retrieval feedback)
- Test: `tests/server/hook_server/test_procedural_learnings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/server/hook_server/test_procedural_learnings.py`:

```python
"""Tests for procedural learning extraction at session stop."""


def test_detects_recovery_pattern():
    """Should detect error→success recovery on same tool_name."""
    from omega.server.hook_server.session import _detect_patterns

    rows = [
        {"tool_name": "Bash", "result_status": "error", "result_summary": "FAILED test_auth", "call_index": i}
        for i in range(1, 4)
    ] + [
        {"tool_name": "Bash", "result_status": "ok", "result_summary": "All tests passed", "call_index": 4},
    ]

    recoveries, stuck = _detect_patterns(rows)
    assert len(recoveries) >= 1
    assert recoveries[0]["tool_name"] == "Bash"
    assert recoveries[0]["attempts"] == 3
    assert "FAILED" in recoveries[0]["error_context"]
    assert "passed" in recoveries[0]["success_context"]


def test_detects_stuck_pattern():
    """Should detect 5+ consecutive errors on same tool_name."""
    from omega.server.hook_server.session import _detect_patterns

    rows = [
        {"tool_name": "Edit", "result_status": "error", "result_summary": f"Edit failed attempt {i}", "call_index": i}
        for i in range(1, 7)
    ]

    recoveries, stuck = _detect_patterns(rows)
    assert len(stuck) >= 1
    assert stuck[0]["tool_name"] == "Edit"
    assert stuck[0]["consecutive_errors"] >= 5


def test_no_patterns_with_all_ok():
    """Should return empty when all tools succeed."""
    from omega.server.hook_server.session import _detect_patterns

    rows = [
        {"tool_name": "Bash", "result_status": "ok", "result_summary": "ok", "call_index": i}
        for i in range(1, 10)
    ]

    recoveries, stuck = _detect_patterns(rows)
    assert recoveries == []
    assert stuck == []


def test_skips_short_sessions():
    """Should not extract learnings from sessions with <20 tool calls."""
    from omega.server.hook_server.session import _should_extract_learnings

    assert _should_extract_learnings(19) is False
    assert _should_extract_learnings(20) is True
    assert _should_extract_learnings(100) is True


def test_max_3_learnings():
    """Should cap learnings at 3 per session."""
    from omega.server.hook_server.session import _detect_patterns

    # 5 separate recovery patterns (different tool names)
    rows = []
    idx = 1
    for tool in ["Bash", "Edit", "Write", "Grep", "Read"]:
        rows.append({"tool_name": tool, "result_status": "error", "result_summary": f"{tool} failed", "call_index": idx})
        idx += 1
        rows.append({"tool_name": tool, "result_status": "ok", "result_summary": f"{tool} ok", "call_index": idx})
        idx += 1

    recoveries, stuck = _detect_patterns(rows)
    # _detect_patterns returns all, but _extract_procedural_learnings caps at 3
    # So we just verify detection works for multiple patterns
    assert len(recoveries) >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/test_procedural_learnings.py -v`
Expected: FAIL — functions don't exist

- [ ] **Step 3: Implement pattern detection and learning extraction**

In `src/omega/server/hook_server/session.py`, add after `_auto_feedback_on_retrieval`:

```python
def _should_extract_learnings(tool_call_count: int) -> bool:
    """Gate: only extract learnings from sessions with 20+ tool calls."""
    return tool_call_count >= 20


def _detect_patterns(
    audit_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Detect recovery and stuck patterns from sorted audit rows.

    audit_rows must be sorted by call_index ASC.

    Returns: (recovery_patterns, stuck_patterns)
    - recovery: error(s) followed by success on same tool_name within 10 calls
    - stuck: 5+ consecutive errors on same tool_name
    """
    recoveries: list[dict] = []
    stuck_patterns: list[dict] = []

    # Track consecutive errors per tool_name
    consecutive_errors: dict[str, list[dict]] = {}  # tool -> list of error rows
    seen_recovery_tools: set[str] = set()

    for row in audit_rows:
        tool = row.get("tool_name", "")
        status = row.get("result_status", "ok")

        if status == "error":
            if tool not in consecutive_errors:
                consecutive_errors[tool] = []
            consecutive_errors[tool].append(row)
        elif status == "ok" and tool in consecutive_errors:
            error_rows = consecutive_errors[tool]
            error_count = len(error_rows)

            # Recovery pattern: had errors, now succeeded
            if error_count >= 1 and tool not in seen_recovery_tools:
                # Check within-10-calls window
                first_error_idx = error_rows[0].get("call_index", 0)
                current_idx = row.get("call_index", 0)
                if current_idx - first_error_idx <= 10:
                    recoveries.append({
                        "tool_name": tool,
                        "attempts": error_count,
                        "error_context": error_rows[0].get("result_summary", "")[:100],
                        "success_context": row.get("result_summary", "")[:100],
                    })
                    seen_recovery_tools.add(tool)

            # Clear consecutive errors on success
            del consecutive_errors[tool]
        elif status == "ok" and tool not in consecutive_errors:
            pass  # Normal success, no prior errors

    # Check for stuck patterns (5+ consecutive errors, never recovered)
    seen_stuck_tools: set[str] = set()
    for tool, error_rows in consecutive_errors.items():
        if len(error_rows) >= 5 and tool not in seen_stuck_tools:
            stuck_patterns.append({
                "tool_name": tool,
                "consecutive_errors": len(error_rows),
                "error_context": error_rows[-1].get("result_summary", "")[:100],
            })
            seen_stuck_tools.add(tool)

    return recoveries, stuck_patterns


def _extract_procedural_learnings(session_id: str, tool_call_count: int) -> None:
    """Extract procedural learnings from session trace patterns."""
    if not session_id or not _should_extract_learnings(tool_call_count):
        return

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        raw_rows = mgr.query_audit(session_id=session_id, limit=500)
        audit_rows = sorted(raw_rows, key=lambda r: r.get("call_index", 0))

        if not audit_rows:
            return

        recoveries, stuck = _detect_patterns(audit_rows)

        from omega.bridge import auto_capture

        stored = 0
        max_learnings = 3

        for r in recoveries:
            if stored >= max_learnings:
                break
            content = (
                f"Approach that worked: {r['tool_name']} error resolved after "
                f"{r['attempts']} attempts. Error context: {r['error_context']}. "
                f"Success context: {r['success_context']}"
            )
            try:
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
            except Exception:
                pass

        for s in stuck:
            if stored >= max_learnings:
                break
            content = (
                f"Anti-pattern: {s['tool_name']} failed {s['consecutive_errors']} "
                f"consecutive times. Error: {s['error_context']}"
            )
            try:
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
            except Exception:
                pass

        if stored:
            logger.info(f"Procedural learnings: {stored} extracted ({len(recoveries)} recoveries, {len(stuck)} stuck)")
    except Exception as e:
        _log_hook_error("procedural_learnings", e)
```

- [ ] **Step 4: Wire into handle_session_stop**

In `src/omega/server/hook_server/session.py`, add after `_auto_feedback_on_retrieval(session_id)`:

```python
    # --- Procedural learning extraction ---
    _extract_procedural_learnings(session_id, _tool_call_count)
```

- [ ] **Step 5: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/test_procedural_learnings.py -v`
Expected: PASS

- [ ] **Step 6: Run full session hook tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/ -v --timeout=60`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/hook_server/session.py tests/server/hook_server/test_procedural_learnings.py
git commit -m "feat(hooks): add procedural learning extraction at session stop

Detects error->recovery patterns (same tool_name) and stuck patterns
(5+ consecutive errors) from coord_audit trace. Stores as lesson_learned
with source=auto_procedural. Max 3 per session, Jaccard deduped."
```

---

## Chunk 4: Mid-Session Context Push

### Task 4: Add memory context push to insights.py

**Files:**
- Modify: `src/omega/server/hook_server/insights.py:52-69` (add block between plan guard and tags gate)
- Test: `tests/server/hook_server/test_memory_context_push.py`

- [ ] **Step 1: Write the failing test**

Create `tests/server/hook_server/test_memory_context_push.py`:

```python
"""Tests for mid-session memory context push in insights.py."""


def test_memory_push_fires_after_50_calls(monkeypatch):
    """Should return [MEMORY_CONTEXT] block when call count >= 50."""
    from omega.server.hook_server import insights
    from omega.server.hook_server.trace import _call_counters

    session_id = "test-session-push"
    _call_counters[session_id] = 60

    # Mock query_structured to return test memories
    def mock_query(query_text, limit=10, event_type=None, **kwargs):
        return [
            {"node_id": "mem-aaa111222333", "content": "Prior decision about auth", "event_type": "decision", "metadata": {}},
            {"node_id": "mem-bbb444555666", "content": "Lesson about error handling", "event_type": "lesson_learned", "metadata": {}},
        ]

    monkeypatch.setattr("omega.bridge.query_structured", mock_query)

    payload = {
        "tool_name": "Edit",
        "tool_input": '{"file_path": "/tmp/test_auth.py", "old_string": "a", "new_string": "b"}',
        "session_id": session_id,
    }

    result = insights.handle_pre_insight_surface(payload)
    output = result.get("output", "")
    assert "[MEMORY_CONTEXT]" in output
    assert "mem-aaa111222333" in output

    # Cleanup
    _call_counters.pop(session_id, None)
    insights._session_memory_pushed.pop(session_id, None)


def test_memory_push_skips_below_50_calls(monkeypatch):
    """Should NOT push when call count < 50."""
    from omega.server.hook_server import insights
    from omega.server.hook_server.trace import _call_counters

    session_id = "test-session-low"
    _call_counters[session_id] = 10

    payload = {
        "tool_name": "Edit",
        "tool_input": '{"file_path": "/tmp/test.py", "old_string": "a", "new_string": "b"}',
        "session_id": session_id,
    }

    result = insights.handle_pre_insight_surface(payload)
    output = result.get("output", "")
    assert "[MEMORY_CONTEXT]" not in output

    # Cleanup
    _call_counters.pop(session_id, None)


def test_memory_push_no_duplicate_per_file(monkeypatch):
    """Should push once per file per session, not twice."""
    from omega.server.hook_server import insights
    from omega.server.hook_server.trace import _call_counters

    session_id = "test-session-dedup"
    _call_counters[session_id] = 60

    def mock_query(query_text, limit=10, event_type=None, **kwargs):
        return [
            {"node_id": "mem-ccc777888999", "content": "Some memory", "event_type": "decision", "metadata": {}},
        ]

    monkeypatch.setattr("omega.bridge.query_structured", mock_query)

    payload = {
        "tool_name": "Edit",
        "tool_input": '{"file_path": "/tmp/dedup_test.py", "old_string": "a", "new_string": "b"}',
        "session_id": session_id,
    }

    # First call should push
    result1 = insights.handle_pre_insight_surface(payload)
    assert "[MEMORY_CONTEXT]" in result1.get("output", "")

    # Second call same file should NOT push
    result2 = insights.handle_pre_insight_surface(payload)
    assert "[MEMORY_CONTEXT]" not in result2.get("output", "")

    # Cleanup
    _call_counters.pop(session_id, None)
    insights._session_memory_pushed.pop(session_id, None)


def test_memory_push_skips_non_edit_tools():
    """Should not fire for Bash, Read, etc."""
    from omega.server.hook_server import insights

    payload = {
        "tool_name": "Bash",
        "tool_input": '{"command": "ls"}',
        "session_id": "test-session",
    }

    result = insights.handle_pre_insight_surface(payload)
    assert "[MEMORY_CONTEXT]" not in result.get("output", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/test_memory_context_push.py -v`
Expected: FAIL — `_session_memory_pushed` doesn't exist

- [ ] **Step 3: Implement memory context push**

Replace the entire `src/omega/server/hook_server/insights.py` with the enhanced version. The key changes:
1. Add `_session_memory_pushed` module-level dict
2. Add new import of `_call_counters` from trace
3. Insert memory push block between plan guard and tags gate
4. Restructure return to combine memory context + insight output

```python
"""System insight surfacing — contextual insights before file edits."""

import logging
import os

from omega import json_compat as json

logger = logging.getLogger("omega.hook_server.insights")


from .utils import (
    _debounce_check,
    _get_file_path_from_input,
    _log_hook_error,
    _parse_tool_input,
)

# Debounce for insight surfacing — longer than normal surface debounce
# to avoid flooding the agent with repeated insight warnings
_INSIGHT_DEBOUNCE_S = 300.0  # 5 minutes per file
_last_insight_surface: dict[str, float] = {}  # file_path -> monotonic timestamp
_MAX_INSIGHT_ENTRIES = 200

# Mid-session memory context push — once per file per session
_session_memory_pushed: dict[str, set[str]] = {}  # session_id -> set of file paths
_MAX_PUSH_SESSIONS = 50

# Map file path segments to subsystem tags for querying relevant insights
_PATH_TAG_MAP: dict[str, list[str]] = {
    "bridge.py": ["memory_engine", "bridge"],
    "sqlite_store.py": ["memory_engine", "sqlite"],
    "coordination.py": ["coordination", "sessions"],
    "coord_handlers.py": ["coordination"],
    "coord_schemas.py": ["coordination"],
    "hook_server": ["hooks"],
    "fast_hook.py": ["hooks"],
    "guards.py": ["hooks", "guards"],
    "session.py": ["sessions", "hooks"],
    "heartbeat.py": ["heartbeat", "hooks"],
    "maintenance.py": ["alerting", "monitoring", "heartbeat"],
    "cloud/": ["cloud_sync", "supabase"],
    "embedding": ["diagnostics", "sqlite_vec", "vectors"],
    "protocol.py": ["protocol"],
    "notify": ["alerting", "monitoring"],
    "cron": ["alerting", "monitoring", "cron"],
}


def _tags_for_file(file_path: str) -> list[str]:
    """Extract subsystem tags from a file path."""
    tags = []
    for pattern, tag_list in _PATH_TAG_MAP.items():
        if pattern in file_path:
            tags.extend(tag_list)
    return list(set(tags))  # deduplicate


def _memory_context_push(file_path: str, session_id: str) -> str:
    """Push relevant memories for a file. Returns output string or empty."""
    if not session_id or not file_path:
        return ""

    # Gate: only after 50+ tool calls
    try:
        from omega.server.hook_server.trace import _call_counters
        if _call_counters.get(session_id, 0) < 50:
            return ""
    except Exception:
        return ""

    # Gate: once per file per session
    pushed = _session_memory_pushed.get(session_id, set())
    if file_path in pushed:
        return ""

    try:
        from omega.bridge import query_structured

        # Query without event_type filter, post-filter to desired types
        results = query_structured(query_text=file_path, limit=9)
        if not results:
            return ""

        allowed_types = {"lesson_learned", "decision", "error_pattern"}
        matching = [
            r for r in results
            if r.get("event_type") in allowed_types
        ][:3]

        if not matching:
            return ""

        # Mark as pushed (create set if needed, bound size)
        if len(_session_memory_pushed) >= _MAX_PUSH_SESSIONS:
            # Evict oldest session
            oldest = next(iter(_session_memory_pushed))
            del _session_memory_pushed[oldest]
        if session_id not in _session_memory_pushed:
            _session_memory_pushed[session_id] = set()
        _session_memory_pushed[session_id].add(file_path)

        # Track surfaced IDs for feedback loop
        try:
            surfaced_path = os.path.expanduser(f"~/.omega/session-{session_id}.surfaced.json")
            surfaced_data: dict = {}
            if os.path.exists(surfaced_path):
                with open(surfaced_path) as f:
                    surfaced_data = json.load(f)
            surfaced_ids = [r.get("node_id", "") for r in matching if r.get("node_id")]
            if surfaced_ids:
                existing = surfaced_data.get(file_path, [])
                existing.extend(surfaced_ids)
                surfaced_data[file_path] = existing
                with open(surfaced_path, "w") as f:
                    json.dump(surfaced_data, f)
        except Exception:
            pass  # Surfacing tracking is best-effort

        filename = os.path.basename(file_path)
        lines = [f"[MEMORY_CONTEXT] Relevant memories for {filename}:"]
        for r in matching:
            node_id = r.get("node_id", "unknown")
            content = r.get("content", "")[:100].replace("\n", " ")
            lines.append(f"  - `{node_id}`: {content}")

        return "\n".join(lines)

    except Exception as e:
        _log_hook_error("memory_context_push", e)
        return ""


def handle_pre_insight_surface(payload: dict) -> dict:
    """Surface system insights relevant to the file being edited.

    Non-blocking, fail-open. Returns contextual insight text or empty output.
    """
    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return {"output": "", "error": None}

    input_data = _parse_tool_input(payload)
    file_path = _get_file_path_from_input(input_data)
    if not file_path:
        return {"output": "", "error": None}

    # Skip plan files
    from .guards import _is_plan_file
    if _is_plan_file(file_path):
        return {"output": "", "error": None}

    # --- Memory context push (fires for ALL files, before tags gate) ---
    session_id = payload.get("session_id", "")
    memory_output = _memory_context_push(file_path, session_id)

    # --- System insights (only for OMEGA-internal files with tags) ---
    insight_output = ""
    tags = _tags_for_file(file_path)
    if tags:
        # Debounce — same file at most once per 5 minutes
        if _debounce_check(_last_insight_surface, file_path, _INSIGHT_DEBOUNCE_S, _MAX_INSIGHT_ENTRIES):
            try:
                from omega.bridge import query_structured

                # Query for system insights matching these subsystem tags
                query_hint = " ".join(tags)
                results = query_structured(
                    query_text=query_hint,
                    limit=8,
                    event_type="advisor_insight",
                )
                if results:
                    # Filter to system_insight category and matching tags
                    matching = []
                    for r in results:
                        meta = r.get("metadata") or {}
                        if meta.get("category") != "system_insight":
                            continue
                        r_tags = set(r.get("tags") or [])
                        if r_tags & set(tags):
                            content = r.get("content", "")[:200]
                            matching.append(content)
                        if len(matching) >= 3:
                            break

                    if matching:
                        filename = os.path.basename(file_path)
                        lines = [f"[INSIGHT] {filename} — prior lessons:"]
                        for insight in matching:
                            lines.append(f"  - {insight}")
                        insight_output = "\n".join(lines)

            except Exception as e:
                _log_hook_error("pre_insight_surface", e)

    # Combine outputs
    combined = "\n".join(part for part in [memory_output, insight_output] if part)
    return {"output": combined, "error": None}
```

- [ ] **Step 4: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/test_memory_context_push.py -v`
Expected: PASS

- [ ] **Step 5: Run full insight tests for regressions**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/server/hook_server/ -v --timeout=60`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/hook_server/insights.py tests/server/hook_server/test_memory_context_push.py
git commit -m "feat(hooks): add mid-session memory context push on file edits

After 50+ tool calls, surfaces relevant lesson_learned/decision/
error_pattern memories when editing a file. Once per file per session.
Works for all files, not just OMEGA-internal. Tracks surfaced IDs
for feedback loop integration."
```

---

## Chunk 5: CLAUDE.md and Final Validation

### Task 5: Add graph linking bullet to CLAUDE.md

**Files:**
- Modify: `~/.claude/CLAUDE.md` (Core Rules section)

- [ ] **Step 1: Add graph linking bullet**

In `~/.claude/CLAUDE.md`, in the Core Rules section, after the "OMEGA degraded mode" bullet, add:

```markdown
- **Graph linking**: After `omega_store`, check `omega_memory(similar)` and link related memories. This turns flat storage into a knowledge graph.
```

**Note:** `~/.claude/` is not a git repo. The file edit is the deliverable — no commit needed.

### Task 6: Run full test suite and lint

- [ ] **Step 1: Run full OMEGA test suite**

Run: `cd ~/Projects/omega && python3.11 -m pytest -x`
Expected: All PASS

- [ ] **Step 2: Run lint**

Run: `cd ~/Projects/omega && ruff check src/omega/server/hook_server/session.py src/omega/server/hook_server/insights.py src/omega/protocol.py`
Expected: No errors

- [ ] **Step 3: Final commit (if any lint fixes needed)**

```bash
cd ~/Projects/omega
git add -p  # Stage only lint fixes
git commit -m "chore: lint fixes for utilization gap changes"
```
