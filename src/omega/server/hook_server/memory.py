"""Memory surface, capture, and tracking handlers."""

import logging
import json
import os
import re
import subprocess
import time

logger = logging.getLogger("omega.hook_server.memory")

from . import (
    DRIFT_CHECK_INTERVAL,
    PEER_DIR_CHECK_DEBOUNCE_S,
    REMINDER_CHECK_DEBOUNCE_S,
    SURFACE_DEBOUNCE_S,
    _MAX_ERRORS_PER_SESSION,
    _MAX_ERROR_HASHES,
    _MAX_SURFACE_ENTRIES,
    _drift_check_counter,
    _error_counts,
    _error_hashes,
    _last_peer_dir_check,
    _last_surface,
    _session_intent,
)

import omega.server.hook_server as _pkg  # for scalar state access

from .utils import (
    _get_current_branch,
    _agent_nickname,
    _check_milestone,
    _debounce_check,
    _get_file_path_from_input,
    _log_hook_error,
    _omega_dir,
    _parse_tool_input,
    _relative_time_from_iso,
    _resolve_entity,
)



def _auto_drift_check(session_id: str, project: str) -> str | None:
    """Check for goal drift every ~20 PostToolUse calls. Returns warning or None.

    Pure SQL via coordination.check_drift() — no LLM calls, <50ms.
    Fails silently if coordination tables don't exist or no goals found.
    """
    if not session_id:
        return None

    # Increment counter
    count = _drift_check_counter.get(session_id, 0) + 1
    _drift_check_counter[session_id] = count

    if count % DRIFT_CHECK_INTERVAL != 0:
        return None  # Not time yet

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        goals = mgr.list_goals(project=project or None, status="active")
        if not goals:
            return None  # No active goals, skip

        # Check drift on highest-priority goal
        worst_drift = None
        worst_score = 0.0
        for goal in goals[:3]:  # Cap to top 3 goals by priority
            drift = mgr.check_drift(goal["id"])
            if drift and drift.get("drift_score", 0) > worst_score:
                worst_score = drift["drift_score"]
                worst_drift = drift

        if worst_drift and worst_score > 0.5:
            alert = worst_drift.get("alert_level", "warning")
            drift_type = worst_drift.get("drift_type", "unknown")
            goal_id = worst_drift.get("goal_id", "?")
            tag = "DRIFT WARNING" if alert == "warning" else "DRIFT CRITICAL"
            return (
                f"[{tag}] Goal #{goal_id} drift: {worst_score:.0%} "
                f"({drift_type}) — review your goals with omega_query"
            )
    except Exception:
        pass  # Fail silently — coordination may not be available
    return None


def handle_surface_memories(payload: dict) -> dict:
    """Surface memories on file edits, capture errors from Bash."""
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", "{}")
    tool_output = payload.get("tool_output") or ""
    if not isinstance(tool_output, str):
        tool_output = json.dumps(tool_output) if isinstance(tool_output, (dict, list)) else str(tool_output)
    session_id = payload.get("session_id", "")
    project = payload.get("project", "")
    entity_id = _resolve_entity(project) if project else None

    # Parse tool input once for all branches
    input_data = _parse_tool_input(payload)

    lines = []

    # Get card tracker for adaptive transparency
    from . import get_card_tracker
    tracker = get_card_tracker(session_id) if session_id else None

    # Sync intent from module state into tracker
    if tracker and session_id:
        cached_intent = _session_intent.get(session_id)
        if cached_intent:
            tracker.intent = cached_intent

    # Surface memories on file edits
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        file_path = _get_file_path_from_input(input_data)
        if file_path and _debounce_check(_last_surface, file_path, SURFACE_DEBOUNCE_S, _MAX_SURFACE_ENTRIES):
            # Track edit in card tracker for complexity scoring
            if tracker:
                tracker.record_edit(file_path)

            lines.extend(_surface_for_edit(file_path, session_id, project, entity_id=entity_id, tracker=tracker))
            # _surface_lessons removed — the main query_structured in _surface_for_edit
            # already returns lessons via context_file. Separate lesson query was redundant
            # and added 1-2 embedding queries per edit (6→4 queries, ~30% faster).

            # Proactive advisor -> [OMEGA WARNING] cards
            try:
                from omega.advisor import Advisor as _Adv
                from omega.advisor import _file_cooldowns as _adv_cooldowns
                from .cards import format_warning_card

                _adv = _Adv(project=project, entity_id=entity_id)
                _adv_results = _adv.suggest_for_file(
                    file_path=file_path,
                    session_id=session_id,
                    tool_name=tool_name,
                    already_surfaced=set(),
                )
                if _adv_results:
                    level = tracker.transparency if tracker else __import__("omega.server.hook_server.cards", fromlist=["TransparencyLevel"]).TransparencyLevel.NORMAL
                    warnings = [
                        {"message": _al.message, "tag": _al.tag, "count": 1, "memory_ids": _al.memory_ids}
                        for _al in _adv_results
                    ]
                    lines.extend(format_warning_card(warnings, level))

                # Co-edit suggestions (keep original format, not a card type)
                _coedit = _adv.suggest_co_edits(
                    file_path=file_path,
                    session_edited_files=set(_adv_cooldowns.keys()),
                )
                for _cl in _coedit:
                    lines.append(_cl.format())
            except Exception as e:
                logger.debug("advisor suggest_for_file/suggest_co_edits failed: %s", e)

            # Preference contradiction check removed — fired on every edit with
            # an embedding query, but rarely caught real conflicts. The advisor
            # pipeline above covers the important warning cases.

            # Transparent "no results" -- show once per session on first edit with no context
            if not lines:
                no_ctx_key = f"_no_ctx_{session_id}"
                if no_ctx_key not in _last_surface:
                    _last_surface[no_ctx_key] = time.monotonic()
                    lines.append(f"[OMEGA] No stored context for {os.path.basename(file_path)} yet")

    # Surface memories on file reads (lightweight — no lessons)
    if tool_name == "Read":
        file_path = input_data.get("file_path", "")
        if file_path and _debounce_check(_last_surface, file_path, SURFACE_DEBOUNCE_S, _MAX_SURFACE_ENTRIES):
            lines.extend(_surface_for_edit(file_path, session_id, project, entity_id=entity_id))

    # Surface decisions/lessons on code searches (Grep/Glob signal exploration intent)
    if tool_name in ("Grep", "Glob") and project:
        search_pattern = input_data.get("pattern", "")
        if search_pattern and len(search_pattern) > 3:
            search_key = f"_search_{search_pattern[:50]}"
            if _debounce_check(_last_surface, search_key, 60.0, _MAX_SURFACE_ENTRIES):
                try:
                    from omega.bridge import query_structured as _qs_search

                    search_results = _qs_search(
                        query_text=search_pattern,
                        limit=2,
                        project=project,
                        entity_id=entity_id,
                        event_type="decision",
                    )
                    for r in search_results or []:
                        if r.get("relevance", 0) >= 0.35:
                            preview = r.get("content", "")[:100].replace("\n", " ").strip()
                            etype = r.get("event_type", "")
                            lines.append(f"[OMEGA] {etype}: {preview}")
                except Exception as e:
                    logger.debug("structured query for search pattern failed: %s", e)

    # Auto-capture errors from Bash failures + track git commits + auto-claim branches
    _client = payload.get("client", "claude-code")
    if tool_name == "Bash" and tool_output:
        recall_lines = _capture_error(tool_output, session_id, project, entity_id=entity_id, client=_client)
        if recall_lines:
            lines.extend(recall_lines)
            if tracker:
                tracker.record_error()
        git_lines = _track_git_commit(tool_input, tool_output, session_id, project, client=_client)
        if git_lines:
            lines.extend(git_lines)
        _auto_claim_branch(tool_input, session_id, project)

    # Surface peer claims in same directory on edits (multi-agent only, debounced)
    if tool_name in ("Edit", "Write", "NotebookEdit") and session_id and project:
        try:
            edit_path = _get_file_path_from_input(input_data)
            if edit_path:
                edit_dir = os.path.dirname(os.path.abspath(edit_path))
                if _debounce_check(_last_peer_dir_check, edit_dir, PEER_DIR_CHECK_DEBOUNCE_S, _MAX_SURFACE_ENTRIES):
                    from omega.coordination import get_manager

                    mgr = get_manager()
                    sessions = mgr.list_sessions(auto_clean=False)
                    peers = [
                        s
                        for s in sessions
                        if s.get("session_id") != session_id
                        and s.get("project") == project
                        and s.get("status") == "active"
                    ]
                    if peers:
                        peer_lines = []
                        for p in peers[:4]:
                            claims = mgr.get_session_claims(p["session_id"])
                            peer_files = claims.get("file_claims", [])
                            same_dir = [
                                os.path.basename(f)
                                for f in peer_files
                                if os.path.dirname(os.path.abspath(f)) == edit_dir
                            ]
                            if same_dir:
                                p_name = _agent_nickname(p["session_id"])
                                flist = ", ".join(same_dir[:4])
                                if len(same_dir) > 4:
                                    flist += f" +{len(same_dir) - 4}"
                                peer_lines.append(f"[PEER] {p_name} has {flist} claimed (same dir as your edit)")
                        if peer_lines:
                            lines.extend(peer_lines[:2])
        except Exception as e:
            logger.debug("peer directory claims check failed: %s", e)

    # Check for due reminders (debounced — max once per 5 minutes)
    now_mono = time.monotonic()
    if _pkg._last_reminder_check == 0.0 or now_mono - _pkg._last_reminder_check >= REMINDER_CHECK_DEBOUNCE_S:
        _pkg._last_reminder_check = now_mono
        try:
            from omega.bridge import get_due_reminders

            due = get_due_reminders(mark_fired=True, entity_id=entity_id)
            for r in due[:3]:
                overdue_label = " [OVERDUE]" if r.get("is_overdue") else ""
                lines.append(f"\n[REMINDER]{overdue_label} {r['text']}")
                lines.append(f"  ID: {r['id'][:12]} — dismiss with omega_remind_dismiss")
        except Exception as e:
            logger.debug("reminder retrieval failed: %s", e)

    # Tool discovery nudges — suggest underused tools (once per session)
    if tracker and session_id:
        try:
            nudge_marker = _omega_dir() / f"session-{session_id}.nudged"
            if not nudge_marker.exists():
                total_edits = sum(tracker.edit_counts.values()) if hasattr(tracker, "edit_counts") else len(tracker.files_edited)
                nudge = _check_tool_nudge(total_edits, session_id)
                if nudge:
                    lines.append(nudge)
                    nudge_marker.parent.mkdir(parents=True, exist_ok=True)
                    nudge_marker.touch()
        except Exception:
            pass  # Nudges are best-effort

    # Periodic goal drift check (~every 20 PostToolUse calls)
    drift_warning = _auto_drift_check(session_id, project)
    if drift_warning:
        lines.append(drift_warning)

    return {"output": "\n".join(lines), "error": None}


def _check_tool_nudge(edit_count: int, session_id: str) -> "str | None":
    """Return an [OMEGA TIP] string if agent is missing a useful tool call, or None."""
    try:
        from omega.server.hook_server import _protocol_calls

        called = _protocol_calls.get(session_id, set())
    except Exception:
        called = set()

    if edit_count >= 10 and "omega_reflect" not in called:
        return "[OMEGA TIP] You've made many edits. Consider `omega_reflect()` to check for contradictions or stale memories."

    return None



def _track_surfaced_ids(session_id: str, file_path: str, memory_ids: list):
    """Append surfaced memory IDs to the session's .surfaced.json file."""
    if not session_id or not memory_ids:
        return
    try:
        json_path = _omega_dir() / f"session-{session_id}.surfaced.json"
        existing = {}
        if json_path.exists():
            existing = json.loads(json_path.read_text())
        prev = existing.get(file_path, [])
        merged = list(set(prev + memory_ids))
        existing[file_path] = merged
        data = json.dumps(existing).encode("utf-8")
        fd = os.open(str(json_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
    except (OSError, json.JSONDecodeError) as e:
        _log_hook_error("_track_surfaced_ids", e)




def _ext_to_tags(file_path: str) -> list:
    """Derive context tags from file extension for re-ranking boost."""
    ext = os.path.splitext(file_path)[1].lower()
    _EXT_MAP = {
        ".py": ["python"],
        ".js": ["javascript"],
        ".ts": ["typescript"],
        ".tsx": ["typescript", "react"],
        ".jsx": ["javascript", "react"],
        ".rs": ["rust"],
        ".go": ["go"],
        ".rb": ["ruby"],
        ".java": ["java"],
        ".swift": ["swift"],
        ".sh": ["bash"],
        ".sql": ["sql"],
        ".md": ["markdown"],
        ".yml": ["yaml"],
        ".yaml": ["yaml"],
        ".json": ["json"],
        ".toml": ["toml"],
        ".css": ["css"],
        ".html": ["html"],
        ".c": ["c"],
        ".cpp": ["c++"],
        ".vue": ["vue", "javascript"],
        ".svelte": ["svelte", "javascript"],
        ".tf": ["terraform"],
        ".graphql": ["graphql"],
        ".prisma": ["prisma"],
        ".env": ["config"],
        ".ini": ["config"],
        ".kt": ["kotlin"],
        ".sc": ["scala"],
        ".ex": ["elixir"],
        ".php": ["php"],
        ".r": ["r"],
    }
    return _EXT_MAP.get(ext, [])




def _format_results_as_cards(
    results: list,
    session_id: str = "",
    project: str = "",
) -> list[str]:
    """Convert query results to compact [OMEGA] intelligence cards.

    Each result becomes either an [OMEGA] Used: card (for memories/lessons)
    or an [OMEGA] Warning: card (for error patterns). Also records surfacings
    in the CardTracker singleton for outcome tracking.
    """
    from .cards import format_compact_memory_card, format_compact_warning_card
    from .card_tracker import get_card_tracker

    compact_tracker = get_card_tracker()
    cards: list[str] = []

    for r in results:
        mem_id = r.get("id", "")
        content = r.get("content", "")
        event_type = r.get("event_type", "memory")
        meta = r.get("metadata") or {}
        last_accessed = r.get("last_accessed", "")

        # Calculate days since last access
        days_ago = 0
        if last_accessed:
            try:
                from datetime import datetime, timezone

                accessed_dt = datetime.fromisoformat(last_accessed.replace("Z", "+00:00"))
                if accessed_dt.tzinfo is None:
                    accessed_dt = accessed_dt.replace(tzinfo=timezone.utc)
                days_ago = max(0, (datetime.now(timezone.utc) - accessed_dt).days)
            except (ValueError, TypeError):
                pass

        if event_type == "error_pattern":
            card = format_compact_warning_card(
                filename=meta.get("file", meta.get("context_file", "unknown")),
                error_count=meta.get("error_count", 1),
                pattern=meta.get("pattern", content[:60]),
                last_fix_date=last_accessed[:10] if last_accessed else None,
            )
        else:
            card = format_compact_memory_card(
                content=content,
                verified_count=meta.get("verified_count", 0),
                last_accessed_days=days_ago,
                project=meta.get("project") or project or None,
            )

        if card:
            cards.append(card)
            if session_id and mem_id:
                compact_tracker.record_surfaced(session_id, mem_id, content[:200])

    return cards


def _apply_confidence_boost(results: list) -> list:
    """Boost relevance scores by capture confidence: high=1.2x, low=0.7x."""
    for r in results:
        confidence = (r.get("metadata") or {}).get("capture_confidence", "medium")
        score = r.get("relevance", 0.0)
        if confidence == "high":
            r["relevance"] = min(1.0, score * 1.2)
        elif confidence == "low":
            r["relevance"] = score * 0.7
    return results




def _surface_for_edit(
    file_path: str,
    session_id: str,
    project: str,
    *,
    entity_id: "Optional[str]" = None,
    tracker: "Optional[object]" = None,
) -> list[str]:
    """Surface memories related to a file being edited."""
    lines = []
    try:
        from omega.bridge import query_structured
        from omega.sqlite_store import SurfacingContext

        filename = os.path.basename(file_path)
        dirname = os.path.basename(os.path.dirname(file_path))
        context_tags = _ext_to_tags(file_path)
        # Bias query with session intent if available
        intent_hint = ""
        if session_id:
            cached_intent = _session_intent.get(session_id)
            _INTENT_HINTS = {
                "coding": "code implementation",
                "logic": "logic analysis",
                "creative": "creative writing",
                "exploration": "research exploration",
            }
            if cached_intent and cached_intent in _INTENT_HINTS:
                intent_hint = _INTENT_HINTS[cached_intent] + " "
        results = query_structured(
            query_text=f"{intent_hint}{filename} {dirname} {file_path}",
            limit=3,
            session_id=session_id,
            project=project,
            context_file=file_path,
            context_tags=context_tags or None,
            filter_tags=context_tags or None,
            entity_id=entity_id,
            surfacing_context=SurfacingContext.FILE_EDIT,
        )
        results = _apply_confidence_boost(results)
        results = [r for r in results if r.get("relevance", 0.0) >= 0.20]
        if results:
            # Enrich results with age and is_remembered flag for card formatter
            for r in results:
                created = r.get("created_at", "")
                r["age"] = _relative_time_from_iso(created) if created else ""
                score = r.get("relevance", 0.0)
                is_remembered = False
                if score >= 0.85 and created:
                    try:
                        from datetime import datetime as _dt, timezone as _tz
                        _created_dt = _dt.fromisoformat(created.replace("Z", "+00:00"))
                        if _created_dt.tzinfo is None:
                            _created_dt = _created_dt.replace(tzinfo=_tz.utc)
                        _age_secs = (_dt.now(_tz.utc) - _created_dt).total_seconds()
                        is_remembered = _age_secs > 3600
                    except (ValueError, TypeError):
                        pass
                r["is_remembered"] = is_remembered

            # Traverse: linked memories (1 hop from top result)
            linked_memories = []
            try:
                top_id = results[0].get("id", "")
                shown_ids = {r.get("id") for r in results}
                if top_id:
                    from omega.bridge import _get_store as _gs

                    _store = _gs()
                    linked = _store.get_related_chain(top_id, max_hops=1, min_weight=0.4)
                    linked_memories = [ln for ln in linked if ln.get("node_id") not in shown_ids][:2]
            except Exception as e:
                _log_hook_error("_surface_for_edit", e)

            # First-recall milestone — show above card to frame the experience
            if _check_milestone("first-recall"):
                lines.append("[OMEGA] First memory recall! Context from a previous session:\n")

            # Format via intelligence cards -- full structured at NORMAL+, compact at MINIMAL
            from .cards import format_memory_card, TransparencyLevel

            level = tracker.transparency if tracker else TransparencyLevel.MINIMAL
            # Escalate to NORMAL for files with 3+ edits (deep focus deserves context)
            if level == TransparencyLevel.MINIMAL and tracker and hasattr(tracker, "edit_counts"):
                if tracker.edit_counts.get(file_path, 0) >= 3:
                    level = TransparencyLevel.NORMAL
            if level != TransparencyLevel.MINIMAL:
                filename_short = os.path.basename(file_path)
                lines.extend(format_memory_card(results, filename_short, level, linked=linked_memories))
                # Also record surfacings in compact tracker for outcome tracking
                from .card_tracker import get_card_tracker as _get_ct
                _ct = _get_ct()
                for r in results:
                    mid = r.get("id", "")
                    if mid:
                        _ct.record_surfaced(session_id, mid, r.get("content", "")[:200])
            else:
                lines.extend(_format_results_as_cards(results, session_id=session_id, project=project))

            # Decision card from main results — reuse decisions already in `results`
            # instead of a separate embedding query. The main query_structured with
            # context_file already boosts decision-type memories.
            if level in (TransparencyLevel.NORMAL, TransparencyLevel.VERBOSE):
                try:
                    from .cards import format_decision_card
                    file_decisions = [
                        r for r in results
                        if r.get("event_type") == "decision"
                        and r.get("relevance", 0) >= 0.35
                        and (r.get("metadata") or {}).get("session_id") != session_id
                    ]
                    if file_decisions:
                        lines.extend(format_decision_card(file_decisions, level))
                        if tracker:
                            tracker.record_decisions_seen()
                            for d in file_decisions:
                                mid = d.get("id", "")
                                if mid:
                                    tracker.record_surfacing(mid, file_path, card_type="decisions")
                except Exception as e:
                    _log_hook_error("decision_card_on_edit", e)

            # Track surfaced memory IDs for auto-feedback
            memory_ids = [r.get("id") for r in results if r.get("id")]
            _track_surfaced_ids(session_id, file_path, memory_ids)

            # Record surfacings in card tracker for diff correlation
            if tracker:
                for mid in memory_ids:
                    tracker.record_surfacing(mid, file_path, card_type="memory")

            # Phrase search: exact-match error patterns for this file
            try:
                from omega.bridge import _get_store as _gs2

                _store2 = _gs2()
                exact_errors = _store2.phrase_search(filename, limit=2, event_type="error_pattern")
                shown_ids_updated = {r.get("id") for r in results}
                for err in exact_errors:
                    if err.id not in shown_ids_updated:
                        preview = err.content[:100].replace("\n", " ")
                        lines.append(f"  [exact] error: {preview}")
            except Exception as e:
                _log_hook_error("_surface_for_edit", e)
    except Exception as e:
        _log_hook_error("surface_for_edit", e)

    # Surface relevant knowledge base chunks for this file
    if file_path:
        try:
            from omega.knowledge.engine import search_documents as _kb_search

            filename = os.path.basename(file_path)
            kb_result = _kb_search(query=filename, limit=1, entity_id=entity_id)
            if kb_result and "No document matches" not in kb_result and "No documents ingested" not in kb_result:
                # Extract first line of content (skip header formatting)
                kb_lines_raw = [ln.strip() for ln in kb_result.split("\n") if ln.strip() and not ln.startswith("#")]
                if kb_lines_raw:
                    snippet = kb_lines_raw[0][:120]
                    lines.append(f"[KB] {snippet}")
        except ImportError as e:
            logger.debug("knowledge engine not available: %s", e)
        except Exception as e:
            logger.debug("knowledge engine search failed: %s", e)

    return lines




def _surface_lessons(
    file_path: str,
    session_id: str,
    project: str,
    *,
    entity_id: "Optional[str]" = None,
    context_tags: "Optional[list]" = None,
) -> list[str]:
    """Surface verified cross-session lessons and peer decisions."""
    lines = []
    try:
        from omega.bridge import get_cross_session_lessons

        filename = os.path.basename(file_path)
        lessons = get_cross_session_lessons(
            task=f"editing {filename}",
            project_path=project,
            exclude_session=session_id,
            limit=2,
            context_file=file_path,
            context_tags=context_tags,
        )
        verified = [lesson for lesson in lessons if lesson.get("verified")]
        if verified:
            lines.append(f"\n[LESSON] Verified wisdom for {filename}:")
            for lesson in verified:
                content = lesson.get("content", "")[:150]
                lines.append(f"  - {content}")
    except Exception as e:
        _log_hook_error("surface_lessons", e)

    # Surface recent peer decisions about this file
    if file_path and session_id:
        try:
            from omega.bridge import query_structured as _qs_peer

            filename = os.path.basename(file_path)
            peer_decisions = _qs_peer(
                query_text=f"decisions about {filename}",
                event_type="decision",
                limit=3,
                context_file=file_path,
                context_tags=context_tags,
                entity_id=entity_id,
            )
            # Filter out own session's decisions and low-relevance results
            for d in peer_decisions:
                meta = d.get("metadata") or {}
                if meta.get("session_id") == session_id:
                    continue
                if d.get("relevance", 0) < 0.5:
                    continue
                content = d.get("content", "")[:100].replace("\n", " ")
                lines.append(f"[PEER-DECISION] {content}")
                break  # Only show 1 to avoid noise
        except Exception as e:
            logger.debug("peer decision query failed: %s", e)

    return lines




def _extract_error_summary(raw_output: str) -> str:
    """Extract a clean error summary from raw tool output.

    For tracebacks: grab the last non-frame line (the actual error).
    For JSON blobs: skip JSON structure, find the error marker line.
    """
    lines = raw_output.strip().split("\n")

    if "Traceback (most recent call last)" in raw_output:
        for line in reversed(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("File ") and not stripped.startswith("^"):
                return stripped[:300]

    non_json_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith(("{", "[", "}", "]", '"')):
            non_json_lines.append(stripped)
    if non_json_lines:
        error_markers_local = [
            "Error:",
            "ERROR:",
            "error:",
            "FAILED",
            "Failed",
            "SyntaxError:",
            "TypeError:",
            "NameError:",
            "ImportError:",
            "ModuleNotFoundError:",
            "AttributeError:",
            "ValueError:",
            "KeyError:",
            "IndexError:",
            "FileNotFoundError:",
            "fatal:",
            "FATAL:",
            "panic:",
            "command not found",
            "No such file or directory",
            "Permission denied",
            "Connection refused",
        ]
        for line in non_json_lines:
            if any(m in line for m in error_markers_local):
                return line[:300]
        return non_json_lines[0][:300]

    return raw_output[:300]




def _capture_error(tool_output: str, session_id: str, project: str, *, entity_id: "Optional[str]" = None, client: str = "claude-code") -> list[str]:
    """Auto-capture error patterns from Bash failures + recall past fixes.

    Session-level dedup: skip if same error pattern already captured.
    Cap at _MAX_ERRORS_PER_SESSION to prevent test-run floods.
    Returns lines for "you've seen this before" recall output.
    """
    if not tool_output:
        return []
    if not isinstance(tool_output, str):
        tool_output = str(tool_output)

    # Cap errors per session
    if _error_counts.get(session_id, 0) >= _MAX_ERRORS_PER_SESSION:
        return []

    error_markers = [
        "Error:",
        "ERROR:",
        "error:",
        "FAILED",
        "Failed",
        "Traceback (most recent call last)",
        "SyntaxError:",
        "TypeError:",
        "NameError:",
        "ImportError:",
        "ModuleNotFoundError:",
        "AttributeError:",
        "ValueError:",
        "KeyError:",
        "IndexError:",
        "FileNotFoundError:",
        "fatal:",
        "FATAL:",
        "panic:",
        "command not found",
        "No such file or directory",
        "Permission denied",
        "Connection refused",
    ]

    if not any(marker in tool_output for marker in error_markers):
        return []

    error_summary = _extract_error_summary(tool_output)

    # Session-level dedup: hash the first 100 chars (normalized)
    error_hash = re.sub(r"\s+", " ", error_summary[:100].lower()).strip()
    if error_hash in _error_hashes:
        return []
    if len(_error_hashes) >= _MAX_ERROR_HASHES:
        return []  # Cap reached — stop tracking new hashes to bound memory
    _error_hashes.add(error_hash)
    _error_counts[session_id] = _error_counts.get(session_id, 0) + 1

    recall_lines: list[str] = []

    # --- Feature: "You've seen this before" — proactive error recall ---
    try:
        from omega.bridge import query_structured
        from omega.sqlite_store import SurfacingContext

        # Search for matching error_pattern and lesson_learned memories
        past_errors = query_structured(
            query_text=error_summary[:200],
            limit=2,
            project=project,
            event_type="error_pattern",
            entity_id=entity_id,
            surfacing_context=SurfacingContext.ERROR_DEBUG,
        )
        past_lessons = query_structured(
            query_text=error_summary[:200],
            limit=2,
            event_type="lesson_learned",
            entity_id=entity_id,
        )

        # Filter to only high-relevance matches (>= 0.35) from previous sessions
        past_matches = []
        for m in (past_errors or []) + (past_lessons or []):
            if m.get("relevance", 0) >= 0.35 and m.get("session_id") != session_id:
                past_matches.append(m)

        if past_matches:
            recall_lines.append("")
            recall_lines.append("[RECALL] You've seen this before:")
            for m in past_matches[:2]:
                etype = m.get("event_type", "memory")
                content = m.get("content", "")[:150].replace("\n", " ").strip()
                rel_time = m.get("relative_time") or ""
                time_note = f" ({rel_time})" if rel_time else ""
                recall_lines.append(f"  [{etype}]{time_note} {content}")
    except Exception as e:
        _log_hook_error("error_recall", e)

    # Store the new error pattern
    try:
        from omega.bridge import auto_capture

        result = auto_capture(
            content=f"Error: {error_summary}",
            event_type="error_pattern",
            metadata={"source": "auto_capture_hook", "project": project},
            session_id=session_id,
            project=project,
            entity_id=entity_id,
            agent_type=client,
        )
        if result and ("Stored" in result or "Evolved" in result):
            recall_lines.append(f"[OMEGA] {result}")
    except Exception as e:
        _log_hook_error("capture_error", e)

    # Proactive advisor: [WATCH] for repeat errors
    try:
        from omega.advisor import Advisor as _AdvErr

        _adv_err = _AdvErr(project=project, entity_id=entity_id)
        _watch = _adv_err.suggest_for_error(
            error_summary=error_summary,
            file_path=None,
            session_id=session_id,
        )
        if _watch:
            recall_lines.append(_watch.format())
    except Exception as e:
        logger.debug("advisor error suggestion failed: %s", e)

    return recall_lines




def _track_git_commit(tool_input: str, tool_output: str, session_id: str, project: str, *, client: str = "claude-code") -> list[str]:
    """Detect git commit in Bash output, log to coordination, return advisory lines."""
    if not tool_output:
        return []
    if not isinstance(tool_output, str):
        tool_output = str(tool_output)

    try:
        input_data = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
    except (json.JSONDecodeError, TypeError):
        return []

    command = input_data.get("command", "")
    if "git commit" not in command:
        return []

    match = re.search(r"\[[\w/.-]+\s+([0-9a-f]{7,12})\]", tool_output)
    if not match:
        return []

    commit_hash = match.group(1)
    msg_match = re.search(r"\[[\w/.-]+\s+[0-9a-f]{7,12}\]\s+(.+)", tool_output)
    message = msg_match.group(1).strip() if msg_match else ""

    branch = _get_current_branch(project)

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        mgr.log_git_event(
            project=project,
            event_type="commit",
            commit_hash=commit_hash,
            branch=branch,
            message=message,
            session_id=session_id,
        )

        # Auto-release file claims for committed files
        committed_files = []
        if session_id and project and commit_hash:
            try:
                diff_result = subprocess.run(
                    ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=project,
                )
                if diff_result.returncode == 0 and diff_result.stdout.strip():
                    committed_files = [f.strip() for f in diff_result.stdout.strip().split("\n") if f.strip()]
                    if committed_files:
                        abs_files = [os.path.join(project, f) for f in committed_files]
                        mgr.release_committed_files(session_id, project, abs_files)
            except (subprocess.SubprocessError, OSError) as e:
                logger.debug("git commit file release failed: %s", e)

        # Diff-correlate surfaced memories with committed files
        if committed_files and session_id:
            try:
                from . import get_card_tracker

                tracker = get_card_tracker(session_id)
                abs_committed = [os.path.join(project, f) for f in committed_files] if project else committed_files
                tracker.correlate_with_diff(abs_committed)
            except Exception as e:
                logger.debug("diff correlation on commit failed: %s", e)

        # Auto-store commit as task_completion in OMEGA (makes work discoverable)
        # Architecture decisions use "decision" type; routine commits use "task_completion"
        try:
            from omega.bridge import auto_capture

            entity_id = _resolve_entity(project) if project else None
            file_list = ", ".join(committed_files[:5]) if committed_files else ""
            if len(committed_files) > 5:
                file_list += f" +{len(committed_files) - 5}"
            content = f"Committed {commit_hash}: {message}"
            if file_list:
                content += f". Files: {file_list}"
            # Route to decision only if commit message signals architecture/design choice
            _decision_signals = ("architect", "decision", "schema", "migration", "breaking")
            _msg_lower = message.lower()
            _etype = "decision" if any(s in _msg_lower for s in _decision_signals) else "task_completion"
            _commit_capture_result = auto_capture(
                content=content,
                event_type=_etype,
                metadata={"source": "auto_commit_capture", "commit": commit_hash, "branch": branch},
                session_id=session_id,
                project=project,
                entity_id=entity_id,
                agent_type=client,
            )
        except Exception as e:
            _commit_capture_result = None
            logger.debug("auto-capture of git commit failed: %s", e)

    except Exception as e:
        _commit_capture_result = None
        _log_hook_error("track_git_commit", e)

    # Pre-deploy gate: check edited files for unresolved errors
    advisory_lines: list[str] = []
    if _commit_capture_result and ("Stored" in _commit_capture_result or "Evolved" in _commit_capture_result):
        advisory_lines.append(f"[OMEGA] {_commit_capture_result}")
    try:
        from omega.advisor import Advisor as _GateAdv

        entity_id = _resolve_entity(project) if project else None
        _gate_adv = _GateAdv(project=project, entity_id=entity_id)
        _gate_results = _gate_adv.suggest_pre_deploy(
            session_id=session_id,
            commit_hash=commit_hash,
        )
        for _gl in _gate_results:
            advisory_lines.append(_gl.format())
    except Exception as e:
        logger.debug("pre-deploy gate advisor failed: %s", e)

    return advisory_lines




def _auto_claim_branch(tool_input: str, session_id: str, project: str):
    """Auto-claim branch on git checkout/switch (PostToolUse, best-effort)."""
    if not session_id or not project:
        return
    try:
        input_data = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
    except (json.JSONDecodeError, TypeError):
        return

    command = input_data.get("command", "")
    if not any(cmd in command for cmd in ("git checkout", "git switch", "git push")):
        return

    try:
        branch = _get_current_branch(project)
        if not branch or branch == "HEAD":
            return  # Detached HEAD or not a git repo

        from omega.coordination import get_manager

        mgr = get_manager()
        mgr.claim_branch(session_id, project, branch, task="auto-claimed on checkout")
    except Exception as e:
        logger.debug("branch auto-claim failed: %s", e)
