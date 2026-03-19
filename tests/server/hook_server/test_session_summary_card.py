"""Tests for session summary intelligence card."""
import pytest
from omega.server.hook_server.card_tracker import CardTracker


class TestSessionSummaryCard:
    def test_summary_card_from_tracker_stats(self):
        from omega.server.hook_server.cards import format_session_summary_card

        card = format_session_summary_card(
            memories_surfaced=12,
            memories_used=8,
            lessons_captured=3,
            contradictions=1,
            repeated_mistakes=0,
            verified_lessons_this_week=2,
        )
        assert "[OMEGA] Session intelligence:" in card
        assert "12 memories surfaced" in card
        assert "8 used" in card

    def test_build_summary_from_tracker(self):
        """Integration test: build summary card from actual tracker state."""
        from omega.server.hook_server.cards import format_session_summary_card

        tracker = CardTracker()
        tracker.record_surfaced("test-session", "mem-1", "content 1")
        tracker.record_surfaced("test-session", "mem-2", "content 2")
        tracker.record_surfaced("test-session", "mem-3", "content 3")
        tracker.record_used("test-session", "mem-1")
        tracker.record_used("test-session", "mem-2")
        tracker.record_lesson("test-session")

        stats = tracker.get_stats("test-session")
        card = format_session_summary_card(
            memories_surfaced=stats["memories_surfaced"],
            memories_used=stats["memories_used"],
            lessons_captured=stats["lessons_captured"],
            contradictions=stats["contradictions"],
            repeated_mistakes=stats["repeated_mistakes"],
            verified_lessons_this_week=0,
        )
        assert "3 memories surfaced" in card
        assert "2 used" in card
        assert "1 new lessons" in card

    def test_zero_activity_still_produces_card(self):
        from omega.server.hook_server.cards import format_session_summary_card

        card = format_session_summary_card(
            memories_surfaced=0,
            memories_used=0,
            lessons_captured=0,
            contradictions=0,
            repeated_mistakes=0,
            verified_lessons_this_week=0,
        )
        assert "[OMEGA]" in card


class TestSessionStopEmitsCompactSummary:
    """Verify session stop handler includes compact summary card."""

    def test_emit_summary_card_on_session_stop(self):
        """When CardTracker has activity, session stop should include compact summary."""
        from omega.server.hook_server.card_tracker import get_card_tracker

        tracker = get_card_tracker()
        tracker.cleanup("summary-test")
        tracker.record_surfaced("summary-test", "mem-1", "test content")
        tracker.record_lesson("summary-test")

        from omega.server.hook_server.session import _build_compact_summary_card
        card = _build_compact_summary_card("summary-test")

        assert card is not None
        assert "[OMEGA] Session intelligence:" in card
        assert "1 memories surfaced" in card
        tracker.cleanup("summary-test")

    def test_no_summary_when_no_activity(self):
        """When CardTracker has no activity, no compact summary should be emitted."""
        from omega.server.hook_server.card_tracker import get_card_tracker

        tracker = get_card_tracker()
        tracker.cleanup("empty-test")

        from omega.server.hook_server.session import _build_compact_summary_card
        card = _build_compact_summary_card("empty-test")

        assert card is None
        tracker.cleanup("empty-test")
