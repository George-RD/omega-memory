"""Assistant response capture hook handler.

Captures high-value content from Claude's responses (fixes, decisions,
lessons, recommendations) via the Stop hook's ``last_assistant_message``
field. Complements auto_capture (which captures from user prompts).

Tag convention: ``[LEARNED]`` for assistant-originated captures vs
``[CAPTURED]`` for user-prompt captures.
"""

import logging
import re

logger = logging.getLogger("omega.hook_server.assistant")

# Per-session capture cap -- prevents flooding on long sessions
_MAX_CAPTURES_PER_SESSION = 10

# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```", re.DOTALL)
_LONG_INLINE_CODE_RE = re.compile(r"`[^`]{40,}`")
_FILE_PATH_LINE_RE = re.compile(r"^\s*/[\w./-]{20,}\s*$", re.MULTILINE)
_BOILERPLATE_LINE_RE = re.compile(
    r"^\s*(?:Let me (?:read|check|look|search|explore)|"
    r"I'll (?:read|check|look|search|explore)|"
    r"Reading |Searching |Looking at |Checking )",
    re.MULTILINE,
)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

# Insight block detection -- matches ★ Insight delimited blocks
_INSIGHT_OPEN_RE = re.compile(r"[★✦]\s*Insight\s*─+", re.IGNORECASE)
_INSIGHT_CLOSE_RE = re.compile(r"─{10,}")

# Keywords derived from insights.py _PATH_TAG_MAP for auto-tagging captured insights
_INSIGHT_TAG_KEYWORDS: dict[str, list[str]] = {
    "memory_engine": ["bridge", "memory engine", "auto_capture", "dedup", "contradiction", "strength decay", "consolidation", "fact splitting", "temporal", "FTS5"],
    "sqlite": ["sqlite", "WAL", "database locked", "journal_mode"],
    "coordination": ["coordination", "session", "file claim", "branch claim", "task dep", "deadlock", "handoff", "drift"],
    "hooks": ["hook", "fast_hook", "guard", "pre-edit", "pre-push", "fail-open", "exit code 2"],
    "cloud_sync": ["cloud sync", "supabase", "cloud_delete", "dual-write"],
    "protocol": ["protocol", "system prompt", "provider_notes"],
    "diagnostics": ["embedding", "sqlite_vec", "vector", "ONNX"],
    "alerting": ["heartbeat", "monitoring", "alerting", "cron", "maintenance"],
    "sessions": ["session", "stale session", "register_session"],
}


def _extract_tags_from_content(text: str) -> list[str]:
    """Extract subsystem tags from insight content using keyword matching."""
    text_lower = text.lower()
    tags = []
    for tag, keywords in _INSIGHT_TAG_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            tags.append(tag)
    return tags


def _clean_assistant_message(text: str) -> str:
    """Strip code blocks, boilerplate, and noise from assistant text."""
    text = _FENCED_CODE_RE.sub("", text)
    text = _LONG_INLINE_CODE_RE.sub("", text)
    text = _FILE_PATH_LINE_RE.sub("", text)
    text = _BOILERPLATE_LINE_RE.sub("", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def _extract_insight_blocks(text: str) -> list[str]:
    """Extract all ★ Insight delimited blocks from assistant text.

    Returns the full body of each insight block (between opening and
    closing dash delimiters), preserving multi-paragraph structure.
    """
    blocks = []
    search_start = 0
    while True:
        open_match = _INSIGHT_OPEN_RE.search(text, search_start)
        if not open_match:
            break
        body_start = open_match.end()
        # Find closing delimiter (─{10,}) after the body
        close_match = _INSIGHT_CLOSE_RE.search(text, body_start)
        if not close_match:
            # No closing delimiter -- take rest of text up to 2000 chars
            body = text[body_start:body_start + 2000].strip()
        else:
            body = text[body_start:close_match.start()].strip()
        if body and len(body) >= _MIN_CONTENT_CHARS:
            blocks.append(body[:2000])  # Cap at 2000 chars per block
        search_start = close_match.end() if close_match else len(text)
    return blocks


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------

_FIX_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"the (?:fix|issue|problem|bug) was\b",
        r"root cause (?:was|is)\b",
        r"the error (?:occurred|happens|was caused) because\b",
        r"fixed (?:by|this by)\b",
    ]
]

_DECISION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"(?:decided|choosing) to\b",
        r"going with\b",
        r"switched to\b",
        r"using \S+ instead of\b",
        r"chose \S+ because\b",
    ]
]

_LESSON_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"(?:note|notice) that\b",
        r"important:\s",
        r"be careful\b",
        r"gotcha:\s",
        r"caveat:\s",
        r"key takeaway\b",
    ]
]

_RECOMMENDATION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"I recommend\b",
        r"I suggest\b",
        r"best practice is\b",
    ]
]

_SUMMARY_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"in summary\b",
        r"to summarize\b",
        r"key changes:\s",
        r"what changed:\s",
    ]
]

# All pattern groups with their labels
_PATTERN_GROUPS = [
    ("fix", _FIX_PATTERNS),
    ("decision", _DECISION_PATTERNS),
    ("lesson", _LESSON_PATTERNS),
    ("recommendation", _RECOMMENDATION_PATTERNS),
    ("summary", _SUMMARY_PATTERNS),
]

# Sentence splitter: split on '. ' or newlines (keeps paragraphs intact)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# Quality gate thresholds for extracted content
_MIN_CONTENT_CHARS = 40
_MIN_CONTENT_WORDS = 8


def _extract_best_sentence(text: str, pattern: "re.Pattern") -> str | None:
    """Return the first sentence matching *pattern* that passes quality gate."""
    sentences = _SENTENCE_SPLIT_RE.split(text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if pattern.search(sentence):
            if len(sentence) >= _MIN_CONTENT_CHARS and len(sentence.split()) >= _MIN_CONTENT_WORDS:
                return sentence
    return None


# ---------------------------------------------------------------------------
# Map capture types to bridge event_type values
# ---------------------------------------------------------------------------

_TYPE_TO_EVENT = {
    "fix": "lesson_learned",
    "decision": "decision",
    "lesson": "lesson_learned",
    "recommendation": "lesson_learned",
    "summary": "task_completion",
}


# ---------------------------------------------------------------------------
# Outcome tracking -- detect which surfaced memories were used
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "to",
    "of", "in", "for", "on", "with", "at", "by", "from", "this",
    "that", "it", "its", "and", "or", "but", "not", "no", "if",
    "then", "than", "so", "as", "into", "also", "just", "about",
})


def _detect_used_memories(response: str, surfaced_content: dict) -> set:
    """Detect which surfaced memories were referenced in Claude's response.

    Uses keyword overlap: if 40%+ of significant words from the memory content
    appear in the response, it's considered 'used'.
    """
    response_lower = response.lower()
    used = set()

    for mem_id, content in surfaced_content.items():
        words = [w for w in content.lower().split() if len(w) > 2 and w not in _STOPWORDS]
        if not words:
            continue
        matches = sum(1 for w in words if w in response_lower)
        if matches / len(words) >= 0.4:
            used.add(mem_id)
    return used


def _track_outcomes(session_id: str, response: str, tracker=None) -> None:
    """Track which surfaced memories were used vs ignored in Claude's response."""
    if tracker is None:
        from .card_tracker import get_card_tracker
        tracker = get_card_tracker()

    surfaced_content = tracker.get_surfaced_content_map(session_id)
    if not surfaced_content:
        return

    used_ids = _detect_used_memories(response, surfaced_content)
    for mem_id in used_ids:
        tracker.record_used(session_id, mem_id)


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_assistant_capture(payload: dict) -> dict:
    """Capture high-value content from Claude's assistant responses.

    Called on every Stop event. Lightweight (regex only, no LLM calls).
    """
    message = payload.get("last_assistant_message", "")
    if not message:
        return {"output": "", "error": None}

    # Short messages (< 200 chars) are usually tool-use boilerplate, but allow
    # through if they contain high-value patterns (fixes, decisions, lessons).
    if len(message) < 200:
        _has_signal = any(
            pat.search(message)
            for _, patterns in _PATTERN_GROUPS
            for pat in patterns
        )
        if not _has_signal or len(message) < 40:
            return {"output": "", "error": None}

    session_id = payload.get("session_id", "")
    if not session_id:
        return {"output": "", "error": None}

    # Track which surfaced memories were used in this response
    try:
        _track_outcomes(session_id, message)
    except Exception as e:
        logger.debug("outcome tracking failed: %s", e)

    # Import here to access the module-level counter dict
    from omega.server.hook_server import _assistant_capture_count

    # Per-session cap check
    count = _assistant_capture_count.get(session_id, 0)
    if count >= _MAX_CAPTURES_PER_SESSION:
        return {"output": "", "error": None}

    cleaned = _clean_assistant_message(message)
    if not cleaned:
        return {"output": "", "error": None}

    project = payload.get("project", "")

    # Pre-pass: detect ★ Insight delimited blocks (full multi-paragraph capture)
    insight_blocks = _extract_insight_blocks(message)  # Use raw message, not cleaned
    if insight_blocks:
        from omega.server.hook_server import _assistant_capture_count as _insight_cap_ref

        stored_count = 0
        for block in insight_blocks:
            cap_count = _insight_cap_ref.get(session_id, 0)
            if cap_count >= _MAX_CAPTURES_PER_SESSION:
                break
            try:
                from omega.bridge import auto_capture
                from omega.server.hook_server.utils import _resolve_entity

                entity_id = _resolve_entity(project) if project else None
                tags = _extract_tags_from_content(block)
                auto_capture(
                    content=f"Insight: {block}",
                    event_type="advisor_insight",
                    metadata={
                        "source": "assistant_capture_hook",
                        "project": project,
                        "capture_confidence": "high",
                        "category": "system_insight",
                        "tags": tags,
                    },
                    session_id=session_id,
                    project=project,
                    entity_id=entity_id,
                )
                _insight_cap_ref[session_id] = cap_count + 1
                stored_count += 1
            except Exception as e:
                from omega.server.hook_server.utils import _log_hook_error
                _log_hook_error("assistant_capture_insight", e)
                break

        if stored_count > 0:
            # Format card for user-visible output
            preview = insight_blocks[0][:120].replace("\n", " ").strip()
            suffix = f" (+{stored_count - 1} more)" if stored_count > 1 else ""
            try:
                from .cards import format_compact_learning_card
                card = format_compact_learning_card(
                    content=preview + suffix,
                    event_type="advisor_insight",
                )
                # Record in trackers
                from . import get_card_tracker as _get_session_tracker
                from .card_tracker import get_card_tracker as _get_compact_tracker
                _get_compact_tracker().record_lesson(session_id)
                session_tracker = _get_session_tracker(session_id)
                session_tracker.card_type_surfacings["learned"] += 1
                return {"output": card, "error": None}
            except Exception:
                return {"output": f"[OMEGA LEARNED] insight: {preview}{suffix}", "error": None}

    # Try each pattern group, take first match
    matched_type = None
    matched_content = None
    for label, patterns in _PATTERN_GROUPS:
        for pat in patterns:
            content = _extract_best_sentence(cleaned, pat)
            if content:
                matched_type = label
                matched_content = content
                break
        if matched_content:
            break

    if not matched_content:
        return {"output": "", "error": None}

    # Store via bridge
    event_type = _TYPE_TO_EVENT.get(matched_type, "lesson_learned")

    try:
        from omega.bridge import auto_capture
        from omega.server.hook_server.utils import _resolve_entity, _log_hook_error

        entity_id = _resolve_entity(project) if project else None

        auto_capture(
            content=f"Assistant {matched_type}: {matched_content[:500]}",
            event_type=event_type,
            metadata={"source": "assistant_capture_hook", "project": project, "capture_confidence": "medium"},
            session_id=session_id,
            project=project,
            entity_id=entity_id,
        )
    except Exception as e:
        from omega.server.hook_server.utils import _log_hook_error

        _log_hook_error("assistant_capture", e)
        return {"output": "", "error": None}

    # Success: increment counter and return user-visible card
    _assistant_capture_count[session_id] = count + 1

    # Compute confidence from pattern match density
    # More pattern matches in the text = higher confidence
    match_count = sum(
        1 for _, patterns in _PATTERN_GROUPS
        for pat in patterns
        if pat.search(cleaned)
    )
    confidence = min(1.0, match_count * 0.25)  # 1 match = 0.25, 4+ = 1.0

    # Format via intelligence card -- full at NORMAL+, compact at MINIMAL
    try:
        from . import get_card_tracker as _get_session_tracker
        from .cards import format_compact_learning_card, format_learning_card, TransparencyLevel
        from .card_tracker import get_card_tracker as _get_compact_tracker

        # Check transparency level
        session_tracker = _get_session_tracker(session_id)
        level = session_tracker.transparency if session_tracker else TransparencyLevel.MINIMAL

        if level != TransparencyLevel.MINIMAL:
            card_lines = format_learning_card(
                matched_type=matched_type,
                content=matched_content[:500],
                confidence=confidence,
                level=level,
            )
            card = "\n".join(card_lines) if card_lines else ""
        else:
            # Compact card for user-facing output
            card = format_compact_learning_card(
                content=matched_content[:500],
                event_type=event_type,
            )

        # Record in compact CardTracker for session summary
        compact_tracker = _get_compact_tracker()
        compact_tracker.record_lesson(session_id)

        # Record in SessionCardTracker for complexity scoring
        session_tracker = _get_session_tracker(session_id)
        session_tracker.card_type_surfacings["learned"] += 1

        return {"output": card, "error": None}
    except Exception:
        pass  # Fall through to legacy format

    # Legacy fallback
    preview = matched_content[:80].replace("\n", " ").strip()
    return {"output": f"[OMEGA LEARNED] {matched_type}: {preview}", "error": None}
