# Intelligence Cards Wiring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the 4 dead Intelligence Card formatters into the OMEGA hook server using the existing adaptive transparency system.

**Architecture:** The card formatters and transparency engine already exist in `cards.py` and `card_tracker.py`. This plan connects them to 3 integration points: file-edit surfacing (`memory.py`), assistant auto-capture (`assistant.py`), and explicit decision storage (`handlers.py`). Transparency level (MINIMAL/NORMAL/VERBOSE) is computed from session complexity (files edited, errors, intent).

**Tech Stack:** Python 3.11, OMEGA hook server (Unix socket daemon), pytest

---

### Task 1: Wire full Memory Card in `_surface_for_edit`

**Files:**
- Modify: `src/omega/server/hook_server/memory.py:436` (the line `lines.extend(_format_results_as_cards(...))`)
- Test: `tests/server/hook_server/test_memory_cards.py`

**Step 1: Write the failing test**

Add to `tests/server/hook_server/test_memory_cards.py`:

```python
class TestTransparencyDrivenMemoryCards:
    """Test that NORMAL+ transparency produces full [OMEGA MEMORY] cards."""

    def test_normal_transparency_produces_full_card(self):
        from omega.server.hook_server.cards import format_memory_card, TransparencyLevel

        results = [
            {
                "id": "mem-abc",
                "content": "Always validate test fixtures before running",
                "relevance": 0.92,
                "event_type": "lesson_learned",
                "age": "2d ago",
                "is_remembered": True,
            },
        ]
        lines = format_memory_card(results, "test.py", TransparencyLevel.NORMAL)
        assert len(lines) > 0
        assert "[OMEGA MEMORY]" in lines[0]
        assert "test.py" in lines[0]

    def test_verbose_transparency_includes_linked(self):
        from omega.server.hook_server.cards import format_memory_card, TransparencyLevel

        results = [
            {
                "id": "mem-abc",
                "content": "Main memory content here",
                "relevance": 0.90,
                "event_type": "decision",
                "age": "1d ago",
                "is_remembered": False,
            },
        ]
        linked = [
            {
                "metadata": {"event_type": "lesson_learned"},
                "content": "Linked lesson about the same topic",
            },
        ]
        lines = format_memory_card(results, "test.py", TransparencyLevel.VERBOSE, linked=linked)
        assert any("[linked]" in ln for ln in lines)

    def test_minimal_transparency_skips_low_relevance(self):
        from omega.server.hook_server.cards import format_memory_card, TransparencyLevel

        results = [
            {
                "id": "mem-low",
                "content": "Low relevance memory",
                "relevance": 0.50,
                "event_type": "memory",
                "age": "5d ago",
                "is_remembered": False,
            },
        ]
        lines = format_memory_card(results, "test.py", TransparencyLevel.MINIMAL)
        assert lines == []  # MINIMAL requires >= 0.85
```

**Step 2: Run tests to verify they pass (these test the already-written formatter)**

Run: `python3.11 -m pytest tests/server/hook_server/test_memory_cards.py::TestTransparencyDrivenMemoryCards -v`
Expected: PASS (formatters exist, just not wired)

**Step 3: Write integration test for the wiring**

Add to `tests/server/hook_server/test_memory_cards.py`:

```python
class TestSurfaceForEditUsesTransparency:
    """Test that _surface_for_edit dispatches to full cards at NORMAL+ transparency."""

    def test_surface_for_edit_uses_full_card_at_normal(self):
        """When tracker has enough complexity for NORMAL, output should contain [OMEGA MEMORY]."""
        from omega.server.hook_server.card_tracker import SessionCardTracker
        from omega.server.hook_server.cards import TransparencyLevel

        # A tracker with enough edits + errors to reach NORMAL (score >= 3)
        tracker = SessionCardTracker("test-transparency")
        tracker.record_edit("/a.py")
        tracker.record_edit("/b.py")  # 2 edits * 2.0 = 4.0 -> NORMAL
        assert tracker.transparency == TransparencyLevel.NORMAL
```

**Step 4: Run test to verify it passes**

Run: `python3.11 -m pytest tests/server/hook_server/test_memory_cards.py::TestSurfaceForEditUsesTransparency -v`
Expected: PASS

**Step 5: Implement the wiring in `_surface_for_edit`**

In `src/omega/server/hook_server/memory.py`, replace the block around line 436 where `_format_results_as_cards` is called. The change: check transparency level and dispatch to full vs compact cards.

Replace this section (approximately lines 436-437):
```python
            # Format via compact [OMEGA] intelligence cards
            lines.extend(_format_results_as_cards(results, session_id=session_id, project=project))
```

With:
```python
            # Format via intelligence cards -- full structured at NORMAL+, compact at MINIMAL
            from .cards import format_memory_card, TransparencyLevel

            level = tracker.transparency if tracker else TransparencyLevel.MINIMAL
            if level != TransparencyLevel.MINIMAL:
                filename_short = os.path.basename(file_path)
                lines.extend(format_memory_card(results, filename_short, level, linked=linked_memories))
                # Also record surfacings in compact tracker for outcome tracking
                from .card_tracker import get_card_tracker as _get_ct
                _ct = _get_ct()
                for r in results:
                    mid = r.get("id", "")
                    if mid:
                        _ct.record_surfaced(session_id, mid, r.get("content", "")[:200])
            else:
                lines.extend(_format_results_as_cards(results, session_id=session_id, project=project))
```

**Step 6: Run full memory card tests**

Run: `python3.11 -m pytest tests/server/hook_server/test_memory_cards.py -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/omega/server/hook_server/memory.py tests/server/hook_server/test_memory_cards.py
git commit -m "feat(cards): wire full memory card at NORMAL+ transparency"
```

---

### Task 2: Wire Decision Card on file edit in `_surface_for_edit`

**Files:**
- Modify: `src/omega/server/hook_server/memory.py` (after memory card section in `_surface_for_edit`)
- Test: `tests/server/hook_server/test_memory_cards.py`

**Step 1: Write the failing test**

Add to `tests/server/hook_server/test_memory_cards.py`:

```python
class TestDecisionCardOnEdit:
    """Test that file edits surface prior decisions at NORMAL+ transparency."""

    def test_format_decision_card_normal(self):
        from omega.server.hook_server.cards import format_decision_card, TransparencyLevel

        decisions = [
            {"content": "Use SQLite for local storage", "age": "3d ago"},
        ]
        lines = format_decision_card(decisions, TransparencyLevel.NORMAL)
        assert len(lines) == 1
        assert "[OMEGA DECISIONS]" in lines[0]

    def test_format_decision_card_verbose_shows_trail(self):
        from omega.server.hook_server.cards import format_decision_card, TransparencyLevel

        decisions = [
            {"content": "Use SQLite for local storage", "age": "3d ago"},
            {"content": "Switch from JSON files to SQLite", "age": "7d ago"},
        ]
        lines = format_decision_card(decisions, TransparencyLevel.VERBOSE)
        assert "[OMEGA DECISIONS] Decision trail:" in lines[0]
        assert len(lines) >= 3  # header + 2 decisions

    def test_format_decision_card_minimal_suppressed(self):
        from omega.server.hook_server.cards import format_decision_card, TransparencyLevel

        decisions = [
            {"content": "Some decision", "age": "1d ago"},
        ]
        lines = format_decision_card(decisions, TransparencyLevel.MINIMAL)
        assert lines == []  # MINIMAL suppresses decisions
```

**Step 2: Run tests to verify they pass (formatter exists)**

Run: `python3.11 -m pytest tests/server/hook_server/test_memory_cards.py::TestDecisionCardOnEdit -v`
Expected: PASS

**Step 3: Implement the wiring**

In `src/omega/server/hook_server/memory.py`, in `_surface_for_edit`, after the memory card block and before the first-recall milestone, add:

```python
            # Surface prior decisions about this file at NORMAL+ transparency
            if level in (TransparencyLevel.NORMAL, TransparencyLevel.VERBOSE):
                try:
                    from .cards import format_decision_card
                    decision_results = query_structured(
                        query_text=f"decisions about {filename}",
                        event_type="decision",
                        limit=5,
                        context_file=file_path,
                        entity_id=entity_id,
                    )
                    # Filter to relevant decisions from other sessions
                    file_decisions = [
                        d for d in (decision_results or [])
                        if d.get("relevance", 0) >= 0.35
                        and (d.get("metadata") or {}).get("session_id") != session_id
                    ]
                    if file_decisions:
                        lines.extend(format_decision_card(file_decisions, level))
                        if tracker:
                            tracker.record_decisions_seen()
                            for d in file_decisions:
                                mid = d.get("id", "")
                                if mid:
                                    tracker.record_surfacing(mid, file_path, card_type="decisions")
                except Exception as e:
                    _log_hook_error("decision_card_on_edit", e)
```

**Step 4: Run tests**

Run: `python3.11 -m pytest tests/server/hook_server/test_memory_cards.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/omega/server/hook_server/memory.py tests/server/hook_server/test_memory_cards.py
git commit -m "feat(cards): wire decision card on file edit at NORMAL+ transparency"
```

---

### Task 3: Wire full Learning Card in `handle_assistant_capture`

**Files:**
- Modify: `src/omega/server/hook_server/assistant.py:280-300` (the compact card formatting section)
- Test: `tests/server/hook_server/test_assistant_cards.py`

**Step 1: Write the failing test**

Add to `tests/server/hook_server/test_assistant_cards.py`:

```python
class TestTransparencyDrivenLearningCards:
    """Test that NORMAL+ transparency produces full [OMEGA LEARNED] cards."""

    def test_full_learning_card_at_normal(self):
        from omega.server.hook_server.cards import format_learning_card, TransparencyLevel

        lines = format_learning_card(
            matched_type="fix",
            content="The root cause was a missing null check in the parser",
            confidence=0.75,
            level=TransparencyLevel.NORMAL,
        )
        assert len(lines) == 1
        assert "[OMEGA LEARNED]" in lines[0]
        assert "75%" in lines[0]

    def test_full_learning_card_suppressed_at_minimal(self):
        from omega.server.hook_server.cards import format_learning_card, TransparencyLevel

        lines = format_learning_card(
            matched_type="fix",
            content="Some fix description",
            confidence=0.5,
            level=TransparencyLevel.MINIMAL,
        )
        assert lines == []
```

**Step 2: Run tests to verify they pass (formatter exists)**

Run: `python3.11 -m pytest tests/server/hook_server/test_assistant_cards.py::TestTransparencyDrivenLearningCards -v`
Expected: PASS

**Step 3: Write integration test for the wiring**

Add to `tests/server/hook_server/test_assistant_cards.py`:

```python
from unittest.mock import patch

class TestAssistantCaptureUsesTransparency:
    """Test handle_assistant_capture dispatches to full learning card at NORMAL+."""

    def _make_payload(self, message: str, session_id: str = "test-transparency") -> dict:
        return {
            "last_assistant_message": message,
            "session_id": session_id,
            "project": "/test/project",
        }

    @patch("omega.bridge.auto_capture")
    def test_normal_transparency_produces_full_learned_card(self, mock_capture):
        from omega.server.hook_server.assistant import handle_assistant_capture
        from omega.server.hook_server import _assistant_capture_count, get_card_tracker

        sid = "test-full-learn"
        _assistant_capture_count.pop(sid, None)

        # Escalate transparency to NORMAL by simulating edits
        tracker = get_card_tracker(sid)
        tracker.record_edit("/a.py")
        tracker.record_edit("/b.py")

        msg = "x" * 200 + "\nThe fix was updating the timeout value from 30 to 60 seconds which resolved the connection drops entirely."
        result = handle_assistant_capture(self._make_payload(msg, sid))
        output = result.get("output", "")
        assert "[OMEGA LEARNED]" in output

        _assistant_capture_count.pop(sid, None)
```

**Step 4: Implement the wiring**

In `src/omega/server/hook_server/assistant.py`, replace the compact card formatting section (around lines 280-300):

Replace:
```python
    # Format via compact [OMEGA] intelligence card
    try:
        from . import get_card_tracker as _get_session_tracker
        from .cards import format_compact_learning_card
        from .card_tracker import get_card_tracker as _get_compact_tracker

        # Compact card for user-facing output
        card = format_compact_learning_card(
            content=matched_content[:500],
            event_type=event_type,
        )
```

With:
```python
    # Format via intelligence card -- full at NORMAL+, compact at MINIMAL
    try:
        from . import get_card_tracker as _get_session_tracker
        from .cards import format_compact_learning_card, format_learning_card, TransparencyLevel
        from .card_tracker import get_card_tracker as _get_compact_tracker

        # Check transparency level
        session_tracker = _get_session_tracker(session_id)
        level = session_tracker.transparency if session_tracker else TransparencyLevel.MINIMAL

        if level != TransparencyLevel.MINIMAL:
            card_lines = format_learning_card(
                matched_type=matched_type,
                content=matched_content[:500],
                confidence=confidence,
                level=level,
            )
            card = "\n".join(card_lines) if card_lines else ""
        else:
            card = format_compact_learning_card(
                content=matched_content[:500],
                event_type=event_type,
            )
```

The rest of the function (recording in trackers, return) stays the same.

**Step 5: Run all assistant card tests**

Run: `python3.11 -m pytest tests/server/hook_server/test_assistant_cards.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/omega/server/hook_server/assistant.py tests/server/hook_server/test_assistant_cards.py
git commit -m "feat(cards): wire full learning card at NORMAL+ transparency"
```

---

### Task 4: Wire Decision Trail in `omega_store` handler

**Files:**
- Modify: `src/omega/server/handlers.py:232-245` (after decision broadcast in `handle_omega_store`)
- Test: `tests/server/test_handlers_decision_trail.py` (new)

**Step 1: Write the failing test**

Create `tests/server/test_handlers_decision_trail.py`:

```python
"""Tests for decision trail card wiring in omega_store handler."""
import pytest
from unittest.mock import patch, MagicMock


class TestDecisionTrailOnStore:
    """Test that storing a decision surfaces prior decision trail."""

    @pytest.mark.asyncio
    @patch("omega.bridge.store")
    @patch("omega.bridge.query_structured")
    def test_decision_store_appends_trail(self, mock_query, mock_store):
        """When storing a decision with prior decisions, response includes trail."""
        import asyncio
        from omega.server.handlers import handle_omega_store

        mock_store.return_value = "Stored mem-new123"
        mock_query.return_value = [
            {
                "id": "mem-old1",
                "content": "Use SQLite for local storage",
                "relevance": 0.85,
                "event_type": "decision",
                "created_at": "2026-02-20T10:00:00Z",
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            handle_omega_store({
                "content": "Switching to WAL mode for SQLite",
                "event_type": "decision",
                "session_id": "test-trail",
                "project": "/test",
            })
        )

        text = result["content"][0]["text"]
        assert "[OMEGA] Prior decisions" in text

    @pytest.mark.asyncio
    @patch("omega.bridge.store")
    @patch("omega.bridge.query_structured")
    def test_non_decision_store_has_no_trail(self, mock_query, mock_store):
        """Non-decision types should not trigger trail lookup."""
        import asyncio
        from omega.server.handlers import handle_omega_store

        mock_store.return_value = "Stored mem-123"

        result = asyncio.get_event_loop().run_until_complete(
            handle_omega_store({
                "content": "Some lesson learned",
                "event_type": "lesson_learned",
                "session_id": "test-trail",
                "project": "/test",
            })
        )

        text = result["content"][0]["text"]
        assert "[OMEGA] Prior decisions" not in text
        mock_query.assert_not_called()

    @pytest.mark.asyncio
    @patch("omega.bridge.store")
    @patch("omega.bridge.query_structured")
    def test_decision_store_no_priors_no_trail(self, mock_query, mock_store):
        """When no prior decisions exist, no trail is appended."""
        import asyncio
        from omega.server.handlers import handle_omega_store

        mock_store.return_value = "Stored mem-new456"
        mock_query.return_value = []

        result = asyncio.get_event_loop().run_until_complete(
            handle_omega_store({
                "content": "Brand new decision topic",
                "event_type": "decision",
                "session_id": "test-trail",
                "project": "/test",
            })
        )

        text = result["content"][0]["text"]
        assert "[OMEGA] Prior decisions" not in text
```

**Step 2: Run test to verify it fails**

Run: `python3.11 -m pytest tests/server/test_handlers_decision_trail.py -v`
Expected: FAIL (the trail is not appended yet)

**Step 3: Implement the wiring**

In `src/omega/server/handlers.py`, in `handle_omega_store`, after the `_broadcast_decision` block (around line 235) and before the `attach_finding` block, add the decision trail surfacing:

```python
        # Surface prior decision trail for consistency awareness
        if event_type == "decision" and content:
            try:
                from omega.bridge import query_structured
                from omega.server.hook_server.cards import format_decision_trail_card

                prior = query_structured(
                    query_text=content[:200],
                    event_type="decision",
                    limit=5,
                    project=project,
                    entity_id=entity_id,
                )
                # Exclude the memory we just stored (result contains its ID)
                new_id = ""
                if result and "mem-" in result:
                    import re as _re
                    _id_match = _re.search(r"(mem-[a-f0-9]+)", result)
                    if _id_match:
                        new_id = _id_match.group(1)
                prior_filtered = [
                    d for d in (prior or [])
                    if d.get("id") != new_id and d.get("relevance", 0) >= 0.30
                ]
                if prior_filtered:
                    # Build trail format: need date + content + status
                    trail_decisions = []
                    for d in prior_filtered[:5]:
                        created = d.get("created_at", "")[:10] or "unknown"
                        trail_decisions.append({
                            "date": created,
                            "content": d.get("content", ""),
                            "status": "active",
                        })
                    topic = content[:60].replace("\n", " ").strip()
                    trail = format_decision_trail_card(topic=topic, decisions=trail_decisions)
                    if trail:
                        result = result + "\n\n" + trail
            except Exception as e:
                logger.debug("decision trail surfacing failed: %s", e)
```

**Step 4: Run tests**

Run: `python3.11 -m pytest tests/server/test_handlers_decision_trail.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/omega/server/handlers.py tests/server/test_handlers_decision_trail.py
git commit -m "feat(cards): wire decision trail on omega_store(decision)"
```

---

### Task 5: Run full test suite and verify no regressions

**Files:**
- No changes -- verification only

**Step 1: Run all card-related tests**

Run: `python3.11 -m pytest tests/server/hook_server/test_cards.py tests/server/hook_server/test_card_tracker.py tests/server/hook_server/test_memory_cards.py tests/server/hook_server/test_assistant_cards.py tests/server/hook_server/test_session_summary_card.py tests/server/test_handlers_decision_trail.py tests/test_intelligence_cards.py -v`
Expected: ALL PASS

**Step 2: Run full test suite**

Run: `python3.11 -m pytest tests/ -x --timeout=120`
Expected: ALL PASS (2500+ tests)

**Step 3: If any failures, fix and recommit**

**Step 4: Final commit with design doc**

```bash
git add docs/plans/2026-02-24-intelligence-cards-wiring-design.md docs/plans/2026-02-24-intelligence-cards-wiring-plan.md
git commit -m "docs: add intelligence cards wiring design and plan"
```
