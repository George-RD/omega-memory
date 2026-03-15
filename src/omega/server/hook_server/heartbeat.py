"""Coordination heartbeat handler."""

import logging
import json
import os
import subprocess
import time

logger = logging.getLogger("omega.hook_server.heartbeat")

from . import (
    DEADLOCK_PUSH_DEBOUNCE_S,
    FILE_READ_DEBOUNCE_S,
    HEARTBEAT_DEBOUNCE_S,
    _MAX_READ_ENTRIES,
    _heartbeat_count,
    _last_deadlock_push,
    _last_file_read,
    _last_heartbeat,
    _last_progress_beat,
    _last_pulse_state,
    _last_project,
    _peer_snapshot,
)

from .utils import _agent_nickname, _append_output, _debounce_check, _drain_urgent_queue, _get_file_path_from_input, _log_hook_error, _omega_dir, _parse_tool_input


_READ_SKIP_PATTERNS = {"node_modules/", ".git/", "__pycache__/", ".env", "package-lock.json", ".claude/"}


def _is_filtered_read(file_path: str) -> bool:
    """Skip noisy/irrelevant file reads from tracking."""
    return any(p in file_path for p in _READ_SKIP_PATTERNS)


def handle_coord_heartbeat(payload: dict) -> dict:
    """Update session heartbeat (debounced to max once per 30s).

    Every 5th heartbeat, check for unread messages and surface count.
    """
    session_id = payload.get("session_id", "")
    if not session_id:
        return {"output": "", "error": None}

    # Drain urgent queue BEFORE debounce — every tool use can deliver push notifications
    urgent_output = _drain_urgent_queue(session_id)

    # File read tracking (independent of heartbeat debounce)
    tool_name_raw = payload.get("tool_name", "")
    if tool_name_raw == "Read":
        input_data = _parse_tool_input(payload)
        file_path = _get_file_path_from_input(input_data)
        if file_path and not _is_filtered_read(file_path):
            read_key = (session_id, file_path)
            if _debounce_check(_last_file_read, read_key, FILE_READ_DEBOUNCE_S, _MAX_READ_ENTRIES):
                try:
                    from omega.coordination import get_manager
                    mgr = get_manager()
                    mgr.record_file_read(session_id, file_path)
                except Exception:
                    pass

    now = time.monotonic()
    if now - _last_heartbeat.get(session_id, 0) < HEARTBEAT_DEBOUNCE_S:
        return {"output": urgent_output, "error": None}

    _last_heartbeat[session_id] = now
    output = urgent_output

    # Project-switch rebriefing — detect CWD change and surface new project context
    project = payload.get("project", "")
    prev_project = _last_project.get(session_id, "")
    if project and prev_project and project != prev_project:
        try:
            from omega.bridge import query_structured
            from .utils import _resolve_entity

            entity_id = _resolve_entity(project) if project else None
            proj_name = os.path.basename(project)
            results = query_structured(
                query_text=f"recent decisions and context for {proj_name}",
                limit=3,
                project=project,
                entity_id=entity_id,
                event_type="decision",
            )
            switch_lines = [f"[PROJECT SWITCH] {os.path.basename(prev_project)} → {proj_name}"]
            for r in (results or []):
                if r.get("relevance", 0) >= 0.25:
                    preview = r.get("content", "")[:120].replace("\n", " ").strip()
                    switch_lines.append(f"  [context] {preview}")
            if not results:
                switch_lines.append(f"  No stored context for {proj_name} yet")
            output = _append_output(output, "\n".join(switch_lines))
        except Exception as e:
            logger.debug("project switch rebriefing failed: %s", e)
    if project:
        _last_project[session_id] = project

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        mgr.heartbeat(session_id)

        # Single-agent fast path: skip coordination overhead when alone
        try:
            multi_agent = mgr.active_session_count() > 1
        except Exception as e:
            logger.debug("active session count check failed: %s", e)
            multi_agent = True  # Assume multi-agent when check fails

        # Every 2nd heartbeat, check inbox (~60s polling)
        # Non-4th beats: show inbox preview with nicknames (inform-type only,
        #   preserves request/complete unread for 4th-beat coordination check)
        # 4th beats: full coordination check below handles request/complete messages
        count = _heartbeat_count.get(session_id, 0) + 1
        _heartbeat_count[session_id] = count

        # Track progress tool calls — reset counter when agent reports progress
        tool_name = payload.get("tool_name", "")
        if tool_name in ("omega_task_progress", "omega_task_complete", "omega_task_fail"):
            _last_progress_beat[session_id] = count

        # First heartbeat: auto-surface team roster in multi-agent mode
        if count == 1 and multi_agent:
            try:
                sessions = mgr.list_sessions(auto_clean=False)
                peers = [s for s in sessions if s.get("session_id") != session_id and s.get("status") == "active"]
                if peers:
                    roster = []
                    for p in peers[:3]:
                        p_name = _agent_nickname(p["session_id"])
                        p_task = (p.get("task") or "idle")[:30]
                        roster.append(f"{p_name}:{p_task}")
                    output = _append_output(output, f"[COORD] Team: {', '.join(roster)}")
            except Exception:
                pass  # Fail-open: never block heartbeat

        # Mid-session activity pulse — fires once at heartbeat #5
        if count == 5:
            try:
                surfaced_json = _omega_dir() / f"session-{session_id}.surfaced.json"
                if surfaced_json.exists():
                    data = json.loads(surfaced_json.read_text())
                    surfaced_so_far = sum(len(ids) for ids in data.values())
                    if surfaced_so_far > 0:
                        output = _append_output(
                            output, f"[OMEGA MEMORY] {surfaced_so_far} memories surfaced so far this session"
                        )
            except (OSError, json.JSONDecodeError) as e:
                logger.debug("activity pulse file read failed: %s", e)

        unread = 0
        if count % 2 == 0:
            try:
                unread = mgr.get_unread_count(session_id)
                if unread > 0 and count % 4 != 0:
                    # Show inbox preview with nicknames (inform-type only)
                    try:
                        msgs = mgr.check_inbox(session_id, unread_only=True, limit=2, msg_type="inform")
                        if msgs:
                            previews = []
                            for m in msgs[:2]:
                                from_name = _agent_nickname(m.get("from_session") or "unknown")
                                subj = (m.get("subject") or "")[:60]
                                previews.append(f'{from_name}: "{subj}"')
                            remaining = unread - len(msgs)
                            output = f"[INBOX] {unread} unread — " + " | ".join(previews)
                            if remaining > 0:
                                output += " — use omega_inbox for more"
                        else:
                            output = f"[INBOX] {unread} unread message(s) — use omega_inbox to read"
                    except Exception as e:
                        logger.debug("inbox preview check failed: %s", e)
                        output = f"[INBOX] {unread} unread message(s) — use omega_inbox to read"
            except Exception as e:
                logger.debug("inbox check failed: %s", e)

        # Every 4th heartbeat (~2 min), surface messages + coordination check
        if count % 4 == 0:
            try:
                coord_lines = []

                # Multi-agent only: check if my task is blocked by another agent's task
                if multi_agent:
                    try:
                        all_tasks = mgr.list_tasks(project=project, status="in_progress")
                        my_tasks = [t for t in all_tasks if t.get("session_id") == session_id]
                        for task in my_tasks[:1]:
                            for dep_id in task.get("depends_on") or []:
                                dep_tasks = [t for t in all_tasks if t.get("id") == dep_id]
                                if dep_tasks and dep_tasks[0].get("status") != "completed":
                                    owner_name = _agent_nickname(dep_tasks[0].get("session_id") or "unknown")
                                    coord_lines.append(
                                        f"[BLOCKED] Task #{task['id']} waiting on #{dep_id} "
                                        f"(owner: {owner_name}, status: {dep_tasks[0].get('status', 'unknown')})"
                                    )
                    except Exception as e:
                        _log_hook_error("handle_coord_heartbeat", e)

                # Surface first request-type message content (not just count)
                if unread > 0:
                    try:
                        msgs = mgr.check_inbox(session_id, unread_only=True, limit=1, msg_type="request")
                        if msgs:
                            m = msgs[0]
                            from_name = _agent_nickname(m.get("from_session") or "unknown")
                            subj = (m.get("subject") or "")[:80]
                            coord_lines.append(f"[REQUEST] From {from_name}: {subj}")
                    except Exception as e:
                        _log_hook_error("handle_coord_heartbeat", e)

                # Surface first complete-type message (handoff from departed peer)
                try:
                    complete_msgs = mgr.check_inbox(session_id, unread_only=True, limit=1, msg_type="complete")
                    if complete_msgs:
                        m = complete_msgs[0]
                        from_name = _agent_nickname(m.get("from_session") or "unknown")
                        subj = (m.get("subject") or "")[:80]
                        body_preview = (m.get("body") or "")[:200].split("\n")[0]
                        coord_lines.append(
                            f"[HANDOFF] From {from_name}: {subj}" + (f"\n  {body_preview}" if body_preview else "")
                        )
                except Exception as e:
                    _log_hook_error("handle_coord_heartbeat", e)

                # Multi-agent only: [TEAM] activity line — recent peer coordination events
                if multi_agent and project:
                    try:
                        events = mgr.get_recent_events(
                            project=project,
                            minutes=2,
                            limit=3,
                            exclude_session=session_id,
                        )
                        if events:
                            parts = []
                            for ev in events[:2]:
                                ev_name = _agent_nickname(ev["session_id"])
                                parts.append(f"{ev_name} {ev['summary']}")
                            coord_lines.append(f"[TEAM] {' | '.join(parts)}")
                    except Exception as e:
                        logger.debug("recent events check failed: %s", e)

                if coord_lines:
                    output = _append_output(output, "\n".join(coord_lines))
            except Exception as e:
                logger.debug("coordination check failed: %s", e)

        # Every 6th heartbeat (~3 min), idle detection — nudge agent to claim a task
        if count % 6 == 0:
            try:
                all_tasks = mgr.list_tasks(status="in_progress")
                my_tasks = [t for t in all_tasks if t.get("session_id") == session_id]
                if not my_tasks:
                    pending = mgr.list_tasks(project=project or None, status="pending")
                    unblocked = [t for t in pending if not t.get("blocked")]
                    if unblocked:
                        idle_line = (
                            f"[IDLE] No active task — {len(unblocked)} unclaimed task(s) available. "
                            f"Use omega_task_next to claim one."
                        )
                        output = _append_output(output, idle_line)
            except Exception as e:
                logger.debug("task listing for idle detection failed: %s", e)

        # Every 12th heartbeat (~6 min), nudge for task progress updates
        if count % 12 == 0:
            try:
                all_tasks = mgr.list_tasks(status="in_progress")
                my_tasks = [t for t in all_tasks if t.get("session_id") == session_id]
                if my_tasks:
                    last_prog = _last_progress_beat.get(session_id, 0)
                    beats_since = count - last_prog
                    if beats_since >= 12:
                        task = my_tasks[0]
                        nudge_line = (
                            f"[NUDGE] {beats_since} heartbeats on task "
                            f'#{task["id"]} "{task["title"][:40]}" without progress update. '
                            f"Consider omega_task_progress(task_id={task['id']}, progress=<est>)"
                        )
                        output = _append_output(output, nudge_line)
            except Exception as e:
                logger.debug("progress nudge failed: %s", e)

        # Every 8th heartbeat (~4 min), detect peer state changes
        if multi_agent and count % 8 == 0 and project:
            try:
                sessions = mgr.list_sessions(auto_clean=False)
                current_peers = {
                    s["session_id"]
                    for s in sessions
                    if s.get("session_id") != session_id and s.get("project") == project and s.get("status") == "active"
                }
                prev_peers = _peer_snapshot.get(session_id, set())
                _peer_snapshot[session_id] = current_peers

                # Only report changes after first snapshot (skip initial population)
                if prev_peers is not None and prev_peers != current_peers:
                    change_parts = []
                    joined = current_peers - prev_peers
                    departed = prev_peers - current_peers
                    for sid in list(joined)[:2]:
                        change_parts.append(f"{_agent_nickname(sid)} joined")
                    for sid in list(departed)[:2]:
                        change_parts.append(f"{_agent_nickname(sid)} left")

                    # Check for new claims in same project from peers + detect conflicts
                    for p_sid in list(current_peers)[:4]:
                        try:
                            claims = mgr.get_session_claims(p_sid)
                            new_files = claims.get("file_claims", [])
                            if new_files:
                                p_name = _agent_nickname(p_sid)
                                fname = os.path.basename(new_files[-1])
                                change_parts.append(f"{p_name} claimed {fname}")

                                # [COORD-CONFLICT] — detect overlapping file claims
                                try:
                                    my_claims = set(mgr.get_session_claims(session_id).get("file_claims", []))
                                    overlaps = set(new_files) & my_claims
                                    if overlaps:
                                        overlap_names = [os.path.basename(f) for f in list(overlaps)[:2]]
                                        conflict_line = (
                                            f"[COORD-CONFLICT] You and {p_name} both have claims on "
                                            f"{', '.join(overlap_names)}. "
                                            "Tell the user immediately and explain what you're doing about it: "
                                            "either coordinate via omega_send_message, or yield with omega_file_release."
                                        )
                                        output = _append_output(output, conflict_line)
                                except Exception as e:
                                    _log_hook_error("handle_coord_heartbeat", e)
                        except Exception as e:
                            _log_hook_error("handle_coord_heartbeat", e)

                    if change_parts:
                        active_count = len(current_peers)
                        summary = " | ".join(change_parts[:3])
                        refresh_line = (
                            f"[TEAM] {summary} | {active_count} peer{'s' if active_count != 1 else ''} active"
                        )
                        output = _append_output(output, refresh_line)

                        # [COORD-EVENT] — instruct Claude to narrate team change to user
                        event_line = (
                            f"[COORD-EVENT] {summary}. "
                            "Briefly mention this team change to the user in your next response."
                        )
                        output = _append_output(output, event_line)

                # [COORD-PULSE] — periodic team progress summary
                try:
                    all_tasks = mgr.list_tasks(project=project)
                    completed = [t for t in all_tasks if t.get("status") == "completed"]
                    in_prog = [t for t in all_tasks if t.get("status") == "in_progress"]
                    total = len(all_tasks) if all_tasks else 0
                    active_count = len(current_peers)

                    pulse_key = f"{len(completed)}:{len(in_prog)}:{active_count}"
                    if pulse_key != _last_pulse_state.get(session_id):
                        _last_pulse_state[session_id] = pulse_key

                        try:
                            pulse_status = mgr.get_status()
                            nc = len(pulse_status.get("conflicts", []))
                        except Exception as e:
                            logger.debug("coord pulse status check failed: %s", e)
                            nc = 0
                        conflict_str = "no conflicts" if nc == 0 else f"{nc} conflict(s)"

                        pulse_parts = []
                        if total > 0:
                            pulse_parts.append(f"{len(completed)} of {total} tasks done")
                        if in_prog:
                            names = [
                                f"{_agent_nickname(t.get('session_id', ''))}:{t['title'][:20]}"
                                for t in in_prog[:3]
                            ]
                            pulse_parts.append(f"in progress: {', '.join(names)}")
                        pulse_parts.append(conflict_str)

                        pulse_summary = ". ".join(pulse_parts)
                        pulse_line = (
                            f"[COORD-PULSE] Team: {pulse_summary}. "
                            "Give the user a brief team progress update (1-2 sentences)."
                        )
                        output = _append_output(output, pulse_line)
                except Exception as e:
                    logger.debug("coord pulse failed: %s", e)

            except Exception as e:
                logger.debug("peer state change detection failed: %s", e)

        # Every 10th heartbeat (~5 min), deadlock detection
        if multi_agent and count % 10 == 0:
            try:
                cycles = mgr.detect_deadlocks()
                if cycles:
                    now_dl = time.monotonic()
                    for cycle in cycles[:2]:
                        cycle_str = " -> ".join(_agent_nickname(s) for s in cycle)
                        deadlock_line = f"[DEADLOCK] Circular wait: {cycle_str}"
                        output = _append_output(output, deadlock_line)

                        # Push [DEADLOCK] to all OTHER sessions in the cycle (debounced)
                        cycle_key = str(hash(tuple(sorted(cycle[:-1]))))
                        if (
                            cycle_key not in _last_deadlock_push
                            or now_dl - _last_deadlock_push[cycle_key] >= DEADLOCK_PUSH_DEBOUNCE_S
                        ):
                            _last_deadlock_push[cycle_key] = now_dl
                            for peer in set(cycle[:-1]):
                                if peer == session_id:
                                    continue  # detecting session sees it in hook output
                                try:
                                    mgr.send_message(
                                        from_session=session_id,
                                        subject=f"[DEADLOCK] Circular wait: {cycle_str}",
                                        to_session=peer,
                                        msg_type="inform",
                                        ttl_minutes=30,
                                    )
                                except (KeyError, TypeError, ValueError) as e:
                                    logger.debug("deadlock message send failed: %s", e)
            except (KeyError, TypeError, ValueError) as e:
                logger.debug("deadlock detection failed: %s", e)

        # Every 20th heartbeat (~10 min), lightweight git divergence check
        if count % 20 == 0 and project:
            try:
                result = subprocess.run(
                    ["git", "rev-list", "--count", "--left-right", "HEAD...@{u}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=project,
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split("\t")
                    if len(parts) == 2:
                        ahead, behind = int(parts[0]), int(parts[1])
                        if behind > 0:
                            div_line = f"[GIT] Branch is {behind} commit(s) behind upstream"
                            if ahead > 0:
                                div_line += f" (and {ahead} ahead)"
                            output = _append_output(output, div_line)
            except (ValueError, subprocess.SubprocessError, OSError) as e:
                logger.debug("git divergence check failed: %s", e)
    except Exception as e:
        # Database locked is expected under multi-process contention — skip silently
        if "database is locked" in str(e):
            logger.debug("coord_heartbeat skipped: database locked")
        else:
            _log_hook_error("coord_heartbeat", e)
        return {"output": output, "error": None}

    return {"output": output, "error": None}
