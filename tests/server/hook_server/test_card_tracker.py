"""Tests for per-session intelligence card tracking."""
import pytest
from omega.server.hook_server.card_tracker import CardTracker


class TestCardTracker:
    def test_record_surfaced(self):
        tracker = CardTracker()
        tracker.record_surfaced("session-1", "mem-abc", "Always validate fixtures")
        stats = tracker.get_stats("session-1")
        assert stats["memories_surfaced"] == 1

    def test_record_used(self):
        tracker = CardTracker()
        tracker.record_surfaced("session-1", "mem-abc", "validate fixtures")
        tracker.record_used("session-1", "mem-abc")
        stats = tracker.get_stats("session-1")
        assert stats["memories_used"] == 1

    def test_record_lesson_captured(self):
        tracker = CardTracker()
        tracker.record_lesson("session-1")
        tracker.record_lesson("session-1")
        stats = tracker.get_stats("session-1")
        assert stats["lessons_captured"] == 2

    def test_record_contradiction(self):
        tracker = CardTracker()
        tracker.record_contradiction("session-1")
        stats = tracker.get_stats("session-1")
        assert stats["contradictions"] == 1

    def test_get_surfaced_memory_ids(self):
        tracker = CardTracker()
        tracker.record_surfaced("session-1", "mem-abc", "content a")
        tracker.record_surfaced("session-1", "mem-def", "content b")
        ids = tracker.get_surfaced_ids("session-1")
        assert ids == {"mem-abc", "mem-def"}

    def test_get_surfaced_content(self):
        tracker = CardTracker()
        tracker.record_surfaced("session-1", "mem-abc", "validate fixtures")
        content = tracker.get_surfaced_content("session-1")
        assert "validate fixtures" in content

    def test_get_surfaced_content_map(self):
        tracker = CardTracker()
        tracker.record_surfaced("session-1", "mem-abc", "validate fixtures")
        tracker.record_surfaced("session-1", "mem-def", "use python3.11")
        content_map = tracker.get_surfaced_content_map("session-1")
        assert content_map == {"mem-abc": "validate fixtures", "mem-def": "use python3.11"}

    def test_cleanup(self):
        tracker = CardTracker()
        tracker.record_surfaced("session-1", "mem-abc", "content")
        tracker.cleanup("session-1")
        stats = tracker.get_stats("session-1")
        assert stats["memories_surfaced"] == 0

    def test_empty_stats(self):
        tracker = CardTracker()
        stats = tracker.get_stats("nonexistent")
        assert stats["memories_surfaced"] == 0
        assert stats["memories_used"] == 0
        assert stats["lessons_captured"] == 0
        assert stats["contradictions"] == 0
        assert stats["repeated_mistakes"] == 0
