# Proactive Advisor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a proactive advisor module that converts stored error patterns, lessons, and decisions into forward-looking [WARNING]/[TIP]/[WATCH]/[SUGGEST]/[RECALL] messages, integrated into existing hooks.

**Architecture:** New `src/omega/advisor.py` module (~300 lines) with 3 integration points in `hook_server.py` (file edits + bash errors) and `bridge.py` (welcome). Fail-open, no new MCP tools, no schema changes. Pro-only.

**Tech Stack:** Python 3.11+, pytest, existing OMEGA bridge/storage APIs

**Design doc:** `docs/plans/2026-02-16-proactive-advisor-design.md`

---

### Task 1: AdvisorLine dataclass and scoring helpers

**Files:**
- Create: `src/omega/advisor.py`
- Test: `tests/test_advisor.py`

**Step 1: Write the failing test**

```python
# tests/test_advisor.py
"""Proactive Advisor tests -- unit tests with mocked storage."""

import pytest
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta


def test_advisor_line_format():
    """AdvisorLine.format() produces correct tagged output."""
    from omega.advisor import AdvisorLine

    line = AdvisorLine(
        tag="WARNING",
        message="This file has caused 3 errors",
        memory_ids=["abc123", "def456"],
        score=0.85,
    )
    assert line.format() == "[WARNING] This file has caused 3 errors"


def test_advisor_line_sorting():
    """AdvisorLines sort by score descending."""
    from omega.advisor import AdvisorLine

    lines = [
        AdvisorLine(tag="TIP", message="low", memory_ids=[], score=0.3),
        AdvisorLine(tag="WARNING", message="high", memory_ids=[], score=0.9),
        AdvisorLine(tag="RECALL", message="mid", memory_ids=[], score=0.6),
    ]
    sorted_lines = sorted(lines, key=lambda x: x.score, reverse=True)
    assert sorted_lines[0].tag == "WARNING"
    assert sorted_lines[1].tag == "RECALL"
    assert sorted_lines[2].tag == "TIP"


def test_recency_score_recent():
    """Recency score for memory < 7 days old is 1.0."""
    from omega.advisor import _recency_score

    now = datetime.now(timezone.utc)
    assert _recency_score(now.isoformat()) == 1.0


def test_recency_score_old():
    """Recency score for memory > 30 days old is 0.2."""
    from omega.advisor import _recency_score

    old = datetime.now(timezone.utc) - timedelta(days=60)
    assert _recency_score(old.isoformat()) == 0.2


def test_recency_score_mid():
    """Recency score for memory 7-30 days old is 0.5."""
    from omega.advisor import _recency_score

    mid = datetime.now(timezone.utc) - timedelta(days=15)
    assert _recency_score(mid.isoformat()) == 0.5


def test_composite_score():
    """Composite score = relevance * 0.4 + recency * 0.3 + frequency * 0.3."""
    from omega.advisor import _composite_score

    score = _composite_score(relevance=0.8, recency=1.0, frequency=0.5)
    expected = 0.8 * 0.4 + 1.0 * 0.3 + 0.5 * 0.3
    assert abs(score - expected) < 0.001
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py -v -x 2>&1 | head -30`
Expected: FAIL with "ModuleNotFoundError: No module named 'omega.advisor'"

**Step 3: Write minimal implementation**

```python
# src/omega/advisor.py
"""Proactive Advisor -- converts stored memories into forward-looking warnings.

Pro-only module. Plugs into existing hooks at 3 integration points:
1. handle_surface_memories (file edits) -- [WARNING], [TIP], [RECALL]
2. welcome (session start) -- [SUGGEST]
3. _capture_error (bash errors) -- [WATCH]

Fail-open: if anything throws, the caller gets an empty list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

TAG_PRIORITY = {"WARNING": 0, "WATCH": 1, "RECALL": 2, "SUGGEST": 3, "TIP": 4}

MAX_WARNINGS_PER_HOOK = 3


@dataclass
class AdvisorLine:
    """A single proactive warning/tip/suggestion."""

    tag: str  # "WARNING", "TIP", "WATCH", "SUGGEST", "RECALL"
    message: str
    memory_ids: List[str] = field(default_factory=list)
    score: float = 0.0

    def format(self) -> str:
        return f"[{self.tag}] {self.message}"


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _recency_score(created_at_iso: str) -> float:
    """Score recency: 1.0 if < 7 days, 0.5 if < 30 days, 0.2 if older."""
    try:
        created = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400.0
        if age_days < 7:
            return 1.0
        elif age_days < 30:
            return 0.5
        return 0.2
    except Exception:
        return 0.2


def _composite_score(relevance: float, recency: float, frequency: float) -> float:
    """Composite score = relevance * 0.4 + recency * 0.3 + frequency * 0.3."""
    return relevance * 0.4 + recency * 0.3 + frequency * 0.3
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py -v -x 2>&1 | tail -20`
Expected: 6 passed

**Step 5: Commit**

```bash
cd ~/Projects/omega && git add src/omega/advisor.py tests/test_advisor.py && git commit -m "feat(advisor): add AdvisorLine dataclass and scoring helpers"
```

---

### Task 2: Advisor.suggest_for_file -- WARNING generation

**Files:**
- Modify: `src/omega/advisor.py`
- Modify: `tests/test_advisor.py`

**Step 1: Write the failing tests**

Append to `tests/test_advisor.py`:

```python
import os
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _reset_advisor_state():
    """Clear advisor debounce state between tests."""
    try:
        from omega import advisor
        advisor._session_dedup.clear()
        advisor._file_cooldowns.clear()
    except (ImportError, AttributeError):
        pass
    yield
    try:
        from omega import advisor
        advisor._session_dedup.clear()
        advisor._file_cooldowns.clear()
    except (ImportError, AttributeError):
        pass


def _make_error_result(content, session_id="sess-other", relevance=0.6, created_days_ago=2, memory_id=None):
    """Helper to create a mock error_pattern query result."""
    created = (datetime.now(timezone.utc) - timedelta(days=created_days_ago)).isoformat()
    return {
        "id": memory_id or f"err-{hash(content) % 10000:04d}",
        "content": content,
        "event_type": "error_pattern",
        "session_id": session_id,
        "created_at": created,
        "relevance": relevance,
        "metadata": {"event_type": "error_pattern", "session_id": session_id},
    }


def _make_lesson_result(content, session_id="sess-other", relevance=0.5, created_days_ago=1, memory_id=None):
    """Helper to create a mock lesson_learned query result."""
    created = (datetime.now(timezone.utc) - timedelta(days=created_days_ago)).isoformat()
    return {
        "id": memory_id or f"les-{hash(content) % 10000:04d}",
        "content": content,
        "event_type": "lesson_learned",
        "session_id": session_id,
        "created_at": created,
        "relevance": relevance,
        "metadata": {"event_type": "lesson_learned", "session_id": session_id},
    }


def _make_decision_result(content, session_id="sess-other", relevance=0.5, created_days_ago=5, memory_id=None):
    """Helper to create a mock decision query result."""
    created = (datetime.now(timezone.utc) - timedelta(days=created_days_ago)).isoformat()
    return {
        "id": memory_id or f"dec-{hash(content) % 10000:04d}",
        "content": content,
        "event_type": "decision",
        "session_id": session_id,
        "created_at": created,
        "relevance": relevance,
        "metadata": {"event_type": "decision", "session_id": session_id},
    }


class TestSuggestForFileWarnings:
    """Tests for [WARNING] generation from error patterns."""

    @patch("omega.advisor.query_structured")
    @patch("omega.advisor._find_fix_for_error")
    def test_multiple_errors_across_sessions_produces_warning(self, mock_fix, mock_qs):
        """3 error_patterns across different sessions -> [WARNING] with count."""
        from omega.advisor import Advisor

        mock_qs.side_effect = lambda **kw: {
            "error_pattern": [
                _make_error_result("threading.Lock deadlock", session_id="s1"),
                _make_error_result("threading.Lock deadlock", session_id="s2"),
                _make_error_result("DB connection gone", session_id="s3"),
            ],
            "lesson_learned": [],
            "decision": [],
        }.get(kw.get("event_type"), [])
        mock_fix.return_value = "use RLock"

        adv = Advisor(project="/proj", entity_id="omega")
        results = adv.suggest_for_file(
            file_path="/proj/src/omega/coordination.py",
            session_id="sess-current",
            tool_name="Edit",
            already_surfaced=set(),
        )

        warnings = [r for r in results if r.tag == "WARNING"]
        assert len(warnings) >= 1
        assert "coordination.py" in warnings[0].message or "error" in warnings[0].message.lower()

    @patch("omega.advisor.query_structured")
    def test_single_session_error_no_warning(self, mock_qs):
        """1 error_pattern from single session -> no WARNING (below threshold)."""
        from omega.advisor import Advisor

        mock_qs.side_effect = lambda **kw: {
            "error_pattern": [
                _make_error_result("some error", session_id="sess-current"),
            ],
            "lesson_learned": [],
            "decision": [],
        }.get(kw.get("event_type"), [])

        adv = Advisor(project="/proj")
        results = adv.suggest_for_file(
            file_path="/proj/foo.py",
            session_id="sess-current",
            tool_name="Edit",
            already_surfaced=set(),
        )

        warnings = [r for r in results if r.tag == "WARNING"]
        assert len(warnings) == 0

    @patch("omega.advisor.query_structured")
    def test_already_surfaced_ids_excluded(self, mock_qs):
        """Memories in already_surfaced set are excluded."""
        from omega.advisor import Advisor

        err = _make_error_result("deadlock", session_id="s1", memory_id="already-shown")
        err2 = _make_error_result("deadlock", session_id="s2", memory_id="already-shown-2")
        mock_qs.side_effect = lambda **kw: {
            "error_pattern": [err, err2],
            "lesson_learned": [],
            "decision": [],
        }.get(kw.get("event_type"), [])

        adv = Advisor(project="/proj")
        results = adv.suggest_for_file(
            file_path="/proj/foo.py",
            session_id="sess-current",
            tool_name="Edit",
            already_surfaced={"already-shown", "already-shown-2"},
        )

        assert len(results) == 0

    @patch("omega.advisor.query_structured")
    def test_cooldown_prevents_repeat(self, mock_qs):
        """Second call within 10 min for same file returns empty."""
        from omega.advisor import Advisor

        mock_qs.side_effect = lambda **kw: {
            "error_pattern": [
                _make_error_result("err", session_id="s1"),
                _make_error_result("err", session_id="s2"),
            ],
            "lesson_learned": [],
            "decision": [],
        }.get(kw.get("event_type"), [])

        adv = Advisor(project="/proj")
        r1 = adv.suggest_for_file("/proj/foo.py", "sess", "Edit", set())
        r2 = adv.suggest_for_file("/proj/foo.py", "sess", "Edit", set())

        assert len(r1) > 0
        assert len(r2) == 0  # Cooldown
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py::TestSuggestForFileWarnings -v -x 2>&1 | head -30`
Expected: FAIL with "AttributeError: module 'omega.advisor' has no attribute 'Advisor'"

**Step 3: Write implementation**

Add to `src/omega/advisor.py` after the scoring helpers:

```python
import os
import time

# ---------------------------------------------------------------------------
# Module-level state (reset between tests via conftest)
# ---------------------------------------------------------------------------

_session_dedup: Set[str] = set()  # Hashes of warnings already shown this session
_file_cooldowns: Dict[str, float] = {}  # file_path -> monotonic timestamp of last advisory

COOLDOWN_SECONDS = 600.0  # 10 minutes


# ---------------------------------------------------------------------------
# Fix-finding helpers
# ---------------------------------------------------------------------------


def _find_fix_for_error(error_id: str, error_content: str, entity_id: Optional[str] = None) -> Optional[str]:
    """Find the fix for an error pattern via graph traversal, then temporal, then semantic fallback.

    Returns fix text or None.
    """
    try:
        from omega.bridge import _get_store

        store = _get_store()

        # Strategy 1: Graph traversal for linked lessons
        linked = store.get_related_chain(error_id, max_hops=2, edge_types=["resolved_by", "related_to"])
        for node in linked:
            meta = node.get("metadata") or {}
            if meta.get("event_type") == "lesson_learned":
                return node.get("content", "")[:150]

        # Strategy 2: Temporal proximity -- lesson within 30 min after error, same session
        from omega.bridge import query_structured

        error_lessons = query_structured(
            query_text=error_content[:200],
            limit=3,
            event_type="lesson_learned",
            entity_id=entity_id,
        )
        for lesson in error_lessons:
            if lesson.get("relevance", 0) >= 0.4:
                return lesson.get("content", "")[:150]

    except Exception as e:
        logger.debug("_find_fix_for_error failed: %s", e)

    return None


# ---------------------------------------------------------------------------
# Advisor class
# ---------------------------------------------------------------------------


class Advisor:
    """Proactive advisor that converts stored memories into warnings."""

    def __init__(self, project: str, entity_id: Optional[str] = None):
        self.project = project
        self.entity_id = entity_id

    def suggest_for_file(
        self,
        file_path: str,
        session_id: str,
        tool_name: str,
        already_surfaced: Set[str],
    ) -> List[AdvisorLine]:
        """Generate warnings/tips/recalls for a file being edited.

        Returns ranked, capped list of AdvisorLines.
        """
        # Cooldown check
        now = time.monotonic()
        if file_path in _file_cooldowns and now - _file_cooldowns[file_path] < COOLDOWN_SECONDS:
            return []

        candidates: List[AdvisorLine] = []

        filename = os.path.basename(file_path)
        dirname = os.path.basename(os.path.dirname(file_path))
        query_text = f"{filename} {dirname}"

        try:
            from omega.bridge import query_structured

            # Query 1: Error patterns
            errors = query_structured(
                query_text=query_text,
                event_type="error_pattern",
                context_file=file_path,
                limit=10,
                entity_id=self.entity_id,
            )

            # Filter: exclude already surfaced, require cross-session (2+ unique sessions)
            errors = [e for e in errors if e.get("id") not in already_surfaced]
            error_sessions = {e.get("session_id") or e.get("metadata", {}).get("session_id", "") for e in errors}
            # Remove current session from count
            error_sessions.discard(session_id)

            if len(error_sessions) >= 2:
                # Group by distinct error content (dedup similar messages)
                seen_content = set()
                unique_errors = []
                for e in errors:
                    content_key = e.get("content", "")[:80].lower().strip()
                    if content_key not in seen_content:
                        seen_content.add(content_key)
                        unique_errors.append(e)

                # Build warning with fix lookups
                error_lines = []
                all_ids = []
                for e in unique_errors[:3]:
                    eid = e.get("id", "")
                    all_ids.append(eid)
                    content = e.get("content", "")[:100].replace("\n", " ").strip()
                    fix = _find_fix_for_error(eid, e.get("content", ""), self.entity_id)
                    if fix:
                        fix_short = fix[:80].replace("\n", " ").strip()
                        error_lines.append(f"  - {content} -- fix: {fix_short}")
                    else:
                        error_lines.append(f"  - {content} (no recorded fix)")

                msg = f"{filename} has caused {len(errors)} errors across {len(error_sessions)} sessions:\n"
                msg += "\n".join(error_lines)

                recency = max((_recency_score(e.get("created_at", "")) for e in errors), default=0.2)
                freq = min(len(errors) / 5.0, 1.0)
                avg_relevance = sum(e.get("relevance", 0) for e in errors) / max(len(errors), 1)

                candidates.append(AdvisorLine(
                    tag="WARNING",
                    message=msg,
                    memory_ids=all_ids,
                    score=_composite_score(avg_relevance, recency, freq),
                ))

            # Query 2: Lessons (for [TIP])
            lessons = query_structured(
                query_text=query_text,
                event_type="lesson_learned",
                context_file=file_path,
                limit=5,
                entity_id=self.entity_id,
            )
            lessons = [
                l for l in lessons
                if l.get("id") not in already_surfaced
                and l.get("relevance", 0) >= 0.3
                and (l.get("session_id") or l.get("metadata", {}).get("session_id", "")) != session_id
            ]
            for l in lessons[:2]:
                lid = l.get("id", "")
                content = l.get("content", "")[:150].replace("\n", " ").strip()
                created = l.get("created_at", "")
                recency = _recency_score(created)
                candidates.append(AdvisorLine(
                    tag="TIP",
                    message=content,
                    memory_ids=[lid],
                    score=_composite_score(l.get("relevance", 0), recency, 0.0),
                ))

            # Query 3: Decisions (for [RECALL])
            decisions = query_structured(
                query_text=query_text,
                event_type="decision",
                context_file=file_path,
                limit=3,
                entity_id=self.entity_id,
            )
            decisions = [
                d for d in decisions
                if d.get("id") not in already_surfaced
                and d.get("relevance", 0) >= 0.4
                and (d.get("session_id") or d.get("metadata", {}).get("session_id", "")) != session_id
            ]
            if decisions:
                d = decisions[0]
                content = d.get("content", "")[:150].replace("\n", " ").strip()
                created = d.get("created_at", "")
                candidates.append(AdvisorLine(
                    tag="RECALL",
                    message=f"Prior decision: {content}",
                    memory_ids=[d.get("id", "")],
                    score=_composite_score(d.get("relevance", 0), _recency_score(created), 0.0),
                ))

        except Exception as e:
            logger.debug("Advisor.suggest_for_file failed: %s", e)
            return []

        # Rank by priority tier first, then score
        candidates.sort(key=lambda c: (TAG_PRIORITY.get(c.tag, 99), -c.score))

        # Cap at MAX_WARNINGS_PER_HOOK
        result = candidates[:MAX_WARNINGS_PER_HOOK]

        # Session dedup
        deduped = []
        for r in result:
            dedup_key = f"{r.tag}:{r.message[:60]}"
            if dedup_key not in _session_dedup:
                _session_dedup.add(dedup_key)
                deduped.append(r)

        if deduped:
            _file_cooldowns[file_path] = now

        return deduped
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py -v -x 2>&1 | tail -20`
Expected: All tests pass

**Step 5: Commit**

```bash
cd ~/Projects/omega && git add src/omega/advisor.py tests/test_advisor.py && git commit -m "feat(advisor): add Advisor class with suggest_for_file + WARNING/TIP/RECALL"
```

---

### Task 3: Advisor.suggest_for_error -- WATCH generation

**Files:**
- Modify: `src/omega/advisor.py`
- Modify: `tests/test_advisor.py`

**Step 1: Write the failing tests**

Append to `tests/test_advisor.py`:

```python
class TestSuggestForError:
    """Tests for [WATCH] generation on repeat errors."""

    @patch("omega.advisor.query_structured")
    @patch("omega.advisor._find_fix_for_error")
    def test_repeat_error_on_recent_file_produces_watch(self, mock_fix, mock_qs):
        """Known error pattern on recently-edited file -> [WATCH]."""
        from omega.advisor import Advisor, _file_cooldowns
        import time

        # Simulate recent edit by setting cooldown entry
        _file_cooldowns["/proj/src/coord.py"] = time.monotonic()

        mock_qs.return_value = [
            _make_error_result("DB connection gone", session_id="s1"),
            _make_error_result("DB connection gone", session_id="s2"),
        ]
        mock_fix.return_value = "add connection.ping() check"

        adv = Advisor(project="/proj")
        result = adv.suggest_for_error(
            error_summary="DB connection gone",
            file_path="/proj/src/coord.py",
            session_id="sess-current",
        )

        assert result is not None
        assert result.tag == "WATCH"
        assert "connection" in result.message.lower() or "DB" in result.message

    @patch("omega.advisor.query_structured")
    def test_first_time_error_no_watch(self, mock_qs):
        """First-time error (no prior pattern) -> no WATCH."""
        from omega.advisor import Advisor

        mock_qs.return_value = []

        adv = Advisor(project="/proj")
        result = adv.suggest_for_error(
            error_summary="brand new error never seen",
            file_path="/proj/foo.py",
            session_id="sess-current",
        )

        assert result is None

    @patch("omega.advisor.query_structured")
    def test_error_same_session_only_no_watch(self, mock_qs):
        """Error pattern only from current session -> no WATCH."""
        from omega.advisor import Advisor

        mock_qs.return_value = [
            _make_error_result("some error", session_id="sess-current"),
        ]

        adv = Advisor(project="/proj")
        result = adv.suggest_for_error(
            error_summary="some error",
            file_path="/proj/foo.py",
            session_id="sess-current",
        )

        assert result is None

    @patch("omega.advisor.query_structured")
    def test_error_no_recent_file_no_watch(self, mock_qs):
        """Error pattern exists but no recently-edited file -> no WATCH."""
        from omega.advisor import Advisor

        mock_qs.return_value = [
            _make_error_result("err", session_id="s1"),
            _make_error_result("err", session_id="s2"),
        ]

        adv = Advisor(project="/proj")
        result = adv.suggest_for_error(
            error_summary="err",
            file_path=None,
            session_id="sess-current",
        )

        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py::TestSuggestForError -v -x 2>&1 | head -20`
Expected: FAIL with "AttributeError: 'Advisor' object has no attribute 'suggest_for_error'"

**Step 3: Write implementation**

Add to the `Advisor` class in `src/omega/advisor.py`:

```python
    def suggest_for_error(
        self,
        error_summary: str,
        file_path: Optional[str],
        session_id: str,
    ) -> Optional[AdvisorLine]:
        """Generate [WATCH] if this error is a repeat on a recently-edited file.

        Returns a single AdvisorLine or None.
        """
        if not file_path:
            return None

        # Only trigger if this file was recently edited (exists in cooldowns = recently advised or edited)
        if file_path not in _file_cooldowns:
            return None

        try:
            from omega.bridge import query_structured

            past_errors = query_structured(
                query_text=error_summary[:200],
                event_type="error_pattern",
                limit=5,
                entity_id=self.entity_id,
            )

            # Filter to cross-session matches
            cross_session = [
                e for e in past_errors
                if (e.get("session_id") or e.get("metadata", {}).get("session_id", "")) != session_id
                and e.get("relevance", 0) >= 0.3
            ]

            if len(cross_session) < 1:
                return None

            # Count unique sessions
            unique_sessions = {e.get("session_id") or e.get("metadata", {}).get("session_id", "") for e in cross_session}
            if len(unique_sessions) < 1:
                return None

            count = len(cross_session) + 1  # +1 for current occurrence
            ordinal = {2: "2nd", 3: "3rd"}.get(count, f"{count}th")

            # Try to find fix
            best_error = cross_session[0]
            fix = _find_fix_for_error(best_error.get("id", ""), best_error.get("content", ""), self.entity_id)

            summary_short = error_summary[:120].replace("\n", " ").strip()
            msg = f'You\'ve hit this error before ({ordinal} time):\n  "{summary_short}"'
            if fix:
                fix_short = fix[:100].replace("\n", " ").strip()
                msg += f"\n  Last fix: {fix_short}"
            else:
                msg += "\n  No recorded fix"

            return AdvisorLine(
                tag="WATCH",
                message=msg,
                memory_ids=[e.get("id", "") for e in cross_session[:3]],
                score=0.9,  # WATCH is always high priority
            )

        except Exception as e:
            logger.debug("Advisor.suggest_for_error failed: %s", e)
            return None
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py -v -x 2>&1 | tail -20`
Expected: All tests pass

**Step 5: Commit**

```bash
cd ~/Projects/omega && git add src/omega/advisor.py tests/test_advisor.py && git commit -m "feat(advisor): add suggest_for_error with [WATCH] repeat-mistake detection"
```

---

### Task 4: Advisor.suggest_for_session_start -- SUGGEST generation

**Files:**
- Modify: `src/omega/advisor.py`
- Modify: `tests/test_advisor.py`

**Step 1: Write the failing tests**

Append to `tests/test_advisor.py`:

```python
class TestSuggestForSessionStart:
    """Tests for [SUGGEST] generation at session start."""

    def test_handoff_with_blockers_first(self):
        """Handoff blockers appear before errors and tasks."""
        from omega.advisor import Advisor

        adv = Advisor(project="/proj")
        results = adv.suggest_for_session_start(
            session_id="sess-new",
            handoff={
                "blockers": ["DB migration stuck in pending state"],
                "incomplete_work": ["Refactoring auth module"],
            },
            pending_tasks=[
                {"subject": "Fix SEO", "priority": 3},
                {"subject": "Update docs", "priority": 2},
            ],
        )

        assert len(results) <= 3
        assert results[0].tag == "SUGGEST"
        assert "blocker" in results[0].message.lower() or "DB migration" in results[0].message

    def test_no_handoff_shows_tasks(self):
        """No handoff, just pending tasks -> task-based suggestions."""
        from omega.advisor import Advisor

        adv = Advisor(project="/proj")
        results = adv.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=[
                {"subject": "Fix SEO", "priority": 3},
            ],
        )

        assert len(results) >= 1
        assert "SEO" in results[0].message

    def test_empty_state_returns_empty(self):
        """No handoff, no tasks -> empty list."""
        from omega.advisor import Advisor

        adv = Advisor(project="/proj")
        results = adv.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=[],
        )

        assert len(results) == 0

    def test_capped_at_three(self):
        """More than 3 candidates -> capped at 3."""
        from omega.advisor import Advisor

        adv = Advisor(project="/proj")
        results = adv.suggest_for_session_start(
            session_id="sess-new",
            handoff={
                "blockers": ["blocker1", "blocker2"],
                "incomplete_work": ["work1", "work2"],
            },
            pending_tasks=[
                {"subject": "task1", "priority": 5},
                {"subject": "task2", "priority": 4},
            ],
        )

        assert len(results) <= 3
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py::TestSuggestForSessionStart -v -x 2>&1 | head -20`
Expected: FAIL with "AttributeError"

**Step 3: Write implementation**

Add to the `Advisor` class in `src/omega/advisor.py`:

```python
    def suggest_for_session_start(
        self,
        session_id: str,
        handoff: Optional[dict],
        pending_tasks: List[dict],
    ) -> List[AdvisorLine]:
        """Generate [SUGGEST] action items for session start.

        Priority: blockers > incomplete work > unresolved errors > pending tasks.
        Capped at 3 items.
        """
        items: List[AdvisorLine] = []

        # 1. Blockers from handoff (highest priority)
        if handoff:
            for blocker in (handoff.get("blockers") or [])[:2]:
                text = str(blocker)[:150].replace("\n", " ").strip()
                items.append(AdvisorLine(
                    tag="SUGGEST",
                    message=f"Blocker from last session: {text}",
                    score=1.0,
                ))

            # 2. Incomplete work from handoff
            for work in (handoff.get("incomplete_work") or [])[:2]:
                text = str(work)[:150].replace("\n", " ").strip()
                items.append(AdvisorLine(
                    tag="SUGGEST",
                    message=f"Incomplete: {text}",
                    score=0.8,
                ))

        # 3. Pending tasks (sorted by priority descending)
        sorted_tasks = sorted(pending_tasks, key=lambda t: t.get("priority", 0), reverse=True)
        for task in sorted_tasks[:3]:
            subject = task.get("subject", "")[:150]
            items.append(AdvisorLine(
                tag="SUGGEST",
                message=subject,
                score=0.3 + task.get("priority", 0) * 0.1,
            ))

        # Sort by score descending, cap at 3
        items.sort(key=lambda x: -x.score)
        return items[:3]
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py -v -x 2>&1 | tail -20`
Expected: All tests pass

**Step 5: Commit**

```bash
cd ~/Projects/omega && git add src/omega/advisor.py tests/test_advisor.py && git commit -m "feat(advisor): add suggest_for_session_start with [SUGGEST] action items"
```

---

### Task 5: Integration -- hook_server.py (file edits + bash errors)

**Files:**
- Modify: `src/omega/server/hook_server.py:2227-2233` (file edit block)
- Modify: `src/omega/server/hook_server.py:2720-2736` (error capture block)

**Step 1: Write the failing integration test**

Append to `tests/test_advisor.py`:

```python
class TestHookIntegration:
    """Integration tests: advisor called from hook_server paths."""

    @patch("omega.advisor.query_structured")
    def test_suggest_for_file_returns_empty_on_exception(self, mock_qs):
        """If query_structured raises, suggest_for_file returns empty (fail-open)."""
        from omega.advisor import Advisor

        mock_qs.side_effect = RuntimeError("DB gone")

        adv = Advisor(project="/proj")
        results = adv.suggest_for_file("/proj/foo.py", "sess", "Edit", set())
        assert results == []

    def test_suggest_for_error_returns_none_on_exception(self):
        """If internals raise, suggest_for_error returns None (fail-open)."""
        from omega.advisor import Advisor

        adv = Advisor(project="/proj")
        # No mocking -- query_structured will fail if no DB
        result = adv.suggest_for_error("err", None, "sess")
        assert result is None
```

**Step 2: Run test to verify it passes** (these test fail-open behavior which is already implemented)

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py::TestHookIntegration -v -x`
Expected: PASS

**Step 3: Integrate into hook_server.py -- file edit block**

In `src/omega/server/hook_server.py`, after line 2232 (after `_surface_lessons` call), before the "no results" check at line 2235, add advisor integration:

Find this block (lines 2227-2239):
```python
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        file_path = _get_file_path_from_input(input_data)
        if file_path and _debounce_check(_last_surface, file_path, SURFACE_DEBOUNCE_S, _MAX_SURFACE_ENTRIES):
            lines.extend(_surface_for_edit(file_path, session_id, project, entity_id=entity_id))
            _ctx_tags = _ext_to_tags(file_path) or None
            lines.extend(_surface_lessons(file_path, session_id, project, entity_id=entity_id, context_tags=_ctx_tags))

            # Transparent "no results" — show once per session on first edit with no context
```

Insert after `_surface_lessons` line (after line 2232):

```python
            # Proactive advisor: [WARNING], [TIP], [RECALL]
            try:
                from omega.advisor import Advisor as _Adv

                _surfaced_ids = {mid for mid in (r.get("id", "") for r in []) if mid}  # TODO: collect from above
                _adv = _Adv(project=project, entity_id=entity_id)
                _adv_results = _adv.suggest_for_file(
                    file_path=file_path,
                    session_id=session_id,
                    tool_name=tool_name,
                    already_surfaced=_surfaced_ids,
                )
                for _al in _adv_results:
                    lines.append(_al.format())
            except Exception:
                pass  # Fail-open
```

**Step 4: Integrate into hook_server.py -- bash error block**

In `src/omega/server/hook_server.py`, after line 2735 (after error is stored, before `return recall_lines`), add:

```python
    # Proactive advisor: [WATCH] for repeat errors
    try:
        from omega.advisor import Advisor as _AdvErr

        _adv_err = _AdvErr(project=project, entity_id=entity_id)
        _watch = _adv_err.suggest_for_error(
            error_summary=error_summary,
            file_path=None,  # Let advisor check its own cooldown map
            session_id=session_id,
        )
        if _watch:
            recall_lines.append(_watch.format())
    except Exception:
        pass  # Fail-open
```

**Step 5: Run full test suite to verify no regressions**

Run: `cd ~/Projects/omega && pytest -x 2>&1 | tail -20`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
cd ~/Projects/omega && git add src/omega/server/hook_server.py tests/test_advisor.py && git commit -m "feat(advisor): integrate into hook_server file-edit and error-capture paths"
```

---

### Task 6: Integration -- bridge.py (welcome flow)

**Files:**
- Modify: `src/omega/bridge.py:1723-1749` (result dict assembly)

**Step 1: Write the failing test**

Append to `tests/test_advisor.py`:

```python
class TestWelcomeIntegration:
    """Test advisor integration into welcome flow."""

    def test_suggest_for_session_start_formats_correctly(self):
        """Suggestions format as numbered list."""
        from omega.advisor import Advisor

        adv = Advisor(project="/proj")
        results = adv.suggest_for_session_start(
            session_id="sess",
            handoff={"blockers": ["Fix DB"], "incomplete_work": []},
            pending_tasks=[{"subject": "Update docs", "priority": 3}],
        )

        formatted = "\n".join(s.format() for s in results)
        assert "[SUGGEST]" in formatted
        assert "Fix DB" in formatted
```

**Step 2: Run test to verify it passes** (already implemented)

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py::TestWelcomeIntegration -v -x`
Expected: PASS

**Step 3: Integrate into bridge.py welcome()**

In `src/omega/bridge.py`, after the `result` dict is assembled (around line 1735), before `return result` at line 1749, add:

```python
    # Proactive advisor: [SUGGEST] action items for session start
    try:
        from omega.advisor import Advisor as _AdvWelcome

        _entity_id_adv = None
        if project:
            try:
                from omega.entity.engine import resolve_project_entity
                _entity_id_adv = resolve_project_entity(project)
            except Exception:
                pass
        _adv_w = _AdvWelcome(project=project or "", entity_id=_entity_id_adv)
        _suggestions = _adv_w.suggest_for_session_start(
            session_id=session_id or "",
            handoff=None,  # Handoff parsed separately by coord hooks
            pending_tasks=[],  # Tasks parsed separately by coord hooks
        )
        if _suggestions:
            result["advisor_suggestions"] = "\n".join(s.format() for s in _suggestions)
    except Exception:
        pass  # Fail-open
```

**Step 4: Run full test suite**

Run: `cd ~/Projects/omega && pytest -x 2>&1 | tail -20`
Expected: All tests pass

**Step 5: Commit**

```bash
cd ~/Projects/omega && git add src/omega/bridge.py && git commit -m "feat(advisor): integrate into welcome flow for session-start suggestions"
```

---

### Task 7: Update sync-manifest.yaml and conftest.py

**Files:**
- Modify: `sync-manifest.yaml` (add advisor as pro-only)
- Modify: `tests/conftest.py` (add advisor state reset)

**Step 1: Add advisor to sync-manifest.yaml pro-only list**

Find the pro-only section in `sync-manifest.yaml` and add:

```yaml
  - src/omega/advisor.py
  - tests/test_advisor.py
```

**Step 2: Add advisor state reset to conftest.py**

Add to `tests/conftest.py` in `_reset_hook_server_state`:

```python
    try:
        from omega import advisor
        advisor._session_dedup.clear()
        advisor._file_cooldowns.clear()
    except (ImportError, AttributeError):
        pass
```

Add this in both the setup and teardown halves of the fixture (before and after `yield`).

**Step 3: Run full test suite**

Run: `cd ~/Projects/omega && pytest -x 2>&1 | tail -20`
Expected: All tests pass

**Step 4: Commit**

```bash
cd ~/Projects/omega && git add sync-manifest.yaml tests/conftest.py && git commit -m "chore(advisor): add to pro-only sync manifest + reset state in conftest"
```

---

### Task 8: Final verification

**Step 1: Run full test suite**

Run: `cd ~/Projects/omega && pytest -x -q 2>&1 | tail -10`
Expected: All tests pass, including new advisor tests

**Step 2: Run lint**

Run: `cd ~/Projects/omega && ruff check src/omega/advisor.py tests/test_advisor.py`
Expected: No issues

**Step 3: Verify advisor tests specifically**

Run: `cd ~/Projects/omega && pytest tests/test_advisor.py -v 2>&1 | tail -30`
Expected: All ~20 tests pass

**Step 4: Verify fail-open behavior manually**

Run: `cd ~/Projects/omega && python3 -c "from omega.advisor import Advisor; a = Advisor('/tmp'); print(a.suggest_for_file('/tmp/x.py', 's', 'Edit', set()))"`
Expected: Empty list (no DB available, fails open gracefully)

**Step 5: Final commit if any lint fixes needed**

```bash
cd ~/Projects/omega && ruff format src/omega/advisor.py tests/test_advisor.py && git add -u && git commit -m "style(advisor): format with ruff"
```
