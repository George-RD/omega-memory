"""Tests for outcome tracking of intelligence cards."""
import pytest
from omega.server.hook_server.card_tracker import CardTracker


class TestOutcomeDetection:
    def test_detect_used_memory(self):
        from omega.server.hook_server.assistant import _detect_used_memories

        surfaced_content = {
            "mem-abc": "Always validate test fixtures before running",
            "mem-def": "Always use python3.11 explicitly for running omega tests",
        }
        response = "I validated the test fixtures first, then ran the omega tests with python3.11 explicitly."
        used = _detect_used_memories(response, surfaced_content)
        assert "mem-abc" in used
        assert "mem-def" in used

    def test_detect_ignored_memory(self):
        from omega.server.hook_server.assistant import _detect_used_memories

        surfaced_content = {
            "mem-abc": "Always validate test fixtures before running",
        }
        response = "I updated the README with the new installation instructions."
        used = _detect_used_memories(response, surfaced_content)
        assert "mem-abc" not in used

    def test_outcome_tracking_updates_tracker(self):
        from omega.server.hook_server.assistant import _track_outcomes

        tracker = CardTracker()
        tracker.record_surfaced("s1", "mem-abc", "validate fixtures before running tests")
        tracker.record_surfaced("s1", "mem-def", "use python3.11 explicitly")

        response = "I validated the fixtures as recommended before running."
        _track_outcomes("s1", response, tracker)

        stats = tracker.get_stats("s1")
        assert stats["memories_used"] >= 1

    def test_empty_surfaced_content_is_noop(self):
        from omega.server.hook_server.assistant import _track_outcomes

        tracker = CardTracker()
        # No surfaced memories recorded
        _track_outcomes("s1", "some response", tracker)
        stats = tracker.get_stats("s1")
        assert stats["memories_used"] == 0

    def test_detect_partial_overlap_below_threshold(self):
        from omega.server.hook_server.assistant import _detect_used_memories

        surfaced_content = {
            "mem-abc": "Always validate test fixtures before running the full integration suite end to end",
        }
        # Only 1 keyword match out of many - below 40% threshold
        response = "I ran a quick test."
        used = _detect_used_memories(response, surfaced_content)
        assert "mem-abc" not in used
