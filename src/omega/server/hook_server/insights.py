"""System insight surfacing — contextual insights before file edits."""

import logging
import os

from omega import json_compat as json

logger = logging.getLogger("omega.hook_server.insights")


from .utils import (
    _debounce_check,
    _get_file_path_from_input,
    _log_hook_error,
    _parse_tool_input,
)

# Debounce for insight surfacing — longer than normal surface debounce
# to avoid flooding the agent with repeated insight warnings
_INSIGHT_DEBOUNCE_S = 300.0  # 5 minutes per file
_last_insight_surface: dict[str, float] = {}  # file_path -> monotonic timestamp
_MAX_INSIGHT_ENTRIES = 200

# Mid-session memory context push — once per file per session
_session_memory_pushed: dict[str, set[str]] = {}  # session_id -> set of file paths
_MAX_PUSH_SESSIONS = 50

# Map file path segments to subsystem tags for querying relevant insights
_PATH_TAG_MAP: dict[str, list[str]] = {
    "bridge.py": ["memory_engine", "bridge"],
    "sqlite_store.py": ["memory_engine", "sqlite"],
    "coordination.py": ["coordination", "sessions"],
    "coord_handlers.py": ["coordination"],
    "coord_schemas.py": ["coordination"],
    "hook_server": ["hooks"],
    "fast_hook.py": ["hooks"],
    "guards.py": ["hooks", "guards"],
    "session.py": ["sessions", "hooks"],
    "heartbeat.py": ["heartbeat", "hooks"],
    "maintenance.py": ["alerting", "monitoring", "heartbeat"],
    "cloud/": ["cloud_sync", "supabase"],
    "embedding": ["diagnostics", "sqlite_vec", "vectors"],
    "protocol.py": ["protocol"],
    "notify": ["alerting", "monitoring"],
    "cron": ["alerting", "monitoring", "cron"],
}


def _tags_for_file(file_path: str) -> list[str]:
    """Extract subsystem tags from a file path."""
    tags = []
    for pattern, tag_list in _PATH_TAG_MAP.items():
        if pattern in file_path:
            tags.extend(tag_list)
    return list(set(tags))  # deduplicate


def _memory_context_push(file_path: str, session_id: str) -> str:
    """Push relevant memories for a file. Returns output string or empty."""
    if not session_id or not file_path:
        return ""

    # Gate: only after 50+ tool calls
    try:
        from omega.server.hook_server.trace import _call_counters
        if _call_counters.get(session_id, 0) < 50:
            return ""
    except Exception:
        return ""

    # Gate: once per file per session
    pushed = _session_memory_pushed.get(session_id, set())
    if file_path in pushed:
        return ""

    try:
        from omega.bridge import query_structured

        # Query without event_type filter, post-filter to desired types
        results = query_structured(query_text=file_path, limit=9)
        if not results:
            return ""

        allowed_types = {"lesson_learned", "decision", "error_pattern"}
        matching = [
            r for r in results
            if r.get("event_type") in allowed_types
        ][:3]

        if not matching:
            return ""

        # Mark as pushed (create set if needed, bound size)
        if len(_session_memory_pushed) >= _MAX_PUSH_SESSIONS:
            oldest = next(iter(_session_memory_pushed))
            del _session_memory_pushed[oldest]
        if session_id not in _session_memory_pushed:
            _session_memory_pushed[session_id] = set()
        _session_memory_pushed[session_id].add(file_path)

        # Track surfaced IDs for feedback loop
        try:
            surfaced_path = os.path.expanduser(f"~/.omega/session-{session_id}.surfaced.json")
            surfaced_data: dict = {}
            if os.path.exists(surfaced_path):
                with open(surfaced_path) as f:
                    surfaced_data = json.load(f)
            surfaced_ids = [r.get("node_id", "") for r in matching if r.get("node_id")]
            if surfaced_ids:
                existing = surfaced_data.get(file_path, [])
                existing.extend(surfaced_ids)
                surfaced_data[file_path] = existing
                with open(surfaced_path, "w") as f:
                    json.dump(surfaced_data, f)
        except Exception:
            pass  # Surfacing tracking is best-effort

        filename = os.path.basename(file_path)
        lines = [f"[MEMORY_CONTEXT] Relevant memories for {filename}:"]
        for r in matching:
            node_id = r.get("node_id", "unknown")
            content = r.get("content", "")[:100].replace("\n", " ")
            lines.append(f"  - `{node_id}`: {content}")

        return "\n".join(lines)

    except Exception as e:
        _log_hook_error("memory_context_push", e)
        return ""


def handle_pre_insight_surface(payload: dict) -> dict:
    """Surface system insights relevant to the file being edited.

    Non-blocking, fail-open. Returns contextual insight text or empty output.
    """
    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return {"output": "", "error": None}

    input_data = _parse_tool_input(payload)
    file_path = _get_file_path_from_input(input_data)
    if not file_path:
        return {"output": "", "error": None}

    # Skip plan files
    from .guards import _is_plan_file
    if _is_plan_file(file_path):
        return {"output": "", "error": None}

    # --- Memory context push (fires for ALL files, before tags gate) ---
    session_id = payload.get("session_id", "")
    memory_output = _memory_context_push(file_path, session_id)

    # --- System insights (only for OMEGA-internal files with tags) ---
    insight_output = ""
    tags = _tags_for_file(file_path)
    if tags:
        # Debounce — same file at most once per 5 minutes
        if _debounce_check(_last_insight_surface, file_path, _INSIGHT_DEBOUNCE_S, _MAX_INSIGHT_ENTRIES):
            try:
                from omega.bridge import query_structured

                query_hint = " ".join(tags)
                results = query_structured(
                    query_text=query_hint,
                    limit=8,
                    event_type="advisor_insight",
                )
                if results:
                    matching = []
                    for r in results:
                        meta = r.get("metadata") or {}
                        if meta.get("category") != "system_insight":
                            continue
                        r_tags = set(r.get("tags") or [])
                        if r_tags & set(tags):
                            content = r.get("content", "")[:200]
                            matching.append(content)
                        if len(matching) >= 3:
                            break

                    if matching:
                        filename = os.path.basename(file_path)
                        lines = [f"[INSIGHT] {filename} — prior lessons:"]
                        for insight in matching:
                            lines.append(f"  - {insight}")
                        insight_output = "\n".join(lines)

            except Exception as e:
                _log_hook_error("pre_insight_surface", e)

    # Combine outputs
    combined = "\n".join(part for part in [memory_output, insight_output] if part)
    return {"output": combined, "error": None}
