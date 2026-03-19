"""
OMEGA Proactive Advisor -- surfaces contextual warnings, tips, and recalls.

Analyzes the user's current context (file being edited, errors encountered,
session start) and proactively surfaces relevant memories as advisory lines.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

logger = logging.getLogger("omega.advisor")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TAG_PRIORITY: Dict[str, int] = {
    "GATE": -1,
    "WARNING": 0,
    "WATCH": 1,
    "RECALL": 2,
    "SUGGEST": 3,
    "TIP": 4,
    "COEDIT": 5,
    "THEME": 6,
}

MAX_WARNINGS_PER_HOOK = 3

COOLDOWN_SECONDS = 600.0  # 10 minutes

# ---------------------------------------------------------------------------
# Module-level state (reset between tests via _reset_advisor_state)
# ---------------------------------------------------------------------------

_MAX_DEDUP_ENTRIES = 10_000

_session_dedup: Set[str] = set()
_file_cooldowns: Dict[str, float] = {}


def _prune_file_cooldowns() -> None:
    """Remove expired entries from _file_cooldowns."""
    now = time.monotonic()
    expired = [k for k, v in _file_cooldowns.items() if (now - v) >= COOLDOWN_SECONDS]
    for k in expired:
        del _file_cooldowns[k]


def _check_dedup(key: str) -> bool:
    """Check if key is already in dedup set. If not, add it. Returns True if new."""
    global _session_dedup
    if key in _session_dedup:
        return False
    if len(_session_dedup) >= _MAX_DEDUP_ENTRIES:
        _session_dedup = set()
    _session_dedup.add(key)
    return True

# ---------------------------------------------------------------------------
# AdvisorLine dataclass
# ---------------------------------------------------------------------------


@dataclass
class AdvisorLine:
    """A single advisory line to surface to the user."""

    tag: str
    message: str
    memory_ids: List[str] = field(default_factory=list)
    score: float = 0.0

    def format(self) -> str:
        """Format the advisory line for display."""
        return f"[{self.tag}] {self.message}"


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _recency_score(created_at_iso: str) -> float:
    """Score a memory by its age: 1.0 if <7d, 0.5 if <30d, 0.2 otherwise."""
    if not created_at_iso:
        return 0.2
    try:
        # Handle "Z" suffix and parse ISO format
        iso = created_at_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        # Make offset-aware if naive
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days = (now - dt).total_seconds() / 86400.0
        if days < 7:
            return 1.0
        if days < 30:
            return 0.5
        return 0.2
    except (ValueError, TypeError):
        return 0.2


def _composite_score(relevance: float, recency: float, frequency: float) -> float:
    """Weighted composite: 40% relevance, 30% recency, 30% frequency."""
    return relevance * 0.4 + recency * 0.3 + frequency * 0.3


# ---------------------------------------------------------------------------
# Fix-finding helper
# ---------------------------------------------------------------------------


def _find_fix_for_error(
    error_id: str,
    error_content: str,
    entity_id: Optional[str] = None,
) -> Optional[str]:
    """Try to find a fix for an error via graph traversal, then semantic fallback.

    Returns fix text or None.
    """
    # 1. Graph traversal: look for resolved_by / related_to edges
    try:
        from omega.bridge import _get_store

        store = _get_store()
        chain = store.get_related_chain(
            error_id,
            max_hops=2,
            edge_types=["resolved_by", "related_to"],
        )
        for node in chain:
            content = node.get("content", "")
            etype = (node.get("metadata") or {}).get("event_type", "")
            if etype in ("lesson_learned", "decision") and content:
                return content[:200]
    except Exception:
        logger.debug("Graph traversal failed for error %s", error_id, exc_info=True)

    # 2. Semantic fallback: query for lessons related to the error content
    try:
        from omega.bridge import query_structured

        results = query_structured(
            query_text=f"fix for: {error_content[:120]}",
            event_type="lesson_learned",
            limit=3,
            entity_id=entity_id,
        )
        for r in results:
            rel = r.get("relevance", 0.0)
            if rel >= 0.4 and r.get("content"):
                return r["content"][:200]
    except Exception:
        logger.debug("Semantic fallback failed for error %s", error_id, exc_info=True)

    return None


# ---------------------------------------------------------------------------
# Co-edit extraction helper
# ---------------------------------------------------------------------------


def _extract_co_edited_files(content: str) -> List[str]:
    """Extract filenames from commit memory content.

    Parses patterns like "Files: a.py, b.py, c.py" or "Files: a.py, b.py +3"
    from auto-captured commit decision memories.
    """
    match = re.search(r"Files:\s*(.+?)(?:\s*\+\d+)?$", content, re.MULTILINE)
    if not match:
        return []
    raw = match.group(1).strip()
    files = [f.strip() for f in raw.split(",") if f.strip()]
    return files


# ---------------------------------------------------------------------------
# Advisor class
# ---------------------------------------------------------------------------


class Advisor:
    """Proactive advisor that surfaces contextual memories."""

    def __init__(self, project: str, entity_id: Optional[str] = None):
        self.project = project
        self.entity_id = entity_id

    def _get_theme_advisories(
        self,
        context_keywords: Set[str],
        limit: int = 2,
        min_overlap: int = 2,
    ) -> List[AdvisorLine]:
        """Surface cluster themes when context overlaps with cluster keywords.

        Args:
            min_overlap: Minimum keyword overlap to trigger a match.
                Use 2 for file-level context (rich keywords), 1 for session-start
                (sparse path-only keywords).
        """
        try:
            from omega.pattern_learner import PatternLearner
            learner = PatternLearner()
            clusters = learner.get_active_clusters()
        except Exception as e:
            logger.debug("Cluster loading for theme advisories failed: %s", e)
            return []

        advisories: List[AdvisorLine] = []
        for cluster in clusters:
            # Match against both representative_keywords and label words
            raw_kws = cluster.get("keywords") or ""
            cluster_kws = {k.strip().lower() for k in raw_kws.split(",") if k.strip()}
            label = cluster.get("label", "")
            label_words = {w.lower() for w in label.replace("&", " ").split() if len(w) >= 3}
            all_cluster_kws = cluster_kws | label_words
            overlap = context_keywords & all_cluster_kws
            if len(overlap) >= min_overlap:
                label = cluster.get("label", "unknown")
                count = cluster.get("member_count", 0)
                overlap_display = ", ".join(sorted(overlap)[:4])
                confidence = min(len(overlap) / 4, 1.0)
                advisories.append(
                    AdvisorLine(
                        tag="THEME",
                        message=f"Related theme: '{label}' ({count} memories). Keywords: {overlap_display}",
                        score=confidence * 0.5,
                    )
                )

        advisories.sort(key=lambda a: -a.score)
        return advisories[:limit]

    def suggest_for_file(
        self,
        file_path: str,
        session_id: str,
        tool_name: str,
        already_surfaced: Optional[Set[str]] = None,
    ) -> List[AdvisorLine]:
        """Generate advisory lines for a file being edited.

        Returns WARNING for recurring errors, TIP for lessons learned,
        and RECALL for relevant past decisions.
        """
        from omega.bridge import query_structured

        if already_surfaced is None:
            already_surfaced = set()

        now = time.monotonic()

        # --- Prune expired cooldowns to bound memory ---
        _prune_file_cooldowns()

        # --- Cooldown check ---
        if file_path in _file_cooldowns and (now - _file_cooldowns[file_path]) < COOLDOWN_SECONDS:
            return []

        lines: List[AdvisorLine] = []

        # Derive search terms from file path
        parts = file_path.rsplit("/", 2)
        filename = parts[-1] if parts else file_path
        dirname = parts[-2] if len(parts) >= 2 else ""
        query_text = f"{filename} {dirname}".strip()

        # --- 1. Error patterns (WARNING) ---
        try:
            error_results = query_structured(
                query_text=query_text,
                event_type="error_pattern",
                context_file=file_path,
                limit=10,
                entity_id=self.entity_id,
            )
        except Exception:
            logger.debug("Error query failed for %s", file_path, exc_info=True)
            error_results = []

        # Filter out already_surfaced and current-session errors
        error_results = [
            r
            for r in error_results
            if r.get("id") not in already_surfaced
            and (r.get("session_id", "") or (r.get("metadata") or {}).get("session_id", "")) != session_id
        ]

        # Need 2+ error patterns from other sessions to warrant a WARNING
        if len(error_results) >= 2:
            # Dedup by content[:80] for display
            seen_content: Set[str] = set()
            error_lines_parts = []
            all_ids = []
            for r in error_results:
                content = r.get("content", "")
                content_key = content[:80].lower().strip()
                if content_key in seen_content:
                    continue
                seen_content.add(content_key)

                eid = r.get("id", "")
                all_ids.append(eid)
                fix = _find_fix_for_error(eid, content, entity_id=self.entity_id)
                short = content[:100].replace("\n", " ").strip()
                if fix:
                    error_lines_parts.append(f"  - {short} -- fix: {fix[:80]}")
                else:
                    error_lines_parts.append(f"  - {short} (no recorded fix)")

            if error_lines_parts:
                msg = f"{filename} has {len(error_results)} error patterns:\n"
                msg += "\n".join(error_lines_parts[:3])

                avg_rel = sum(r.get("relevance", 0) for r in error_results) / len(error_results)
                recency = max((_recency_score(r.get("created_at", "")) for r in error_results), default=0.2)
                freq = min(len(error_results) / 5.0, 1.0)

                lines.append(
                    AdvisorLine(
                        tag="WARNING",
                        message=msg,
                        memory_ids=all_ids[:5],
                        score=_composite_score(avg_rel, recency, freq),
                    )
                )

        # --- 2. Lessons learned (TIP) ---
        try:
            lesson_results = query_structured(
                query_text=query_text,
                event_type="lesson_learned",
                context_file=file_path,
                limit=5,
                entity_id=self.entity_id,
            )
        except Exception:
            logger.debug("Lesson query failed for %s", file_path, exc_info=True)
            lesson_results = []

        tip_count = 0
        for r in lesson_results:
            if tip_count >= 2:
                break
            rel = r.get("relevance", 0.0)
            r_session = r.get("session_id", "") or (r.get("metadata") or {}).get("session_id", "")
            if rel < 0.3 or r_session == session_id:
                continue
            if r.get("id") in already_surfaced:
                continue

            recency = _recency_score(r.get("created_at", ""))
            score = _composite_score(rel, recency, 0.5)
            content = r.get("content", "")
            lines.append(
                AdvisorLine(
                    tag="TIP",
                    message=content[:200],
                    memory_ids=[r.get("id", "")],
                    score=score,
                )
            )
            tip_count += 1

        # --- 3. Decisions (RECALL) ---
        try:
            decision_results = query_structured(
                query_text=query_text,
                event_type="decision",
                context_file=file_path,
                limit=3,
                entity_id=self.entity_id,
            )
        except Exception:
            logger.debug("Decision query failed for %s", file_path, exc_info=True)
            decision_results = []

        recall_count = 0
        for r in decision_results:
            if recall_count >= 1:
                break
            rel = r.get("relevance", 0.0)
            r_session = r.get("session_id", "") or (r.get("metadata") or {}).get("session_id", "")
            if rel < 0.4 or r_session == session_id:
                continue
            if r.get("id") in already_surfaced:
                continue

            recency = _recency_score(r.get("created_at", ""))
            score = _composite_score(rel, recency, 0.5)
            content = r.get("content", "")
            lines.append(
                AdvisorLine(
                    tag="RECALL",
                    message=content[:200],
                    memory_ids=[r.get("id", "")],
                    score=score,
                )
            )
            recall_count += 1

        # --- 4. Behavioral co-edit patterns (COEDIT) ---
        try:
            behavior_results = query_structured(
                query_text=query_text,
                event_type="behavioral_pattern",
                limit=5,
                entity_id=self.entity_id,
            )
        except Exception as e:
            logger.debug("Behavioral co-edit pattern query failed: %s", e)
            behavior_results = []

        for r in behavior_results:
            meta = r.get("metadata") or {}
            if meta.get("suppressed"):
                continue
            if meta.get("pattern_type") != "co_edit_cluster":
                continue
            conf = meta.get("confidence", 0)
            if conf < 0.7:
                continue
            if r.get("id") in already_surfaced:
                continue
            content = r.get("content", "")
            if filename.removesuffix(".py").lower() not in content.lower():
                continue
            recency = _recency_score(r.get("created_at", ""))
            score = _composite_score(conf, recency, 0.5)
            lines.append(
                AdvisorLine(
                    tag="COEDIT",
                    message=content[:200],
                    memory_ids=[r.get("id", "")],
                    score=score,
                )
            )

        # --- 5. Theme advisories from cluster patterns (THEME) ---
        try:
            context_keywords: Set[str] = set()
            context_keywords.add(filename.removesuffix(".py").lower())
            if dirname:
                context_keywords.add(dirname.lower())
            # Add keywords from query text
            for word in query_text.lower().split():
                if len(word) >= 3:
                    context_keywords.add(word)
            theme_advisories = self._get_theme_advisories(context_keywords)
            lines.extend(theme_advisories)
        except Exception:
            logger.debug("Theme advisory failed for %s", file_path, exc_info=True)

        # --- Sort by tag priority then -score, cap at MAX_WARNINGS_PER_HOOK ---
        lines.sort(key=lambda l: (TAG_PRIORITY.get(l.tag, 99), -l.score))
        lines = lines[:MAX_WARNINGS_PER_HOOK]

        # --- Session dedup: skip lines already shown this session ---
        deduped: List[AdvisorLine] = []
        for line in lines:
            dedup_key = hashlib.md5(f"{line.tag}:{line.message[:60]}".encode()).hexdigest()
            if _check_dedup(dedup_key):
                deduped.append(line)

        # --- Set cooldown ---
        if deduped:
            _file_cooldowns[file_path] = now

        return deduped

    def suggest_for_error(
        self,
        error_summary: str,
        file_path: Optional[str],
        session_id: str,
    ) -> Optional[AdvisorLine]:
        """Generate a WATCH advisory if this error has recurred across sessions.

        Queries error_pattern memories and checks for cross-session matches.
        Works with or without a specific file_path.

        Returns a single AdvisorLine with tag "WATCH", or None.
        """

        from omega.bridge import query_structured

        try:
            results = query_structured(
                query_text=error_summary[:200],
                event_type="error_pattern",
                limit=5,
                entity_id=self.entity_id,
            )
        except Exception:
            logger.debug("Error query failed for suggest_for_error", exc_info=True)
            return None

        # Filter to cross-session matches: different session, relevance >= 0.3
        cross_session_results = []
        other_sessions: Set[str] = set()
        for r in results:
            r_session = r.get("session_id", "") or (r.get("metadata") or {}).get("session_id", "")
            rel = r.get("relevance", 0.0)
            if r_session != session_id and rel >= 0.3:
                cross_session_results.append(r)
                if r_session:
                    other_sessions.add(r_session)

        # Need 1+ unique other sessions to trigger
        if not other_sessions:
            return None

        # Count total occurrences (current session counts as +1)
        total = len(other_sessions) + 1

        # Format as ordinal (2nd, 3rd, 4th, etc.)
        def _ordinal(n: int) -> str:
            if 11 <= n % 100 <= 13:
                return f"{n}th"
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            return f"{n}{suffix}"

        # Find fix for best match
        best = cross_session_results[0]
        fix = _find_fix_for_error(
            best.get("id", ""),
            best.get("content", ""),
            entity_id=self.entity_id,
        )

        msg = f"This error has occurred for the {_ordinal(total)} time: {error_summary[:100]}"
        if fix:
            msg += f" -- Fix: {fix[:120]}"

        memory_ids = [r.get("id", "") for r in cross_session_results if r.get("id")]

        return AdvisorLine(
            tag="WATCH",
            message=msg,
            memory_ids=memory_ids,
            score=0.9,
        )

    def suggest_co_edits(
        self,
        file_path: str,
        session_edited_files: Set[str],
    ) -> List[AdvisorLine]:
        """Suggest co-edited files based on git commit history.

        Searches decision memories for commits that mention the current file,
        extracts other files from those commits, and surfaces files that
        co-occur in 2+ commits and haven't been edited this session.

        Returns max 2 COEDIT advisory lines with score 0.5.
        """
        from omega.bridge import _get_store

        filename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

        try:
            store = _get_store()
            results = store.phrase_search(
                phrase=filename,
                event_type="decision",
                limit=10,
                entity_id=self.entity_id,
            )
        except Exception:
            logger.debug("Co-edit phrase_search failed for %s", filename, exc_info=True)
            return []

        # Count co-occurrences of other files across commits
        co_counts: Counter = Counter()
        for r in results:
            content = r.content if hasattr(r, "content") else r.get("content", "")
            co_files = _extract_co_edited_files(content)
            # Normalize to basenames for comparison
            co_basenames = {f.rsplit("/", 1)[-1] if "/" in f else f for f in co_files}
            if filename not in co_basenames:
                continue  # This commit didn't actually mention our file
            for cf in co_basenames:
                if cf != filename:
                    co_counts[cf] += 1

        # Filter: require 2+ co-occurrences, exclude files already edited this session
        session_basenames = {fp.rsplit("/", 1)[-1] if "/" in fp else fp for fp in session_edited_files}

        lines: List[AdvisorLine] = []
        for co_file, count in co_counts.most_common():
            if len(lines) >= 2:
                break
            if count < 2:
                break
            if co_file in session_basenames:
                continue

            dedup_key = hashlib.md5(f"COEDIT:{filename}:{co_file}".encode()).hexdigest()
            if not _check_dedup(dedup_key):
                continue

            lines.append(
                AdvisorLine(
                    tag="COEDIT",
                    message=f"{filename} is often edited with {co_file} ({count} commits)",
                    score=0.5,
                )
            )

        return lines

    def suggest_pre_deploy(
        self,
        session_id: str,
        commit_hash: str = "",
    ) -> List[AdvisorLine]:
        """Generate a GATE advisory before a commit if edited files have unresolved errors.

        Checks all files edited this session (from _file_cooldowns) for
        error_pattern memories from other sessions with no linked fix.

        Returns max 1 GATE line with score 0.95. Deduped by commit hash.
        """
        # Session dedup by commit hash
        if commit_hash:
            gate_key = f"GATE:{commit_hash}"
            if not _check_dedup(gate_key):
                return []

        edited_files = list(_file_cooldowns.keys())
        if not edited_files:
            return []

        from omega.bridge import query_structured

        files_with_errors: List[str] = []
        error_summaries: List[str] = []

        for fp in edited_files:
            filename = fp.rsplit("/", 1)[-1] if "/" in fp else fp
            try:
                results = query_structured(
                    query_text=filename,
                    event_type="error_pattern",
                    context_file=fp,
                    limit=3,
                    entity_id=self.entity_id,
                )
            except Exception:
                logger.debug("Pre-deploy query failed for %s", fp, exc_info=True)
                continue

            # Filter to errors from other sessions
            for r in results:
                r_session = r.get("session_id", "") or (r.get("metadata") or {}).get("session_id", "")
                if r_session == session_id:
                    continue
                if r.get("relevance", 0) < 0.3:
                    continue

                # Check if error has a known fix (if so, skip it)
                eid = r.get("id", "")
                fix = _find_fix_for_error(eid, r.get("content", ""), entity_id=self.entity_id)
                if fix:
                    continue

                # Unresolved error found for this file
                content = r.get("content", "")[:60].replace("\n", " ").strip()
                if filename not in [f for f, _ in zip(files_with_errors, error_summaries)]:
                    files_with_errors.append(filename)
                    error_summaries.append(content)
                break  # One unresolved error per file is enough

        if not files_with_errors:
            return []

        details = ", ".join(f"{f} ({s})" for f, s in zip(files_with_errors, error_summaries))
        msg = (
            f"{len(files_with_errors)} file{'s' if len(files_with_errors) != 1 else ''} "
            f"you edited {'have' if len(files_with_errors) != 1 else 'has'} "
            f"unresolved errors: {details}"
        )

        return [
            AdvisorLine(
                tag="GATE",
                message=msg,
                score=0.95,
            )
        ]

    def suggest_for_session_start(
        self,
        session_id: str,
        handoff: Optional[dict] = None,
        pending_tasks: Optional[List[dict]] = None,
    ) -> List[AdvisorLine]:
        """Generate SUGGEST advisories for session start.

        Collects items from:
        1. Previous-session handoff (blockers and incomplete work)
        2. Pending tasks
        3. Self-queried data: recent unresolved errors and key decisions
        """
        items: List[AdvisorLine] = []

        # 1. Collect from handoff
        if handoff:
            for blocker in handoff.get("blockers", []):
                items.append(
                    AdvisorLine(
                        tag="SUGGEST",
                        message=f"Blocker from last session: {blocker}",
                        score=1.0,
                    )
                )
            for incomplete in handoff.get("incomplete_work", []):
                items.append(
                    AdvisorLine(
                        tag="SUGGEST",
                        message=f"Incomplete: {incomplete}",
                        score=0.8,
                    )
                )

        # 2. Collect from pending_tasks (scored by priority + freshness)
        import math as _math_adv
        import time as _time_adv

        _now_adv = _time_adv.time()
        for task in (pending_tasks or []):
            subject = task.get("subject", "") or task.get("title", "")
            priority = task.get("priority", 0) or 3
            # Freshness decay: half-life ~7 days
            age_days = 0.0
            created_at = task.get("created_at", "")
            if created_at:
                try:
                    from datetime import datetime, timezone

                    if isinstance(created_at, str):
                        _ct = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    else:
                        _ct = datetime.fromtimestamp(created_at, tz=timezone.utc)
                    age_days = (_now_adv - _ct.timestamp()) / 86400.0
                except Exception as e:
                    logger.debug("Task created_at time parsing failed: %s", e)
            _pri_norm = priority / 5.0  # 0.2 to 1.0
            _recency = _math_adv.exp(-0.099 * age_days)  # ~0.5 at 7d
            score = _pri_norm * 0.5 + _recency * 0.5
            items.append(
                AdvisorLine(
                    tag="SUGGEST",
                    message=subject,
                    score=score,
                )
            )

        # 3. Self-query: surface recent unresolved errors for this project
        #    Only when no handoff or tasks were provided (fallback mode)
        has_structured_input = bool(handoff) or bool(pending_tasks)
        if not items and not has_structured_input:
            try:
                from omega.bridge import query_structured

                recent_errors = query_structured(
                    query_text=self.project.rsplit("/", 1)[-1] if self.project else "error",
                    event_type="error_pattern",
                    limit=5,
                    entity_id=self.entity_id,
                )
                # Group by unique error content, count cross-session occurrences
                seen: Set[str] = set()
                for r in (recent_errors or []):
                    r_session = r.get("session_id", "") or (r.get("metadata") or {}).get("session_id", "")
                    if r_session == session_id:
                        continue
                    content = r.get("content", "")[:80].lower().strip()
                    if content in seen:
                        continue
                    seen.add(content)
                    recency = _recency_score(r.get("created_at", ""))
                    if recency >= 0.5:  # Only recent errors (< 30 days)
                        items.append(
                            AdvisorLine(
                                tag="SUGGEST",
                                message=f"Recent error to watch: {r.get('content', '')[:120]}",
                                memory_ids=[r.get("id", "")],
                                score=0.6 * recency,
                            )
                        )
                    if len(items) >= 2:
                        break
            except Exception:
                logger.debug("Session start error query failed", exc_info=True)

        # 4. Self-query: surface recent key decisions for context
        if len(items) < 3 and not has_structured_input:
            try:
                from omega.bridge import query_structured

                recent_decisions = query_structured(
                    query_text=self.project.rsplit("/", 1)[-1] if self.project else "decision",
                    event_type="decision",
                    limit=3,
                    entity_id=self.entity_id,
                )
                for r in (recent_decisions or []):
                    r_session = r.get("session_id", "") or (r.get("metadata") or {}).get("session_id", "")
                    if r_session == session_id:
                        continue
                    rel = r.get("relevance", 0.0)
                    if rel < 0.25:
                        continue
                    recency = _recency_score(r.get("created_at", ""))
                    if recency >= 0.5:
                        content = r.get("content", "")[:150]
                        items.append(
                            AdvisorLine(
                                tag="SUGGEST",
                                message=f"Recent decision: {content}",
                                memory_ids=[r.get("id", "")],
                                score=0.5 * recency,
                            )
                        )
                    if len(items) >= 3:
                        break
            except Exception:
                logger.debug("Session start decision query failed", exc_info=True)

        # 4.5 Behavioral insight (only if we have room)
        if len(items) < 3:
            try:
                from omega.behavioral import BehavioralAnalyzer
                analyzer = BehavioralAnalyzer()
                recommendations = analyzer.generate_recommendations()
                for rec in recommendations[:1]:  # At most 1 behavioral insight
                    items.append(
                        AdvisorLine(
                            tag="TIP",
                            message=rec["recommendation"][:150],
                            score=0.4,
                        )
                    )
            except Exception:
                logger.debug("Session start behavioral suggestion failed", exc_info=True)

        # 4.6 Theme advisories from cluster patterns (only if we have room)
        if len(items) < 3:
            try:
                project_keywords: Set[str] = set()
                if self.project:
                    import re as _re_adv
                    for part in self.project.rsplit("/", 3)[-3:]:
                        # Split on hyphens/underscores for granular matching
                        for word in _re_adv.split(r"[-_]", part):
                            if len(word) >= 3:
                                project_keywords.add(word.lower())
                theme_items = self._get_theme_advisories(
                    project_keywords, limit=1, min_overlap=1,
                )
                items.extend(theme_items)
            except Exception:
                logger.debug("Session start theme suggestion failed", exc_info=True)

        # 5. Sort all by score descending
        items.sort(key=lambda l: -l.score)

        # 6. Cap at 3
        return items[:3]
