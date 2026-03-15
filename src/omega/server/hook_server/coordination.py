"""Coordination session start/stop handlers."""

import os
import sqlite3
import subprocess

from .utils import (
    _agent_nickname,
    _format_age,
    _get_current_branch,
    _log_hook_error,
)


def _detect_transport() -> str:
    """Detect MCP transport — checks PID registry, then env var, then daemon health."""
    # 1. PID registry (works when running inside daemon)
    try:
        from pathlib import Path
        import json as _json
        pid_file = Path.home() / ".omega" / "mcp_pids" / f"{os.getpid()}.pid"
        if pid_file.exists():
            data = _json.loads(pid_file.read_text())
            return data.get("transport", "stdio")
    except Exception:
        pass
    # 2. Check if HTTP daemon is running (fallback mode — we're not in daemon)
    try:
        from pathlib import Path
        import json as _json
        pid_dir = Path.home() / ".omega" / "mcp_pids"
        if pid_dir.is_dir():
            for pid_file in pid_dir.glob("*.pid"):
                try:
                    data = _json.loads(pid_file.read_text())
                    if data.get("transport") == "http" and data.get("port"):
                        # Verify process is alive
                        os.kill(data["pid"], 0)
                        return "http"
                except (OSError, KeyError, ValueError):
                    pass
    except Exception:
        pass
    return "stdio"


def _detect_parent_session(mgr, session_id: str, caller_pid: int) -> None:
    """Detect if this session is a subagent by walking PID ancestry.

    If the parent PID of caller_pid matches another active session's PID,
    link them via metadata (parent_session_id / child_session_ids).
    Best-effort — never blocks session start.
    """
    try:
        from omega.server.pid_registry import _get_ppid

        ppid = _get_ppid(caller_pid)
        if not ppid or ppid <= 1:
            return

        # Search active sessions for one whose pid matches our ppid
        sessions = mgr.list_sessions()
        parent_sid = None
        for s in sessions:
            if s.get("session_id") == session_id:
                continue
            if s.get("pid") == ppid and s.get("status") == "active":
                parent_sid = s["session_id"]
                break

        if not parent_sid:
            return

        # Set parent_session_id on the child
        child_meta = mgr._get_session_metadata(session_id)
        child_meta["parent_session_id"] = parent_sid
        mgr._update_session_metadata(session_id, child_meta)

        # Append to child_session_ids on the parent
        parent_meta = mgr._get_session_metadata(parent_sid)
        children = parent_meta.get("child_session_ids", [])
        if session_id not in children:
            children.append(session_id)
        parent_meta["child_session_ids"] = children
        mgr._update_session_metadata(parent_sid, parent_meta)
    except Exception as e:
        _log_hook_error("detect_parent_session", e)


def handle_coord_session_start(payload: dict) -> dict:
    """Register agent session + git sync check + session resume."""
    session_id = payload.get("session_id", "")
    project = payload.get("project", "")
    if not session_id:
        return {"output": "", "error": None}

    # Three-zone output for prompt cache optimization:
    # stable = [SESSION] id, [DECISIONS], [COORD-PROTOCOL]
    # semi = [RESUME], [HANDOFF], [CHECKPOINT]
    # volatile = [!] alerts, [GIT], [COORD] roster, [STANDUP], [INBOX], [TODO], etc.
    stable: list[str] = []
    semi: list[str] = []
    volatile: list[str] = []
    peer_count = 0
    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        mgr.list_sessions()  # Force-clean stale sessions (bypasses rate limit)
        caller_pid = payload.get("caller_pid") or os.getpid()

        # Detect client type and MCP transport for diagnostic dashboard
        client = payload.get("client", "unknown")
        transport = _detect_transport()
        session_meta = {"client": client, "mcp_transport": transport}

        result = mgr.register_session(
            session_id=session_id,
            pid=caller_pid,
            project=project,
            task=payload.get("task"),
            metadata=session_meta,
            agent_type=client,
        )

        # Defer non-critical work to background thread to cut startup time.
        # Parent-child detection, git baseline, and git fetch are I/O-bound
        # and don't produce user-visible output.
        from .utils import _HOOK_BG_EXECUTOR

        def _deferred_session_init():
            try:
                _detect_parent_session(mgr, session_id, caller_pid)
            except Exception:
                pass
            # Store git baseline
            if project:
                try:
                    baseline_result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True, text=True, timeout=5, cwd=project,
                    )
                    if baseline_result.returncode == 0:
                        dirty_at_start = []
                        for line in baseline_result.stdout.strip().split("\n"):
                            if line.strip():
                                parts = line[3:].split(" -> ")
                                dirty_at_start.append(parts[-1].strip())
                        mgr._merge_session_metadata(session_id, {"git_baseline_dirty": dirty_at_start})
                except (subprocess.SubprocessError, OSError):
                    pass

        _HOOK_BG_EXECUTOR.submit(_deferred_session_init)

        peer_count = result.get("peers_on_project", 0)

        # --- [!] Alerts: file/branch conflicts from peers ---
        if peer_count > 0:
            try:
                status = mgr.get_status()
                conflicts = status.get("conflicts", [])
                for conflict in conflicts[:3]:
                    file_path = conflict.get("file", conflict.get("file_path", "unknown"))
                    owner_sid = conflict.get("owner", conflict.get("session_id", "another agent"))
                    owner_name = _agent_nickname(owner_sid) if owner_sid != "another agent" else owner_sid
                    volatile.append(f"[!] File conflict: {file_path} claimed by {owner_name}")
            except Exception:
                pass  # Conflict check is best-effort

            # --- [!] Alerts: uncommitted git files that peers own ---
            try:
                if project:
                    git_result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        cwd=project,
                    )
                    if git_result.returncode == 0 and git_result.stdout.strip():
                        uncommitted = set()
                        for line in git_result.stdout.strip().split("\n"):
                            if line.strip():
                                parts = line[3:].split(" -> ")
                                rel_path = parts[-1].strip()
                                uncommitted.add(os.path.abspath(os.path.join(project, rel_path)))

                        peer_owned: dict[str, list[str]] = {}
                        claimed_paths = set()
                        for f in status.get("files", []):
                            f_path = f.get("path", "")
                            f_sid = f.get("session_id", "")
                            if f_path in uncommitted:
                                claimed_paths.add(f_path)
                            if f_sid != session_id and f_path in uncommitted:
                                name = _agent_nickname(f_sid)
                                peer_owned.setdefault(name, []).append(os.path.basename(f_path))

                        for name, fnames in peer_owned.items():
                            flist = ", ".join(fnames[:4])
                            if len(fnames) > 4:
                                flist += f" +{len(fnames) - 4}"
                            volatile.append(
                                f"[!] {len(fnames)} uncommitted file{'s' if len(fnames) != 1 else ''}"
                                f" owned by {name}: {flist} — do NOT commit these"
                            )

                        # Warn about unclaimed uncommitted files (the Cedar gap)
                        # These are dirty files nobody has claimed — could be from a
                        # prior session that ended without committing.
                        unclaimed = uncommitted - claimed_paths
                        if unclaimed:
                            unclaimed_names = sorted(os.path.basename(p) for p in list(unclaimed)[:6])
                            flist = ", ".join(unclaimed_names[:5])
                            if len(unclaimed) > 5:
                                flist += f" +{len(unclaimed) - 5}"
                            volatile.append(
                                f"[!] {len(unclaimed)} uncommitted file{'s' if len(unclaimed) != 1 else ''}"
                                f" with NO owner: {flist}"
                                f" — investigate before staging (may be from a prior session)"
                            )
            except (subprocess.SubprocessError, OSError):
                pass  # Uncommitted file check is best-effort

            # Check for unread messages → feed into [TODO] section
            try:
                unread = mgr.get_unread_count(session_id)
            except Exception:
                unread = 0
        else:
            unread = 0

        # --- Git sync check → deferred (network I/O from git fetch) ---
        # Git sync and recent commits are informational — defer to background
        # to avoid blocking session start with network I/O.
        _HOOK_BG_EXECUTOR.submit(lambda: _check_git_sync(session_id, project, mgr))

        # Session intent announce + branch claim on start (silent)
        try:
            branch = _get_current_branch(project) if project else None
            if branch and branch not in ("main", "master", "develop", "release"):
                mgr.announce_intent(
                    session_id=session_id,
                    description=f"Working on branch {branch}",
                    intent_type="session_start",
                    target_files=[],
                    target_branch=branch,
                    ttl_minutes=120,
                )
                mgr.claim_branch(session_id, project, branch, task="session start")
        except Exception:
            pass  # Intent/branch claim is best-effort

        # --- [RESUME] from predecessor session → semi-stable ---
        resume_lines = _session_resume(session_id, project, mgr)
        semi.extend(resume_lines)

        # --- [HANDOFF] from predecessor's complete message or structured handoff ---
        _got_handoff = False
        try:
            handoff_msgs = mgr.check_inbox(session_id, unread_only=True, msg_type="complete", limit=1)
            if handoff_msgs:
                msg = handoff_msgs[0]
                from_sid = msg.get("from_session") or "unknown"
                from_name = _agent_nickname(from_sid)
                subj = (msg.get("subject") or "")[:80]
                body = (msg.get("body") or "")[:500]
                handoff_line = f"\n[HANDOFF] From {from_name}: {subj}"
                if body:
                    for bl in body.strip().split("\n")[:10]:
                        handoff_line += f"\n  {bl.strip()}"
                semi.append(handoff_line)
                _got_handoff = True
                try:
                    mgr.record_metric("handoff_read", session_id=session_id)
                except Exception:
                    pass
        except Exception:
            pass  # Handoff surfacing is best-effort

        # Fallback: check coord_handoffs table if no message-based handoff found
        if not _got_handoff:
            try:
                structured = mgr.get_latest_handoff(project=project, reader_session_id=session_id)
                if structured and structured.get("session_id") != session_id:
                    from_name = _agent_nickname(structured.get("session_id") or "unknown")
                    parts = [f"\n[HANDOFF] Structured handoff from {from_name}"]
                    if structured.get("key_context"):
                        parts.append(f"  Context: {structured['key_context'][:200]}")
                    if structured.get("next_steps"):
                        steps = structured["next_steps"][:3]
                        for s in steps:
                            parts.append(f"  Next: {s[:80]}" if isinstance(s, str) else f"  Next: {str(s)[:80]}")
                    if structured.get("blocked_items"):
                        for b in structured["blocked_items"][:2]:
                            parts.append(f"  Blocked: {b[:80]}" if isinstance(b, str) else f"  Blocked: {str(b)[:80]}")
                    semi.append("\n".join(parts))
                    try:
                        mgr.record_metric("handoff_read", session_id=session_id)
                    except Exception:
                        pass
            except Exception:
                pass  # Structured handoff fallback is best-effort

        # --- [INBOX] surface actual message content (not just count) ---
        if peer_count > 0 and unread > 0:
            try:
                # Surface non-complete messages (complete messages handled by [HANDOFF] above)
                inbox_msgs = mgr.check_inbox(
                    session_id,
                    unread_only=True,
                    limit=3,
                )
                # Filter out complete-type (already surfaced as [HANDOFF])
                inbox_msgs = [m for m in inbox_msgs if m.get("msg_type") != "complete"]
                if inbox_msgs:
                    inbox_lines = [f"\n[INBOX] {len(inbox_msgs)} unread message(s):"]
                    for m in inbox_msgs[:3]:
                        from_name = _agent_nickname(m.get("from_session") or "unknown")
                        msg_type = m.get("msg_type", "inform")
                        subj = (m.get("subject") or "")[:80]
                        inbox_lines.append(f"  [{msg_type}] from {from_name}: {subj}")
                    volatile.append("\n".join(inbox_lines))
            except Exception:
                pass  # Inbox content surfacing is best-effort

        # --- [CONTINUE] recently reassigned tasks (have progress > 0) ---
        try:
            all_pending = mgr.list_tasks(project=project, status="pending")
            continued = [t for t in all_pending if t.get("progress", 0) > 0]
            if continued:
                t = continued[0]  # highest priority (list_tasks already sorted)
                pct = f" [{t['progress']}%]" if t.get("progress") else ""
                volatile.append(
                    f'\n[CONTINUE] Task #{t["id"]} "{t["title"]}"{pct} was in progress '
                    f"when last session ended — claim with omega_task_next"
                )
        except Exception:
            all_pending = None

        # --- [TODO] pending tasks + unread messages ---
        try:
            tasks = all_pending if all_pending is not None else mgr.list_tasks(project=project, status="pending")
        except Exception:
            tasks = []

        todo_parts = []
        if tasks:
            todo_parts.append(f"{len(tasks)} pending tasks")
        if unread > 0:
            todo_parts.append(f"{unread} unread msg")
        if todo_parts:
            volatile.append(f"\n[TODO] {' | '.join(todo_parts)} — query omega_tasks_list / omega_inbox for full list")
            # Show the highest-priority next task with auto-claim hint
            if tasks:
                unblocked = [t for t in tasks if not t.get("blocked")]
                show_task = unblocked[0] if unblocked else max(tasks, key=lambda t: t.get("priority", 0))
                prio = f" P{show_task['priority']}" if show_task.get("priority") else ""
                hint = " — use omega_task_next to auto-claim" if unblocked else ""
                volatile.append(f"  NEXT: #{show_task['id']}{prio} {show_task['title']}{hint}")

        # Goal drift check deferred — per-goal drift calculation is expensive
        # and rarely surfaces actionable alerts at session start.

        # --- [DECISIONS] Active decisions → stable zone ---
        try:
            decisions = mgr.query_decisions(project=project, status="active", limit=5)
            if decisions:
                stable.append(f"\n[DECISIONS] {len(decisions)} active decision(s):")
                for d in decisions[:5]:
                    stable.append(f"  [{d['domain']}] {d['decision'][:120]}")
        except Exception:
            pass  # Decision surfacing is best-effort

        # Router warmup — deferred (not user-visible, just cache warming)
        def _deferred_router_warmup():
            try:
                from omega.router.classifier import warm_up
                warm_up()
            except Exception:
                pass
        _HOOK_BG_EXECUTOR.submit(_deferred_router_warmup)

        # --- Footer: rich [COORD] team roster (cross-project) ---
        # Cache sessions list for roster + greet (avoid redundant DB query)
        try:
            _cached_sessions = mgr.list_sessions(auto_clean=False)
        except Exception:
            _cached_sessions = []
        try:
            sessions = _cached_sessions
            peers = [s for s in sessions if s.get("session_id") != session_id][:6]
            if peers:
                # Fetch in-progress coord tasks to prefer over session.task
                _roster_tasks: dict[str, dict] = {}
                try:
                    for _rt in mgr.list_tasks(project=project, status="in_progress"):
                        _rt_sid = _rt.get("session_id")
                        if _rt_sid and _rt_sid not in _roster_tasks:
                            _roster_tasks[_rt_sid] = _rt
                except Exception as e:
                    _log_hook_error("handle_coord_session_start", e)
                volatile.append(f"\n[COORD] {len(peers)} peer{'s' if len(peers) != 1 else ''} active:")
                for p in peers:
                    p_name = _agent_nickname(p["session_id"])
                    # Prefer coord_task over session.task
                    _ct = _roster_tasks.get(p["session_id"])
                    if _ct:
                        _pct = f" [{_ct['progress']}%]" if _ct.get("progress") else ""
                        p_task = f"#{_ct['id']} {_ct['title'][:40]}{_pct}"
                    else:
                        p_task = (p.get("task") or "idle")[:50]
                    # Get claimed files and branch
                    p_files = ""
                    p_branch = ""
                    try:
                        claims = mgr.get_session_claims(p["session_id"])
                        file_claims = claims.get("file_claims", [])
                        if file_claims:
                            fnames = [os.path.basename(f) for f in file_claims[:2]]
                            if len(file_claims) > 2:
                                fnames.append(f"+{len(file_claims) - 2}")
                            p_files = f" [{', '.join(fnames)}]"
                        branch_claims = claims.get("branch_claims", [])
                        if branch_claims:
                            p_branch = f" ({branch_claims[0]})"
                    except Exception as e:
                        _log_hook_error("handle_coord_session_start", e)
                    # Project label when different from current session
                    p_proj_label = ""
                    p_project = p.get("project") or ""
                    if p_project and p_project != project:
                        p_proj_label = f" [{os.path.basename(p_project)}]"
                    # Subagent indicator
                    p_meta = p.get("metadata") or {}
                    if isinstance(p_meta, str):
                        try:
                            p_meta = __import__("json").loads(p_meta)
                        except Exception:
                            p_meta = {}
                    sub_tag = " [sub]" if p_meta.get("parent_session_id") else ""
                    # Heartbeat age
                    age = _format_age(p.get("last_heartbeat", ""))
                    age_str = f" — {age}" if age else ""
                    volatile.append(f"  {p_name}{sub_tag}: {p_task}{p_proj_label}{p_files}{p_branch}{age_str}")
        except Exception:
            if peer_count > 0:
                volatile.append(f"\n{peer_count} peer(s) active — query omega_sessions_list for details")

    except Exception as e:
        _log_hook_error("coord_session_start", e)
        return {"output": "", "error": str(e)}

    # --- Route multi-agent framing to appropriate zones ---

    # [STANDUP] header → volatile (changes every session)
    if peer_count > 0 and (stable or semi or volatile):
        # Determine recommended first action
        action_parts = []
        if unread > 0:
            action_parts.append("check omega_inbox")
        action_parts.append("omega_task_next to claim work")
        action_parts.append("omega_intent_announce to declare your plan")
        action_line = f"  Action: {', then '.join(action_parts)}"

        standup_header = f"[STANDUP] {peer_count} peer{'s' if peer_count != 1 else ''} active"
        volatile.insert(0, standup_header)
        volatile.append(action_line)

        # COORD-GREET removed from critical path — the [COORD] roster above
        # already lists peers and tasks. The greet directive was redundant and
        # required a second list_tasks query.

    # --- [COORD-PROTOCOL] → stable zone (rules don't change between sessions) ---
    if peer_count > 0:
        stable.append("")
        stable.append(
            "[COORD-PROTOCOL] Multi-agent rules (peers are active):\n"
            "- Your session_id is in the [SESSION] block above — pass it to tools that require it\n"
            "- Check `omega_inbox(session_id=...)` within first 3 tool calls for unread peer messages\n"
            "- Announce intent: `omega_intent_announce(description=\"<goal>\")` within first 5 tool calls\n"
            "- Before editing shared files: `omega_file_check(file_path=...)` for conflicts\n"
            "- After significant work: `omega_task_complete(task_id=..., result=\"summary\")`\n"
            "- Before deploy/force-push: `omega_action_check()` then `omega_action_claim()` (atomic gate)"
        )

    # --- [SESSION] id → stable zone (constant within a session) ---
    stable.insert(0, f"[SESSION] {session_id}")

    # --- Join zones with cache breakpoint markers ---
    parts = stable
    if semi:
        parts = parts + ["<!-- omega:cache_breakpoint -->"] + semi
    if volatile:
        parts = parts + ["<!-- omega:cache_breakpoint -->"] + volatile
    return {"output": "\n".join(parts), "error": None}




def _check_git_sync(session_id: str, project: str, mgr) -> list[str]:
    """Detect upstream commits from uncoordinated agents."""
    lines = []
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project,
        )
        if result.returncode != 0:
            return lines

        subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=project,
        )

        branch = _get_current_branch(project) or "main"

        upstream_result = subprocess.run(
            ["git", "log", f"HEAD..origin/{branch}", "--oneline", "--no-decorate", "-20"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project,
        )
        if upstream_result.returncode != 0 or not upstream_result.stdout.strip():
            return lines

        upstream_lines = upstream_result.stdout.strip().split("\n")
        upstream_hashes = [line.split()[0] for line in upstream_lines if line.strip()]
        if not upstream_hashes:
            return lines

        untracked = mgr.detect_untracked_commits(project, upstream_hashes)

        for line in upstream_lines:
            parts = line.split(None, 1)
            if parts:
                mgr.log_git_event(
                    project=project,
                    event_type="upstream_detected",
                    commit_hash=parts[0],
                    branch=branch,
                    message=parts[1] if len(parts) > 1 else "",
                )

        lines.append(
            f"[!] {len(upstream_hashes)} upstream commit(s) on origin/{branch} — run `git pull` before editing"
        )
    except Exception as e:
        _log_hook_error("git_sync_check", e)
    return lines




def _session_resume(session_id: str, project: str, mgr) -> list[str]:
    """Check for predecessor session snapshots with enriched context."""
    lines = []
    try:
        if not project:
            return lines
        snapshots = mgr.recover_session(project)
        if not snapshots:
            snapshots = []  # Fall through to checkpoint surfacing

        if snapshots:
            snap = snapshots[0]
            meta = snap.get("metadata") or {}

            # Compute how long ago the predecessor ended
            age = _format_age(snap.get("created_at", ""))
            age_str = f" ended {age}" if age else ""

            # Build compact single-line [RESUME]
            task_desc = (snap.get("task") or "")[:60]
            task_part = f'"{task_desc}"' if task_desc else "previous session"

            # Get top decisions as Key: summary
            key_parts = []
            try:
                from omega.bridge import query_structured

                decisions = query_structured(
                    query_text="decisions made",
                    limit=5,
                    session_id=snap["session_id"],
                    project=project,
                    event_type="decision",
                )
                for d in decisions or []:
                    content = d.get("content", "")
                    # Strip auto-capture prefixes
                    for prefix in ("Plan/decision captured: ", "Decision: "):
                        if content.startswith(prefix):
                            content = content[len(prefix) :]
                    # Skip JSON blobs
                    stripped = content.lstrip()
                    if stripped.startswith(("{", "[", '"filePath')):
                        continue
                    # Take first meaningful line only
                    first_line = content.split("\n")[0].strip()
                    if first_line and len(first_line) > 10:
                        key_parts.append(first_line[:80])
                    if len(key_parts) >= 2:
                        break
            except Exception:
                pass  # Decision surfacing is best-effort

            key_str = f" | Key: {'; '.join(key_parts)}" if key_parts else ""
            lines.append(f"[RESUME] {task_part}{age_str}{key_str}")
    except Exception as e:
        _log_hook_error("session_resume", e)

    # Surface recent checkpoints for this project
    try:
        if project:
            from omega.bridge import query_structured

            checkpoints = query_structured(
                query_text="checkpoint",
                limit=3,
                event_type="checkpoint",
                project=project,
            )
            if checkpoints:
                checkpoints.sort(key=lambda c: c.get("created_at", ""), reverse=True)
                latest = checkpoints[0]
                meta = latest.get("metadata", {})
                cp_data = meta.get("checkpoint_data", {})
                task_title = cp_data.get("task_title", "Unknown task")
                next_steps = cp_data.get("next_steps", "")

                # Compute age
                age = _format_age(latest.get("created_at", ""))
                cp_age = f" saved {age}" if age else ""

                cp_line = f'[CHECKPOINT] "{task_title}"{cp_age}'
                if next_steps:
                    cp_line += f" | Next: {next_steps[:80]}"
                cp_line += " — call `omega_resume_task` for full context"
                lines.append(cp_line)
    except Exception:
        pass  # Fail-open

    return lines




def handle_coord_session_stop(payload: dict) -> dict:
    """Deregister session and release all claims."""
    session_id = payload.get("session_id", "")
    if not session_id:
        return {"output": "", "error": None}

    lines = []
    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        project = payload.get("project", "")
        if project:
            mgr.enrich_session_metadata(session_id, project)

        # Count peers before deregistering (for footer)
        peer_count = 0
        try:
            sessions = mgr.list_sessions(auto_clean=True)
            peer_count = sum(1 for s in sessions if s.get("session_id") != session_id)
        except Exception as e:
            _log_hook_error("handle_coord_session_stop", e)

        # Broadcast structured handoff message for successor sessions (silent)
        try:
            summary = "Session ended"
            try:
                from omega.bridge import _get_store

                store = _get_store()
                counts = store.get_session_event_counts(session_id) if session_id else {}
                if counts:
                    total = sum(counts.values())
                    summary = f"Session ended ({total} memories captured)"
            except Exception as e:
                _log_hook_error("handle_coord_session_stop", e)

            handoff_parts = [f"## Session Summary\n{summary[:300]}"]

            # Git activity: commits made and files changed
            try:
                if project:
                    # Recent commits (session-scoped via recency — last 10 is generous)
                    git_log = subprocess.run(
                        ["git", "log", "--oneline", "-10", "--format=%h %s"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        cwd=project,
                    )
                    if git_log.returncode == 0 and git_log.stdout.strip():
                        handoff_parts.append("## Commits")
                        for cl in git_log.stdout.strip().split("\n")[:5]:
                            handoff_parts.append(f"- {cl.strip()}")
                    # Files modified (staged + unstaged)
                    git_diff = subprocess.run(
                        ["git", "diff", "--name-only", "HEAD~5", "HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        cwd=project,
                    )
                    if git_diff.returncode == 0 and git_diff.stdout.strip():
                        changed_files = git_diff.stdout.strip().split("\n")[:10]
                        handoff_parts.append("## Files Modified")
                        for f in changed_files:
                            handoff_parts.append(f"- {f.strip()}")
            except (subprocess.SubprocessError, OSError):
                pass  # Git info in handoff is best-effort

            # Decisions made this session
            try:
                from omega.bridge import query_structured as _qs_handoff

                decisions = _qs_handoff(
                    query_text="decisions made",
                    session_id=session_id,
                    event_type="decision",
                    limit=5,
                )
                if decisions:
                    handoff_parts.append("## Decisions")
                    for d in decisions:
                        handoff_parts.append(f"- {d.get('content', '')[:120]}")
            except Exception as e:
                _log_hook_error("handle_coord_session_stop", e)

            # Errors/blockers encountered
            try:
                from omega.bridge import query_structured as _qs_errors

                errors = _qs_errors(
                    query_text="errors encountered",
                    session_id=session_id,
                    event_type="error_pattern",
                    limit=3,
                )
                if errors:
                    handoff_parts.append("## Blockers")
                    for e in errors:
                        handoff_parts.append(f"- {e.get('content', '')[:120]}")
            except Exception as e:
                _log_hook_error("handle_coord_session_stop", e)

            # Incomplete tasks owned by this session
            incomplete = []
            try:
                all_tasks = mgr.list_tasks(project=project, status="in_progress")
                incomplete = [t for t in all_tasks if t.get("session_id") == session_id]
                if incomplete:
                    handoff_parts.append("## Incomplete Work")
                    for t in incomplete:
                        handoff_parts.append(f"- Task #{t['id']}: {t['title']}")
            except Exception as e:
                _log_hook_error("handle_coord_session_stop", e)

            handoff_body = "\n".join(handoff_parts)[:8000]

            mgr.send_message(
                from_session=session_id,
                subject=f"Handoff: {summary[:60]}",
                msg_type="complete",
                project=project or None,
                body=handoff_body,
                ttl_minutes=1440,
            )
        except Exception:
            pass  # Handoff message is best-effort

        # Reassign orphaned tasks to pending so next session can claim them
        reassigned = []
        try:
            reassigned = mgr.reassign_orphaned_tasks(session_id)
            if reassigned:
                task_list = ", ".join(f"#{t['id']} {t['title']}" for t in reassigned[:3])
                lines.append(f"  Tasks returned to queue: {task_list}")
                # Nudge: incomplete work without explicit handoff
                lines.append(
                    "[HANDOFF] You had active work returned to queue. "
                    "Next time, use omega_handoff(action='create', ...) before ending "
                    "to give your successor structured context."
                )
        except (KeyError, TypeError, ValueError):
            pass  # Reassign is best-effort

        # Task state for output (completed + continuing)
        my_completed = []
        try:
            completed_tasks = mgr.list_tasks(project=project, status="completed")
            my_completed = [t for t in completed_tasks if t.get("session_id") == session_id]
            for t in my_completed[:2]:
                lines.append(f"  Done: #{t['id']} {t['title']}")
            for t in reassigned[:2]:
                progress = t.get("progress", 0)
                prog_str = f" ({progress}%)" if progress else ""
                lines.append(f"  Continuing: #{t['id']} {t['title']}{prog_str} — returned to queue for next session")
        except Exception as e:
            _log_hook_error("handle_coord_session_stop", e)

        # [COORD] summary block — files, messages, tasks
        try:
            coord_parts = []
            # Files claimed this session
            claims = mgr.get_session_claims(session_id)
            file_claims = claims.get("file_claims", [])
            if file_claims:
                fnames = [os.path.basename(f) for f in file_claims[:3]]
                if len(file_claims) > 3:
                    fnames.append(f"+{len(file_claims) - 3}")
                coord_parts.append(f"Files: {', '.join(fnames)} ({len(file_claims)} released)")
            # Messages sent/received
            msg_sent = 0
            msg_received = 0
            try:
                sent_rows = mgr._conn.execute(
                    "SELECT COUNT(*) FROM coord_messages WHERE from_session = ?",
                    (session_id,),
                ).fetchone()
                msg_sent = sent_rows[0] if sent_rows else 0
                recv_rows = mgr._conn.execute(
                    "SELECT COUNT(*) FROM coord_messages WHERE to_session = ? OR "
                    "(to_session IS NULL AND from_session != ?)",
                    (session_id, session_id),
                ).fetchone()
                msg_received = recv_rows[0] if recv_rows else 0
            except (sqlite3.OperationalError) as e:
                _log_hook_error("handle_coord_session_stop", e)
            if msg_sent or msg_received:
                coord_parts.append(f"Messages: {msg_sent} sent, {msg_received} received")
            # Tasks summary
            task_parts = []
            if my_completed:
                task_parts.append(f"{len(my_completed)} completed")
            if incomplete:
                for t in incomplete[:2]:
                    progress = t.get("progress", 0)
                    prog_str = f" ({progress}%)" if progress else ""
                    task_parts.append(f"#{t['id']} in progress{prog_str}")
            if task_parts:
                coord_parts.append(f"Tasks: {', '.join(task_parts)}")
            if coord_parts:
                lines.append("[COORD] Session coordination:")
                for part in coord_parts:
                    lines.append(f"  {part}")
        except Exception:
            pass  # Coord summary is best-effort

        # [!] Warn about untracked files — invisible to coordination
        try:
            if project:
                git_untracked = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=project,
                )
                if git_untracked.returncode == 0 and git_untracked.stdout.strip():
                    untracked = [f.strip() for f in git_untracked.stdout.strip().split("\n") if f.strip()]
                    if untracked:
                        fnames = [os.path.basename(f) for f in untracked[:5]]
                        if len(untracked) > 5:
                            fnames.append(f"+{len(untracked) - 5}")
                        lines.append(
                            f"[!] {len(untracked)} untracked file{'s' if len(untracked) != 1 else ''}"
                            f" invisible to coordination: {', '.join(fnames)}"
                            f" — commit or delete before leaving"
                        )
        except (subprocess.SubprocessError, OSError):
            pass  # Untracked warning is best-effort

        mgr.deregister_session(session_id)

        # Footer: snapshot + peer notification
        footer = "Snapshot stored."
        if peer_count > 0:
            footer += f" {peer_count} peer(s) notified."
        lines.append(footer)

    except Exception as e:
        _log_hook_error("coord_session_stop", e)
        return {"output": "", "error": str(e)}

    return {"output": "\n".join(lines), "error": None}
