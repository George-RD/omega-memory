"""Trace capture hook handler -- records tool calls to coord_audit."""

import logging
import re

logger = logging.getLogger("omega.hook_server.trace")

# Per-session call index counters (in-memory, reset on server restart)
_call_counters: dict[str, int] = {}

# Patterns for classifying tool output
_ERROR_PATTERN = re.compile(r"Traceback|Error:|FAILED|exit code [1-9]", re.IGNORECASE)
_TIMEOUT_PATTERN = re.compile(r"timed out|timeout", re.IGNORECASE)


def _next_call_index(session_id: str) -> int:
    """Increment and return the 1-based call index for a session."""
    count = _call_counters.get(session_id, 0) + 1
    _call_counters[session_id] = count
    return count


def _classify_result_status(output: str) -> str:
    """Classify tool output as 'ok', 'error', or 'timeout'."""
    if not output:
        return "ok"
    if _ERROR_PATTERN.search(output):
        return "error"
    if _TIMEOUT_PATTERN.search(output):
        return "timeout"
    return "ok"


def handle_trace_capture(payload: dict) -> dict:
    """Record a tool call trace to coord_audit. Silent (no user output).

    This handler is non-critical: exceptions are caught and logged
    so the hook chain is never broken.
    """
    try:
        tool_name = payload.get("tool_name", "")
        session_id = payload.get("session_id", "")

        # Skip if missing required fields
        if not session_id or not tool_name:
            return {}

        tool_input = payload.get("tool_input", "")
        tool_output = payload.get("tool_output", "")

        call_index = _next_call_index(session_id)
        result_status = _classify_result_status(tool_output)
        input_size = len(tool_input) if tool_input else 0

        # Write to coord_audit via CoordinationManager singleton
        from omega.coordination import CoordinationManager

        mgr = CoordinationManager.get_instance()
        if mgr is not None:
            mgr.log_audit(
                session_id=session_id,
                tool_name=tool_name,
                arguments=None,
                result_summary=tool_output[:200] if tool_output else None,
                call_index=call_index,
                result_status=result_status,
                input_size=input_size,
            )

    except Exception:
        logger.debug("trace capture failed (non-critical)", exc_info=True)

    return {}


def cleanup_session(session_id: str) -> None:
    """Remove call counter for a closed session."""
    _call_counters.pop(session_id, None)
