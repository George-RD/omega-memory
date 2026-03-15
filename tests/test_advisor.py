"""Tests for the OMEGA Proactive Advisor module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import patch

import pytest

from omega.advisor import (
    MAX_WARNINGS_PER_HOOK,
    TAG_PRIORITY,
    Advisor,
    AdvisorLine,
    _composite_score,
    _extract_co_edited_files,
    _file_cooldowns,
    _recency_score,
    _session_dedup,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_advisor_state():
    """Clear module-level state before and after each test."""
    _session_dedup.clear()
    _file_cooldowns.clear()
    yield
    _session_dedup.clear()
    _file_cooldowns.clear()


# ---------------------------------------------------------------------------
# Helpers: create mock query results
# ---------------------------------------------------------------------------


def _make_error_result(
    content: str = "TypeError: cannot read property 'x' of undefined",
    session_id: str = "sess-old-1",
    relevance: float = 0.7,
    memory_id: str = "mem-err-1",
    created_at: str | None = None,
) -> dict:
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    return {
        "id": memory_id,
        "content": content,
        "event_type": "error_pattern",
        "session_id": session_id,
        "created_at": created_at,
        "tags": [],
        "metadata": {"event_type": "error_pattern", "session_id": session_id},
        "relevance": relevance,
    }


def _make_lesson_result(
    content: str = "Always check for null before accessing properties",
    session_id: str = "sess-old-2",
    relevance: float = 0.5,
    memory_id: str = "mem-lesson-1",
    created_at: str | None = None,
) -> dict:
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    return {
        "id": memory_id,
        "content": content,
        "event_type": "lesson_learned",
        "session_id": session_id,
        "created_at": created_at,
        "tags": [],
        "metadata": {"event_type": "lesson_learned", "session_id": session_id},
        "relevance": relevance,
    }


def _make_decision_result(
    content: str = "Decided to use strict null checks in tsconfig",
    session_id: str = "sess-old-3",
    relevance: float = 0.6,
    memory_id: str = "mem-dec-1",
    created_at: str | None = None,
) -> dict:
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    return {
        "id": memory_id,
        "content": content,
        "event_type": "decision",
        "session_id": session_id,
        "created_at": created_at,
        "tags": [],
        "metadata": {"event_type": "decision", "session_id": session_id},
        "relevance": relevance,
    }


# ============================================================================
# Task 1: AdvisorLine dataclass and scoring helpers
# ============================================================================


class TestAdvisorLine:
    """Tests for AdvisorLine dataclass."""

    def test_format(self):
        line = AdvisorLine(tag="WARNING", message="Something broke")
        assert line.format() == "[WARNING] Something broke"

    def test_format_with_tip(self):
        line = AdvisorLine(tag="TIP", message="Try this approach")
        assert line.format() == "[TIP] Try this approach"

    def test_default_fields(self):
        line = AdvisorLine(tag="RECALL", message="Past decision")
        assert line.memory_ids == []
        assert line.score == 0.0

    def test_sorting_by_score(self):
        lines = [
            AdvisorLine(tag="WARNING", message="low", score=0.2),
            AdvisorLine(tag="WARNING", message="high", score=0.9),
            AdvisorLine(tag="WARNING", message="mid", score=0.5),
        ]
        sorted_lines = sorted(lines, key=lambda l: -l.score)
        assert sorted_lines[0].message == "high"
        assert sorted_lines[1].message == "mid"
        assert sorted_lines[2].message == "low"


class TestRecencyScore:
    """Tests for _recency_score."""

    def test_recent(self):
        """Memories less than 7 days old score 1.0."""
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        assert _recency_score(recent) == 1.0

    def test_mid(self):
        """Memories between 7 and 30 days old score 0.5."""
        mid = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        assert _recency_score(mid) == 0.5

    def test_old(self):
        """Memories older than 30 days score 0.2."""
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        assert _recency_score(old) == 0.2

    def test_z_suffix(self):
        """Handles ISO strings ending with Z."""
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _recency_score(recent) == 1.0

    def test_empty_string(self):
        assert _recency_score("") == 0.2

    def test_invalid_string(self):
        assert _recency_score("not-a-date") == 0.2


class TestCompositeScore:
    """Tests for _composite_score."""

    def test_equal_weights(self):
        # 1.0 * 0.4 + 1.0 * 0.3 + 1.0 * 0.3 = 1.0
        assert _composite_score(1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_zero(self):
        assert _composite_score(0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_mixed(self):
        # 0.8 * 0.4 + 0.5 * 0.3 + 0.3 * 0.3 = 0.32 + 0.15 + 0.09 = 0.56
        assert _composite_score(0.8, 0.5, 0.3) == pytest.approx(0.56)


class TestTagPriority:
    """Verify TAG_PRIORITY ordering."""

    def test_warning_highest(self):
        assert TAG_PRIORITY["WARNING"] < TAG_PRIORITY["TIP"]

    def test_order(self):
        ordered = sorted(TAG_PRIORITY, key=TAG_PRIORITY.get)
        assert ordered == ["GATE", "WARNING", "WATCH", "RECALL", "SUGGEST", "TIP", "COEDIT", "THEME"]


# ============================================================================
# Task 2: Advisor.suggest_for_file
# ============================================================================


class TestSuggestForFileWarnings:
    """Tests for Advisor.suggest_for_file WARNING generation."""

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_multi_session_errors_produce_warning(self, mock_fix, mock_qs):
        """Errors seen in 2+ other sessions produce a WARNING."""
        error_content = "ImportError: cannot import name 'foo'"
        # Three results with same content but different sessions (all != current)
        mock_qs.side_effect = [
            # error_pattern query
            [
                _make_error_result(content=error_content, session_id="sess-a", memory_id="e1"),
                _make_error_result(content=error_content, session_id="sess-b", memory_id="e2"),
                _make_error_result(content=error_content, session_id="sess-c", memory_id="e3"),
            ],
            # lesson_learned query
            [],
            # decision query
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/main.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        warnings = [l for l in lines if l.tag == "WARNING"]
        assert len(warnings) >= 1
        assert "error pattern" in warnings[0].message.lower()
        assert warnings[0].memory_ids  # Has source IDs

    @patch("omega.bridge.query_structured")
    def test_single_session_no_warning(self, mock_qs):
        """Errors from only one other session do not produce a WARNING."""
        mock_qs.side_effect = [
            # error_pattern query - only 1 other session
            [
                _make_error_result(session_id="sess-a", memory_id="e1"),
            ],
            # lesson_learned query
            [],
            # decision query
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/main.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        warnings = [l for l in lines if l.tag == "WARNING"]
        assert len(warnings) == 0

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_already_surfaced_excluded(self, mock_fix, mock_qs):
        """Memories in already_surfaced are filtered out."""
        error_content = "ValueError: invalid literal"
        mock_qs.side_effect = [
            # error_pattern query - all have same ID that's already surfaced
            [
                _make_error_result(content=error_content, session_id="sess-a", memory_id="e-surfaced"),
                _make_error_result(content=error_content, session_id="sess-b", memory_id="e-surfaced-2"),
            ],
            [],
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/main.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced={"e-surfaced", "e-surfaced-2"},
        )

        warnings = [l for l in lines if l.tag == "WARNING"]
        assert len(warnings) == 0

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_cooldown_prevents_repeat(self, mock_fix, mock_qs):
        """After advising on a file, no advice within cooldown period."""
        error_content = "RuntimeError: something failed"
        results = [
            _make_error_result(content=error_content, session_id="sess-a", memory_id="e1"),
            _make_error_result(content=error_content, session_id="sess-b", memory_id="e2"),
            _make_error_result(content=error_content, session_id="sess-c", memory_id="e3"),
        ]

        mock_qs.side_effect = [results, [], []]

        advisor = Advisor(project="/test/project")
        file = "/test/project/src/handler.py"

        # First call should produce results
        lines1 = advisor.suggest_for_file(
            file_path=file,
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )
        assert len(lines1) > 0

        # Second call (within cooldown) should return empty
        mock_qs.side_effect = [results, [], []]
        lines2 = advisor.suggest_for_file(
            file_path=file,
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )
        assert len(lines2) == 0

    @patch("omega.bridge.query_structured")
    def test_errors_from_current_session_excluded(self, mock_qs):
        """Errors only from the current session are not counted."""
        error_content = "KeyError: 'missing_key'"
        mock_qs.side_effect = [
            [
                _make_error_result(content=error_content, session_id="sess-current", memory_id="e1"),
                _make_error_result(content=error_content, session_id="sess-current", memory_id="e2"),
            ],
            [],
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/main.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        warnings = [l for l in lines if l.tag == "WARNING"]
        assert len(warnings) == 0


class TestSuggestForFileTips:
    """Tests for TIP generation from lesson_learned memories."""

    @patch("omega.bridge.query_structured")
    def test_lesson_produces_tip(self, mock_qs):
        """Relevant lessons from other sessions produce TIPs."""
        mock_qs.side_effect = [
            # error_pattern
            [],
            # lesson_learned
            [
                _make_lesson_result(
                    content="Use explicit type annotations for clarity",
                    session_id="sess-old",
                    relevance=0.6,
                    memory_id="les-1",
                ),
            ],
            # decision
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/utils.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        tips = [l for l in lines if l.tag == "TIP"]
        assert len(tips) == 1
        assert "type annotations" in tips[0].message

    @patch("omega.bridge.query_structured")
    def test_low_relevance_lesson_excluded(self, mock_qs):
        """Lessons with relevance < 0.3 are not surfaced."""
        mock_qs.side_effect = [
            [],
            [
                _make_lesson_result(relevance=0.1, memory_id="les-low"),
            ],
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/utils.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        tips = [l for l in lines if l.tag == "TIP"]
        assert len(tips) == 0

    @patch("omega.bridge.query_structured")
    def test_max_two_tips(self, mock_qs):
        """At most 2 TIPs are generated."""
        mock_qs.side_effect = [
            [],
            [
                _make_lesson_result(memory_id="les-1", session_id="s1", relevance=0.5),
                _make_lesson_result(memory_id="les-2", session_id="s2", relevance=0.5),
                _make_lesson_result(memory_id="les-3", session_id="s3", relevance=0.5),
            ],
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/utils.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        tips = [l for l in lines if l.tag == "TIP"]
        assert len(tips) <= 2


class TestSuggestForFileRecall:
    """Tests for RECALL generation from decision memories."""

    @patch("omega.bridge.query_structured")
    def test_decision_produces_recall(self, mock_qs):
        """Relevant decisions from other sessions produce RECALL."""
        mock_qs.side_effect = [
            [],
            [],
            [
                _make_decision_result(
                    content="Decided to use pydantic for validation",
                    session_id="sess-old",
                    relevance=0.7,
                    memory_id="dec-1",
                ),
            ],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/models.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        recalls = [l for l in lines if l.tag == "RECALL"]
        assert len(recalls) == 1
        assert "pydantic" in recalls[0].message

    @patch("omega.bridge.query_structured")
    def test_low_relevance_decision_excluded(self, mock_qs):
        """Decisions with relevance < 0.4 are not surfaced."""
        mock_qs.side_effect = [
            [],
            [],
            [
                _make_decision_result(relevance=0.2, memory_id="dec-low"),
            ],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/models.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        recalls = [l for l in lines if l.tag == "RECALL"]
        assert len(recalls) == 0


class TestSuggestForFileSorting:
    """Tests for sorting and capping behavior."""

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_capped_at_max_warnings(self, mock_fix, mock_qs):
        """Total advisory lines capped at MAX_WARNINGS_PER_HOOK."""
        error_content = "SomeError"
        # Create many errors with different content to generate multiple WARNINGs
        errors = []
        for i in range(5):
            c = f"Error type {i}: something went wrong in module {i}"
            for sid in [f"sess-a{i}", f"sess-b{i}", f"sess-c{i}"]:
                errors.append(_make_error_result(content=c, session_id=sid, memory_id=f"e-{i}-{sid}"))

        mock_qs.side_effect = [
            errors,
            [
                _make_lesson_result(memory_id="les-1", session_id="s1", relevance=0.5),
            ],
            [
                _make_decision_result(memory_id="dec-1", session_id="s2", relevance=0.6),
            ],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/big_module.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        assert len(lines) <= MAX_WARNINGS_PER_HOOK

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_warnings_sorted_before_tips(self, mock_fix, mock_qs):
        """WARNINGs appear before TIPs in the output."""
        error_content = "ConnectionError: timeout"
        mock_qs.side_effect = [
            [
                _make_error_result(content=error_content, session_id="sess-a", memory_id="e1"),
                _make_error_result(content=error_content, session_id="sess-b", memory_id="e2"),
                _make_error_result(content=error_content, session_id="sess-c", memory_id="e3"),
            ],
            [
                _make_lesson_result(memory_id="les-1", session_id="s-old", relevance=0.5),
            ],
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/network.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        if len(lines) >= 2:
            tags = [l.tag for l in lines]
            # WARNINGs should come before TIPs
            warning_indices = [i for i, t in enumerate(tags) if t == "WARNING"]
            tip_indices = [i for i, t in enumerate(tags) if t == "TIP"]
            if warning_indices and tip_indices:
                assert max(warning_indices) < min(tip_indices)


class TestSuggestForFileFixIntegration:
    """Tests for fix text inclusion in WARNINGs."""

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value="Add null check before access")
    def test_fix_text_included_in_warning(self, mock_fix, mock_qs):
        """When a fix is found, it's appended to the WARNING message."""
        error_content = "NullPointerException in handler"
        mock_qs.side_effect = [
            [
                _make_error_result(content=error_content, session_id="sess-a", memory_id="e1"),
                _make_error_result(content=error_content, session_id="sess-b", memory_id="e2"),
                _make_error_result(content=error_content, session_id="sess-c", memory_id="e3"),
            ],
            [],
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_file(
            file_path="/test/project/src/handler.py",
            session_id="sess-current",
            tool_name="edit_file",
            already_surfaced=set(),
        )

        warnings = [l for l in lines if l.tag == "WARNING"]
        assert len(warnings) == 1
        assert "fix:" in warnings[0].message.lower()
        assert "null check" in warnings[0].message.lower()


# ============================================================================
# Task 3: Advisor.suggest_for_error (WATCH)
# ============================================================================


class TestSuggestForError:
    """Tests for Advisor.suggest_for_error WATCH generation."""

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value="Use try/except around the call")
    def test_repeat_error_on_recent_file_produces_watch(self, mock_fix, mock_qs):
        """Repeat error on a recently edited file produces a WATCH advisory."""
        import time

        _file_cooldowns["/test/project/src/main.py"] = time.monotonic()

        mock_qs.return_value = [
            _make_error_result(
                content="TypeError: NoneType",
                session_id="sess-old-1",
                relevance=0.5,
                memory_id="e1",
            ),
            _make_error_result(
                content="TypeError: NoneType",
                session_id="sess-old-2",
                relevance=0.6,
                memory_id="e2",
            ),
        ]

        advisor = Advisor(project="/test/project")
        result = advisor.suggest_for_error(
            error_summary="TypeError: NoneType has no attribute 'x'",
            file_path="/test/project/src/main.py",
            session_id="sess-current",
        )

        assert result is not None
        assert result.tag == "WATCH"
        assert "[WATCH]" in result.format()
        assert result.score == 0.9
        assert "Fix:" in result.message

    @patch("omega.bridge.query_structured")
    def test_first_time_error_no_watch(self, mock_qs):
        """First-time error (no matches) does not produce a WATCH."""
        import time

        _file_cooldowns["/test/project/src/main.py"] = time.monotonic()

        mock_qs.return_value = []

        advisor = Advisor(project="/test/project")
        result = advisor.suggest_for_error(
            error_summary="BrandNewError: never seen before",
            file_path="/test/project/src/main.py",
            session_id="sess-current",
        )

        assert result is None

    @patch("omega.bridge.query_structured")
    def test_error_same_session_only_no_watch(self, mock_qs):
        """Errors only from the current session do not produce a WATCH."""
        import time

        _file_cooldowns["/test/project/src/main.py"] = time.monotonic()

        mock_qs.return_value = [
            _make_error_result(
                content="SomeError",
                session_id="sess-current",
                relevance=0.7,
                memory_id="e1",
            ),
        ]

        advisor = Advisor(project="/test/project")
        result = advisor.suggest_for_error(
            error_summary="SomeError: happened again",
            file_path="/test/project/src/main.py",
            session_id="sess-current",
        )

        assert result is None

    @mock.patch("omega.bridge.query_structured")
    def test_error_no_recent_file_still_queries(self, mock_qs):
        """Error on a file NOT in _file_cooldowns still queries for cross-session matches."""
        mock_qs.return_value = []  # No cross-session matches

        advisor = Advisor(project="/test/project")
        result = advisor.suggest_for_error(
            error_summary="SomeError: something",
            file_path="/test/project/src/not_recently_edited.py",
            session_id="sess-current",
        )

        assert result is None
        mock_qs.assert_called_once()

    @mock.patch("omega.bridge.query_structured")
    def test_error_no_file_path_still_queries(self, mock_qs):
        """Error with file_path=None still queries for cross-session matches."""
        mock_qs.return_value = []  # No cross-session matches

        advisor = Advisor(project="/test/project")
        result = advisor.suggest_for_error(
            error_summary="SomeError: something",
            file_path=None,
            session_id="sess-current",
        )

        assert result is None
        mock_qs.assert_called_once()


# ============================================================================
# Task 4: Advisor.suggest_for_session_start (SUGGEST)
# ============================================================================


class TestSuggestForSessionStart:
    """Tests for Advisor.suggest_for_session_start SUGGEST generation."""

    def test_handoff_with_blockers_first(self):
        """Blockers from handoff appear before task-based suggestions."""
        handoff = {
            "blockers": ["CI is broken on main"],
            "incomplete_work": ["Refactor auth module"],
        }
        tasks = [
            {"subject": "Update docs", "priority": 2},
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=handoff,
            pending_tasks=tasks,
        )

        assert len(lines) >= 1
        assert lines[0].tag == "SUGGEST"
        # Blocker has score 1.0, should be first
        assert "Blocker from last session:" in lines[0].message
        assert "CI is broken" in lines[0].message
        # Incomplete work (score 0.8) should come before tasks (score ~0.5)
        if len(lines) >= 2:
            assert "Incomplete:" in lines[1].message

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters", return_value=[])
    @mock.patch("omega.behavioral.BehavioralAnalyzer.generate_recommendations", return_value=[])
    def test_no_handoff_shows_tasks(self, _mock_recs, _mock_clusters):
        """Without a handoff, pending tasks are surfaced."""
        tasks = [
            {"subject": "Fix login bug", "priority": 5},
            {"subject": "Add tests", "priority": 3},
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=tasks,
        )

        assert len(lines) == 2
        # Higher priority task should come first (score = 0.3 + 5*0.1 = 0.8)
        assert "Fix login bug" in lines[0].message
        assert "Add tests" in lines[1].message

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters", return_value=[])
    @mock.patch("omega.behavioral.BehavioralAnalyzer.generate_recommendations", return_value=[])
    @mock.patch("omega.bridge.query_structured")
    def test_empty_state_self_queries(self, mock_qs, _mock_recs, _mock_clusters):
        """No handoff and no tasks triggers self-query for recent data."""
        mock_qs.return_value = []

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=[],
        )

        assert lines == []
        # Self-query should have been called (errors + decisions)
        assert mock_qs.call_count == 2

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters", return_value=[])
    @mock.patch("omega.behavioral.BehavioralAnalyzer.generate_recommendations", return_value=[])
    @mock.patch("omega.bridge.query_structured")
    def test_empty_state_surfaces_recent_errors(self, mock_qs, _mock_recs, _mock_clusters):
        """Self-query surfaces recent unresolved errors when no handoff/tasks."""
        mock_qs.side_effect = [
            # First call: error_pattern query
            [
                {
                    "id": "err-1",
                    "content": "Error: ConnectionRefused on deploy",
                    "session_id": "sess-old",
                    "relevance": 0.5,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
            # Second call: decision query
            [],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=[],
        )

        assert len(lines) == 1
        assert lines[0].tag == "SUGGEST"
        assert "Recent error" in lines[0].message

    def test_capped_at_three(self):
        """Many candidates are capped at 3 results."""
        handoff = {
            "blockers": ["Blocker 1", "Blocker 2"],
            "incomplete_work": ["Incomplete 1", "Incomplete 2"],
        }
        tasks = [
            {"subject": "Task 1", "priority": 5},
            {"subject": "Task 2", "priority": 3},
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=handoff,
            pending_tasks=tasks,
        )

        assert len(lines) <= 3


# ============================================================================
# Task 5: _extract_co_edited_files helper
# ============================================================================


class TestExtractCoEditedFiles:
    """Tests for _extract_co_edited_files helper."""

    def test_standard_format(self):
        content = "Committed abc1234: Add feature. Files: bridge.py, sqlite_store.py, handlers.py"
        assert _extract_co_edited_files(content) == ["bridge.py", "sqlite_store.py", "handlers.py"]

    def test_with_overflow(self):
        content = "Committed abc1234: Refactor. Files: a.py, b.py, c.py +3"
        assert _extract_co_edited_files(content) == ["a.py", "b.py", "c.py"]

    def test_single_file(self):
        content = "Committed abc1234: Fix. Files: main.py"
        assert _extract_co_edited_files(content) == ["main.py"]

    def test_no_files_section(self):
        content = "Some random decision without file listing"
        assert _extract_co_edited_files(content) == []

    def test_empty_string(self):
        assert _extract_co_edited_files("") == []


# ============================================================================
# Task 6: Advisor.suggest_co_edits (COEDIT)
# ============================================================================


class _FakeMemoryResult:
    """Minimal stand-in for MemoryResult returned by sqlite_store.phrase_search."""

    def __init__(self, content: str, node_id: str = "m1"):
        self.content = content
        self.id = node_id


class TestCoEditWarnings:
    """Tests for Advisor.suggest_co_edits COEDIT generation."""

    @patch("omega.bridge._get_store")
    def test_co_edited_file_suggested(self, mock_get_store):
        """Files appearing in 2+ commits with the target file produce COEDIT."""
        store = mock_get_store.return_value
        store.phrase_search.return_value = [
            _FakeMemoryResult("Committed aaa: X. Files: bridge.py, sqlite_store.py"),
            _FakeMemoryResult("Committed bbb: Y. Files: bridge.py, sqlite_store.py, handlers.py"),
            _FakeMemoryResult("Committed ccc: Z. Files: bridge.py, sqlite_store.py"),
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_co_edits(
            file_path="/test/project/src/bridge.py",
            session_edited_files=set(),
        )

        assert len(lines) >= 1
        coedit_lines = [l for l in lines if l.tag == "COEDIT"]
        assert len(coedit_lines) >= 1
        assert "sqlite_store.py" in coedit_lines[0].message
        assert coedit_lines[0].score == 0.5

    @patch("omega.bridge._get_store")
    def test_single_commit_not_enough(self, mock_get_store):
        """Files appearing in only 1 commit are not suggested."""
        store = mock_get_store.return_value
        store.phrase_search.return_value = [
            _FakeMemoryResult("Committed aaa: X. Files: bridge.py, rare_file.py"),
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_co_edits(
            file_path="/test/project/src/bridge.py",
            session_edited_files=set(),
        )

        assert len(lines) == 0

    @patch("omega.bridge._get_store")
    def test_already_edited_files_excluded(self, mock_get_store):
        """Files already edited this session are excluded from suggestions."""
        store = mock_get_store.return_value
        store.phrase_search.return_value = [
            _FakeMemoryResult("Committed aaa: X. Files: bridge.py, sqlite_store.py"),
            _FakeMemoryResult("Committed bbb: Y. Files: bridge.py, sqlite_store.py"),
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_co_edits(
            file_path="/test/project/src/bridge.py",
            session_edited_files={"/test/project/src/sqlite_store.py"},
        )

        assert len(lines) == 0

    @patch("omega.bridge._get_store")
    def test_max_two_coedit_lines(self, mock_get_store):
        """At most 2 COEDIT lines are returned."""
        store = mock_get_store.return_value
        store.phrase_search.return_value = [
            _FakeMemoryResult("Committed a: X. Files: main.py, a.py, b.py, c.py"),
            _FakeMemoryResult("Committed b: Y. Files: main.py, a.py, b.py, c.py"),
            _FakeMemoryResult("Committed c: Z. Files: main.py, a.py, b.py, c.py"),
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_co_edits(
            file_path="/test/project/src/main.py",
            session_edited_files=set(),
        )

        assert len(lines) <= 2

    @patch("omega.bridge._get_store")
    def test_session_dedup(self, mock_get_store):
        """Same co-edit suggestion is not repeated within a session."""
        store = mock_get_store.return_value
        store.phrase_search.return_value = [
            _FakeMemoryResult("Committed a: X. Files: bridge.py, sqlite_store.py"),
            _FakeMemoryResult("Committed b: Y. Files: bridge.py, sqlite_store.py"),
        ]

        advisor = Advisor(project="/test/project")
        lines1 = advisor.suggest_co_edits(
            file_path="/test/project/src/bridge.py",
            session_edited_files=set(),
        )
        lines2 = advisor.suggest_co_edits(
            file_path="/test/project/src/bridge.py",
            session_edited_files=set(),
        )

        assert len(lines1) == 1
        assert len(lines2) == 0  # Deduped

    @patch("omega.bridge._get_store")
    def test_no_results_returns_empty(self, mock_get_store):
        """No matching commit memories returns empty list."""
        store = mock_get_store.return_value
        store.phrase_search.return_value = []

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_co_edits(
            file_path="/test/project/src/new_file.py",
            session_edited_files=set(),
        )

        assert lines == []


# ============================================================================
# Task 7: Advisor.suggest_pre_deploy (GATE)
# ============================================================================


class TestPreDeployGate:
    """Tests for Advisor.suggest_pre_deploy GATE generation."""

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_unresolved_errors_produce_gate(self, mock_fix, mock_qs):
        """Files with unresolved errors from other sessions produce a GATE."""
        import time

        _file_cooldowns["/test/project/src/coordination.py"] = time.monotonic()
        _file_cooldowns["/test/project/src/hook_server.py"] = time.monotonic()

        mock_qs.side_effect = [
            # coordination.py errors
            [
                _make_error_result(
                    content="DB connection timeout",
                    session_id="sess-old",
                    relevance=0.6,
                    memory_id="e1",
                ),
            ],
            # hook_server.py errors
            [
                _make_error_result(
                    content="TypeError: unexpected None",
                    session_id="sess-old-2",
                    relevance=0.5,
                    memory_id="e2",
                ),
            ],
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_pre_deploy(session_id="sess-current", commit_hash="abc1234")

        assert len(lines) == 1
        gate = lines[0]
        assert gate.tag == "GATE"
        assert gate.score == 0.95
        assert "2 files" in gate.message
        assert "unresolved errors" in gate.message

    @patch("omega.bridge.query_structured")
    def test_no_errors_no_gate(self, mock_qs):
        """Files with no error patterns produce no GATE."""
        import time

        _file_cooldowns["/test/project/src/clean.py"] = time.monotonic()

        mock_qs.return_value = []

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_pre_deploy(session_id="sess-current", commit_hash="def5678")

        assert lines == []

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value="Use try/except")
    def test_resolved_errors_no_gate(self, mock_fix, mock_qs):
        """Errors with known fixes are not flagged."""
        import time

        _file_cooldowns["/test/project/src/fixed.py"] = time.monotonic()

        mock_qs.return_value = [
            _make_error_result(
                content="Some error that was fixed",
                session_id="sess-old",
                relevance=0.6,
                memory_id="e1",
            ),
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_pre_deploy(session_id="sess-current", commit_hash="ghi9012")

        assert lines == []

    def test_no_edited_files_no_gate(self):
        """No files in _file_cooldowns means no GATE."""
        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_pre_deploy(session_id="sess-current", commit_hash="jkl3456")

        assert lines == []

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_commit_hash_dedup(self, mock_fix, mock_qs):
        """Same commit hash does not produce duplicate GATE."""
        import time

        _file_cooldowns["/test/project/src/main.py"] = time.monotonic()

        mock_qs.return_value = [
            _make_error_result(
                content="Error in main",
                session_id="sess-old",
                relevance=0.6,
                memory_id="e1",
            ),
        ]

        advisor = Advisor(project="/test/project")
        lines1 = advisor.suggest_pre_deploy(session_id="sess-current", commit_hash="same123")
        assert len(lines1) == 1

        # Reset mock for second call
        mock_qs.return_value = [
            _make_error_result(
                content="Error in main",
                session_id="sess-old",
                relevance=0.6,
                memory_id="e1",
            ),
        ]
        lines2 = advisor.suggest_pre_deploy(session_id="sess-current", commit_hash="same123")
        assert lines2 == []  # Deduped

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_current_session_errors_excluded(self, mock_fix, mock_qs):
        """Errors from the current session are not flagged."""
        import time

        _file_cooldowns["/test/project/src/main.py"] = time.monotonic()

        mock_qs.return_value = [
            _make_error_result(
                content="Error from this session",
                session_id="sess-current",
                relevance=0.6,
                memory_id="e1",
            ),
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_pre_deploy(session_id="sess-current", commit_hash="mno7890")

        assert lines == []

    @patch("omega.bridge.query_structured")
    @patch("omega.advisor._find_fix_for_error", return_value=None)
    def test_single_file_grammar(self, mock_fix, mock_qs):
        """Single file uses singular grammar."""
        import time

        _file_cooldowns["/test/project/src/only.py"] = time.monotonic()

        mock_qs.return_value = [
            _make_error_result(
                content="Some error",
                session_id="sess-old",
                relevance=0.6,
                memory_id="e1",
            ),
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_pre_deploy(session_id="sess-current", commit_hash="pqr1234")

        assert len(lines) == 1
        assert "1 file" in lines[0].message
        assert "has" in lines[0].message


# ============================================================================
# Phase 4: Behavioral TIP in session start
# ============================================================================


class TestSessionStartBehavioralTip:
    """Tests for behavioral insight surfacing at session start."""

    @mock.patch("omega.behavioral.BehavioralAnalyzer.generate_recommendations")
    def test_session_start_includes_behavioral_tip(self, mock_recs):
        """Behavioral TIP appears when room exists and recommendations available."""
        mock_recs.return_value = [
            {
                "id": "long_sessions",
                "recommendation": "Your sessions average over an hour. Consider taking breaks.",
                "category": "productivity",
                "based_on": ["session_avg_duration"],
            }
        ]

        # Provide a task so self-queries (steps 3/4) are skipped
        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=[{"subject": "Low priority task", "priority": 1}],
        )

        tip_lines = [l for l in lines if l.tag == "TIP"]
        assert len(tip_lines) == 1
        assert "sessions average" in tip_lines[0].message
        assert tip_lines[0].score == 0.4

    def test_behavioral_tip_only_when_room(self):
        """Behavioral TIP excluded when 3 higher-priority items exist."""
        handoff = {
            "blockers": ["Blocker 1", "Blocker 2"],
            "incomplete_work": ["Incomplete 1"],
        }

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=handoff,
            pending_tasks=[],
        )

        # 3 items from handoff fill up the slots
        assert len(lines) == 3
        tip_lines = [l for l in lines if l.tag == "TIP"]
        assert len(tip_lines) == 0

    @mock.patch("omega.behavioral.BehavioralAnalyzer.generate_recommendations")
    def test_behavioral_failure_doesnt_break_welcome(self, mock_recs):
        """If behavioral analyzer raises, session start still works."""
        mock_recs.side_effect = RuntimeError("DB connection failed")

        tasks = [
            {"subject": "Fix login bug", "priority": 5},
            {"subject": "Another task", "priority": 3},
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=tasks,
        )

        # Should still get the task suggestions despite behavioral failure
        assert len(lines) >= 1
        assert any("Fix login bug" in l.message for l in lines)

    @mock.patch("omega.behavioral.BehavioralAnalyzer.generate_recommendations")
    def test_behavioral_tip_truncated_at_150(self, mock_recs):
        """Behavioral TIP message is truncated to 150 chars."""
        long_rec = "A" * 200
        mock_recs.return_value = [
            {
                "id": "test",
                "recommendation": long_rec,
                "category": "test",
                "based_on": ["test"],
            }
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=[{"subject": "Placeholder task", "priority": 1}],
        )

        tip_lines = [l for l in lines if l.tag == "TIP"]
        assert len(tip_lines) == 1
        assert len(tip_lines[0].message) == 150


# ============================================================================
# THEME advisory tests (cluster pattern intelligence)
# ============================================================================


class TestThemeAdvisories:
    """Tests for cluster-based THEME advisories."""

    def test_theme_in_tag_priority(self):
        """THEME tag exists in TAG_PRIORITY with lowest priority."""
        assert "THEME" in TAG_PRIORITY
        assert TAG_PRIORITY["THEME"] > TAG_PRIORITY["COEDIT"]

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    def test_theme_fires_on_keyword_overlap(self, mock_clusters):
        """THEME advisory fires when 2+ keywords overlap with cluster."""
        mock_clusters.return_value = [
            {
                "cluster_id": 0,
                "label": "threading & concurrency",
                "member_count": 15,
                "keywords": "threading, concurrency, lock, mutex",
                "representative_memory_ids": ["n1"],
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor._get_theme_advisories({"threading", "lock", "other"})

        assert len(lines) == 1
        assert lines[0].tag == "THEME"
        assert "threading & concurrency" in lines[0].message
        assert "15 memories" in lines[0].message

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    def test_theme_requires_two_keywords_by_default(self, mock_clusters):
        """THEME requires 2+ keyword matches by default; single keyword is not enough."""
        mock_clusters.return_value = [
            {
                "cluster_id": 0,
                "label": "threading",
                "member_count": 10,
                "keywords": "threading, concurrency, lock",
                "representative_memory_ids": [],
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor._get_theme_advisories({"threading", "unrelated"})

        assert len(lines) == 0

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    def test_theme_min_overlap_1_fires_on_single_keyword(self, mock_clusters):
        """THEME fires with 1 keyword match when min_overlap=1."""
        mock_clusters.return_value = [
            {
                "cluster_id": 0,
                "label": "database patterns",
                "member_count": 12,
                "keywords": "database, sqlite, migration",
                "representative_memory_ids": [],
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor._get_theme_advisories({"database", "unrelated"}, min_overlap=1)

        assert len(lines) == 1
        assert "database patterns" in lines[0].message

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    def test_theme_matches_label_words(self, mock_clusters):
        """THEME matches against cluster label words, not just keywords."""
        mock_clusters.return_value = [
            {
                "cluster_id": 0,
                "label": "concurrency & threading",
                "member_count": 15,
                "keywords": "lock, mutex, deadlock",
                "representative_memory_ids": [],
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

        advisor = Advisor(project="/test/project")
        # "concurrency" is in label, "lock" is in keywords
        lines = advisor._get_theme_advisories({"concurrency", "lock"})

        assert len(lines) == 1
        assert "concurrency & threading" in lines[0].message

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    def test_theme_respects_limit(self, mock_clusters):
        """THEME advisory respects the limit parameter."""
        mock_clusters.return_value = [
            {
                "cluster_id": i,
                "label": f"theme-{i}",
                "member_count": 10,
                "keywords": "alpha, beta, gamma, delta",
                "representative_memory_ids": [],
                "created_at": "2026-01-01T00:00:00Z",
            }
            for i in range(5)
        ]

        advisor = Advisor(project="/test/project")
        lines = advisor._get_theme_advisories({"alpha", "beta", "gamma"}, limit=2)
        assert len(lines) <= 2

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    def test_theme_graceful_on_exception(self, mock_clusters):
        """THEME returns empty list if PatternLearner raises."""
        mock_clusters.side_effect = RuntimeError("DB error")

        advisor = Advisor(project="/test/project")
        lines = advisor._get_theme_advisories({"threading", "lock"})
        assert lines == []

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    @mock.patch("omega.bridge.query_structured")
    def test_theme_in_suggest_for_file(self, mock_query, mock_clusters):
        """THEME advisory appears in suggest_for_file output."""
        mock_query.return_value = []  # No error/lesson/decision results
        mock_clusters.return_value = [
            {
                "cluster_id": 0,
                "label": "sqlite & database",
                "member_count": 12,
                # Use keywords that overlap with filename parts
                "keywords": "sqlite, database, store, migration",
                "representative_memory_ids": [],
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

        advisor = Advisor(project="/test/project")
        # Use path where filename + dirname produce 2+ overlapping keywords
        lines = advisor.suggest_for_file(
            file_path="/test/project/sqlite/database.py",
            session_id="sess-current",
            tool_name="Edit",
        )

        theme_lines = [l for l in lines if l.tag == "THEME"]
        assert len(theme_lines) == 1
        assert "sqlite & database" in theme_lines[0].message

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    def test_theme_in_suggest_for_session_start(self, mock_clusters):
        """THEME advisory fires at session start with path keyword + min_overlap=1."""
        mock_clusters.return_value = [
            {
                "cluster_id": 0,
                "label": "omega & memory",
                "member_count": 20,
                "keywords": "omega, memory, store, query",
                "representative_memory_ids": [],
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

        advisor = Advisor(project="/test/projects/omega")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=[{"subject": "Fix bug", "priority": 3}],
        )

        theme_lines = [l for l in lines if l.tag == "THEME"]
        # "omega" from path matches "omega" in cluster keywords, with min_overlap=1
        assert len(theme_lines) == 1
        assert "omega & memory" in theme_lines[0].message

    @mock.patch("omega.pattern_learner.PatternLearner.get_active_clusters")
    def test_theme_session_start_splits_hyphenated_path(self, mock_clusters):
        """Session start splits hyphenated project names for better matching."""
        mock_clusters.return_value = [
            {
                "cluster_id": 0,
                "label": "database optimization",
                "member_count": 8,
                "keywords": "database, query, index, optimization",
                "representative_memory_ids": [],
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

        # "my-database-app" splits into {my, database, app}
        advisor = Advisor(project="/test/projects/my-database-app")
        lines = advisor.suggest_for_session_start(
            session_id="sess-new",
            handoff=None,
            pending_tasks=[{"subject": "Fix bug", "priority": 3}],
        )

        theme_lines = [l for l in lines if l.tag == "THEME"]
        assert len(theme_lines) == 1
        assert "database optimization" in theme_lines[0].message
