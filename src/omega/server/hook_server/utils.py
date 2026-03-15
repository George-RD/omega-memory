"""Hook server utility functions — nickname, debounce, formatting, logging."""

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# Background executor for non-blocking hook work (parent detection, git baseline, etc.)
_HOOK_BG_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hook-bg")

logger = logging.getLogger("omega.hook_server")


def _omega_dir() -> Path:
    """Return the OMEGA home directory, respecting OMEGA_HOME env var."""
    return Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega")))


from . import (
    _AGENT_NAMES,
    _MAX_URGENT_PER_SESSION,
    _hook_error_counts,
    _pending_urgent,
)



def _agent_nickname(session_id: str) -> str:
    """Generate a deterministic, memorable nickname from a session ID.

    Pure hash: always returns the same name for the same session_id, matching
    the status bar algorithm. The 8-char hex suffix disambiguates collisions.

    Returns format: "Name (abcd1234)" — e.g. "Cedar (a3f2b1c8)".
    """
    if not session_id:
        return "unknown"
    if isinstance(session_id, bytes):
        session_id = session_id.decode("utf-8", errors="replace")
    elif not isinstance(session_id, str):
        session_id = str(session_id)
    idx = int(hashlib.md5(session_id.encode()).hexdigest()[:8], 16) % len(_AGENT_NAMES)
    return f"{_AGENT_NAMES[idx]} ({session_id[:8]})"







def notify_session(target_session_id: str, msg_summary: dict) -> None:
    """Queue an urgent message notification for a target session.

    Called from coord_handlers after a successful send_message. The recipient's
    next heartbeat (even if debounced) will drain and surface these.
    """
    try:
        if not target_session_id or not msg_summary:
            return
        queue = _pending_urgent.setdefault(target_session_id, [])
        queue.append(msg_summary)
        # Cap at max, keeping newest
        if len(queue) > _MAX_URGENT_PER_SESSION:
            _pending_urgent[target_session_id] = queue[-_MAX_URGENT_PER_SESSION:]
    except (KeyError, TypeError, ValueError):
        pass  # Fail-open




def _drain_urgent_queue(session_id: str) -> str:
    """Pop and format all pending urgent messages for a session.

    Returns formatted [INBOX] lines or empty string.
    """
    queue = _pending_urgent.pop(session_id, None)
    if not queue:
        return ""
    try:
        previews = []
        for msg in queue:
            from_name = _agent_nickname(msg.get("from_session") or "unknown")
            subj = (msg.get("subject") or "")[:60]
            mtype = msg.get("msg_type", "inform")
            previews.append(f'{from_name} [{mtype}]: "{subj}"')
        return "[INBOX] " + " | ".join(previews) + " — use omega_inbox for details"
    except (KeyError, TypeError, ValueError):
        return ""




def _secure_append(log_path: Path, data: str):
    """Append to a file with secure permissions (0o600)."""
    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)




def _log_hook_error(hook_name: str, error: Exception, *, session_id: str = ""):
    """Log hook errors to ~/.omega/hooks.log with structured context.

    Tracks per-handler error rate for diagnostics (via ``_hook_error_counts``).
    """
    try:
        # Track error rate
        rate_key = f"{hook_name}:{session_id}" if session_id else hook_name
        _hook_error_counts[rate_key] = _hook_error_counts.get(rate_key, 0) + 1

        error_type = type(error).__name__
        log_path = _omega_dir() / "hooks.log"
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tb = traceback.format_exc()
        sid_tag = f" sid={session_id[:12]}" if session_id else ""
        count = _hook_error_counts[rate_key]
        _secure_append(
            log_path,
            f"[{timestamp}] hook_server/{hook_name} [{error_type}]{sid_tag} (#{count}): {error}\n{tb}\n",
        )
    except Exception:
        pass  # Last resort: never propagate from the error logger




def _log_timing(hook_name: str, elapsed_ms: float):
    """Log hook timing to ~/.omega/hooks.log."""
    try:
        log_path = _omega_dir() / "hooks.log"
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _secure_append(log_path, f"[{timestamp}] hook_server/{hook_name}: OK ({elapsed_ms:.0f}ms)\n")
    except (KeyError, TypeError, ValueError):
        pass




def _auto_cloud_sync(session_id: str):
    """Fire-and-forget cloud sync on session stop. Fully fail-open."""
    try:
        secrets_path = _omega_dir() / "secrets.json"
        if not secrets_path.exists():
            return  # Cloud not configured — fast bail

        import threading

        def _sync():
            t0 = time.monotonic()
            try:
                from omega.cloud.sync import get_sync

                get_sync().sync_all()
                # Write push marker for status tracking
                push_marker = _omega_dir() / "last-cloud-push"
                push_marker.parent.mkdir(parents=True, exist_ok=True)
                push_marker.write_text(datetime.now(timezone.utc).isoformat())
                _log_timing("auto_cloud_sync", (time.monotonic() - t0) * 1000)
            except Exception as e:
                _log_hook_error("auto_cloud_sync", e)

        t = threading.Thread(target=_sync, daemon=True, name="omega-cloud-sync")
        t.start()
    except Exception as e:
        logger.debug("Cloud sync trigger failed: %s", e)




def _resolve_entity(project: str) -> "Optional[str]":
    """Resolve project→entity_id. Fail-open: returns None on any error.

    Delegates to resolve_project_entity() which reads config-file mappings.
    Returns None when no mappings exist or no match found.
    """
    try:
        from omega.entity.engine import resolve_project_entity

        return resolve_project_entity(project)
    except ImportError:
        return None
    except Exception:
        logger.debug("entity resolution failed for %s", project, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _relative_time_from_iso(iso_str: str) -> str:
    """Convert an ISO timestamp to a human-readable relative time like '2d ago'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = (datetime.now(timezone.utc) - dt).total_seconds()
        if secs < 0:
            return "just now"
        if secs < 60:
            return f"{int(secs)}s ago"
        if secs < 3600:
            return f"{int(secs / 60)}m ago"
        if secs < 86400:
            return f"{int(secs / 3600)}h ago"
        return f"{int(secs / 86400)}d ago"
    except (ValueError, TypeError, AttributeError):
        return ""




def _check_milestone(name: str) -> bool:
    """DEPRECATED: Use omega.milestones._check_milestone instead."""
    from omega.milestones import _check_milestone as _cm

    return _cm(name)




def _try_acquire_periodic(marker_name: str, interval_seconds: int):
    """Atomically check and claim a periodic task via file lock.

    Returns the old marker content (for rollback) if claimed, None if skipped.
    Uses fcntl.flock on Unix, msvcrt.locking on Windows.
    """
    omega_dir = _omega_dir()
    omega_dir.mkdir(parents=True, exist_ok=True)
    marker = omega_dir / marker_name
    lock_path = omega_dir / f"{marker_name}.lock"
    lock_fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lock_fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        os.close(lock_fd)
        return None

    try:
        old_content = None
        if marker.exists():
            old_content = marker.read_text().strip()
            last = datetime.fromisoformat(old_content)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - last).total_seconds()
            if age_seconds < interval_seconds:
                return None

        # Write marker BEFORE the slow operation to block other processes
        marker.write_text(datetime.now(timezone.utc).isoformat())
        return old_content if old_content else ""
    except (OSError, ValueError):
        return None
    finally:
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)




def _rollback_marker(marker_name: str, old_content: str) -> None:
    """Restore a marker to its previous value on failure."""
    marker = _omega_dir() / marker_name
    if old_content == "":
        marker.unlink(missing_ok=True)
    else:
        marker.write_text(old_content)




def _should_run_periodic(marker_name: str, interval_seconds: int) -> bool:
    """Legacy wrapper: check if a periodic task is due (no locking).

    Used by non-critical periodic tasks (digest, error-mine, dedup-hygiene)
    where concurrent execution is harmless. Critical tasks (consolidate,
    compact, backup) use _try_acquire_periodic instead.
    """
    marker = _omega_dir() / marker_name
    if not marker.exists():
        return True
    try:
        last_ts = marker.read_text().strip()
        last = datetime.fromisoformat(last_ts)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - last).total_seconds()
        return age_seconds >= interval_seconds
    except (OSError, ValueError):
        return True




def _update_marker(marker_name: str) -> None:
    """Write current UTC timestamp to a marker file."""
    marker = _omega_dir() / marker_name
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now(timezone.utc).isoformat())




def _parse_tool_input(payload: dict) -> dict:
    """Parse tool_input from a hook payload into a dict. Returns {} on failure."""
    raw = payload.get("tool_input", "{}")
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (json.JSONDecodeError, TypeError):
        return {}




def _get_file_path_from_input(input_data: dict) -> str:
    """Extract file_path or notebook_path from parsed tool input."""
    return input_data.get("file_path", input_data.get("notebook_path", ""))




def _debounce_check(cache: dict, key, debounce_s: float, max_entries: int) -> bool:
    """Check if a key has been seen within debounce_s seconds.

    Returns True if the action should proceed (not debounced).
    Updates the cache timestamp and evicts the oldest entry if over max_entries.
    Supports both plain dict and OrderedDict; uses O(1) eviction with OrderedDict.
    """
    from collections import OrderedDict

    now = time.monotonic()
    if key in cache and now - cache[key] < debounce_s:
        # Move to end on access if OrderedDict (keeps LRU order)
        if isinstance(cache, OrderedDict):
            cache.move_to_end(key)
        return False
    cache[key] = now
    if isinstance(cache, OrderedDict):
        cache.move_to_end(key)
    if len(cache) > max_entries:
        if isinstance(cache, OrderedDict):
            cache.popitem(last=False)  # O(1) eviction of oldest
        else:
            oldest = min(cache, key=cache.get)
            del cache[oldest]
    return True




def _format_age(dt_str: str) -> str:
    """Format a datetime ISO string as a human-readable relative age.

    Returns e.g. "5m ago", "2h15m ago", or "" on failure.
    """
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        delta = datetime.now(timezone.utc).replace(tzinfo=None) - dt
        mins = int(delta.total_seconds() / 60)
        if mins < 60:
            return f"{mins}m ago"
        return f"{mins // 60}h{mins % 60}m ago"
    except (ValueError, TypeError, AttributeError):
        return ""




def _append_output(existing: str, new_line: str) -> str:
    """Append a line to output with newline separator."""
    return (existing + "\n" + new_line) if existing else new_line


# ---------------------------------------------------------------------------
# Personal briefing helpers
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Personal briefing helpers
# ---------------------------------------------------------------------------


def _get_user_name() -> str:
    """Try to get the user's display name from the profile engine."""
    try:
        from omega.profile.engine import get_profile_engine
        pe = get_profile_engine()
        for field in ("display_name", "name", "first_name"):
            try:
                val = pe.get_field("identity", field)
                if val and not val.startswith("Error") and not val.startswith("No field"):
                    return val.split()[0]
            except (KeyError, TypeError, ValueError):
                continue
    except Exception as e:
        logger.debug("_get_user_name failed: %s", e)
    return ""




def _agent_name_only(session_id: str) -> str:
    """Get just the name part of an agent nickname (no ID suffix)."""
    if not session_id:
        return ""
    h = hashlib.md5(session_id.encode()).hexdigest()
    idx = int(h[:8], 16) % len(_AGENT_NAMES)
    return _AGENT_NAMES[idx]




def _get_last_session_info(current_session_id: str) -> dict:
    """Get info about the most recently ended session for the personal greeting."""
    result = {"agent_name": "", "task": "", "ended_ago": "", "checkpoint_text": ""}
    try:
        db_path = _omega_dir() / "omega.db"
        if not db_path.exists():
            return result
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT session_id, task, last_heartbeat FROM coord_sessions "
                "WHERE status = 'ended' AND session_id != ? "
                "ORDER BY last_heartbeat DESC LIMIT 1",
                (current_session_id,),
            ).fetchone()
            if row:
                sid = row["session_id"] or ""
                result["agent_name"] = _agent_name_only(sid)
                task_text = row["task"] or ""
                if task_text and task_text not in ("idle", "no task", "null", "New session"):
                    result["task"] = task_text
                if row["last_heartbeat"]:
                    try:
                        ended_dt = datetime.fromisoformat(row["last_heartbeat"].replace("Z", "+00:00"))
                        if ended_dt.tzinfo is None:
                            ended_dt = ended_dt.replace(tzinfo=timezone.utc)
                        delta = datetime.now(timezone.utc) - ended_dt
                        secs = delta.total_seconds()
                        if secs < 60:
                            result["ended_ago"] = f"{int(secs)}s ago"
                        elif secs < 3600:
                            result["ended_ago"] = f"{int(secs/60)}m ago"
                        elif secs < 86400:
                            result["ended_ago"] = f"{int(secs/3600)}h ago"
                        else:
                            result["ended_ago"] = f"{int(secs/86400)}d ago"
                    except (ValueError, TypeError, AttributeError):
                        pass

            ckpt_row = conn.execute(
                "SELECT content FROM memories "
                "WHERE event_type = 'checkpoint' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()
            if ckpt_row:
                content = ckpt_row["content"] or ""
                first_line = content.split("\n")[0].strip()
                if first_line.startswith("CHECKPOINT: "):
                    first_line = first_line[12:]
                result["checkpoint_text"] = first_line[:120]
        finally:
            conn.close()
    except (OSError, ValueError, sqlite3.OperationalError):
        pass
    return result


# ---------------------------------------------------------------------------
# Git utilities
# ---------------------------------------------------------------------------


def _get_current_branch(project: str) -> str | None:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _parse_checkout_target(command: str) -> str | None:
    """Parse the target branch from git checkout/switch commands.

    Returns None for new branch creation (-b/-B/-c/-C/--orphan)
    and file restores (-- separator).
    """
    for segment in re.split(r"&&|\|\||;", command):
        segment = segment.strip()
        match = re.match(r"git\s+(checkout|switch)\s+(.*)", segment)
        if not match:
            continue
        args_str = match.group(2).strip()

        if re.search(r"(?:^|\s)-[bBcC]\b", args_str):
            return None
        if "--orphan" in args_str:
            return None
        if " -- " in args_str or args_str.startswith("-- "):
            return None

        for token in args_str.split():
            if token.startswith("-"):
                continue
            return token

    return None
