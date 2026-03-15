"""Tests for learning card output from assistant capture."""
import pytest
from unittest.mock import patch


class TestLearningCardOutput:
    def test_lesson_capture_produces_learning_card(self):
        from omega.server.hook_server.cards import format_compact_learning_card

        card = format_compact_learning_card(
            content="threading.Lock is non-reentrant -- never nest",
            event_type="lesson_learned",
        )
        assert "[OMEGA] Learned:" in card
        assert "threading.Lock" in card

    def test_decision_capture_produces_decision_card(self):
        from omega.server.hook_server.cards import format_compact_learning_card

        card = format_compact_learning_card(
            content="Going with approach B for caching",
            event_type="decision",
        )
        assert "[OMEGA] Captured decision:" in card


class TestAssistantCaptureEmitsCompactCards:
    """Verify handle_assistant_capture returns compact [OMEGA] cards."""

    def _make_payload(self, message: str, session_id: str = "test-session") -> dict:
        return {
            "last_assistant_message": message,
            "session_id": session_id,
            "project": "/test/project",
        }

    @patch("omega.bridge.auto_capture")
    def test_fix_capture_produces_omega_card(self, mock_capture):
        from omega.server.hook_server.assistant import handle_assistant_capture
        from omega.server.hook_server import _assistant_capture_count

        _assistant_capture_count.pop("test-fix", None)
        # Message with a fix pattern, long enough to pass quality gate
        msg = "x" * 200 + "\nThe fix was updating the timeout value from 30 to 60 seconds which resolved the connection drops entirely."
        result = handle_assistant_capture(self._make_payload(msg, "test-fix"))
        output = result.get("output", "")
        assert "[OMEGA]" in output
        _assistant_capture_count.pop("test-fix", None)

    @patch("omega.bridge.auto_capture")
    def test_decision_capture_produces_omega_card(self, mock_capture):
        from omega.server.hook_server.assistant import handle_assistant_capture
        from omega.server.hook_server import _assistant_capture_count

        _assistant_capture_count.pop("test-dec", None)
        msg = "x" * 200 + "\nI decided to use Redis instead of Memcached because it supports pub/sub and has better persistence options for our workload."
        result = handle_assistant_capture(self._make_payload(msg, "test-dec"))
        output = result.get("output", "")
        assert "[OMEGA]" in output
        _assistant_capture_count.pop("test-dec", None)

    @patch("omega.bridge.auto_capture")
    def test_lesson_recorded_in_card_tracker(self, mock_capture):
        from omega.server.hook_server.assistant import handle_assistant_capture
        from omega.server.hook_server.card_tracker import get_card_tracker
        from omega.server.hook_server import _assistant_capture_count

        tracker = get_card_tracker()
        tracker.cleanup("test-lesson-track")
        _assistant_capture_count.pop("test-lesson-track", None)

        msg = "x" * 200 + "\nThe root cause was a missing null check in the parser that caused the crash on empty input strings from the API."
        handle_assistant_capture(self._make_payload(msg, "test-lesson-track"))

        stats = tracker.get_stats("test-lesson-track")
        assert stats["lessons_captured"] >= 1
        tracker.cleanup("test-lesson-track")
        _assistant_capture_count.pop("test-lesson-track", None)


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
