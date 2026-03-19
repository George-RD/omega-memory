"""Debounce state management for hook server.

Wraps the 15+ module-level debounce dicts with lifecycle methods:
  - cleanup(session_id) — removes entries for a closed session
  - prune_stale(max_age) — evicts entries older than max_age
  - stats() — entry counts per dict (for diagnostics)
  - reset() — clears all state (for test isolation)
"""

import time


class DebouncedState:
    """Manages hook server debounce state with lifecycle operations.

    Does NOT own the dicts — it wraps references to the module-level dicts
    defined in __init__.py. Mutations through either path are visible to both.
    """

    def __init__(
        self,
        *,
        # Session-keyed dicts (str -> value)
        last_heartbeat: dict,
        heartbeat_count: dict,
        gate_call_count: dict,
        last_coord_query: dict,
        last_progress_beat: dict,
        last_pulse_state: dict,
        session_intent: dict,
        pending_urgent: dict,
        error_counts: dict,
        # Tuple-keyed dicts ((session_id, ...) -> timestamp)
        last_claim: dict,
        last_overlap_notify: dict,
        last_block_notify: dict,
        last_file_read: dict | None = None,
        # Non-session-keyed dicts
        last_surface: dict,
        last_project: dict | None = None,
        last_peer_dir_check: dict,
        last_deadlock_push: dict,
        error_hashes: set,
        hook_error_counts: dict,
        peer_snapshot: dict,
        protocol_calls: dict,
        session_peer_count: dict,
        session_peer_count_time: dict,
        assistant_capture_count: dict | None = None,
        card_trackers: dict | None = None,
        session_approach_domains: dict | None = None,
        session_approach_warned: dict | None = None,
        session_external_actions: dict | None = None,
        drift_check_counter: dict | None = None,
    ):
        # Session-keyed (simple pop)
        self._session_keyed = {
            "last_heartbeat": last_heartbeat,
            "heartbeat_count": heartbeat_count,
            "gate_call_count": gate_call_count,
            "last_coord_query": last_coord_query,
            "last_progress_beat": last_progress_beat,
            "last_pulse_state": last_pulse_state,
            "session_intent": session_intent,
            "pending_urgent": pending_urgent,
            "error_counts": error_counts,
            "peer_snapshot": peer_snapshot,
            "protocol_calls": protocol_calls,
            "session_peer_count": session_peer_count,
            "session_peer_count_time": session_peer_count_time,
            **({"assistant_capture_count": assistant_capture_count} if assistant_capture_count is not None else {}),
            **({"card_trackers": card_trackers} if card_trackers is not None else {}),
            **({"session_approach_domains": session_approach_domains} if session_approach_domains is not None else {}),
            **({"session_approach_warned": session_approach_warned} if session_approach_warned is not None else {}),
            **({"last_project": last_project} if last_project is not None else {}),
            **({"session_external_actions": session_external_actions} if session_external_actions is not None else {}),
            **({"drift_check_counter": drift_check_counter} if drift_check_counter is not None else {}),
        }

        # Tuple-keyed (need to filter by first element)
        self._tuple_keyed = {
            "last_claim": last_claim,
            "last_overlap_notify": last_overlap_notify,
            "last_block_notify": last_block_notify,
            **({"last_file_read": last_file_read} if last_file_read is not None else {}),
        }

        # Non-session dicts (time-based pruning only)
        self._time_keyed = {
            "last_surface": last_surface,
            "last_peer_dir_check": last_peer_dir_check,
            "last_deadlock_push": last_deadlock_push,
        }

        # Misc state
        self._error_hashes = error_hashes
        self._hook_error_counts = hook_error_counts

        # All dicts for stats/reset
        self._all = {
            **self._session_keyed,
            **self._tuple_keyed,
            **self._time_keyed,
            "error_hashes": error_hashes,
            "hook_error_counts": hook_error_counts,
        }

    def cleanup(self, session_id: str) -> None:
        """Remove all entries for a session. Called from handle_session_stop."""
        # Session-keyed dicts: simple pop
        for d in self._session_keyed.values():
            d.pop(session_id, None)

        # Tuple-keyed dicts: filter by first element
        for d in self._tuple_keyed.values():
            stale = [k for k in d if k[0] == session_id]
            for k in stale:
                del d[k]

        # Clear session-scoped error tracking
        self._error_hashes.clear()

        # Clear per-session error rate tracking
        prefix = f":{session_id}"
        stale_rates = [k for k in self._hook_error_counts if prefix in k]
        for k in stale_rates:
            del self._hook_error_counts[k]

    def prune_stale(self, max_age: float) -> int:
        """Evict entries older than max_age seconds across all time-keyed dicts.

        Returns the total number of entries evicted.
        """
        now = time.monotonic()
        cutoff = now - max_age
        evicted = 0

        # Time-keyed dicts have float timestamps as values
        for d in self._time_keyed.values():
            stale = [k for k, v in d.items() if isinstance(v, (int, float)) and v < cutoff]
            for k in stale:
                del d[k]
            evicted += len(stale)

        # Session-keyed dicts with monotonic timestamps
        for name in ("last_heartbeat", "last_coord_query"):
            d = self._session_keyed[name]
            stale = [k for k, v in d.items() if isinstance(v, (int, float)) and v < cutoff]
            for k in stale:
                del d[k]
            evicted += len(stale)

        # Tuple-keyed dicts with monotonic timestamps
        for d in self._tuple_keyed.values():
            stale = [k for k, v in d.items() if isinstance(v, (int, float)) and v < cutoff]
            for k in stale:
                del d[k]
            evicted += len(stale)

        return evicted

    def stats(self) -> dict[str, int]:
        """Return entry counts per dict (for diagnostics)."""
        return {name: len(d) for name, d in sorted(self._all.items())}

    def reset(self) -> None:
        """Clear all state. Used for test isolation."""
        for d in self._all.values():
            if isinstance(d, set):
                d.clear()
            elif isinstance(d, dict):
                d.clear()
