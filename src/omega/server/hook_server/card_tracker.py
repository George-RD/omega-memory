"""Session card tracker -- complexity scoring, surfacing tracking, diff correlation.

Maintains per-session state for Intelligence Cards:
- Tracks files edited and errors encountered for complexity scoring
- Maps surfaced memory IDs to the files they were surfaced for (diff correlation)
- Records outcomes when git commits are detected
- Per-session counters for surfaced/used/lessons/contradictions (CardTracker)
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from .cards import TransparencyLevel, compute_transparency

logger = logging.getLogger("omega.hook_server.card_tracker")


class SessionCardTracker:
    """Per-session tracker for Intelligence Card state."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.files_edited: set[str] = set()
        self.edit_counts: dict[str, int] = {}  # per-file edit count for repeat-edit detection
        self.error_count: int = 0
        self.intent: str = ""
        self.has_prior_decisions: bool = False

        # Surfacing tracking: memory_id -> set of file_paths it was surfaced for
        self.surfaced_file_map: dict[str, set[str]] = {}

        # Outcome tracking: memory_id -> outcome ("positive", "weak_negative", None)
        self.outcomes: dict[str, Optional[str]] = {}

        # Card type tracking for Thompson bandit
        self.card_type_surfacings: dict[str, int] = {
            "memory": 0,
            "decisions": 0,
            "learned": 0,
            "warning": 0,
        }

    @property
    def transparency(self) -> TransparencyLevel:
        """Compute current transparency level from session state."""
        return compute_transparency(
            files_edited=len(self.files_edited),
            error_count=self.error_count,
            intent=self.intent,
            has_prior_decisions=self.has_prior_decisions,
        )

    def record_edit(self, file_path: str) -> None:
        """Record a file edit for complexity scoring."""
        self.files_edited.add(file_path)
        self.edit_counts[file_path] = self.edit_counts.get(file_path, 0) + 1

    def record_error(self) -> None:
        """Record an error for complexity scoring."""
        self.error_count += 1

    def record_surfacing(self, memory_id: str, file_path: str, card_type: str = "memory") -> None:
        """Record that a memory was surfaced for a specific file."""
        if memory_id not in self.surfaced_file_map:
            self.surfaced_file_map[memory_id] = set()
        self.surfaced_file_map[memory_id].add(file_path)

        if card_type in self.card_type_surfacings:
            self.card_type_surfacings[card_type] += 1

    def record_decisions_seen(self) -> None:
        """Mark that prior decisions were found, escalating complexity."""
        self.has_prior_decisions = True

    def correlate_with_diff(self, committed_files: list[str]) -> dict:
        """Correlate surfaced memories with committed files.

        For each surfaced memory:
        - If it was surfaced for a committed file: positive outcome (2x weight)
        - If surfaced for a non-committed file but committed file exists: weak negative (0.5x)
        - If surfaced file wasn't committed at all: no signal (may commit later)

        Returns:
            dict with 'positive', 'weak_negative', 'no_signal' counts
            and 'outcomes' mapping memory_id -> outcome string
        """
        committed_set = set(committed_files)
        positive = 0
        weak_negative = 0
        no_signal = 0

        for memory_id, surfaced_files in self.surfaced_file_map.items():
            # Check if any surfaced file was committed
            has_committed = bool(surfaced_files & committed_set)
            # Check if ANY file was committed (session is producing output)
            session_has_commits = len(committed_set) > 0

            if has_committed:
                self.outcomes[memory_id] = "positive"
                positive += 1
            elif session_has_commits:
                self.outcomes[memory_id] = "weak_negative"
                weak_negative += 1
            else:
                # No commits yet, can't determine
                no_signal += 1

        return {
            "positive": positive,
            "weak_negative": weak_negative,
            "no_signal": no_signal,
            "outcomes": dict(self.outcomes),
        }

    def get_outcome_stats(self) -> dict:
        """Get summary stats for session card display."""
        total = len(self.surfaced_file_map)
        correlated = sum(1 for o in self.outcomes.values() if o == "positive")
        return {
            "diff_correlated": correlated,
            "diff_total": total,
            "files_edited": len(self.files_edited),
            "error_count": self.error_count,
            "card_surfacings": dict(self.card_type_surfacings),
        }


# ---------------------------------------------------------------------------
# CardTracker -- lightweight per-session counters for compact [OMEGA] cards
# ---------------------------------------------------------------------------


@dataclass
class _SessionCards:
    surfaced_ids: Set[str] = field(default_factory=set)
    surfaced_content: Dict[str, str] = field(default_factory=dict)  # id -> content preview
    used_ids: Set[str] = field(default_factory=set)
    lessons_captured: int = 0
    contradictions: int = 0
    repeated_mistakes: int = 0


class CardTracker:
    """Track intelligence card activity per session. Thread-safe."""

    def __init__(self) -> None:
        self._sessions: Dict[str, _SessionCards] = {}
        self._lock = threading.Lock()

    def _get(self, session_id: str) -> _SessionCards:
        if session_id not in self._sessions:
            self._sessions[session_id] = _SessionCards()
        return self._sessions[session_id]

    def record_surfaced(self, session_id: str, memory_id: str, content: str) -> None:
        with self._lock:
            sc = self._get(session_id)
            sc.surfaced_ids.add(memory_id)
            sc.surfaced_content[memory_id] = content[:200]

    def record_used(self, session_id: str, memory_id: str) -> None:
        with self._lock:
            self._get(session_id).used_ids.add(memory_id)

    def record_lesson(self, session_id: str) -> None:
        with self._lock:
            self._get(session_id).lessons_captured += 1

    def record_contradiction(self, session_id: str) -> None:
        with self._lock:
            self._get(session_id).contradictions += 1

    def record_repeated_mistake(self, session_id: str) -> None:
        with self._lock:
            self._get(session_id).repeated_mistakes += 1

    def get_surfaced_ids(self, session_id: str) -> Set[str]:
        with self._lock:
            return set(self._get(session_id).surfaced_ids)

    def get_surfaced_content_map(self, session_id: str) -> Dict[str, str]:
        """Return {memory_id: content_preview} for all surfaced memories."""
        with self._lock:
            return dict(self._get(session_id).surfaced_content)

    def get_surfaced_content(self, session_id: str) -> str:
        with self._lock:
            return " ".join(self._get(session_id).surfaced_content.values())

    def get_stats(self, session_id: str) -> dict:
        with self._lock:
            sc = self._get(session_id)
            return {
                "memories_surfaced": len(sc.surfaced_ids),
                "memories_used": len(sc.used_ids),
                "lessons_captured": sc.lessons_captured,
                "contradictions": sc.contradictions,
                "repeated_mistakes": sc.repeated_mistakes,
            }

    def cleanup(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


# Module-level singleton
_tracker = CardTracker()


def get_card_tracker() -> CardTracker:
    return _tracker
