"""Tests for compact intelligence card formatting."""
import pytest
from omega.server.hook_server.cards import (
    format_compact_memory_card as format_memory_card,
    format_decision_trail_card,
    format_compact_learning_card as format_learning_card,
    format_compact_warning_card as format_warning_card,
    format_session_summary_card,
)


class TestMemoryCard:
    def test_basic_memory_card(self):
        card = format_memory_card(
            content="Always validate test fixtures before running",
            verified_count=4,
            last_accessed_days=2,
            project="omega",
        )
        assert "[OMEGA] Used:" in card
        assert "Always validate test fixtures" in card
        assert "verified 4x" in card
        assert "2d ago" in card
        assert "project: omega" in card

    def test_unverified_memory_card(self):
        card = format_memory_card(
            content="Some new insight",
            verified_count=0,
            last_accessed_days=0,
            project="omega",
        )
        assert "verified" not in card
        assert "today" in card or "0d" in card

    def test_truncates_long_content(self):
        card = format_memory_card(
            content="x" * 200,
            verified_count=1,
            last_accessed_days=5,
        )
        # Card content should be truncated to ~120 chars
        lines = card.strip().split("\n")
        assert len(lines[0]) < 160


class TestDecisionTrailCard:
    def test_basic_decision_trail(self):
        decisions = [
            {"date": "Feb 15", "content": "Coordination is PRO-ONLY", "status": "active"},
            {"date": "Feb 13", "content": "Hide pro until 100+ stars", "status": "active"},
        ]
        card = format_decision_trail_card(topic="sync policy", decisions=decisions)
        assert "[OMEGA] Prior decisions" in card
        assert "sync policy" in card
        assert "Feb 15" in card
        assert "Coordination is PRO-ONLY" in card
        assert "consistent" in card.lower()

    def test_empty_decisions(self):
        card = format_decision_trail_card(topic="new topic", decisions=[])
        assert card == ""  # No card if no prior decisions


class TestLearningCard:
    def test_basic_learning_card(self):
        card = format_learning_card(
            content="threading.Lock is non-reentrant -- never nest",
            event_type="lesson_learned",
        )
        assert "[OMEGA] Learned:" in card
        assert "threading.Lock" in card
        assert "verify in future sessions" in card

    def test_decision_learning_card(self):
        card = format_learning_card(
            content="Going with approach B for caching",
            event_type="decision",
        )
        assert "[OMEGA] Captured decision:" in card


class TestWarningCard:
    def test_basic_warning_card(self):
        card = format_warning_card(
            filename="coordination.py",
            error_count=3,
            pattern="lock nesting",
            last_fix_session="abc123",
            last_fix_date="Feb 20",
        )
        assert "[OMEGA]" in card
        assert "Warning" in card or "warning" in card.lower()
        assert "coordination.py" in card
        assert "3 prior errors" in card
        assert "lock nesting" in card

    def test_single_error_warning(self):
        card = format_warning_card(
            filename="store.py",
            error_count=1,
            pattern="timeout",
        )
        assert "1 prior error" in card  # singular


class TestSessionSummaryCard:
    def test_basic_summary(self):
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
        assert "3 new lessons" in card

    def test_zero_activity_summary(self):
        card = format_session_summary_card(
            memories_surfaced=0,
            memories_used=0,
            lessons_captured=0,
            contradictions=0,
            repeated_mistakes=0,
            verified_lessons_this_week=0,
        )
        # Should still produce a card (shows OMEGA was watching)
        assert "[OMEGA]" in card
