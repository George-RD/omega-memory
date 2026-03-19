"""Session start/stop hook handlers."""

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import sqlite3
import subprocess
import time

logger = logging.getLogger("omega.hook_server.session")

from . import (
    _debounce_state,
    _last_surface,
)

from .utils import (
    _get_current_branch,
    _agent_nickname,
    _auto_cloud_sync,
    _get_last_session_info,
    _get_user_name,
    _log_hook_error,
    _omega_dir,
    _resolve_entity,
    _should_run_periodic,
    _update_marker,
)



# ---------------------------------------------------------------------------
# User tier system — adapts welcome based on OMEGA journey stage
# ---------------------------------------------------------------------------

_TIERS = [
    (10, "Newcomer", "First Seed"),
    (50, "Explorer", "Growing Graph"),
    (200, "Builder", "Power Builder"),
    (1000, "Veteran", "Veteran"),
    (float("inf"), "Unhinged", "Unhinged"),
]

# Tools to suggest per tier (lower tiers get basics, higher tiers get power features)
_TIER_TIPS = {
    "Explorer": {
        "omega_query": "search past decisions relevant to your current task",
        "omega_remind": "set reminders for follow-ups",
        "omega_checkpoint": "save your progress so the next session can pick up where you left off",
    },
    "Builder": {
        "omega_relate": "link related memories to build a richer knowledge graph",
        "omega_weekly_digest": "get a weekly summary of your activity",
        "omega_coord_status": "see what other agents are working on",
        "omega_consult_claude": "get a second opinion from Claude on complex decisions",
    },
}


def _get_user_tier(memory_count: int) -> tuple[str, str, bool]:
    """Return (tier_name, badge, is_graduation).

    Graduation is detected by comparing against ~/.omega/tier-milestone marker.
    """
    tier_name, badge = "Newcomer", "First Seed"
    for threshold, name, bdg in _TIERS:
        if memory_count <= threshold:
            tier_name, badge = name, bdg
            break

    # Check for graduation
    is_graduation = False
    marker_path = _omega_dir() / "tier-milestone"
    try:
        previous_tier = marker_path.read_text().strip() if marker_path.exists() else ""
        if tier_name != previous_tier and previous_tier != "":
            # Graduated to a new tier (not first session)
            is_graduation = True
        marker_path.write_text(tier_name)
    except OSError:
        pass

    return tier_name, badge, is_graduation


def _get_unused_features(tier: str) -> str | None:
    """Return one tip about an undiscovered tool for this tier, or None."""
    tips = _TIER_TIPS.get(tier)
    if not tips:
        return None

    try:
        omega_home = Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega")))
        db_path = omega_home / "llm_usage.db"
        if not db_path.exists():
            # No usage data yet — pick the first tip
            first_tool = next(iter(tips))
            return f"Try `{first_tool}()` — it can {tips[first_tool]}."
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            used = {r[0] for r in conn.execute("SELECT DISTINCT tool_name FROM llm_usage").fetchall()}
        finally:
            conn.close()
        unused = {t: desc for t, desc in tips.items() if t not in used}
        if unused:
            tool, desc = next(iter(unused.items()))
            return f"Try `{tool}()` — it can {desc}."
    except Exception:
        pass
    return None


_UNHINGED_GREETINGS_PATH = Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega"))) / "unhinged-greetings.json"


def _pop_unhinged_greeting() -> str | None:
    """Pop one pre-generated Grok greeting from the cache queue.

    Returns the greeting text or None if the queue is empty / unreadable.
    """
    try:
        if not _UNHINGED_GREETINGS_PATH.exists():
            return None
        queue = json.loads(_UNHINGED_GREETINGS_PATH.read_text())
        if not isinstance(queue, list) or not queue:
            return None
        greeting = queue.pop(0)
        # Atomic write: write to temp file then os.replace() (POSIX-atomic)
        tmp_path = _UNHINGED_GREETINGS_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(queue, indent=2))
        os.replace(tmp_path, _UNHINGED_GREETINGS_PATH)
        return greeting
    except (OSError, json.JSONDecodeError, IndexError) as e:
        _log_hook_error("pop_unhinged_greeting", e)
        return None


def _pregenerate_unhinged_greeting(memory_count: int, session_summary: str) -> None:
    """Fire-and-forget: call xAI Grok to pre-generate an Unhinged greeting.

    Called at session stop. Stores the result in the greeting queue for the
    next session start to pop. Does nothing if the user hasn't reached 1000
    memories or if the queue already has 5+ greetings buffered.
    """
    try:
        if not isinstance(memory_count, int) or memory_count < 1000:
            return
    except TypeError:
        return

    # Don't over-fill the queue
    try:
        if _UNHINGED_GREETINGS_PATH.exists():
            queue = json.loads(_UNHINGED_GREETINGS_PATH.read_text())
            if isinstance(queue, list) and len(queue) >= 5:
                return
    except (OSError, json.JSONDecodeError):
        pass

    # Read xAI API key
    try:
        secrets_path = _omega_dir() / "secrets.json"
        if not secrets_path.exists():
            return
        secrets = json.loads(secrets_path.read_text())
        xai_key = secrets.get("XAI_API_KEY")
        if not xai_key:
            return
    except (OSError, json.JSONDecodeError):
        return

    import urllib.request
    from .utils import _HOOK_BG_EXECUTOR

    def _generate():
        try:
            prompt = (
                "You are writing a short behavioral directive for an AI coding assistant "
                "at the start of a conversation. The user has 1000+ memories stored with OMEGA "
                "and has earned the 'Unhinged' tier — they're a power user who wants personality, "
                "not corporate pleasantries.\n\n"
                "Write a 2-3 sentence directive that tells the AI how to behave this session. "
                "Be creative, irreverent, and funny. Reference the session context below for flavor. "
                "The directive should still be FUNCTIONAL — it must tell the agent to skip boot-up "
                "narration, open with situational awareness, and be direct. But do it with style.\n\n"
                "DO NOT use emojis. DO NOT be cringe. Think dry wit, not try-hard.\n\n"
                f"Session context: {session_summary[:500]}\n"
                f"Memory count: {memory_count}\n\n"
                "Output ONLY the directive text, nothing else."
            )

            body = json.dumps({
                "model": "grok-3-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.9,
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.x.ai/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {xai_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read().decode("utf-8"))
            greeting = result["choices"][0]["message"]["content"].strip()

            if not greeting or len(greeting) < 20:
                return

            # Append to queue (atomic read-modify-write)
            queue = []
            try:
                if _UNHINGED_GREETINGS_PATH.exists():
                    queue = json.loads(_UNHINGED_GREETINGS_PATH.read_text())
                    if not isinstance(queue, list):
                        queue = []
            except (OSError, json.JSONDecodeError):
                queue = []

            queue.append(greeting)
            # Atomic write: write to temp file then os.replace() (POSIX-atomic)
            tmp_path = _UNHINGED_GREETINGS_PATH.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(queue, indent=2))
            os.replace(tmp_path, _UNHINGED_GREETINGS_PATH)
        except Exception:
            pass  # Fire-and-forget — never block session stop

    _HOOK_BG_EXECUTOR.submit(_generate)


def _build_context_nugget(
    tier: str,
    peers: list[dict],
    last_info: dict,
    pending_tasks: list[dict],
    git_status_str: str,
    streak: dict | None,
    memory_count: int,
    tip: str | None,
) -> str:
    """Assemble a situational context nugget for the [GREET] block."""
    parts: list[str] = []

    # Solo vs team
    if peers:
        peer_descs = []
        for p in peers[:3]:
            pname = _agent_nickname(p.get("session_id", ""))
            ptask = p.get("task", "")
            if ptask and ptask not in ("idle", "no task", "null", "New session"):
                peer_descs.append(f"{pname} on {ptask[:30]}")
            else:
                peer_descs.append(pname)
        parts.append(f"{len(peers)} peer{'s' if len(peers) != 1 else ''} active ({', '.join(peer_descs)})")
    else:
        parts.append("solo session")

    # Last session / checkpoint
    if last_info.get("checkpoint_text"):
        parts.append(f'checkpoint "{last_info["checkpoint_text"][:50]}"')
    elif last_info.get("ended_ago"):
        parts.append(f"last session {last_info['ended_ago']}")

    # Pending tasks
    if pending_tasks:
        top = pending_tasks[0]
        parts.append(f"{len(pending_tasks)} task{'s' if len(pending_tasks) != 1 else ''} pending (top: {top['title'][:40]})")

    # Git status
    if git_status_str not in ("Clean", "unknown"):
        parts.append(git_status_str)

    # Streak only at milestones
    if streak and streak.get("current", 0) in (7, 30, 100, 365):
        parts.append(f"{streak['current']}-day streak milestone")

    nugget = "Situation: " + ", ".join(parts) + "."

    # Behavioral directive — adapted by tier and solo/team mode
    if tier == "Unhinged":
        directive = _pop_unhinged_greeting()
        if not directive:
            # Fallback to Veteran directive if no cached greeting available
            directive = (
                "You are a veteran OMEGA agent — you know this system inside out. "
                "Never narrate boot-up or say you're getting oriented. "
                "Open with brief situational awareness, not pleasantries."
            )
    elif tier == "Veteran":
        directive = (
            "You are a veteran OMEGA agent — you know this system inside out. "
            "Never narrate boot-up or say you're getting oriented. "
            "Open with brief situational awareness, not pleasantries."
        )
    elif tier == "Builder":
        directive = (
            "You are an experienced OMEGA agent. Never narrate boot-up. "
            "Be efficient and share one power tip if relevant."
        )
    elif tier == "Explorer":
        directive = (
            "You are a knowledgeable OMEGA agent helping a growing user. "
            "Never narrate boot-up. Be warm and offer one feature discovery tip."
        )
    else:  # Newcomer
        directive = (
            "You are a friendly OMEGA agent helping a new user get started. "
            "Be encouraging. Explain how OMEGA helps as you work."
        )

    if peers:
        directive += " Coordinate with peers — check claims before editing shared files."

    # Append tip if available
    if tip:
        directive += f" Tip to share: {tip}"

    return f"{nugget}\n{directive}"


# ---------------------------------------------------------------------------
# Handler functions — replicate hook script logic using warm singletons
# ---------------------------------------------------------------------------


def handle_session_start(payload: dict) -> dict:
    """Welcome briefing + auto-consolidation check."""
    session_id = payload.get("session_id", "")
    project = payload.get("project", "")

    # GC stale debounce entries from dead sessions (1 hour threshold)
    _debounce_state.prune_stale(3600)

    # Run maintenance pipeline (consolidate, compact, backup, doctor, doc_scan, cloud_pull, surfacing_gc)
    from .maintenance import build_session_start_pipeline

    maintenance_pipeline = build_session_start_pipeline()
    maintenance_result = maintenance_pipeline.run()

    # Backward-compatible summary extraction
    doctor_summary = maintenance_result.get_output("doctor") or ""
    doc_scan_summary = maintenance_result.get_output("doc_scan") or ""
    cloud_pull_summary = maintenance_result.get_output("cloud_pull") or ""

    # Gather session context for briefing
    try:
        from omega.bridge import get_session_context

        ctx = get_session_context(project=project, exclude_session=session_id)
    except (ImportError) as e:
        _log_hook_error("session_start", e)
        return {"output": f"OMEGA welcome failed: {e}", "error": str(e)}

    memory_count = ctx.get("memory_count", 0)
    health_status = ctx.get("health_status", "ok")
    last_capture = ctx.get("last_capture_ago", "unknown")
    context_items = ctx.get("context_items", [])

    # Detect project name and git branch/status
    project_name = Path(project).name if project else "unknown"
    git_branch = _get_current_branch(project or ".") or "unknown"
    git_status_str = "unknown"
    try:
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project or ".",
        )
        if status_result.returncode == 0:
            changed = len([l for l in status_result.stdout.strip().split("\n") if l.strip()])
            git_status_str = "Clean" if changed == 0 else f"{changed} unstaged changes"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # ===================================================================
    # OUTPUT BUILDING — Three-zone layout for prompt cache optimization
    # Stable content first (cache-friendly prefix), volatile content last.
    # Zones joined with <!-- omega:cache_breakpoint --> markers.
    # ===================================================================

    stable: list[str] = []    # [PROTOCOL], [PATTERNS], [OMEGA MEMORY], [GREET], footer
    semi: list[str] = []      # Greeting, alerts, [CONTEXT] stable items
    volatile: list[str] = []  # [RECENT ACTIVITY], tasks, reminders, nudges

    # --- Layer 1: Personal Greeting (first 2-3 lines) ---

    # First-time user onboarding — bootstrap project scan + quick start guide
    if memory_count == 0:
        # New users get a simple flat output (no cache optimization needed)
        onboard_lines: list[str] = []
        # Run project bootstrap scan
        bootstrap_summary = ""
        bootstrap_count = 0
        try:
            from omega.bootstrap import scan_project, format_summary, store_bootstrap

            if project:
                ctx = scan_project(project)
                if ctx:
                    bootstrap_summary = format_summary(ctx)
                    entity = Path(project).name if project else ""
                    bootstrap_count = store_bootstrap(ctx, project=project, entity_id=entity)
        except Exception as e:
            _log_hook_error("bootstrap", e)

        if bootstrap_summary:
            onboard_lines.append("Welcome! I scanned your project and learned:")
            onboard_lines.append(bootstrap_summary)
            onboard_lines.append("")
            if bootstrap_count:
                onboard_lines.append(f"Stored {bootstrap_count} project memories. I'll build on these as we work.")
            onboard_lines.append("")

            # Demo recall card — show what memory surfacing looks like
            try:
                from omega.bridge import query_structured as _qs_demo
                demo_results = _qs_demo(
                    query_text="project context",
                    limit=1,
                    project=project,
                    event_type="project_context",
                )
                if demo_results:
                    demo_content = demo_results[0].get("content", "")[:100].replace("\n", " ").strip()
                    if demo_content:
                        onboard_lines.append("Here's how recall works -- when you edit a file, you'll see:")
                        onboard_lines.append(f"  [OMEGA] project_context: {demo_content}")
                        onboard_lines.append("")
                        onboard_lines.append("This happens automatically. No action needed.")
                        onboard_lines.append("")
            except Exception:
                pass  # Demo card is best-effort
        else:
            onboard_lines.append("Welcome! OMEGA is ready.")
            onboard_lines.append("")

        onboard_lines.append("OMEGA captures decisions, lessons, and errors automatically as you work.")
        onboard_lines.append("Next session, I'll surface relevant context from this one.")
        onboard_lines.append("")
        onboard_lines.append("**Quick start:**")
        onboard_lines.append('- Say "remember X" to store a preference')
        onboard_lines.append("- Decisions and errors are captured automatically")
        onboard_lines.append("")

        # Footer for new users
        onboard_lines.append(f"OMEGA: {bootstrap_count} memories | {health_status}")
        return {"output": "\n".join(onboard_lines), "error": None}

    # Returning user — warm personal greeting
    # Time-of-day greeting
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        greeting_tod = "Good morning"
    elif 12 <= current_hour < 17:
        greeting_tod = "Good afternoon"
    elif 17 <= current_hour < 22:
        greeting_tod = "Good evening"
    else:
        greeting_tod = "Evening"

    # User name
    user_name = _get_user_name()

    # Usage streak (suppress noise — only surface at milestones)
    streak: dict | None = None
    streak_text = ""
    try:
        from omega.milestones import get_streak, check_streak_milestones
        from omega.bridge import _get_store as _gs_streak

        _store_streak = _gs_streak()
        streak = get_streak(_store_streak)
        # Only mention streak at milestones (7, 30, 100, 365) — not every session
        if streak["current"] in (7, 30, 100, 365):
            streak_text = f" {streak['current']}-day streak!"
        streak_milestone = check_streak_milestones(streak["current"])
        if streak_milestone:
            semi.append(f"[MILESTONE] {streak_milestone}")
    except Exception as e:
        _log_hook_error("handle_session_start", e)

    # Tier system — adapt welcome based on user journey
    tier_name, tier_badge, is_graduation = _get_user_tier(memory_count)
    if is_graduation:
        semi.append(f"[MILESTONE] You've reached {tier_badge} tier ({tier_name}). {memory_count:,} memories and growing.")

    # Build greeting line
    if user_name:
        semi.append(f"{greeting_tod}, {user_name}.{streak_text}")
    else:
        semi.append(f"{greeting_tod}.{streak_text}")

    # Early user encouragement (memory_count <= 10)
    if memory_count <= 10:
        semi.append(
            f"OMEGA has {memory_count} memories from your first sessions. These will surface when you edit related files."
        )
        try:
            from omega.bridge import type_stats as _ts_first

            first_stats = _ts_first()
            stat_parts = []
            for k, v in sorted(first_stats.items(), key=lambda x: x[1], reverse=True):
                if v > 0 and k != "session_summary":
                    stat_parts.append(f"{v} {k.replace('_', ' ')}")
            if stat_parts:
                semi.append(f"Captured so far: {', '.join(stat_parts[:4])}")
        except Exception as e:
            _log_hook_error("handle_session_start", e)

    # Last session info + checkpoint
    last_info = _get_last_session_info(session_id)
    if last_info["ended_ago"] or last_info["task"]:
        agent_label = last_info["agent_name"] or "Previous session"
        if last_info["ended_ago"]:
            line_start = f"{agent_label}'s last session ended {last_info['ended_ago']}"
        else:
            line_start = f"{agent_label} was here"
        if last_info["task"]:
            task_preview = last_info["task"][:60]
            semi.append(f"{line_start}, working on: {task_preview}.")
        else:
            semi.append(f"{line_start}.")
    if last_info["checkpoint_text"]:
        semi.append(f"You left off at: {last_info['checkpoint_text']}")

    # --- Layer 1.5: Recent Activity (what happened recently) ---
    # This is the key proactive context — agents know what was accomplished
    # without needing to call omega_welcome() or omega_query().
    # Pure SQLite index scan, no embeddings — <10ms overhead.
    # Decisions use a 7-day window (rare, high-value); other types use 48h.
    try:
        from omega.bridge import _get_store as _gs_recent

        _store_recent = _gs_recent()
        _now_recent = datetime.now(timezone.utc)
        _cutoff_48h = (_now_recent - timedelta(hours=48)).isoformat()
        _cutoff_7d = (_now_recent - timedelta(days=7)).isoformat()
        _recent_types_48h = (
            "task_completion", "lesson_learned", "error_pattern",
        )
        _placeholders_48h = ",".join("?" for _ in _recent_types_48h)

        # Prefer project-scoped activity when we know the project
        _recent_entity = _resolve_entity(project) if project else None
        if _recent_entity:
            # Decisions from last 7 days
            _recent_rows = list(_store_recent._conn.execute(
                "SELECT content, event_type, created_at FROM memories "
                "WHERE event_type = 'decision' "
                "AND created_at >= ? AND entity_id = ? "
                "ORDER BY created_at DESC LIMIT 10",
                (_cutoff_7d, _recent_entity),
            ).fetchall())
            # Other types from last 48h
            _recent_rows += _store_recent._conn.execute(
                f"SELECT content, event_type, created_at FROM memories "
                f"WHERE event_type IN ({_placeholders_48h}) "
                f"AND created_at >= ? AND entity_id = ? "
                f"ORDER BY created_at DESC LIMIT 10",
                (*_recent_types_48h, _cutoff_48h, _recent_entity),
            ).fetchall()
            # If project has <3 items, supplement with cross-project activity
            if len(_recent_rows) < 3:
                _seen_content = {r[0][:50] if isinstance(r, (list, tuple)) else r["content"][:50] for r in _recent_rows}
                _cross_rows = list(_store_recent._conn.execute(
                    "SELECT content, event_type, created_at FROM memories "
                    "WHERE event_type = 'decision' "
                    "AND created_at >= ? "
                    "ORDER BY created_at DESC LIMIT 10",
                    (_cutoff_7d,),
                ).fetchall())
                _cross_rows += _store_recent._conn.execute(
                    f"SELECT content, event_type, created_at FROM memories "
                    f"WHERE event_type IN ({_placeholders_48h}) "
                    f"AND created_at >= ? "
                    f"ORDER BY created_at DESC LIMIT 10",
                    (*_recent_types_48h, _cutoff_48h),
                ).fetchall()
                for cr in _cross_rows:
                    _cr_content = cr[0] if isinstance(cr, (list, tuple)) else cr["content"]
                    if _cr_content[:50] not in _seen_content:
                        _recent_rows.append(cr)
                        _seen_content.add(_cr_content[:50])
                    if len(_recent_rows) >= 10:
                        break
        else:
            # Decisions from last 7 days
            _recent_rows = list(_store_recent._conn.execute(
                "SELECT content, event_type, created_at FROM memories "
                "WHERE event_type = 'decision' "
                "AND created_at >= ? "
                "ORDER BY created_at DESC LIMIT 10",
                (_cutoff_7d,),
            ).fetchall())
            # Other types from last 48h
            _recent_rows += _store_recent._conn.execute(
                f"SELECT content, event_type, created_at FROM memories "
                f"WHERE event_type IN ({_placeholders_48h}) "
                f"AND created_at >= ? "
                f"ORDER BY created_at DESC LIMIT 10",
                (*_recent_types_48h, _cutoff_48h),
            ).fetchall()

        if _recent_rows:
            # Format as brief timeline
            _activity_lines: list[str] = []
            for row in _recent_rows:
                if isinstance(row, (list, tuple)):
                    _r_content, _r_type, _r_created = row
                else:
                    _r_content = row["content"]
                    _r_type = row["event_type"]
                    _r_created = row["created_at"]

                # Relative time
                try:
                    if isinstance(_r_created, str):
                        _r_dt = datetime.fromisoformat(_r_created.replace("Z", "+00:00"))
                    else:
                        _r_dt = datetime.fromtimestamp(_r_created, tz=timezone.utc)
                    _r_age_s = (_now_recent - _r_dt).total_seconds()
                    if _r_age_s < 3600:
                        _r_ago = f"{int(_r_age_s / 60)}m ago"
                    elif _r_age_s < 86400:
                        _r_ago = f"{int(_r_age_s / 3600)}h ago"
                    else:
                        _r_ago = f"{int(_r_age_s / 86400)}d ago"
                except (ValueError, TypeError, OSError):
                    _r_ago = "recently"

                # Type label
                _type_labels = {
                    "decision": "decided",
                    "task_completion": "completed",
                    "lesson_learned": "learned",
                    "error_pattern": "error",
                }
                _r_label = _type_labels.get(_r_type, _r_type)

                # Extract first meaningful line, trim to 100 chars
                _r_summary = _r_content.split("\n")[0].strip()
                # Strip common prefixes (case-insensitive match, preserve original casing)
                for _prefix in (
                    "DECISION: ", "TASK: ", "LESSON: ", "ERROR: ",
                    "Assistant lesson: ", "status: ", "resume: ",
                    "Completed: ", "Task completed: ",
                ):
                    if _r_summary.lower().startswith(_prefix.lower()):
                        _r_summary = _r_summary[len(_prefix):]
                        break
                _r_summary = _r_summary[:200]
                if len(_r_content.split("\n")[0].strip()) > 200:
                    _r_summary += "..."

                _activity_lines.append(f"  {_r_ago}: [{_r_label}] {_r_summary}")

            if _activity_lines:
                volatile.append("")
                volatile.append("[RECENT ACTIVITY] Recent (decisions 7d, other 48h):")
                volatile.extend(_activity_lines[:7])  # Cap at 7 to avoid noise
    except (sqlite3.OperationalError, Exception) as e:
        _log_hook_error("recent_activity", e)

    # Dead memory surfacing — memories never accessed, 14+ days old
    try:
        from omega.bridge import _get_store as _gs_dead

        _dead_store = _gs_dead()
        _dead_rows = _dead_store._conn.execute(
            "SELECT node_id, content FROM memories "
            "WHERE access_count = 0 "
            "AND created_at < datetime('now', '-14 days') "
            "AND event_type NOT IN ('session_summary', 'checkpoint', 'behavioral_pattern') "
            "ORDER BY created_at ASC LIMIT 3"
        ).fetchall()
        _dead_total_row = _dead_store._conn.execute(
            "SELECT COUNT(*) FROM memories "
            "WHERE access_count = 0 "
            "AND created_at < datetime('now', '-14 days') "
            "AND event_type NOT IN ('session_summary', 'checkpoint', 'behavioral_pattern')"
        ).fetchone()
        _dead_total = _dead_total_row[0] if _dead_total_row else 0
        if _dead_rows:
            volatile.append(
                f"**Dead memories ({_dead_total} never accessed, 14+ days old)** — review or delete:"
            )
            for row in _dead_rows:
                if isinstance(row, (list, tuple)):
                    _d_node_id, _d_content = row[0], row[1]
                else:
                    _d_node_id = row["node_id"]
                    _d_content = row["content"]
                _d_preview = _d_content[:80]
                volatile.append(f"  - `{_d_node_id}`: {_d_preview}...")
    except Exception as e:
        _log_hook_error("dead_memories_welcome", e)

    # Stale memory insights — from weekly auto-reflect
    try:
        from omega.bridge import _get_store as _gs_stale

        _stale_store = _gs_stale()
        _stale_rows = _stale_store._conn.execute(
            "SELECT content FROM memories "
            "WHERE event_type = 'advisor_insight' "
            "AND json_extract(metadata, '$.source') = 'auto_reflect_stale' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchall()
        if _stale_rows:
            _stale_content = (
                _stale_rows[0][0]
                if isinstance(_stale_rows[0], (list, tuple))
                else _stale_rows[0]["content"]
            )
            _stale_lines = _stale_content.strip().split("\n")
            volatile.append("**Stale memories to review** (from weekly auto-reflect):")
            for _sl in _stale_lines[:5]:
                volatile.append(f"  {_sl}")
    except Exception as e:
        _log_hook_error("stale_insights_welcome", e)

    # --- Layer 2: What's Ahead (natural language) ---

    # Gather tasks data with freshness-weighted scoring
    pending_tasks: list[dict] = []
    try:
        import math as _math_tasks
        from omega.bridge import _get_store as _gs_tasks

        _task_store = _gs_tasks()
        _task_rows = _task_store._conn.execute(
            "SELECT node_id, content, priority, entity_id, created_at, access_count "
            "FROM memories "
            "WHERE event_type = 'task' "
            "ORDER BY priority DESC, created_at DESC LIMIT 20"
        ).fetchall()
        _now_ts = time.time()
        for row in _task_rows:
            if isinstance(row, (list, tuple)):
                node_id, content, priority, entity_id, created_at, access_count = row
            else:
                node_id = row["node_id"]
                content = row["content"]
                priority = row["priority"]
                entity_id = row.get("entity_id", "")
                created_at = row.get("created_at", "")
                access_count = row.get("access_count", 0)
            if "STATUS: done" in content or "STATUS: completed" in content:
                continue
            # Auto-expire: tasks older than 14 days with 20+ views are stale
            _ac_raw = access_count or 0
            _age_raw = 0.0
            if created_at:
                try:
                    if isinstance(created_at, str):
                        _ct_check = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    else:
                        _ct_check = datetime.fromtimestamp(created_at, tz=timezone.utc)
                    _age_raw = (_now_ts - _ct_check.timestamp()) / 86400.0
                except ValueError:
                    pass
            if _age_raw > 14 and _ac_raw >= 20:
                continue
            # Extract title
            title = content
            if title.startswith("TASK: "):
                title = title[6:]
            title = title.split("\n")[0].split("STATUS:")[0].strip()[:80]
            # Compute age in days
            age_days = 0.0
            if created_at:
                try:
                    if isinstance(created_at, str):
                        _ct = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    else:
                        _ct = datetime.fromtimestamp(created_at, tz=timezone.utc)
                    age_days = (_now_ts - _ct.timestamp()) / 86400.0
                except (ValueError) as e:
                    _log_hook_error("handle_session_start", e)
            # Blended score: priority (0.4) + recency (0.3) + freshness (0.3)
            # Recency: exp decay, half-life ~7 days
            # Freshness: penalize tasks shown many times without resolution
            _pri = (priority or 3) / 5.0  # normalize to 0.2-1.0
            _recency = _math_tasks.exp(-0.099 * age_days)  # ~0.5 at 7d, ~0.25 at 14d
            _ac = access_count or 0
            _freshness = 1.0 / (1.0 + 0.1 * _ac)  # 1.0 at 0, 0.5 at 10, 0.17 at 48
            _score = _pri * 0.4 + _recency * 0.3 + _freshness * 0.3
            # Hard suppress: tasks shown 20+ times are almost certainly stale
            if _ac >= 20:
                _score *= 0.1
            pending_tasks.append(
                {
                    "id": node_id,
                    "content": content,
                    "title": title,
                    "priority": priority or 3,
                    "entity": entity_id or "",
                    "age_days": age_days,
                    "access_count": access_count or 0,
                    "score": _score,
                }
            )
        # Cross-reference: auto-resolve tasks that have matching task_completion memories
        try:
            _completions = _task_store._conn.execute(
                "SELECT content FROM memories "
                "WHERE event_type = 'task_completion' "
                "ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            _completion_texts = [
                (r[0] if isinstance(r, (list, tuple)) else r["content"]).lower()
                for r in _completions
            ]
            if _completion_texts:
                _resolved_ids = []
                for t in pending_tasks:
                    # Check if any completion memory references keywords from this task
                    _task_words = set(t["title"].lower().split())
                    # Need at least 3 matching words (avoid false positives)
                    for ct in _completion_texts:
                        _matches = sum(1 for w in _task_words if len(w) > 3 and w in ct)
                        if _matches >= 3:
                            _resolved_ids.append(t["id"])
                            break
                if _resolved_ids:
                    # Mark as done in DB so they don't come back
                    with _task_store._lock:
                        for _rid in _resolved_ids:
                            _task_store._conn.execute(
                                "UPDATE memories SET content = content || '\nSTATUS: done (auto-resolved)' "
                                "WHERE node_id = ?",
                                (_rid,),
                            )
                        _task_store._conn.commit()
                    pending_tasks = [t for t in pending_tasks if t["id"] not in _resolved_ids]
        except (sqlite3.OperationalError, Exception) as e:
            _log_hook_error("task_auto_resolve", e)

        # Sort by blended score (not raw priority)
        pending_tasks.sort(key=lambda t: t["score"], reverse=True)
        pending_tasks = pending_tasks[:10]

        # Bump access_count for surfaced tasks (thread-safe via store lock)
        _surfaced_ids = [t["id"] for t in pending_tasks[:5]]
        if _surfaced_ids:
            try:
                with _task_store._lock:
                    for _sid in _surfaced_ids:
                        _task_store._conn.execute(
                            "UPDATE memories SET access_count = COALESCE(access_count, 0) + 1 "
                            "WHERE node_id = ?",
                            (_sid,),
                        )
                    _task_store._conn.commit()
            except (sqlite3.OperationalError) as e:
                _log_hook_error("handle_session_start", e)
    except (ValueError, sqlite3.OperationalError) as e:
        _log_hook_error("task_surfacing", e)

    # Gather reminders data (keep query logic, reformat output)
    due_reminders: list[dict] = []
    entity_id = _resolve_entity(project) if project else None
    try:
        from omega.bridge import get_due_reminders

        due_reminders = get_due_reminders(mark_fired=True, entity_id=entity_id) or []
    except (ImportError) as e:
        _log_hook_error("reminder_check", e)

    # Auto-resolve reminders that match recent completions/decisions (keyword overlap)
    if due_reminders:
        try:
            _comp_rows = _task_store._conn.execute(
                "SELECT content FROM memories "
                "WHERE event_type IN ('task_completion', 'decision') "
                "ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            _comp_texts = [
                (r[0] if isinstance(r, (list, tuple)) else r["content"]).lower()
                for r in _comp_rows
            ]
            if _comp_texts:
                _resolved_ids = []
                for rem in due_reminders:
                    _rem_words = {w.lower() for w in rem.get("text", "").split() if len(w) > 3}
                    for ct in _comp_texts:
                        _matches = sum(1 for w in _rem_words if w in ct)
                        if _matches >= 3:
                            _resolved_ids.append(rem["id"])
                            break
                if _resolved_ids:
                    from omega.bridge import dismiss_reminder
                    for _rid in _resolved_ids:
                        try:
                            dismiss_reminder(_rid)
                        except Exception as e:
                            logger.debug("Auto-dismiss reminder %s failed: %s", _rid, e)
                    due_reminders = [r for r in due_reminders if r["id"] not in _resolved_ids]
        except Exception as e:
            _log_hook_error("reminder_auto_resolve", e)

    # Gather active peers
    active_peers_line = ""
    try:
        peers = ctx.get("active_peers", [])
        if peers:
            peer_descs = []
            for p in peers[:3]:
                peer_name = _agent_nickname(p.get("session_id", ""))
                peer_task = p.get("task", "")
                if peer_task and peer_task not in ("idle", "no task", "null", "New session"):
                    peer_descs.append(f"{peer_name} ({peer_task[:40]})")
                else:
                    peer_descs.append(peer_name)
            active_peers_line = f"Active peers: {', '.join(peer_descs)}."
    except (KeyError, TypeError, ValueError) as e:
        _log_hook_error("handle_session_start", e)

    # Build "What's Ahead" lines
    ahead_parts: list[str] = []
    if pending_tasks:
        top_task = pending_tasks[0]
        entity_tag = f" [{top_task['entity']}]" if top_task["entity"] else ""
        ahead_parts.append(
            f"{len(pending_tasks)} task{'s' if len(pending_tasks) != 1 else ''} pending"
            f" -- top: {top_task['title']} (P{top_task['priority']}{entity_tag})"
        )
        # Detailed task lines with freshness metadata
        for t in pending_tasks[:5]:
            _e_tag = f" [{t['entity']}]" if t["entity"] else ""
            _age = t.get("age_days", 0)
            _ac = t.get("access_count", 0)
            if _age < 1:
                _age_str = "today"
            elif _age < 2:
                _age_str = "1d"
            else:
                _age_str = f"{int(_age)}d"
            _meta = f"{_age_str}, shown {_ac}x"
            ahead_parts.append(
                f"  P{t['priority']}{_e_tag} {t['title']} ({_meta})"
            )
    if due_reminders:
        count = len(due_reminders)
        overdue_count = sum(1 for r in due_reminders if r.get("is_overdue"))
        if overdue_count:
            ahead_parts.append(f"{count} reminder{'s' if count != 1 else ''} due ({overdue_count} overdue)")
        else:
            ahead_parts.append(f"{count} reminder{'s' if count != 1 else ''} due")
    if active_peers_line:
        ahead_parts.append(active_peers_line)

    if ahead_parts:
        volatile.append("")
        for part in ahead_parts:
            volatile.append(part)

    # Reminder details (enriched, for due reminders)
    if due_reminders:
        volatile.append("")
        for r in due_reminders[:5]:
            overdue_label = " [OVERDUE]" if r.get("is_overdue") else ""
            volatile.append(f"[REMINDER]{overdue_label} {r['text']}")
            if r.get("context"):
                volatile.append(f"  Context: {r['context'][:120]}")

            # Reminder enrichment (embedding queries) deferred — too expensive
            # for session startup. Agents can query with omega_query if needed.

            volatile.append(f"  ID: {r['id'][:12]} -- dismiss with omega_remind_dismiss")

    # --- Alerts for degraded subsystems → semi-stable zone ---
    # Embedding model warning
    try:
        from omega.embedding import get_active_backend

        if get_active_backend() is None:
            semi.append("[!] Embedding model unavailable -- semantic search degraded (hash fallback)")
    except Exception as e:
        _log_hook_error("handle_session_start", e)

    # Router degradation
    try:
        from omega.router.engine import OmegaRouter

        router = OmegaRouter()
        provider_status = router.get_provider_status()
        available = sum(1 for s in provider_status.values() if s == "available")
        total = len(provider_status)
        if 0 < available < total:
            semi.append(f"[!] Router: {available}/{total} providers active -- some routing degraded")
        elif available == 0 and total > 0:
            semi.append("[!] Router: 0 providers active -- routing unavailable")
    except ImportError:
        pass  # Router is optional
    except Exception as e:
        _log_hook_error("router_status_welcome", e)

    # Doctor issues
    if doctor_summary and "issue" in doctor_summary:
        semi.append(f"[!] {doctor_summary}")

    # Document scan results (only if new files were ingested)
    if doc_scan_summary:
        semi.append(f"[DOCS] {doc_scan_summary}")

    # Cloud pull results (only if new data was pulled)
    if cloud_pull_summary:
        semi.append(f"[CLOUD] {cloud_pull_summary}")

    # --- Layer 3: Agent Context — split by stability ---
    # Stable context types (RULE, PREF, DECISION, LESSON, PITFALL) go to semi zone;
    # volatile context types go to volatile zone.
    _STABLE_CONTEXT_TAGS = {"RULE", "PREF", "DECISION", "LESSON", "PITFALL"}
    if context_items:
        stable_ctx = [item for item in context_items if item.get("tag") in _STABLE_CONTEXT_TAGS]
        volatile_ctx = [item for item in context_items if item.get("tag") not in _STABLE_CONTEXT_TAGS]
        if stable_ctx:
            semi.append("")
            semi.append("[CONTEXT]")
            for item in stable_ctx:
                semi.append(f"  {item['tag']}: {item['text']}")
        if volatile_ctx:
            volatile.append("")
            volatile.append("[CONTEXT] (recent)")
            for item in volatile_ctx:
                volatile.append(f"  {item['tag']}: {item['text']}")

    # Pattern Intelligence — uses pre-computed patterns from DB (no embedding
    # queries at startup). Only reads existing behavioral_pattern rows.
    try:
        from omega.bridge import _get_store as _gs_patterns

        _patt_store = _gs_patterns()
        _patt_rows = _patt_store._conn.execute(
            "SELECT node_id, content, json_extract(metadata, '$.status') as status "
            "FROM memories WHERE event_type = 'behavioral_pattern' "
            "ORDER BY access_count DESC, created_at DESC LIMIT 5"
        ).fetchall()
        if _patt_rows:
            stable.append("")
            stable.append("[PATTERNS]")
            _unconfirmed_ids: list[str] = []
            for row in _patt_rows:
                if isinstance(row, (list, tuple)):
                    _p_node_id, _p_content, _p_status = row[0], row[1], row[2]
                else:
                    _p_node_id = row["node_id"]
                    _p_content = row["content"]
                    _p_status = row["status"]
                _p_status_str = _p_status if _p_status else "unconfirmed"
                _p_first_line = _p_content.split(chr(10))[0][:100]
                stable.append(f"  [{_p_status_str}] {_p_first_line} (id: {_p_node_id})")
                if _p_status != "confirmed":
                    _unconfirmed_ids.append(_p_node_id)
            if len(_unconfirmed_ids) >= 3:
                stable.append("  **Action needed**: Confirm or deny patterns to improve predictions:")
                stable.append("  - Confirm: `omega_stats(action='habits_confirm', pattern_id='<id>')`")
                stable.append("  - Deny: `omega_stats(action='habits_deny', pattern_id='<id>')`")
    except Exception as e:
        _log_hook_error("pattern_welcome", e)

    # --- Layer 4: Nudges (plain sentences, no [NUDGE] prefix, max 2) ---
    nudges: list[str] = []

    # Nudge: overdue backup
    try:
        backup_marker = _omega_dir() / "last-backup"
        if backup_marker.exists():
            last_ts = backup_marker.read_text().strip()
            last = datetime.fromisoformat(last_ts)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - last).days
            if age_days >= 14:
                nudges.append(f"Last backup was {age_days} days ago. Consider running omega_backup.")
        elif memory_count > 50:
            nudges.append("No backup found. Consider running omega_backup.")
    except (OSError, ValueError) as e:
        _log_hook_error("handle_session_start", e)

    # Nudge: due/overdue reminders count (only if not already shown in Layer 2)
    if not due_reminders:
        try:
            from omega.bridge import list_reminders as _lr

            pending = _lr(status="pending")
            due_count = sum(1 for r in pending if r.get("is_due"))
            upcoming_today = 0
            for r in pending:
                if not r.get("is_due"):
                    try:
                        remind_at = datetime.fromisoformat(r["remind_at"])
                        if remind_at.tzinfo is None:
                            remind_at = remind_at.replace(tzinfo=timezone.utc)
                        if (remind_at - datetime.now(timezone.utc)).total_seconds() < 86400:
                            upcoming_today += 1
                    except (ValueError) as e:
                        _log_hook_error("handle_session_start", e)
            if due_count > 0:
                nudges.append(f"{due_count} reminder{'s' if due_count != 1 else ''} due now.")
            elif upcoming_today > 0:
                nudges.append(f"{upcoming_today} reminder{'s' if upcoming_today != 1 else ''} coming up today.")
        except (ValueError) as e:
            _log_hook_error("handle_session_start", e)

    # Nudge: recurring error patterns (3+ of same type this month)
    try:
        from omega.bridge import _get_store as _gs

        _store = _gs()
        month_cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=30)).isoformat()
        error_rows = _store._conn.execute(
            "SELECT content FROM memories "
            "WHERE event_type = 'error_pattern' AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 50",
            (month_cutoff,),
        ).fetchall()
        if len(error_rows) >= 3:
            buckets: dict[str, int] = {}
            for (content,) in error_rows:
                key = re.sub(r"\s+", " ", content[:80].lower()).strip()
                buckets[key] = buckets.get(key, 0) + 1
            top_bucket = max(buckets.items(), key=lambda x: x[1]) if buckets else None
            if top_bucket and top_bucket[1] >= 3:
                nudges.append(f"Same error {top_bucket[1]}x this month: {top_bucket[0][:60]}")
    except (sqlite3.OperationalError) as e:
        _log_hook_error("handle_session_start", e)

    # Nudge: time-of-day project awareness
    try:
        from omega.bridge import _get_store as _gs_tod

        _store_tod = _gs_tod()
        tod_cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=14)).isoformat()
        tod_rows = _store_tod._conn.execute(
            "SELECT created_at, metadata FROM memories "
            "WHERE event_type = 'session_summary' AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 50",
            (tod_cutoff,),
        ).fetchall()
        if len(tod_rows) >= 5:
            _tod_hour = datetime.now().hour
            if 5 <= _tod_hour < 12:
                tod_label = "morning"
            elif 12 <= _tod_hour < 17:
                tod_label = "afternoon"
            elif 17 <= _tod_hour < 22:
                tod_label = "evening"
            else:
                tod_label = "night"

            project_counts: dict[str, int] = {}
            for created_at_str, meta_json in tod_rows:
                try:
                    ca = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    local_hour = ca.astimezone().hour
                    same_bucket = False
                    if tod_label == "morning" and 5 <= local_hour < 12:
                        same_bucket = True
                    elif tod_label == "afternoon" and 12 <= local_hour < 17:
                        same_bucket = True
                    elif tod_label == "evening" and 17 <= local_hour < 22:
                        same_bucket = True
                    elif tod_label == "night" and (local_hour >= 22 or local_hour < 5):
                        same_bucket = True
                    if same_bucket:
                        meta = json.loads(meta_json) if isinstance(meta_json, str) else (meta_json or {})
                        proj = meta.get("project", "")
                        if proj:
                            proj_name = os.path.basename(proj)
                            project_counts[proj_name] = project_counts.get(proj_name, 0) + 1
                except (ValueError, json.JSONDecodeError):
                    continue

            if project_counts:
                top_proj = max(project_counts.items(), key=lambda x: x[1])
                if top_proj[1] >= 3 and project_name != top_proj[0]:
                    nudges.append(f"You typically work on {top_proj[0]} in the {tod_label}s.")
    except (ValueError, json.JSONDecodeError, sqlite3.OperationalError) as e:
        _log_hook_error("handle_session_start", e)

    if nudges:
        volatile.append("")
        for nudge in nudges[:2]:  # Cap at 2 nudges
            volatile.append(nudge)

    # --- Weekly digest (max once per 7 days, 20+ memories) ---
    if memory_count >= 20 and _should_run_periodic("last-digest", 7 * 86400):
        try:
            from omega.bridge import get_weekly_digest

            digest = get_weekly_digest(days=7)
            period_new = digest.get("period_new", 0)
            session_count = digest.get("session_count", 0)
            total = digest.get("total_memories", 0)
            growth_pct = digest.get("growth_pct", 0)
            type_breakdown = digest.get("type_breakdown", {})

            if period_new > 0:
                oldest_recalled = digest.get("oldest_recalled_days")
                sign = "+" if growth_pct >= 0 else ""
                volatile.append("")
                volatile.append(
                    f"[WEEKLY] Your memory grew {sign}{growth_pct:.0f}% this week"
                    f" (+{period_new} across {session_count} sessions)"
                )
                if type_breakdown:
                    bd_parts = [
                        f"{v} {k.replace('_', ' ')}"
                        for k, v in sorted(type_breakdown.items(), key=lambda x: x[1], reverse=True)[:3]
                    ]
                    volatile.append(f"  Top captures: {', '.join(bd_parts)}")
                oldest_part = f"Oldest memory recalled this week: {oldest_recalled}d old | " if oldest_recalled else ""
                volatile.append(f"  {oldest_part}{total} total")

                _update_marker("last-digest")
        except Exception as e:
            _log_hook_error("weekly_digest_surface", e)

    # --- Marketing advisor status line → volatile zone ---
    try:
        marketing_brief_path = Path.home() / ".omega" / "marketing" / f"{datetime.now().strftime('%Y-%m-%d')}.md"
        if marketing_brief_path.exists():
            brief_text = marketing_brief_path.read_text(errors="replace")
            # Extract verdict line and today's task from brief
            verdict_match = re.search(r"Verdict:\s*(\w[\w\s]*?)(?:\s*\||$)", brief_text)
            streak_match = re.search(r"Streak:\s*(\d+)\s*week", brief_text)
            task_match = re.search(r"Today:\s*(.+?)(?:\s*\(|$)", brief_text, re.MULTILINE)
            draft_ready = "draft_ready" in brief_text.lower() or "Draft:" in brief_text

            verdict = verdict_match.group(1).strip() if verdict_match else "unknown"
            streak_val = streak_match.group(1) if streak_match else "0"
            task_desc = task_match.group(1).strip()[:50] if task_match else "check calendar"
            draft_tag = " (draft ready)" if draft_ready else ""

            if verdict.upper() in ("BEHIND", "SLIPPING"):
                volatile.append(f"[MARKETING] {verdict.upper()}: {task_desc}{draft_tag} | /marketing-advisor")
            else:
                volatile.append(f"[MARKETING] Week {streak_val} streak | Today: {task_desc}{draft_tag} | /marketing-advisor")
        else:
            # No brief generated yet — show minimal reminder
            volatile.append("[MARKETING] No brief today. Run /marketing-advisor to check in.")
    except Exception as e:
        _log_hook_error("marketing_status", e)

    # --- Memory stats line → stable zone (only for non-trivial stores) ---
    if memory_count >= 5:
        try:
            type_stats = ctx.get("type_stats", {})
            period_new_7d = ctx.get("period_new_7d", 0)
            _TYPE_LABELS = {
                "decision": "decisions", "lesson_learned": "lessons",
                "error_pattern": "errors", "user_preference": "preferences",
                "user_fact": "facts", "checkpoint": "checkpoints",
                "behavioral_pattern": "habits",
            }
            top_types = sorted(type_stats.items(), key=lambda x: x[1], reverse=True)[:3]
            type_summary = ", ".join(
                f"{v} {_TYPE_LABELS.get(k, k)}" for k, v in top_types if v > 0
            )
            stats_line = f"[OMEGA MEMORY] Loaded {memory_count} relevant memories"
            if type_summary:
                stats_line += f" ({type_summary})"
            if period_new_7d > 0:
                stats_line += f" | +{period_new_7d} this week"
            stable.append("")
            stable.append(stats_line)
        except Exception as e:
            _log_hook_error("memory_stats_line", e)

    # --- Layer 5: System Footer (1 line) ---
    footer_parts = [f"{memory_count} memories", health_status, f"capture: {last_capture}"]
    footer_parts.append(maintenance_result.format_footer())
    # Cloud sync status
    try:
        secrets_path = _omega_dir() / "secrets.json"
        if secrets_path.exists():
            pull_marker = _omega_dir() / "last-cloud-pull"
            if pull_marker.exists():
                last_ts = pull_marker.read_text().strip()
                last = datetime.fromisoformat(last_ts)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - last).days
                if age_days < 1:
                    footer_parts.append("cloud ok")
                else:
                    footer_parts.append(f"cloud: {age_days}d ago")
            else:
                footer_parts.append("cloud: never pulled")
    except (OSError, ValueError) as e:
        _log_hook_error("handle_session_start", e)
    stable.append("")
    stable.append(f"OMEGA: {' | '.join(footer_parts)}")

    # --- Greeting instruction: tier-aware context nugget ---
    if memory_count > 0:
        tip = _get_unused_features(tier_name)
        peers = ctx.get("active_peers", [])
        context_nugget = _build_context_nugget(
            tier=tier_name,
            peers=peers,
            last_info=last_info,
            pending_tasks=pending_tasks,
            git_status_str=git_status_str,
            streak=streak,
            memory_count=memory_count,
            tip=tip,
        )
        stable.append("")
        stable.append(f"[GREET] {context_nugget}")

    # --- Protocol essentials: behavioral rules agents MUST follow → stable zone ---
    stable.append("")
    stable.append(
        "[PROTOCOL] You have OMEGA persistent memory. Recent activity was loaded above — reference it.\n"
        "- Before non-trivial tasks: `omega_query()` if you need deeper context beyond what's above\n"
        "- After completing tasks: `omega_store(content, \"decision\")` for key outcomes\n"
        "- User says \"remember\": `omega_store(text, \"user_preference\")`\n"
        "- Never `git add .` — always `git add <specific files>`\n"
        "- Before risky ops (deploy, force-push, delete): check `omega_coord_status()` first\n"
        "- Early in sessions with code changes: run `/env-preflight` for the target project\n"
        "- At task start: register 3-5 FOCUS KEYWORDS that define the task boundary (see `/session-focus`)\n"
        "- For complete coordination rules: call `omega_protocol()`"
    )

    # --- Join zones with cache breakpoint markers ---
    parts = stable
    if semi:
        parts = parts + ["<!-- omega:cache_breakpoint -->"] + semi
    if volatile:
        parts = parts + ["<!-- omega:cache_breakpoint -->"] + volatile
    return {"output": "\n".join(parts), "error": None}




def _auto_feedback_on_surfaced(session_id: str):
    """Auto-record feedback for surfaced memories with diff-correlation weighting.

    Three signal sources:
    1. Multi-surfacing: surfaced 2+ times across edits = positive (existing)
    2. Single-surfacing in busy session: weak negative (existing)
    3. Diff correlation: memory surfaced for a committed file = strong positive (2x),
       surfaced for non-committed file in session with commits = weak negative (0.5x)
    """
    if not session_id:
        return
    json_path = _omega_dir() / f"session-{session_id}.surfaced.json"
    if not json_path.exists():
        return
    try:
        data = json.loads(json_path.read_text())
        # Count how many times each memory was surfaced across different files.
        id_counts: dict[str, int] = {}
        for ids in data.values():
            for mid in ids:
                id_counts[mid] = id_counts.get(mid, 0) + 1

        if not id_counts:
            return

        from omega.bridge import batch_record_feedback

        total_files = len(data)
        multi_surfaced = [mid for mid, count in id_counts.items() if count >= 2]
        single_surfaced = [mid for mid, count in id_counts.items() if count == 1]

        # Get diff-correlation outcomes from card tracker
        diff_outcomes: dict[str, str] = {}
        try:
            from . import _card_trackers

            tracker = _card_trackers.get(session_id)
            if tracker:
                diff_outcomes = dict(tracker.outcomes)
        except Exception as e:
            _log_hook_error("_auto_feedback_diff_outcomes", e)

        # Collect all feedback for a single batched transaction
        feedback_items: list[tuple] = []

        # Signal 1: Multi-surfacing (positive)
        for mid in multi_surfaced[:10]:
            feedback_items.append((mid, "helpful", "Auto: surfaced across multiple edits"))

        # Signal 2: Single-surfacing in busy session (weak negative)
        if total_files >= 5:
            for mid in single_surfaced[:5]:
                feedback_items.append((mid, "unhelpful", "Auto: single surfacing in busy session"))

        # Signal 3: Diff-correlation (weighted via repeated feedback entries)
        for mid, outcome in diff_outcomes.items():
            if outcome == "positive":
                # 2x weight: record helpful twice
                feedback_items.append((mid, "helpful", "Auto: diff-correlated with commit"))
                feedback_items.append((mid, "helpful", "Auto: diff-correlated with commit (2x)"))
            elif outcome == "weak_negative":
                # 0.5x weight: single unhelpful (vs normal 1x)
                feedback_items.append((mid, "unhelpful", "Auto: surfaced but file not committed"))

        if feedback_items:
            try:
                batch_record_feedback(feedback_items)
            except Exception as e:
                _log_hook_error("_auto_feedback_on_surfaced", e)

        # Record Thompson bandit outcomes for card types (batch at session stop)
        try:
            from . import _card_trackers
            from omega.thompson import ThompsonBandit

            tracker = _card_trackers.get(session_id)
            if tracker and diff_outcomes:
                bandit = ThompsonBandit()
                positive_count = sum(1 for o in diff_outcomes.values() if o == "positive")
                negative_count = sum(1 for o in diff_outcomes.values() if o == "weak_negative")
                for card_type, surfacing_count in tracker.card_type_surfacings.items():
                    if surfacing_count > 0:
                        arm_id = f"card_type:{card_type}"
                        # Record proportional outcomes
                        for _ in range(min(positive_count, 5)):
                            bandit.record_outcome(arm_id, "card_type", success=True)
                        for _ in range(min(negative_count, 3)):
                            bandit.record_outcome(arm_id, "card_type", success=False)
        except Exception as e:
            _log_hook_error("_auto_feedback_thompson", e)

        json_path.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError) as e:
        _log_hook_error("auto_feedback_surfaced", e)
    finally:
        try:
            if json_path.exists():
                json_path.unlink()
        except (OSError) as e:
            _log_hook_error("_auto_feedback_on_surfaced", e)




def _build_compact_summary_card(session_id: str) -> str | None:
    """Build a compact [OMEGA] Session intelligence card from CardTracker stats.

    Returns None if no intelligence activity was recorded this session.
    """
    try:
        from .card_tracker import get_card_tracker
        from .cards import format_session_summary_card

        tracker = get_card_tracker()
        stats = tracker.get_stats(session_id)

        if stats["memories_surfaced"] == 0 and stats["lessons_captured"] == 0:
            return None

        # Fetch pipeline stats (dedup, evolution) for invisible work visibility
        dedup_count = 0
        evolution_count = 0
        try:
            from omega.bridge import get_dedup_stats
            dedup_stats = get_dedup_stats()
            dedup_count = dedup_stats.get("content_dedup_skips", 0)
            evolution_count = dedup_stats.get("memory_evolutions", 0)
        except Exception:
            pass  # Pipeline stats are best-effort

        card = format_session_summary_card(
            memories_surfaced=stats["memories_surfaced"],
            memories_used=stats["memories_used"],
            lessons_captured=stats["lessons_captured"],
            contradictions=stats["contradictions"],
            repeated_mistakes=stats["repeated_mistakes"],
            verified_lessons_this_week=0,
            dedup_count=dedup_count,
            evolution_count=evolution_count,
        )

        # Clean up compact tracker for this session
        tracker.cleanup(session_id)
        return card
    except Exception:
        return None


def _enrich_checkpoint_content(
    base_content: str,
    audit_rows: list[dict],
    handoff_content: str | None,
) -> str:
    """Enrich checkpoint content with files touched and next steps."""
    parts = [base_content]

    # Extract files from Edit/Write audit entries
    edit_tools = [r for r in audit_rows if r.get("tool_name") in ("Edit", "Write")]
    if edit_tools:
        import re as _re_enrich
        file_paths: list[str] = []
        for row in edit_tools:
            summary = row.get("result_summary", "") or ""
            matches = _re_enrich.findall(r"(/[^\s,]+\.\w+)", summary)
            file_paths.extend(matches)
        if file_paths:
            unique_files = list(dict.fromkeys(file_paths))[:10]
            parts.append(f"files_touched={', '.join(unique_files)}")

    # Extract next steps from handoff content
    if handoff_content:
        for section_header in ("## Open issues", "## Blocked", "## Next"):
            idx = handoff_content.find(section_header)
            if idx >= 0:
                section = handoff_content[idx:idx + 200].strip()
                lines = [l.strip() for l in section.split("\n")[1:3] if l.strip().startswith("- ")]
                if lines:
                    parts.append(f"next_steps: {'; '.join(l.lstrip('- ') for l in lines)}")
                break

    return " | ".join(parts) if len(parts) > 1 else base_content


_MEM_ID_PATTERN = re.compile(r"mem-[a-f0-9]{12}")


def _extract_retrieved_ids(result_summary: str | None) -> set[str]:
    """Extract memory IDs from a result_summary string."""
    if not result_summary:
        return set()
    return set(_MEM_ID_PATTERN.findall(result_summary))


def _compute_retrieval_feedback(
    audit_rows: list[dict],
) -> list[tuple[str, str, str]]:
    """Compute positive-only retrieval feedback from audit trail.

    Returns list of (memory_id, "helpful", "retrieval_used") tuples.
    audit_rows must be sorted by call_index ASC.
    """
    query_results: list[tuple[int, set[str]]] = []
    for row in audit_rows:
        tool = row.get("tool_name", "")
        if "omega_query" not in tool:
            continue
        ids = _extract_retrieved_ids(row.get("result_summary"))
        if ids:
            query_results.append((row.get("call_index", 0), ids))

    if not query_results:
        return []

    feedback: list[tuple[str, str, str]] = []
    seen_helpful: set[str] = set()

    for query_idx, retrieved_ids in query_results:
        for row in audit_rows:
            if row.get("call_index", 0) <= query_idx:
                continue
            later_ids = _extract_retrieved_ids(row.get("result_summary"))
            for mid in retrieved_ids & later_ids:
                if mid not in seen_helpful:
                    feedback.append((mid, "helpful", "retrieval_used"))
                    seen_helpful.add(mid)

    return feedback


def _auto_feedback_on_retrieval(session_id: str) -> None:
    """Auto-record positive feedback for memories reused after retrieval."""
    if not session_id:
        return
    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        raw_rows = mgr.query_audit(session_id=session_id, limit=500)
        audit_rows = sorted(raw_rows, key=lambda r: r.get("call_index", 0))

        feedback = _compute_retrieval_feedback(audit_rows)
        if not feedback:
            return

        from omega.bridge import record_feedback

        for memory_id, rating, reason in feedback:
            try:
                record_feedback(memory_id, rating, reason)
            except Exception:
                pass

        logger.info(f"Retrieval feedback: {len(feedback)} helpful signals recorded")
    except Exception as e:
        _log_hook_error("auto_feedback_retrieval", e)


def _should_extract_learnings(tool_call_count: int) -> bool:
    """Gate: only extract learnings from sessions with 20+ tool calls."""
    return tool_call_count >= 20


def _detect_procedural_patterns(audit_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Detect recovery and stuck patterns from sorted audit rows.

    audit_rows must be sorted by call_index ASC.
    Gate: returns ([], []) if len(audit_rows) < 20.

    Returns: (recovery_patterns, stuck_patterns), total capped at 3.
    - recovery: error(s) followed by success on same tool_name within 10 calls
      Keys: tool_name, error_count, first_error, success_summary
    - stuck: 5+ consecutive errors on same tool_name
      Keys: tool_name, consecutive_errors, last_error
    """
    if len(audit_rows) < 20:
        return [], []

    recoveries: list[dict] = []
    stuck_patterns: list[dict] = []

    # Track per-tool error runs: tool_name -> list of error rows (in order)
    error_runs: dict[str, list[dict]] = {}
    seen_recovery_tools: set[str] = set()

    for row in audit_rows:
        tool = row.get("tool_name", "")
        status = row.get("result_status", "ok")

        if status == "error":
            if tool not in error_runs:
                error_runs[tool] = []
            error_runs[tool].append(row)
        elif status == "ok" and tool in error_runs:
            error_rows = error_runs[tool]
            error_count = len(error_rows)

            if error_count >= 1 and tool not in seen_recovery_tools:
                first_error_idx = error_rows[0].get("call_index", 0)
                current_idx = row.get("call_index", 0)
                if current_idx - first_error_idx <= 10:
                    recoveries.append({
                        "tool_name": tool,
                        "error_count": error_count,
                        "first_error": error_rows[0].get("result_summary", "")[:100],
                        "success_summary": row.get("result_summary", "")[:100],
                    })
                    seen_recovery_tools.add(tool)

            del error_runs[tool]

    # Remaining tools with unresolved errors are stuck candidates
    seen_stuck_tools: set[str] = set()
    for tool, error_rows in error_runs.items():
        if len(error_rows) >= 5 and tool not in seen_stuck_tools:
            stuck_patterns.append({
                "tool_name": tool,
                "consecutive_errors": len(error_rows),
                "last_error": error_rows[-1].get("result_summary", "")[:100],
            })
            seen_stuck_tools.add(tool)

    # Cap: recoveries first, then stuck, total <= 3
    combined_max = 3
    capped_recoveries = recoveries[:combined_max]
    remaining = combined_max - len(capped_recoveries)
    capped_stuck = stuck_patterns[:remaining]

    return capped_recoveries, capped_stuck


def _extract_procedural_learnings(session_id: str) -> None:
    """Extract procedural learnings from session trace patterns.

    Gates internally on audit row count (< 20 rows → no-op).
    Stores up to 3 lesson_learned memories via auto_capture.
    """
    if not session_id:
        return

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        raw_rows = mgr.query_audit(session_id=session_id, limit=500)
        # query_audit returns DESC; re-sort ASC for pattern detection
        audit_rows = sorted(raw_rows, key=lambda r: r.get("call_index", 0))

        recoveries, stuck = _detect_procedural_patterns(audit_rows)

        from omega.bridge import auto_capture

        stored = 0
        max_learnings = 3

        for r in recoveries:
            if stored >= max_learnings:
                break
            content = (
                f"Approach that worked: {r['tool_name']} error resolved after "
                f"{r['error_count']} attempts. Error context: {r['first_error']}. "
                f"Success context: {r['success_summary']}"
            )
            auto_capture(
                content=content,
                event_type="lesson_learned",
                metadata={
                    "source": "auto_procedural",
                    "polarity": "positive",
                    "memory_type": "procedural",
                },
                session_id=session_id,
            )
            stored += 1

        for s in stuck:
            if stored >= max_learnings:
                break
            content = (
                f"Anti-pattern: {s['tool_name']} failed {s['consecutive_errors']} "
                f"consecutive times. Error: {s['last_error']}"
            )
            auto_capture(
                content=content,
                event_type="lesson_learned",
                metadata={
                    "source": "auto_procedural",
                    "polarity": "negative",
                    "memory_type": "procedural",
                },
                session_id=session_id,
            )
            stored += 1

        logger.info(f"Procedural learnings: {stored} extracted ({len(recoveries)} recoveries, {len(stuck)} stuck)")
    except Exception as e:
        _log_hook_error("extract_procedural_learnings", e)


def handle_session_stop(payload: dict) -> dict:
    """Generate and store session summary + activity report."""
    session_id = payload.get("session_id", "")
    project = payload.get("project", "")
    entity_id = _resolve_entity(project) if project else None
    _client = payload.get("client", "claude-code")
    lines = []

    # Read surfaced data before auto-feedback cleanup deletes the file
    surfaced_count = 0
    surfaced_unique_ids = 0
    surfaced_unique_files = 0
    try:
        surfaced_json = _omega_dir() / f"session-{session_id}.surfaced.json"
        if surfaced_json.exists():
            data = json.loads(surfaced_json.read_text())
            surfaced_count = sum(len(ids) for ids in data.values())
            all_ids = set()
            for ids in data.values():
                all_ids.update(ids)
            surfaced_unique_ids = len(all_ids)
            surfaced_unique_files = len(data)
    except (OSError, json.JSONDecodeError) as e:
        _log_hook_error("handle_session_stop", e)

    # Auto-feedback for surfaced memories before building summary
    _auto_feedback_on_surfaced(session_id)

    # --- Gather session event counts ---
    counts = {}
    captured = 0
    try:
        from omega.bridge import _get_store

        store = _get_store()
        counts = store.get_session_event_counts(session_id) if session_id else {}
        captured = sum(counts.values()) if counts else 0

        # Clean up surfaced marker
        try:
            marker = _omega_dir() / f"session-{session_id}.surfaced"
            if marker.exists():
                marker.unlink()
        except (OSError) as e:
            _log_hook_error("handle_session_stop", e)
    except Exception as e:
        _log_hook_error("session_stop_activity", e)

    # --- Gather git activity for summary (always, even if 0 OMEGA captures) ---
    git_commits_summary = ""
    git_files_summary = ""
    try:
        if project:
            git_log = subprocess.run(
                ["git", "log", "--oneline", "-5", "--format=%h %s"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=project,
            )
            if git_log.returncode == 0 and git_log.stdout.strip():
                commits = git_log.stdout.strip().split("\n")
                git_commits_summary = f"Commits: {'; '.join(c.strip() for c in commits[:3])}"
            git_diff = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~5", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=project,
            )
            if git_diff.returncode == 0 and git_diff.stdout.strip():
                files = [f.strip() for f in git_diff.stdout.strip().split("\n") if f.strip()]
                git_files_summary = f"Files changed: {', '.join(files[:5])}"
    except (subprocess.SubprocessError, OSError):
        pass  # Git info in summary is best-effort

    # --- Build summary from per-type targeted queries (stored silently) ---
    summary = "Session ended"
    top_decisions: list[str] = []
    try:
        from omega.bridge import query_structured

        decisions = query_structured(
            query_text="decisions made",
            limit=5,
            session_id=session_id,
            project=project,
            event_type="decision",
            entity_id=entity_id,
        )
        errors = query_structured(
            query_text="errors encountered",
            limit=3,
            session_id=session_id,
            project=project,
            event_type="error_pattern",
            entity_id=entity_id,
        )
        # Hard-filter to current session only — historical error patterns are
        # documentation of fixed bugs, not active blockers (gh issue: stale
        # error_pattern memories from Feb 15 propagated as blockers for 22+
        # handoffs because query_structured uses session_id as a relevance
        # boost, not a hard filter).
        if errors and session_id:
            errors = [e for e in errors if e.get("session_id") == session_id]
        tasks = query_structured(
            query_text="completed tasks",
            limit=3,
            session_id=session_id,
            project=project,
            event_type="task_completion",
            entity_id=entity_id,
        )

        parts = []
        if decisions:
            items = [m.get("content", "")[:120] for m in decisions[:3]]
            parts.append(f"Decisions ({len(decisions)}): " + "; ".join(items))
            top_decisions = [m.get("content", "")[:80].replace("\n", " ").strip() for m in decisions[:2]]
        if errors:
            items = [m.get("content", "")[:120] for m in errors[:3]]
            parts.append(f"Errors ({len(errors)}): " + "; ".join(items))
        if tasks:
            items = [m.get("content", "")[:120] for m in tasks[:3]]
            parts.append(f"Tasks ({len(tasks)}): " + "; ".join(items))
        # Always append git activity (critical when 0 OMEGA captures)
        if git_commits_summary:
            parts.append(git_commits_summary)
        if git_files_summary:
            parts.append(git_files_summary)

        if parts:
            summary = " | ".join(parts)[:800]
        elif decisions or errors or tasks:
            total = len(decisions or []) + len(errors or []) + len(tasks or [])
            summary = f"Session ended with {total} captured memories"
    except Exception as e:
        _log_hook_error("session_stop_summary", e)

    # Store the summary only if session had meaningful activity
    # Require 2+ items OR at least one non-trivial decision/error to store a summary
    _decision_count = len(decisions or [])
    _error_count = len(errors or [])
    _task_count = len(tasks or [])
    _total_items = _decision_count + _error_count + _task_count
    _has_git = bool(git_commits_summary)
    _has_activity = (_total_items >= 2) or (_error_count >= 1) or _has_git
    if _has_activity:
        try:
            from omega.bridge import auto_capture

            auto_capture(
                content=f"Session summary: {summary}",
                event_type="session_summary",
                metadata={"source": "session_stop_hook", "project": project},
                session_id=session_id,
                project=project,
                entity_id=entity_id,
                agent_type=_client,
                ttl_override=86400,  # 1 day: survive for same-day recall + consolidation
            )
        except Exception as e:
            _log_hook_error("session_stop", e)
            return {"output": "\n".join(lines), "error": str(e)}

    # --- Auto-store safety net: capture git activity when agent made zero omega_store calls ---
    # This prevents total state loss in sessions where the agent was productive
    # but never called omega_store (observed in 3/3 audited sessions, Feb 2026).
    if captured == 0 and _has_git:
        try:
            from omega.bridge import auto_capture

            auto_summary = f"Auto-captured session (agent made 0 omega_store calls). {git_commits_summary}"
            if git_files_summary:
                auto_summary += f" | {git_files_summary}"
            auto_capture(
                content=auto_summary,
                event_type="session_summary",
                metadata={
                    "source": "session_stop_auto_safety_net",
                    "project": project,
                    "zero_store_calls": True,
                },
                session_id=session_id,
                project=project,
                entity_id=entity_id,
                agent_type=_client,
                ttl_override=86400,  # 1 day: survive for same-day recall + consolidation
            )
            lines.append("  [AUTO-CAPTURED] Agent made 0 omega_store calls; git activity saved as safety net")
        except Exception as e:
            _log_hook_error("session_stop_auto_capture", e)

    # --- Generate structured handoff for next session ---
    try:
        handoff_parts = []
        # What was done
        done_items = []
        if top_decisions:
            for d in top_decisions:
                done_items.append(f"- {d}")
        if git_commits_summary:
            done_items.append(f"- {git_commits_summary}")
        if done_items:
            handoff_parts.append("## What was done\n" + "\n".join(done_items))

        # Files touched
        if git_files_summary:
            handoff_parts.append(f"## Files touched\n- {git_files_summary}")

        # Open issues
        if _error_count > 0:
            err_items = []
            for m in (errors or [])[:3]:
                err_items.append(f"- {m.get('content', '')[:100]}")
            if err_items:
                handoff_parts.append("## Open issues\n" + "\n".join(err_items))

        if handoff_parts:
            handoff_content = "\n\n".join(handoff_parts)
            from omega.bridge import auto_capture as _ac_handoff

            _ac_handoff(
                content=f"Session handoff:\n{handoff_content}",
                event_type="handoff",
                metadata={"source": "session_stop_auto_handoff", "project": project},
                session_id=session_id,
                project=project,
                entity_id=entity_id,
                agent_type=_client,
            )
            lines.append("  [HANDOFF] Auto-generated for next session")
    except Exception as e:
        _log_hook_error("session_stop_handoff", e)

    # --- Write structured handoff to coord_handoffs table ---
    # This ensures the admin dashboard timeline has real data (not empty rows).
    try:
        from omega.coordination import get_manager as _gm_handoff

        _mgr_handoff = _gm_handoff()

        # Build lists from data already in scope
        _completed = [m.get("content", "")[:120] for m in (tasks or [])[:5]]
        _blocked = [m.get("content", "")[:120] for m in (errors or [])[:3]]
        _decisions_list = [d[:120] for d in (top_decisions or [])]
        _files_list = []
        if git_files_summary:
            # Parse "Files changed: a.py, b.py" into list
            _files_raw = git_files_summary.replace("Files changed: ", "")
            _files_list = [f.strip() for f in _files_raw.split(",") if f.strip()]

        # Build key_context: first meaningful decision or summary
        _key_ctx = ""
        if top_decisions:
            _key_ctx = top_decisions[0]
        elif git_commits_summary:
            _key_ctx = git_commits_summary
        elif summary != "Session ended":
            _key_ctx = summary[:200]

        # Only create if we have something meaningful
        if _key_ctx or _completed or _blocked or _files_list or _decisions_list:
            # Clean up prior empty handoffs for this session first
            try:
                _mgr_handoff._conn.execute(
                    "DELETE FROM coord_handoffs WHERE session_id = ? AND "
                    "(key_context IS NULL OR key_context = '')",
                    (session_id,),
                )
                _mgr_handoff._conn.commit()
            except Exception:
                pass  # Dedup cleanup is best-effort

            _mgr_handoff.create_handoff(
                session_id=session_id,
                project=project or None,
                completed_tasks=_completed or None,
                blocked_items=_blocked or None,
                key_context=_key_ctx or None,
                files_modified=_files_list or None,
                decisions_made=_decisions_list or None,
            )
    except Exception as e:
        _log_hook_error("session_stop_coord_handoff", e)

    # --- Auto-checkpoint for sessions with significant activity ---
    # Trigger: 3+ stores (existing) OR 30+ tool calls (new)
    from omega.server.hook_server.trace import _call_counters

    _tool_call_count = _call_counters.get(session_id, 0)
    _should_checkpoint = (
        _has_activity and (captured >= 3 or _tool_call_count >= 30)
    )

    if _should_checkpoint:
        # Skip if agent already saved a checkpoint this session
        try:
            from omega.bridge import _get_store as _gs_ckpt

            _ckpt_store = _gs_ckpt()
            _existing_ckpts = _ckpt_store._conn.execute(
                "SELECT 1 FROM memories WHERE event_type = 'checkpoint' "
                "AND session_id = ? AND json_extract(metadata, '$.source') != 'session_stop_auto_checkpoint' "
                "LIMIT 1",
                (session_id,),
            ).fetchone()
            if _existing_ckpts:
                logger.info("Skipping auto-checkpoint: agent already checkpointed this session")
                _should_checkpoint = False
        except Exception as e:
            _log_hook_error("checkpoint_skip_check", e)

    if _should_checkpoint:
        try:
            from omega.bridge import auto_capture as _ac_checkpoint

            checkpoint_content = f"Auto-checkpoint: {summary[:200]}"
            if git_files_summary:
                checkpoint_content += f" | {git_files_summary}"
            checkpoint_content += f" | tool_calls={_tool_call_count}, stores={captured}"

            # Enrich with files_touched and next_steps
            _enrich_audit: list[dict] = []
            _enrich_handoff: str | None = None
            try:
                from omega.coordination import get_manager as _gm_enrich
                _enrich_mgr = _gm_enrich()
                _enrich_audit = _enrich_mgr.query_audit(session_id=session_id, limit=200)
            except Exception:
                pass
            try:
                from omega.bridge import _get_store as _gs_enrich
                _enrich_store = _gs_enrich()
                _handoff_row = _enrich_store._conn.execute(
                    "SELECT content FROM memories WHERE event_type = 'handoff' "
                    "AND session_id = ? ORDER BY created_at DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
                if _handoff_row:
                    _enrich_handoff = _handoff_row[0]
            except Exception:
                pass
            checkpoint_content = _enrich_checkpoint_content(
                checkpoint_content, _enrich_audit, _enrich_handoff
            )

            _ac_checkpoint(
                content=checkpoint_content,
                event_type="checkpoint",
                metadata={"source": "session_stop_auto_checkpoint", "project": project,
                           "tool_calls": _tool_call_count, "stores": captured},
                session_id=session_id,
                project=project,
                entity_id=entity_id,
                agent_type=_client,
                ttl_override=604800,  # 7 days
            )
        except Exception as e:
            _log_hook_error("session_stop_auto_checkpoint", e)

    # --- Retrieval quality feedback ---
    _auto_feedback_on_retrieval(session_id)

    # --- Cross-session procedural learning extraction ---
    _extract_procedural_learnings(session_id)

    # --- Format output via Intelligence Card ---
    try:
        from .cards import format_session_card
        from . import _card_trackers

        tracker = _card_trackers.get(session_id)
        outcome_stats = tracker.get_outcome_stats() if tracker else {}

        card_lines = format_session_card(
            captured=captured,
            surfaced_count=surfaced_count,
            surfaced_unique_ids=surfaced_unique_ids,
            surfaced_unique_files=surfaced_unique_files,
            diff_correlated=outcome_stats.get("diff_correlated", 0),
            diff_total=outcome_stats.get("diff_total", 0),
            type_breakdown=counts if counts else None,
            top_decisions=top_decisions if top_decisions else None,
        )
        lines.extend(card_lines)
    except Exception as e:
        _log_hook_error("session_stop_card", e)
        # Fallback to legacy format
        if captured > 0:
            lines.append(f"## Session complete -- {captured} captured, {surfaced_count} surfaced")
        else:
            lines.append(f"## Session complete -- {surfaced_count} memories surfaced")

    # --- Protocol compliance report (scored) ---
    try:
        from omega.server.hook_server import _protocol_calls
        called = _protocol_calls.get(session_id, set())
        actual_calls = {c for c in called if not c.startswith("_gate_")}

        # Detect multi-agent for expected tool set
        _compliance_multi = False
        try:
            from omega.coordination import get_manager as _gm_compliance
            _compliance_multi = _gm_compliance().active_session_count() > 1
        except Exception:
            pass

        expected_solo = {"omega_welcome", "omega_protocol"}
        expected_multi = {"omega_welcome", "omega_protocol", "omega_inbox", "omega_coord_status"}
        expected = expected_multi if _compliance_multi else expected_solo
        missing = expected - actual_calls
        score = len(expected - missing) / len(expected) if expected else 1.0
        if missing:
            lines.append(f"  [COMPLIANCE] {score:.0%} adherence. Missing: {', '.join(sorted(missing))}")
        # Store for trend analysis (7-day TTL)
        try:
            from omega.bridge import auto_capture as _ac_compliance
            _ac_compliance(
                content=f"Protocol compliance: {score:.0%}. Missing: {', '.join(sorted(missing)) if missing else 'none'}",
                event_type="session_summary",
                metadata={"source": "protocol_compliance", "score": score, "project": project},
                session_id=session_id, project=project, entity_id=entity_id,
                ttl_override=604800,
            )
        except Exception:
            pass  # Non-critical
    except Exception as e:
        logger.debug("Protocol compliance report failed: %s", e)

    # --- Auto-reflect: stale memory awareness ---
    try:
        from omega.reflect import find_stale
        from omega.bridge import _get_store as _gs_stale

        _store_stale = _gs_stale()
        stale = find_stale(_store_stale, days=30, min_age_days=14, limit=5, entity_id=entity_id)
        stale_count = stale.get("total_candidates", 0) if isinstance(stale, dict) else 0
        if stale_count > 0:
            lines.append(f"  [REFLECT] {stale_count} stale memories detected (14+ days, never accessed)")
            for sm in (stale.get("stale_memories") or [])[:2]:
                preview = sm.get("content_preview", "")[:80]
                lines.append(f"    - {preview}")
    except Exception as e:
        _log_hook_error("session_stop_auto_reflect", e)

    # --- Productivity recap: weekly stats ---
    total_memories = 0
    try:
        from omega.bridge import _get_store as _gs_recap, session_stats as _ss_recap

        store = _gs_recap()
        total_memories = store.node_count()

        # Weekly session count
        all_sessions = _ss_recap()
        weekly_sessions = 0
        try:
            week_cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=7)).isoformat()
            weekly_rows = store._conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM memories WHERE created_at >= ? AND session_id IS NOT NULL",
                (week_cutoff,),
            ).fetchone()
            weekly_sessions = weekly_rows[0] if weekly_rows else 0
        except (sqlite3.OperationalError) as e:
            _log_hook_error("handle_session_stop", e)

        # Weekly memory count
        weekly_memories = 0
        try:
            weekly_mem_row = store._conn.execute(
                "SELECT COUNT(*) FROM memories WHERE created_at >= ?",
                (week_cutoff,),
            ).fetchone()
            weekly_memories = weekly_mem_row[0] if weekly_mem_row else 0
        except (sqlite3.OperationalError) as e:
            _log_hook_error("handle_session_stop", e)

        # Prior week memory count (for growth comparison)
        prev_week_memories = 0
        try:
            prev_cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=14)).isoformat()
            prev_row = store._conn.execute(
                "SELECT COUNT(*) FROM memories WHERE created_at >= ? AND created_at < ?",
                (prev_cutoff, week_cutoff),
            ).fetchone()
            prev_week_memories = prev_row[0] if prev_row else 0
        except (sqlite3.OperationalError) as e:
            _log_hook_error("handle_session_stop", e)

        recap_parts = []
        if weekly_sessions > 1:
            recap_parts.append(f"{weekly_sessions} sessions this week")
        if weekly_memories > 0:
            recap_parts.append(f"{weekly_memories} memories this week")
        recap_parts.append(f"{total_memories} total")
        lines.append(f"  Recap: {', '.join(recap_parts)}")

        # Week-over-week growth
        if prev_week_memories > 0 and weekly_memories > 0:
            growth_pct = ((weekly_memories - prev_week_memories) / prev_week_memories) * 100
            sign = "+" if growth_pct >= 0 else ""
            lines.append(f"  Growth: {sign}{growth_pct:.0f}% vs last week")
    except Exception as e:
        _log_hook_error("handle_session_stop", e)

    # --- Files touched in this session ---
    try:
        from omega.coordination import get_manager as _gm_recap

        mgr = _gm_recap()
        claims = mgr.get_session_claims(session_id)
        file_claims = claims.get("file_claims", [])
        if file_claims:
            fnames = [os.path.basename(f) for f in file_claims[:5]]
            if len(file_claims) > 5:
                fnames.append(f"+{len(file_claims) - 5}")
            lines.append(f"  Files: {', '.join(fnames)}")
    except Exception as e:
        _log_hook_error("handle_session_stop", e)

    # --- Compact [OMEGA] summary card from CardTracker ---
    compact_card = _build_compact_summary_card(session_id)
    if compact_card:
        lines.append(compact_card)

    # Prune debounce dicts for this session to prevent unbounded growth
    _debounce_state.cleanup(session_id)
    # Also clear session-wide caches (not session-id-keyed)
    _last_surface.clear()

    # Clean trace call counters and card tracker for this session
    try:
        from .trace import cleanup_session as _trace_cleanup
        _trace_cleanup(session_id)
    except Exception:
        pass
    try:
        from .card_tracker import _tracker as _card_tracker_singleton
        _card_tracker_singleton.cleanup(session_id)
    except Exception:
        pass

    # --- Auto-mine error patterns from hooks.log ---
    try:
        hooks_log = _omega_dir() / "hooks.log"
        if hooks_log.exists() and _should_run_periodic("last-error-mine", 86400):
            # Read last 500 lines of hooks.log
            log_tail = subprocess.run(
                ["tail", "-500", str(hooks_log)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if log_tail.returncode == 0 and log_tail.stdout:
                # Extract error types and count occurrences
                error_buckets: dict[str, int] = {}
                for line in log_tail.stdout.split("\n"):
                    for pattern in (
                        r"(TypeError: .{10,60})",
                        r"(RuntimeError: .{5,60})",
                        r"(ConnectionResetError: .{5,60})",
                        r"(KeyError: .{3,40})",
                        r"(AttributeError: .{10,60})",
                        r"(ValueError: .{10,60})",
                        r"(ModuleNotFoundError: .{5,60})",
                        r"(ImportError: .{5,60})",
                        r"(SyntaxError: .{5,60})",
                        r"(FileNotFoundError: .{5,60})",
                        r"(IndexError: .{3,40})",
                    ):
                        m = re.search(pattern, line)
                        if m:
                            key = m.group(1).strip()
                            error_buckets[key] = error_buckets.get(key, 0) + 1

                # Only store patterns appearing 2+ times (recurring issues)
                if error_buckets:
                    from omega.bridge import auto_capture as _ac_err, _get_store as _gs_err

                    # Check which patterns we already know about
                    _err_store = _gs_err()
                    existing_errors = _err_store._conn.execute(
                        "SELECT content FROM memories WHERE event_type = 'error_pattern' "
                        "ORDER BY created_at DESC LIMIT 50"
                    ).fetchall()
                    existing_texts = {row[0][:60].lower() for row in existing_errors}

                    for err_msg, count in sorted(error_buckets.items(), key=lambda x: x[1], reverse=True):
                        if count >= 2 and err_msg[:60].lower() not in existing_texts:
                            _ac_err(
                                content=f"Auto-mined error pattern ({count}x in hooks.log): {err_msg}",
                                event_type="error_pattern",
                                metadata={"source": "error_mine", "count": count},
                                session_id=session_id,
                                entity_id=entity_id,
                                agent_type=_client,
                            )
                            lines.append(f"  [ERROR-MINE] New pattern ({count}x): {err_msg[:60]}")

                _update_marker("last-error-mine")
    except (OSError, sqlite3.OperationalError, subprocess.SubprocessError) as e:
        _log_hook_error("error_mine", e)

    # --- Corpus hygiene: deduplicate near-identical memories (daily) ---
    try:
        if _should_run_periodic("last-dedup-hygiene", 86400):
            from omega.bridge import _get_store as _gs_dedup

            _dedup_store = _gs_dedup()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            rows = _dedup_store._conn.execute(
                """SELECT node_id, content, metadata, created_at,
                          access_count, last_accessed, ttl_seconds
                   FROM memories
                   WHERE created_at >= ?
                   ORDER BY created_at DESC
                   LIMIT 200""",
                (cutoff,),
            ).fetchall()

            candidates = []
            for row in rows:
                result = _dedup_store._row_to_result(row)
                if result.is_expired():
                    continue
                if (result.metadata or {}).get("superseded"):
                    continue
                candidates.append(result)

            deduped = 0
            compared = 0
            seen_pairs: set = set()
            for i, a in enumerate(candidates):
                if compared >= 50:
                    break
                a_type = (a.metadata or {}).get("event_type", "")
                for b in candidates[i + 1 :]:
                    if compared >= 50:
                        break
                    b_type = (b.metadata or {}).get("event_type", "")
                    if a_type != b_type:
                        continue
                    pair_key = tuple(sorted([a.id, b.id]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    compared += 1

                    emb_a = _dedup_store.get_embedding(a.id)
                    emb_b = _dedup_store.get_embedding(b.id)
                    if not emb_a or not emb_b:
                        continue
                    dot = sum(x * y for x, y in zip(emb_a, emb_b))
                    norm_a = sum(x * x for x in emb_a) ** 0.5
                    norm_b = sum(x * x for x in emb_b) ** 0.5
                    if norm_a == 0 or norm_b == 0:
                        continue
                    cosine_sim = dot / (norm_a * norm_b)
                    if cosine_sim > 0.90:
                        # Keep newer (a), supersede older (b)
                        _dedup_store.mark_superseded(
                            b.id,
                            superseded_by=a.id,
                        )
                        deduped += 1

            if deduped:
                lines.append(f"  [HYGIENE] Deduped {deduped} near-duplicate memories")
            _update_marker("last-dedup-hygiene")
    except (sqlite3.OperationalError) as e:
        _log_hook_error("corpus_hygiene", e)

    # --- Auto behavioral pattern extraction (every 3 days) ---
    try:
        if _should_run_periodic("last-behavioral-analysis", 3 * 86400):
            from omega.behavioral import BehavioralAnalyzer
            analyzer = BehavioralAnalyzer()
            result = analyzer.analyze_and_store()
            extracted = result.get("total_extracted", 0)
            stored = result.get("stored", 0)
            if stored > 0:
                lines.append(f"  [BEHAVIORAL] Extracted {extracted} patterns, stored {stored} new")
            _update_marker("last-behavioral-analysis")
    except Exception as e:
        _log_hook_error("auto_behavioral", e)

    # --- Auto pattern learning (every 7 days) ---
    try:
        if _should_run_periodic("last-pattern-learning", 7 * 86400):
            from omega.pattern_learner import PatternLearner
            learner = PatternLearner()
            result = learner.analyze_and_store()
            stored = result.get("stored", 0)
            if stored > 0:
                lines.append(
                    f"  [PATTERNS] {result.get('clusters_found', 0)} topic clusters, "
                    f"{stored} patterns stored"
                )
            _update_marker("last-pattern-learning")
    except Exception as e:
        _log_hook_error("auto_pattern_learning", e)

    # Pre-generate Unhinged greeting for next session (fire-and-forget)
    _pregenerate_unhinged_greeting(total_memories, summary)

    # Auto-sync to cloud (fire-and-forget daemon thread)
    _auto_cloud_sync(session_id)

    # Trajectory-to-skill distillation (fail-open, non-blocking)
    try:
        from omega.bridge import distill_trajectory
        distill_trajectory(session_id)
    except Exception as e:
        _log_hook_error("trajectory_distillation", e)

    return {"output": "\n".join(lines), "error": None}
