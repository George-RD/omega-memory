"""Tests for intelligence card output from memory hooks."""
import pytest
from datetime import datetime, timezone, timedelta


class TestFormatResultsAsCards:
    """Test _format_results_as_cards converts query results to [OMEGA] cards."""

    def test_memory_result_produces_used_card(self):
        from omega.server.hook_server.memory import _format_results_as_cards

        results = [
            {
                "id": "mem-abc",
                "content": "Always validate test fixtures",
                "relevance": 0.92,
                "event_type": "lesson_learned",
                "metadata": {"verified_count": 3, "project": "omega"},
                "last_accessed": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            },
        ]
        cards = _format_results_as_cards(results, session_id="s1", project="omega")
        assert len(cards) == 1
        assert cards[0].startswith("[OMEGA] Used:")
        assert "Always validate test fixtures" in cards[0]

    def test_error_pattern_produces_warning_card(self):
        from omega.server.hook_server.memory import _format_results_as_cards

        results = [
            {
                "id": "mem-def",
                "content": "Lock nesting causes hangs in threading code",
                "relevance": 0.88,
                "event_type": "error_pattern",
                "metadata": {"error_count": 3, "pattern": "lock nesting", "file": "coordination.py"},
                "last_accessed": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            },
        ]
        cards = _format_results_as_cards(results, session_id="s1")
        assert len(cards) == 1
        assert "[OMEGA]" in cards[0]
        assert "Warning" in cards[0]
        assert "lock nesting" in cards[0]

    def test_mixed_results_produce_mixed_cards(self):
        from omega.server.hook_server.memory import _format_results_as_cards

        results = [
            {
                "id": "mem-abc",
                "content": "Always validate fixtures",
                "relevance": 0.92,
                "event_type": "lesson_learned",
                "metadata": {"verified_count": 3},
            },
            {
                "id": "mem-def",
                "content": "Lock nesting causes hangs",
                "relevance": 0.88,
                "event_type": "error_pattern",
                "metadata": {"error_count": 2, "pattern": "lock nesting", "file": "store.py"},
            },
        ]
        cards = _format_results_as_cards(results, session_id="s1")
        assert len(cards) == 2
        assert all("[OMEGA]" in c for c in cards)

    def test_records_surfacing_in_card_tracker(self):
        from omega.server.hook_server.memory import _format_results_as_cards
        from omega.server.hook_server.card_tracker import get_card_tracker

        tracker = get_card_tracker()
        tracker.cleanup("test-session")

        results = [
            {
                "id": "mem-xyz",
                "content": "Test content for tracking",
                "relevance": 0.90,
                "event_type": "memory",
                "metadata": {},
            },
        ]
        _format_results_as_cards(results, session_id="test-session")
        ids = tracker.get_surfaced_ids("test-session")
        assert "mem-xyz" in ids
        tracker.cleanup("test-session")

    def test_empty_results_returns_empty(self):
        from omega.server.hook_server.memory import _format_results_as_cards

        cards = _format_results_as_cards([], session_id="s1")
        assert cards == []

    def test_result_without_id_still_produces_card(self):
        from omega.server.hook_server.memory import _format_results_as_cards

        results = [
            {
                "content": "Some insight without an ID",
                "relevance": 0.80,
                "event_type": "memory",
                "metadata": {},
            },
        ]
        cards = _format_results_as_cards(results)
        assert len(cards) == 1
        assert "[OMEGA] Used:" in cards[0]

    def test_verified_count_shown_in_card(self):
        from omega.server.hook_server.memory import _format_results_as_cards

        results = [
            {
                "id": "mem-v",
                "content": "Verified insight",
                "relevance": 0.85,
                "event_type": "lesson_learned",
                "metadata": {"verified_count": 5},
            },
        ]
        cards = _format_results_as_cards(results, session_id="s1")
        assert "verified 5x" in cards[0]

    def test_days_ago_shown_in_card(self):
        from omega.server.hook_server.memory import _format_results_as_cards

        results = [
            {
                "id": "mem-d",
                "content": "Recent insight",
                "relevance": 0.85,
                "event_type": "memory",
                "metadata": {},
                "last_accessed": datetime.now(timezone.utc).isoformat(),
            },
        ]
        cards = _format_results_as_cards(results)
        assert "today" in cards[0]


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


class TestSurfaceForEditUsesTransparency:
    """Test that _surface_for_edit dispatches to full cards at NORMAL+ transparency."""

    def test_tracker_normal_transparency_after_edits(self):
        """When tracker has enough complexity for NORMAL, transparency should be NORMAL."""
        from omega.server.hook_server.card_tracker import SessionCardTracker
        from omega.server.hook_server.cards import TransparencyLevel

        tracker = SessionCardTracker("test-transparency")
        tracker.record_edit("/a.py")
        tracker.record_edit("/b.py")  # 2 edits * 2.0 = 4.0 -> NORMAL
        assert tracker.transparency == TransparencyLevel.NORMAL
