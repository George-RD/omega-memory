"""
OMEGA Coordination MCP Handlers -- Maps coordination tool names to async handlers.

Each handler delegates to omega.coordination.get_manager() and returns
MCP-compatible response dicts.
"""

import json
import logging
import os
from typing import Any, Dict

from omega.server.validation import validate_session_id as _validate_session_id

logger = logging.getLogger("omega.server.coord_handlers")


def _audit_log(tool_name: str, session_id: str, result_summary: str):
    """Best-effort audit logging — never blocks the operation."""
    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        mgr.log_audit(
            session_id=session_id,
            tool_name=tool_name,
            result_summary=result_summary,
        )
    except Exception as e:
        logger.debug("coord audit_log failed: %s", e)


from omega.server.responses import mcp_response, mcp_error

import time
from pathlib import Path

_GATE_DIR = Path.home() / ".omega" / "gates"


def _write_deploy_action_marker(session_id: str | None = None) -> None:
    """Write action_claim gate marker so pre_deploy_guard hook can verify."""
    try:
        _GATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        key = session_id or "default"
        gate_file = _GATE_DIR / f"{key}.action_claim"
        gate_file.write_text(str(time.time()))
    except Exception as e:
        logger.debug("Action claim marker write failed: %s", e)


# ============================================================================
# Handler: omega_session_register
# ============================================================================


async def handle_session_register(arguments: dict) -> dict:
    """Register an agent session."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    project = arguments.get("project")
    task = arguments.get("task")
    capabilities = arguments.get("capabilities")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        pid = os.getpid()
        result = mgr.register_session(
            session_id=session_id,
            pid=pid,
            project=project,
            task=task,
            capabilities=capabilities,
        )

        peers = result.get("peers_on_project", 0)
        refreshed = result.get("refreshed", False)
        msg = f"Session registered: {session_id[:20]}"
        if refreshed:
            msg += " (refreshed existing)"
        if peers > 0:
            msg += f"\n{peers} other agent(s) active on this project"
        _audit_log("session_register", session_id, msg.split("\n")[0])
        return mcp_response(msg)
    except Exception as e:
        logger.error("session_register failed: %s", e, exc_info=True)
        return mcp_error(f"Registration failed: {e}")


# ============================================================================
# Handler: omega_session_heartbeat
# ============================================================================


async def handle_session_heartbeat(arguments: dict) -> dict:
    """Update session heartbeat."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.heartbeat(session_id)
        if result.get("success"):
            return mcp_response(f"Heartbeat updated: {result['timestamp']}")
        return mcp_error(result.get("error", "Heartbeat failed"))
    except Exception as e:
        logger.error("session_heartbeat failed: %s", e, exc_info=True)
        return mcp_error(f"Heartbeat failed: {e}")


# ============================================================================
# Handler: omega_session_deregister
# ============================================================================


async def handle_session_deregister(arguments: dict) -> dict:
    """Deregister a session and release all claims."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.deregister_session(session_id)

        if not result.get("deregistered"):
            return mcp_error(result.get("error", "Deregistration failed"))

        files = result.get("released_files", [])
        branches = result.get("released_branches", [])
        msg = f"Session deregistered: {session_id[:20]}"
        if files:
            msg += f"\nReleased {len(files)} file claim(s)"
        if branches:
            msg += f"\nReleased {len(branches)} branch claim(s)"
        _audit_log("session_deregister", session_id, msg.split("\n")[0])
        return mcp_response(msg)
    except Exception as e:
        logger.error("session_deregister failed: %s", e, exc_info=True)
        return mcp_error(f"Deregistration failed: {e}")


# ============================================================================
# Handler: omega_sessions_list
# ============================================================================


async def handle_sessions_list(arguments: dict) -> dict:
    """List all active sessions."""
    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        sessions = mgr.list_sessions()

        if not sessions:
            return mcp_response("No active sessions.")

        lines = [f"## Active Sessions ({len(sessions)})\n"]
        for s in sessions:
            sid = s["session_id"][:20]
            project = s.get("project") or "unknown"
            task = s.get("task") or "no task"
            hb = s.get("last_heartbeat", "")[:19]
            lines.append(f"- **{sid}** | {project} | {task} | heartbeat: {hb}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("sessions_list failed: %s", e, exc_info=True)
        return mcp_error(f"List failed: {e}")


# ============================================================================
# Handler: omega_file_claim
# ============================================================================


async def handle_file_claim(arguments: dict) -> dict:
    """Claim exclusive file access."""
    session_id = arguments.get("session_id", "").strip()
    file_path = arguments.get("file_path", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not file_path:
        return mcp_error("file_path is required")

    task = arguments.get("task")
    force = arguments.get("force", False)

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.claim_file(session_id, file_path, task=task, force=force)

        if result.get("success"):
            msg = f"File claimed: {file_path}"
            if result.get("refreshed"):
                msg += " (refreshed existing claim)"
            elif result.get("force_override"):
                prev = result.get("previous_owner", "unknown")[:20]
                msg += f" (force-override from {prev})"
            elif result.get("expired_claim_replaced"):
                msg += " (replaced expired claim)"
            _audit_log("file_claim", session_id, msg)
            return mcp_response(msg)
        elif result.get("conflict"):
            owner = result["claimed_by"][:20]
            owner_task = result.get("task") or "unknown task"
            _audit_log("file_claim", session_id, f"CONFLICT: {file_path}")
            return mcp_response(
                f"CONFLICT: {file_path} is claimed by session {owner} ({owner_task}). "
                f"Wait for them to finish, use force=true to override, or ask the human to resolve."
            )
        else:
            return mcp_error(result.get("error", "Claim failed"))
    except Exception as e:
        logger.error("file_claim failed: %s", e, exc_info=True)
        return mcp_error(f"File claim failed: {e}")


# ============================================================================
# Handler: omega_file_release
# ============================================================================


async def handle_file_release(arguments: dict) -> dict:
    """Release a file claim."""
    session_id = arguments.get("session_id", "").strip()
    file_path = arguments.get("file_path", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not file_path:
        return mcp_error("file_path is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.release_file(session_id, file_path)
        if result.get("released"):
            _audit_log("file_release", session_id, f"File released: {file_path}")
            return mcp_response(f"File released: {file_path}")
        return mcp_error(result.get("error", "Release failed"))
    except Exception as e:
        logger.error("file_release failed: %s", e, exc_info=True)
        return mcp_error(f"File release failed: {e}")


# ============================================================================
# Handler: omega_file_check
# ============================================================================


async def handle_file_check(arguments: dict) -> dict:
    """Check who owns a file."""
    file_path = arguments.get("file_path", "").strip()
    if not file_path:
        return mcp_error("file_path is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.check_file(file_path)

        if not result.get("claimed"):
            return mcp_response(f"File is unclaimed: {file_path}")

        return mcp_response(
            f"File is claimed: {file_path}\n"
            f"  Owner: {result['session_id'][:20]}\n"
            f"  Task: {result.get('task') or 'unspecified'}\n"
            f"  Since: {result.get('claimed_at', '')[:19]}"
        )
    except Exception as e:
        logger.error("file_check failed: %s", e, exc_info=True)
        return mcp_error(f"File check failed: {e}")


# ============================================================================
# Handler: POST /coord/async-task
# ============================================================================


async def handle_async_task(arguments: dict) -> dict:
    """Enqueue an async task via the coordinator's async queue.

    Accepts a task payload and returns a task ID immediately without
    waiting for the task to complete.
    """
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    payload = arguments.get("payload")
    if payload is None:
        return mcp_error("payload is required")

    task_type = arguments.get("task_type", "generic").strip()
    priority = arguments.get("priority", 0)

    try:
        from omega.coordination import get_manager

        mgr = get_manager()

        if not hasattr(mgr, "enqueue_async_task"):
            return mcp_error(
                "Coordinator does not support async task queue. "
                "Ensure the coordinator is initialised with async queue support."
            )

        task_id = await mgr.enqueue_async_task(
            session_id=session_id,
            task_type=task_type,
            payload=payload,
            priority=priority,
        )

        msg = (
            f"Async task enqueued successfully.\n"
            f"  Task ID:   {task_id}\n"
            f"  Type:      {task_type}\n"
            f"  Session:   {session_id[:20]}\n"
            f"  Priority:  {priority}\n"
            f"Task is queued for processing; poll with task_id to check status."
        )
        _audit_log("async_task_enqueue", session_id, f"Enqueued task {task_id} (type={task_type})")
        return mcp_response(msg, extra={"task_id": task_id})
    except Exception as e:
        logger.error("async_task enqueue failed: %s", e, exc_info=True)
        return mcp_error(f"Failed to enqueue async task: {e}")


# ============================================================================
# Handler: omega_branch_claim
# ============================================================================


async def handle_branch_claim(arguments: dict) -> dict:
    """Claim a branch."""
    session_id = arguments.get("session_id", "").strip()
    project = arguments.get("project", "").strip()
    branch = arguments.get("branch", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not project:
        return mcp_error("project is required")
    if not branch:
        return mcp_error("branch is required")

    task = arguments.get("task")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.claim_branch(session_id, project, branch, task=task)

        if result.get("success"):
            msg = f"Branch claimed: {project}:{branch}"
            if result.get("refreshed"):
                msg += " (refreshed existing claim)"
            _audit_log("branch_claim", session_id, msg)
            return mcp_response(msg)
        elif result.get("protected"):
            return mcp_error(result["error"])
        elif result.get("conflict"):
            owner = result["claimed_by"][:20]
            return mcp_response(f"CONFLICT: Branch {branch} on {project} is claimed by session {owner}.")
        else:
            return mcp_error(result.get("error", "Branch claim failed"))
    except Exception as e:
        logger.error("branch_claim failed: %s", e, exc_info=True)
        return mcp_error(f"Branch claim failed: {e}")


# ============================================================================
# Handler: omega_branch_release
# ============================================================================


async def handle_branch_release(arguments: dict) -> dict:
    """Release a branch claim."""
    session_id = arguments.get("session_id", "").strip()
    project = arguments.get("project", "").strip()
    branch = arguments.get("branch", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not project:
        return mcp_error("project is required")
    if not branch:
        return mcp_error("branch is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.release_branch(session_id, project, branch)
        if result.get("released"):
            _audit_log("branch_release", session_id, f"released {project}:{branch}")
            return mcp_response(f"Branch released: {project}:{branch}")
        return mcp_error(result.get("error", "Release failed"))
    except Exception as e:
        logger.error("branch_release failed: %s", e, exc_info=True)
        return mcp_error(f"Branch release failed: {e}")


# ============================================================================
# Handler: omega_intent_announce
# ============================================================================


async def handle_intent_announce(arguments: dict) -> dict:
    """Announce planned work."""
    session_id = arguments.get("session_id", "").strip()
    description = arguments.get("description", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not description:
        return mcp_error("description is required")

    try:
        from omega.server.hook_server import mark_protocol_call
        mark_protocol_call(session_id, "omega_intent_announce")
    except Exception as e:
        logger.debug("mark_protocol_call (intent_announce) failed: %s", e)

    target_files = arguments.get("target_files")
    target_branch = arguments.get("target_branch")
    intent_type = arguments.get("intent_type", "work")
    ttl_minutes = arguments.get("ttl_minutes", 30)

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.announce_intent(
            session_id=session_id,
            description=description,
            intent_type=intent_type,
            target_files=target_files,
            target_branch=target_branch,
            ttl_minutes=ttl_minutes,
        )

        if result.get("success"):
            msg = f"Intent announced: {description[:100]}"
            if target_files:
                msg += f"\n  Files: {', '.join(target_files[:5])}"
            if target_branch:
                msg += f"\n  Branch: {target_branch}"
            msg += f"\n  Expires: {result['expires_at'][:19]}"

            overlaps = result.get("overlaps")
            if overlaps:
                msg += f"\n[!] {len(overlaps)} overlap(s) detected:"
                for ov in overlaps[:5]:
                    parts = []
                    if ov.get("overlapping_files"):
                        parts.append(f"files: {', '.join(ov['overlapping_files'][:3])}")
                    if ov.get("overlapping_branches"):
                        parts.append(f"branches: {', '.join(ov['overlapping_branches'])}")
                    msg += f"\n  - {ov['session_id'][:20]}: {' | '.join(parts)}"

            _audit_log("intent_announce", session_id, f"announced: {description[:80]}")
            return mcp_response(msg)
        return mcp_error(result.get("error", "Announce failed"))
    except Exception as e:
        logger.error("intent_announce failed: %s", e, exc_info=True)
        return mcp_error(f"Intent announce failed: {e}")


# ============================================================================
# Handler: omega_intent_check
# ============================================================================


async def handle_intent_check(arguments: dict) -> dict:
    """Check for intent overlaps with other agents."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.check_intents(session_id)

        lines = []

        if result.get("has_overlaps"):
            lines.append("## Intent Overlaps Detected\n")
            for overlap in result["overlaps"]:
                sid = overlap["session_id"][:20]
                desc = overlap.get("description", "")[:100]
                lines.append(f"- **{sid}**: {desc}")
                if "overlapping_files" in overlap:
                    lines.append(f"  Files: {', '.join(overlap['overlapping_files'])}")
                if "overlapping_branches" in overlap:
                    lines.append(f"  Branches: {', '.join(overlap['overlapping_branches'])}")
                if "findings" in overlap:
                    lines.append(f"  **Already explored:**")
                    for finding in overlap["findings"][-3:]:
                        lines.append(f"    - {finding[:200]}")

        # Surface peer findings even without file overlap
        peer_findings = result.get("peer_findings", [])
        if peer_findings:
            if lines:
                lines.append("")
            lines.append("## Peer Findings (already explored)\n")
            for pf in peer_findings:
                sid = pf["session_id"][:20]
                desc = pf.get("description", "")
                lines.append(f"- **{sid}** ({desc}):")
                for finding in pf["findings"][-3:]:
                    lines.append(f"  - {finding[:200]}")

        if not lines:
            return mcp_response("No overlaps detected with other agents' intents.")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("intent_check failed: %s", e, exc_info=True)
        return mcp_error(f"Intent check failed: {e}")


# ============================================================================
# Handler: omega_coord_status
# ============================================================================


async def handle_coord_status(arguments: dict) -> dict:
    """Coordination dashboard."""
    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        status = mgr.get_status()

        lines = [f"Sessions: {status['active_sessions']}"]
        for s in status["sessions"]:
            sid = s["session_id"][:12]
            proj = s.get("project") or "?"
            task = s.get("task") or "idle"
            lines.append(f"  {sid} | {proj} | {task}")

        if status["file_claims"]:
            lines.append(f"Files claimed: {status['file_claims']}")
            for f in status["files"]:
                lines.append(f"  {f['path']} -> {f['session_id'][:12]}")

        if status["branch_claims"]:
            lines.append(f"Branches: {status['branch_claims']}")
            for b in status["branches"]:
                lines.append(f"  {b['project']}:{b['branch']} -> {b['session_id'][:12]}")

        if status["active_intents"]:
            lines.append(f"Intents: {status['active_intents']}")

        if status["conflicts"]:
            lines.append(f"CONFLICTS ({len(status['conflicts'])}):")
            for c in status["conflicts"]:
                lines.append(
                    f"  {c['type']}: {c['file']} "
                    f"(claimed={c['claimed_by'][:12]}, intended={c['intended_by'][:12]})"
                )

        deadlocks = status.get("deadlocks", [])
        if deadlocks:
            lines.append(f"DEADLOCKS ({len(deadlocks)}):")
            for cycle in deadlocks:
                lines.append(f"  Cycle: {' -> '.join(s[:12] for s in cycle)}")

        # Mark coord_status as checked for the deploy gate
        try:
            from omega.server.handlers import _mark_coord_status_checked
            session_id = arguments.get("session_id") or os.environ.get("SESSION_ID")
            _mark_coord_status_checked(session_id)
        except Exception as e:
            logger.debug("coord_status gate marking failed: %s", e)

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("coord_status failed: %s", e, exc_info=True)
        return mcp_error(f"Coordination status failed: {e}")


# ============================================================================
# Handler: omega_session_snapshot
# ============================================================================


async def handle_session_snapshot(arguments: dict) -> dict:
    """Explicitly snapshot a session's state."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    reason = arguments.get("reason", "manual")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.snapshot_session(session_id, reason=reason)

        if result.get("success"):
            _audit_log("session_snapshot", session_id, f"snapshot id={result['snapshot_id']} reason={reason}")
            return mcp_response(f"Session snapshotted (id={result['snapshot_id']}, reason={reason})")
        return mcp_error(result.get("error", "Snapshot failed"))
    except Exception as e:
        logger.error("session_snapshot failed: %s", e, exc_info=True)
        return mcp_error(f"Snapshot failed: {e}")


# ============================================================================
# Handler: omega_session_recover
# ============================================================================


async def handle_session_recover(arguments: dict) -> dict:
    """Recover context from a predecessor session."""
    project = arguments.get("project", "").strip()
    if not project:
        return mcp_error("project is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        snapshots = mgr.recover_session(project)

        if not snapshots:
            return mcp_response(f"No predecessor snapshots found for {project}")

        snap = snapshots[0]
        lines = [
            f"[RESUME] Predecessor session detected ({snap['reason']})",
            f"  Session: {snap['session_id'][:20]}",
            f"  Time: {snap['created_at'][:19]}",
        ]
        if snap.get("task"):
            lines.append(f"  Task: {snap['task']}")
        if snap.get("file_claims"):
            files = [fc["file_path"] for fc in snap["file_claims"]]
            lines.append(f"  Files in progress: {', '.join(files)}")
        if snap.get("branch_claims"):
            branches = [f"{bc['project']}:{bc['branch']}" for bc in snap["branch_claims"]]
            lines.append(f"  Branches: {', '.join(branches)}")
        if snap.get("intents"):
            for intent in snap["intents"]:
                lines.append(f"  Intent: {intent['description']}")
                if intent.get("target_files"):
                    lines.append(f"    Target files: {', '.join(intent['target_files'])}")
                if intent.get("target_branch"):
                    lines.append(f"    Target branch: {intent['target_branch']}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("session_recover failed: %s", e, exc_info=True)
        return mcp_error(f"Recovery failed: {e}")


# ============================================================================
# Handler: omega_task_create
# ============================================================================


async def handle_task_create(arguments: dict) -> dict:
    """Create a coordination task."""
    session_id = arguments.get("session_id", "").strip()
    title = arguments.get("title", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not title:
        return mcp_error("title is required")

    description = arguments.get("description")
    project = arguments.get("project")
    priority = arguments.get("priority", 0)
    depends_on = arguments.get("depends_on")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()

        # Check for similar existing tasks before creating
        similar = mgr.find_similar_tasks(title, project=project)

        result = mgr.create_task(
            created_by=session_id,
            title=title,
            description=description,
            project=project,
            priority=priority,
            depends_on=depends_on,
        )
        if result.get("success"):
            msg = f"Task created: #{result['task_id']} -- {title}"
            blocked_by = result.get("blocked_by")
            if blocked_by:
                msg += f"\n  Blocked by: {', '.join(f'#{d}' for d in blocked_by)}"
            if similar:
                warnings = []
                for s in similar[:3]:
                    owner = s.get("session_id") or s.get("created_by") or "unassigned"
                    warnings.append(
                        f"  #{s['id']} \"{s['title']}\" ({s['status']}, owner: {owner[:20]}, "
                        f"overlap: {', '.join(s['overlap_keywords'])})"
                    )
                msg += "\n\nWARNING: Similar tasks already exist:\n" + "\n".join(warnings)
                msg += "\nConsider checking with the owner before duplicating work."
            _audit_log("task_create", session_id, f"created #{result['task_id']}: {title[:80]}")
            return mcp_response(msg)
        return mcp_error(result.get("error", "Task creation failed"))
    except Exception as e:
        logger.error("task_create failed: %s", e, exc_info=True)
        return mcp_error(f"Task creation failed: {e}")


# ============================================================================
# Handler: omega_task_claim
# ============================================================================


async def handle_task_claim(arguments: dict) -> dict:
    """Claim a pending task."""
    task_id = arguments.get("task_id")
    session_id = arguments.get("session_id", "").strip()
    if task_id is None:
        return mcp_error("task_id is required")
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.claim_task(int(task_id), session_id)

        if result.get("success"):
            _audit_log("task_claim", session_id, f"claimed #{task_id}")
            return mcp_response(f"Task #{task_id} claimed by {session_id[:20]}")
        blocked_by = result.get("blocked_by")
        if blocked_by:
            return mcp_response(
                f"Task #{task_id} is blocked by incomplete dependencies: {', '.join(f'#{d}' for d in blocked_by)}"
            )
        return mcp_error(result.get("error", "Claim failed"))
    except Exception as e:
        logger.error("task_claim failed: %s", e, exc_info=True)
        return mcp_error(f"Task claim failed: {e}")


# ============================================================================
# Handler: omega_task_next
# ============================================================================


async def handle_task_next(arguments: dict) -> dict:
    """Find and auto-claim the next available task."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    project = arguments.get("project")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.next_task(session_id, project=project)

        if result.get("success"):
            task_id = result["task_id"]
            title = result.get("title", "")
            priority = result.get("priority", 0)
            progress = result.get("progress", 0)
            prio_str = f" (P{priority})" if priority else ""
            prog_str = f" [{progress}% done]" if progress else ""
            _audit_log("task_next", session_id, f"auto-claimed #{task_id}")
            return mcp_response(
                f"Claimed task #{task_id}{prio_str}: {title}{prog_str}\n"
                f"Description: {result.get('description') or 'none'}"
            )
        return mcp_response(result.get("message", "No claimable tasks"))
    except Exception as e:
        logger.error("task_next failed: %s", e, exc_info=True)
        return mcp_error(f"Task next failed: {e}")


# ============================================================================
# Handler: omega_task_resolve (unified complete/fail/cancel)
# ============================================================================


async def handle_task_resolve(arguments: dict) -> dict:
    """Resolve a task — complete, fail, or cancel."""
    task_id = arguments.get("task_id")
    session_id = arguments.get("session_id", "").strip()
    status = arguments.get("status", "completed")
    if task_id is None:
        return mcp_error("task_id is required")
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if status not in ("completed", "failed", "canceled"):
        return mcp_error("status must be one of: completed, failed, canceled")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()

        if status == "completed":
            task_result = arguments.get("result")
            result = mgr.complete_task(int(task_id), session_id, result=task_result)
            if result.get("success"):
                msg = f"Task #{task_id} completed"
                unblocked = result.get("unblocked_tasks", [])
                if unblocked:
                    msg += f"\nUnblocked {len(unblocked)} task(s):"
                    for ut in unblocked:
                        msg += f"\n  - #{ut['task_id']} {ut['title']}"
                _audit_log("task_resolve", session_id, f"completed #{task_id}")
                return mcp_response(msg)
            return mcp_error(result.get("error", "Complete failed"))

        elif status == "failed":
            reason = arguments.get("reason")
            result = mgr.fail_task(int(task_id), session_id, reason=reason)
            if result.get("success"):
                msg = f"Task #{task_id} marked as failed"
                if reason:
                    msg += f": {reason[:100]}"
                _audit_log("task_resolve", session_id, f"failed #{task_id}: {(reason or 'no reason')[:80]}")
                return mcp_response(msg)
            return mcp_error(result.get("error", "Fail failed"))

        else:  # canceled
            result = mgr.cancel_task(int(task_id), session_id)
            if result.get("success"):
                _audit_log("task_resolve", session_id, f"canceled #{task_id}")
                return mcp_response(f"Task #{task_id} canceled")
            return mcp_error(result.get("error", "Cancel failed"))

    except Exception as e:
        logger.error("task_resolve failed: %s", e, exc_info=True)
        return mcp_error(f"Task resolve failed: {e}")


# ============================================================================
# Handler: omega_tasks_list
# ============================================================================


async def handle_tasks_list(arguments: dict) -> dict:
    """List coordination tasks."""
    project = arguments.get("project")
    status = arguments.get("status")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        tasks = mgr.list_tasks(project=project, status=status)

        if not tasks:
            return mcp_response("No tasks found.")

        lines = [f"## Tasks ({len(tasks)})\n"]
        for t in tasks:
            status_icon = {
                "pending": "[ ]",
                "in_progress": "[~]",
                "completed": "[x]",
                "failed": "[!]",
                "canceled": "[-]",
            }.get(t["status"], "[?]")
            owner = f" -> {t['session_id'][:16]}" if t.get("session_id") else ""
            prio = f" P{t['priority']}" if t.get("priority") else ""

            # Progress indicator for in_progress tasks
            progress_str = ""
            if t["status"] == "in_progress" and t.get("progress", 0) > 0:
                progress_str = f" [{t['progress']}%]"
                status_note = t.get("metadata", {}).get("status_note")
                if status_note:
                    progress_str += f" {status_note}"

            # Blocked indicator
            blocked_str = ""
            if t.get("blocked") and t.get("depends_on"):
                blocked_str = f" (blocked by {', '.join(f'#{d}' for d in t['depends_on'])})"

            lines.append(f"{status_icon} **#{t['id']}**{prio} {t['title']}{owner}{progress_str}{blocked_str}")
            if t.get("description"):
                lines.append(f"    {t['description'][:100]}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("tasks_list failed: %s", e, exc_info=True)
        return mcp_error(f"Task list failed: {e}")


# ============================================================================
# Handler: omega_audit
# ============================================================================


async def handle_audit(arguments: dict) -> dict:
    """Query the coordination audit log."""
    session_id = arguments.get("session_id")
    tool_name = arguments.get("tool_name")
    limit = arguments.get("limit", 50)

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        entries = mgr.query_audit(
            session_id=session_id,
            tool_name=tool_name,
            limit=limit,
        )

        if not entries:
            return mcp_response("No audit entries found.")

        lines = [f"## Audit Log ({len(entries)} entries)\n"]
        for e in entries:
            ts = e["created_at"][:19]
            sid = e["session_id"][:12] if e.get("session_id") else "?"
            tool = e["tool_name"]
            summary = e.get("result_summary") or ""
            lines.append(f"- `{ts}` | {sid} | **{tool}** | {summary[:80]}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("audit query failed: %s", e, exc_info=True)
        return mcp_error(f"Audit query failed: {e}")


# ============================================================================
# Handler: omega_send_message
# ============================================================================


async def handle_send_message(arguments: dict) -> dict:
    """Send a message to another agent or broadcast to project."""
    session_id = arguments.get("session_id", "").strip()
    subject = arguments.get("subject", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not subject:
        return mcp_error("subject is required")

    # Validate to_session_id if provided
    to_session_id = arguments.get("to_session_id", "").strip()
    if to_session_id:
        to_session_id = _validate_session_id(to_session_id)
        if not to_session_id:
            return mcp_error("Invalid to_session_id")

    # Anti-spoofing: if caller_session_id is provided (injected by server/hook layer),
    # enforce that from_session matches the caller's actual session
    caller_session_id = arguments.get("caller_session_id", "").strip()
    if caller_session_id and session_id != caller_session_id:
        logger.warning(
            "Message spoofing attempt: caller %s tried to send as %s",
            caller_session_id[:12], session_id[:12],
        )
        return mcp_error(
            f"Session mismatch: your session is {caller_session_id[:12]}, "
            f"cannot send as {session_id[:12]}"
        )

    to_session = arguments.get("to_session")
    body = arguments.get("body")
    msg_type = arguments.get("msg_type", "inform")
    context_id = arguments.get("context_id")
    ref_task_id = arguments.get("ref_task_id")
    ttl_minutes = arguments.get("ttl_minutes")
    priority = arguments.get("priority", "medium")
    if priority not in ("critical", "high", "medium"):
        priority = "medium"

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.send_message(
            from_session=session_id,
            subject=subject,
            msg_type=msg_type,
            to_session=to_session,
            body=body,
            context_id=context_id,
            ref_task_id=ref_task_id,
            ttl_minutes=ttl_minutes,
            priority=priority,
        )
        if result.get("success"):
            target = to_session[:20] if to_session else "broadcast"
            _audit_log("send_message", session_id, f"{msg_type} to {target}: {subject[:60]}")

            # Push urgent notification to recipient(s) for immediate surfacing
            # Only notify immediately for critical priority; high/medium are batched
            if priority == "critical":
                try:
                    from omega.server.hook_server import notify_session

                    msg_summary = {
                        "from_session": session_id,
                        "subject": subject,
                        "msg_type": msg_type,
                    }
                    if to_session:
                        notify_session(to_session, msg_summary)
                    else:
                        # Broadcast: notify all same-project peers
                        sessions = mgr.list_sessions(auto_clean=False)
                        sender_project = None
                        for s in sessions:
                            if s["session_id"] == session_id:
                                sender_project = s.get("project")
                                break
                        if sender_project:
                            for s in sessions:
                                peer_id = s["session_id"]
                                if peer_id != session_id and s.get("project") == sender_project:
                                    notify_session(peer_id, msg_summary)
                except Exception as e:
                    logger.debug("peer notification after send_message failed: %s", e)

            return mcp_response(
                f"Message sent ({msg_type}) to {target}: {subject[:80]}\n  context_id: {result['context_id']}"
            )
        return mcp_error(result.get("error", "Send failed"))
    except Exception as e:
        logger.error("send_message failed: %s", e, exc_info=True)
        return mcp_error(f"Send message failed: {e}")


# ============================================================================
# Handler: omega_inbox
# ============================================================================


async def handle_inbox(arguments: dict) -> dict:
    """Check inbox for messages."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    try:
        from omega.server.hook_server import mark_protocol_call
        mark_protocol_call(session_id, "omega_inbox")
    except Exception as e:
        logger.debug("mark_protocol_call (inbox) failed: %s", e)

    unread_only = arguments.get("unread_only", True)
    msg_type = arguments.get("msg_type")
    limit = arguments.get("limit", 20)

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        messages = mgr.check_inbox(
            session_id=session_id,
            unread_only=unread_only,
            msg_type=msg_type,
            limit=limit,
        )

        if not messages:
            return mcp_response("Inbox empty — no unread messages." if unread_only else "Inbox empty.")

        lines = [f"## Inbox ({len(messages)} message{'s' if len(messages) != 1 else ''})\n"]
        for m in messages:
            from_sid = m["from_session"][:16]
            mtype = m["msg_type"]
            subj = m["subject"][:80]
            ts = m["created_at"][:19]
            ctx = f" [thread:{m['context_id'][:8]}]" if m.get("context_id") else ""
            ref = f" (re: task #{m['ref_task_id']})" if m.get("ref_task_id") else ""
            lines.append(f"- **[{mtype}]** {subj} — from {from_sid} at {ts}{ctx}{ref}")
            if m.get("body"):
                lines.append(f"    {m['body'][:150]}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("inbox failed: %s", e, exc_info=True)
        return mcp_error(f"Inbox check failed: {e}")


# ============================================================================
# Handler: omega_task_fail
# ============================================================================


async def handle_task_fail(arguments: dict) -> dict:
    """Mark a task as failed."""
    task_id = arguments.get("task_id")
    session_id = arguments.get("session_id", "").strip()
    if task_id is None:
        return mcp_error("task_id is required")
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    reason = arguments.get("reason")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.fail_task(int(task_id), session_id, reason=reason)

        if result.get("success"):
            msg = f"Task #{task_id} marked as failed"
            if reason:
                msg += f": {reason[:100]}"
            _audit_log("task_fail", session_id, f"failed #{task_id}: {(reason or 'no reason')[:80]}")
            return mcp_response(msg)
        return mcp_error(result.get("error", "Fail failed"))
    except Exception as e:
        logger.error("task_fail failed: %s", e, exc_info=True)
        return mcp_error(f"Task fail failed: {e}")


# ============================================================================
# Handler: omega_task_cancel
# ============================================================================


async def handle_task_cancel(arguments: dict) -> dict:
    """Cancel a task. Only the owning session (or unclaimed tasks) can cancel."""
    task_id = arguments.get("task_id")
    session_id = arguments.get("session_id", "").strip()
    if task_id is None:
        return mcp_error("task_id is required")
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.cancel_task(int(task_id), session_id)

        if result.get("success"):
            _audit_log("task_cancel", session_id, f"canceled #{task_id}")
            return mcp_response(f"Task #{task_id} canceled")
        return mcp_error(result.get("error", "Cancel failed"))
    except Exception as e:
        logger.error("task_cancel failed: %s", e, exc_info=True)
        return mcp_error(f"Task cancel failed: {e}")


# ============================================================================
# Handler: omega_task_progress
# ============================================================================


async def handle_task_progress(arguments: dict) -> dict:
    """Update task progress."""
    task_id = arguments.get("task_id")
    session_id = arguments.get("session_id", "").strip()
    progress = arguments.get("progress")
    if task_id is None:
        return mcp_error("task_id is required")
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if progress is None:
        return mcp_error("progress is required")

    status_note = arguments.get("status_note")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.update_task_progress(
            int(task_id),
            session_id,
            int(progress),
            status_note=status_note,
        )

        if result.get("success"):
            msg = f"Task #{task_id} progress: {result['progress']}%"
            if status_note:
                msg += f" — {status_note}"
            _audit_log("task_progress", session_id, f"#{task_id} -> {result['progress']}%")
            return mcp_response(msg)
        return mcp_error(result.get("error", "Progress update failed"))
    except Exception as e:
        logger.error("task_progress failed: %s", e, exc_info=True)
        return mcp_error(f"Task progress failed: {e}")


# ============================================================================
# Handler: omega_find_agents
# ============================================================================


async def handle_find_agents(arguments: dict) -> dict:
    """Find agents with a specific capability."""
    capability = arguments.get("capability", "").strip()
    if not capability:
        return mcp_error("capability is required")

    project = arguments.get("project")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        matches = mgr.find_capable_sessions(capability, project=project)

        if not matches:
            return mcp_response(f"No active agents found with capability '{capability}'")

        lines = [f"## Agents with '{capability}' ({len(matches)})\n"]
        for m in matches:
            sid = m["session_id"][:20]
            proj = m.get("project") or "?"
            caps = ", ".join(m.get("capabilities", []))
            line = f"- **{sid}** | {proj} | capabilities: [{caps}]"
            if m.get("current_task"):
                ct = m["current_task"]
                line += f"\n    Working on: #{ct['id']} {ct['title']}"
            lines.append(line)

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("find_agents failed: %s", e, exc_info=True)
        return mcp_error(f"Find agents failed: {e}")


# ============================================================================
# Handler: omega_task_deps
# ============================================================================


async def handle_task_deps(arguments: dict) -> dict:
    """Get dependency graph for a task."""
    task_id = arguments.get("task_id")
    if task_id is None:
        return mcp_error("task_id is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.get_task_deps(int(task_id))

        if result.get("error"):
            return mcp_error(result["error"])

        lines = [f"## Task #{task_id} Dependencies\n"]

        deps = result.get("depends_on", [])
        if deps:
            lines.append("**Depends on:**")
            for d in deps:
                icon = "[x]" if d["status"] == "completed" else "[ ]"
                lines.append(f"  {icon} #{d['task_id']} {d['title']} ({d['status']})")
        else:
            lines.append("**Depends on:** none")

        depby = result.get("depended_by", [])
        if depby:
            lines.append("\n**Depended by:**")
            for d in depby:
                lines.append(f"  - #{d['task_id']} {d['title']} ({d['status']})")
        else:
            lines.append("\n**Depended by:** none")

        blocked = result.get("blocked", False)
        lines.append(f"\n**Blocked:** {'yes' if blocked else 'no'}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("task_deps failed: %s", e, exc_info=True)
        return mcp_error(f"Task deps failed: {e}")


# ============================================================================
# Handler: omega_git_events
# ============================================================================


async def handle_git_events(arguments: dict) -> dict:
    """Query recent git events tracked by coordination."""
    project = arguments.get("project")
    event_type = arguments.get("event_type")
    limit = arguments.get("limit", 20)

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        events = mgr.get_recent_git_events(
            project=project,
            event_type=event_type,
            limit=limit,
        )

        if not events:
            return mcp_response("No git events found.")

        lines = [f"## Git Events ({len(events)})\n"]
        for ev in events:
            ts = ev.get("created_at", "")[:19]
            sid = (ev.get("session_id") or "?")[:12]
            etype = ev.get("event_type", "?")
            branch = ev.get("branch") or ""
            msg = (ev.get("message") or "")[:80]
            commit = (ev.get("commit_hash") or "")[:8]
            line = f"- `{ts}` | {sid} | **{etype}** | {branch}"
            if commit:
                line += f" | {commit}"
            if msg:
                line += f" | {msg}"
            lines.append(line)

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("git_events failed: %s", e, exc_info=True)
        return mcp_error(f"Git events failed: {e}")


# ============================================================================
# Handler: omega_branch_check
# ============================================================================


async def handle_branch_check(arguments: dict) -> dict:
    """Check who owns a branch."""
    project = arguments.get("project", "").strip()
    branch = arguments.get("branch", "").strip()
    if not project:
        return mcp_error("project is required")
    if not branch:
        return mcp_error("branch is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.check_branch(project, branch)

        if not result.get("claimed"):
            return mcp_response(f"Branch is unclaimed: {project}:{branch}")

        return mcp_response(
            f"Branch is claimed: {project}:{branch}\n"
            f"  Owner: {result['session_id'][:20]}\n"
            f"  Task: {result.get('task') or 'unspecified'}\n"
            f"  Since: {result.get('claimed_at', '')[:19]}"
        )
    except Exception as e:
        logger.error("branch_check failed: %s", e, exc_info=True)
        return mcp_error(f"Branch check failed: {e}")


# ============================================================================
# Handler: omega_coord_metrics
# ============================================================================


async def handle_coord_metrics(arguments: dict) -> dict:
    """Get coordination metrics over a time period."""
    days = arguments.get("days", 7)
    project = arguments.get("project")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        metrics = mgr.get_metrics(days=days, project=project)

        counts = metrics["counts"]
        rates = metrics["rates"]
        totals = metrics["totals"]

        lines = [f"Coordination Metrics ({days}d):"]
        lines.append(f"  Claims: {totals['total_claims']} | Conflicts: {totals['total_conflicts']} ({rates['conflict_rate']}%)")
        lines.append(f"  Gate checks: {totals['total_gate_checks']} | Skip rate: {rates['gate_skip_rate']}%")
        lines.append(f"  Handoffs: {totals['total_handoffs']} | Read rate: {rates['handoff_read_rate']}%")

        if counts:
            lines.append("  Breakdown:")
            for name, val in sorted(counts.items(), key=lambda x: -x[1]):
                lines.append(f"    {name}: {val}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("coord_metrics failed: %s", e, exc_info=True)
        return mcp_error(f"Metrics query failed: {e}")


# ============================================================================
# Handler: omega_handoff
# ============================================================================


async def handle_handoff(arguments: dict) -> dict:
    """Create or retrieve a structured handoff."""
    session_id = arguments.get("session_id", "").strip()
    action = arguments.get("action", "create")

    if session_id:
        session_id = _validate_session_id(session_id)
        if not session_id:
            return mcp_error("Invalid session_id")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()

        if action == "get":
            project = arguments.get("project")
            handoff = mgr.get_latest_handoff(project=project, reader_session_id=session_id or None)
            if not handoff:
                return mcp_response("No handoffs found.")

            lines = [f"Handoff from {handoff['session_id'][:16]} ({handoff['created_at'][:19]}):"]
            if handoff.get("git_branch"):
                dirty = len(handoff.get("git_dirty_files", []))
                dirty_note = f" ({dirty} uncommitted)" if dirty else ""
                lines.append(f"  Branch: {handoff['git_branch']}{dirty_note}")
            if handoff.get("completed_tasks"):
                lines.append("  Completed:")
                for t in handoff["completed_tasks"]:
                    lines.append(f"    - {t}")
            if handoff.get("decisions_made"):
                lines.append("  Decisions:")
                for d in handoff["decisions_made"]:
                    lines.append(f"    - {d}")
            if handoff.get("blocked_items"):
                lines.append("  Blocked:")
                for b in handoff["blocked_items"]:
                    lines.append(f"    - {b}")
            if handoff.get("key_context"):
                lines.append(f"  Context: {handoff['key_context']}")
            if handoff.get("next_steps"):
                lines.append("  Next steps:")
                for s in handoff["next_steps"]:
                    lines.append(f"    - {s}")
            if handoff.get("files_modified"):
                fnames = [os.path.basename(f) for f in handoff["files_modified"][:5]]
                lines.append(f"  Files: {', '.join(fnames)}")

            return mcp_response("\n".join(lines))

        # Default: create
        if not session_id:
            return mcp_error("session_id is required to create a handoff")

        result = mgr.create_handoff(
            session_id=session_id,
            project=arguments.get("project"),
            completed_tasks=arguments.get("completed_tasks"),
            blocked_items=arguments.get("blocked_items"),
            key_context=arguments.get("key_context"),
            next_steps=arguments.get("next_steps"),
            files_modified=arguments.get("files_modified"),
            decisions_made=arguments.get("decisions_made"),
        )
        _audit_log("omega_handoff", session_id, f"Created handoff #{result['id']}")
        return mcp_response(
            f"Handoff #{result['id']} created.\n"
            f"  Files: {', '.join(os.path.basename(f) for f in result.get('files_modified', [])[:5])}\n"
            f"  Branch: {result.get('git_branch') or 'unknown'}"
        )
    except Exception as e:
        logger.error("handoff failed: %s", e, exc_info=True)
        return mcp_error(f"Handoff failed: {e}")


# ============================================================================
# Handler: omega_action_check
# ============================================================================


async def handle_action_check(arguments: dict) -> dict:
    """Check if an external action has been claimed or completed."""
    action_type = arguments.get("action_type", "").strip()
    action_target = arguments.get("action_target", "").strip()
    if not action_type:
        return mcp_error("action_type is required")
    if not action_target:
        return mcp_error("action_target is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.check_external_action(action_type, action_target)

        if not result.get("exists"):
            return mcp_response(f"No active action found: {action_type}:{action_target} — safe to proceed.")

        status = result["status"]
        sid = result["session_id"][:20]
        if status == "completed":
            return mcp_response(
                f"Action already completed: {action_type}:{action_target}\n"
                f"  By: {sid}\n"
                f"  At: {(result.get('completed_at') or '')[:19]}\n"
                f"  Result: {(result.get('result') or 'none')[:200]}"
            )
        return mcp_response(
            f"Action currently claimed: {action_type}:{action_target}\n"
            f"  By: {sid}\n"
            f"  Since: {(result.get('created_at') or '')[:19]}"
        )
    except Exception as e:
        logger.error("action_check failed: %s", e, exc_info=True)
        return mcp_error(f"Action check failed: {e}")


# ============================================================================
# Handler: omega_action_claim
# ============================================================================


async def handle_action_claim(arguments: dict) -> dict:
    """Atomically claim an external action."""
    session_id = arguments.get("session_id", "").strip()
    action_type = arguments.get("action_type", "").strip()
    action_target = arguments.get("action_target", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not action_type:
        return mcp_error("action_type is required")
    if not action_target:
        return mcp_error("action_target is required")

    params = arguments.get("params")
    params_str = None
    if params is not None:
        import json
        params_str = json.dumps(params) if not isinstance(params, str) else params

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.claim_external_action(
            session_id=session_id,
            action_type=action_type,
            action_target=action_target,
            params=params_str,
        )

        if result.get("success"):
            msg = f"Action claimed: {action_type}:{action_target} (id={result['action_id']})"
            _audit_log("action_claim", session_id, msg)
            # Write gate marker so pre_deploy_guard hook can verify
            if action_type == "deploy":
                _write_deploy_action_marker(session_id)
            return mcp_response(msg)

        error = result.get("error", "Claim failed")
        if "Already claimed" in error:
            claimed_by = result.get("claimed_by", "unknown")[:20]
            _audit_log("action_claim", session_id, f"BLOCKED: {action_type}:{action_target} claimed by {claimed_by}")
            return mcp_response(
                f"BLOCKED: {action_type}:{action_target} is already claimed by {claimed_by}.\n"
                f"  Do NOT proceed — another agent is handling this."
            )
        if "Already completed" in error:
            completed_by = result.get("completed_by", "unknown")[:20]
            _audit_log("action_claim", session_id, f"BLOCKED: {action_type}:{action_target} already completed")
            return mcp_response(
                f"BLOCKED: {action_type}:{action_target} was already completed by {completed_by}.\n"
                f"  At: {(result.get('completed_at') or '')[:19]}\n"
                f"  Result: {(result.get('result') or 'none')[:200]}"
            )
        return mcp_error(error)
    except Exception as e:
        logger.error("action_claim failed: %s", e, exc_info=True)
        return mcp_error(f"Action claim failed: {e}")


# ============================================================================
# Handler: omega_action_complete
# ============================================================================


async def handle_action_complete(arguments: dict) -> dict:
    """Mark a claimed external action as completed or failed."""
    action_id = arguments.get("action_id")
    session_id = arguments.get("session_id", "").strip()
    if action_id is None:
        return mcp_error("action_id is required")
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    result_text = arguments.get("result")
    success = arguments.get("success", True)

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.complete_external_action(
            action_id=int(action_id),
            session_id=session_id,
            result=result_text,
            success=success,
        )

        if result.get("success"):
            status = result["status"]
            msg = f"Action #{action_id} marked as {status}"
            if result_text:
                msg += f": {result_text[:100]}"
            _audit_log("action_complete", session_id, f"#{action_id} -> {status}")
            return mcp_response(msg)
        return mcp_error(result.get("error", "Complete failed"))
    except Exception as e:
        logger.error("action_complete failed: %s", e, exc_info=True)
        return mcp_error(f"Action complete failed: {e}")


# ============================================================================
# Handler: omega_goal
# ============================================================================


async def handle_goal(arguments: dict) -> dict:
    """Goal lifecycle management."""
    action = arguments.get("action", "").strip()
    if not action:
        return mcp_error("action is required (create, evolve, complete, list, get)")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()

        if action == "create":
            session_id = arguments.get("session_id", "").strip()
            title = arguments.get("title", "").strip()
            description = arguments.get("description", "").strip()
            project = arguments.get("project", "").strip()
            if not session_id:
                return mcp_error("session_id is required for create")
            if not title:
                return mcp_error("title is required for create")
            if not description:
                return mcp_error("description is required for create")
            if not project:
                return mcp_error("project is required for create")

            result = mgr.create_goal(
                session_id=session_id,
                title=title,
                description=description,
                project=project,
                target_files=arguments.get("target_files"),
                target_modules=arguments.get("target_modules"),
                success_criteria=arguments.get("success_criteria"),
                parent_goal_id=arguments.get("parent_goal_id"),
                priority=arguments.get("priority", 0),
            )
            if result.get("success"):
                msg = f"Goal #{result['goal_id']} created: {title}"
                if result.get("parent_goal_id"):
                    msg += f" (child of #{result['parent_goal_id']})"
                _audit_log("omega_goal", session_id, f"created #{result['goal_id']}: {title[:60]}")
                return mcp_response(msg)
            return mcp_error(result.get("error", "Create failed"))

        elif action == "evolve":
            session_id = arguments.get("session_id", "").strip()
            goal_id = arguments.get("goal_id")
            description = arguments.get("description", "").strip()
            reason = arguments.get("reason", "").strip()
            if not session_id:
                return mcp_error("session_id is required for evolve")
            if goal_id is None:
                return mcp_error("goal_id is required for evolve")
            if not description:
                return mcp_error("description is required for evolve")
            if not reason:
                return mcp_error("reason is required for evolve")

            result = mgr.evolve_goal(int(goal_id), session_id, description, reason)
            if result.get("success"):
                msg = (
                    f"Goal evolved: #{result['evolved_from_id']} -> #{result['new_goal_id']}\n"
                    f"  Reason: {reason[:100]}"
                )
                _audit_log("omega_goal", session_id, f"evolved #{goal_id} -> #{result['new_goal_id']}")
                return mcp_response(msg)
            return mcp_error(result.get("error", "Evolve failed"))

        elif action == "complete":
            session_id = arguments.get("session_id", "").strip()
            goal_id = arguments.get("goal_id")
            if not session_id:
                return mcp_error("session_id is required for complete")
            if goal_id is None:
                return mcp_error("goal_id is required for complete")

            result = mgr.complete_goal(int(goal_id), session_id)
            if result.get("success"):
                msg = f"Goal #{goal_id} completed"
                if result.get("parent_completed"):
                    msg += " (parent goal also auto-completed)"
                _audit_log("omega_goal", session_id, f"completed #{goal_id}")
                return mcp_response(msg)
            return mcp_error(result.get("error", "Complete failed"))

        elif action == "list":
            project = arguments.get("project")
            status = arguments.get("status", "active")
            include_children = arguments.get("include_children", False)
            goals = mgr.list_goals(project=project, status=status, include_children=include_children)

            if not goals:
                return mcp_response("No goals found.")

            lines = [f"## Goals ({len(goals)})\n"]
            for g in goals:
                status_icon = {"active": "[*]", "paused": "[~]", "completed": "[x]", "abandoned": "[-]"}.get(
                    g["status"], "[?]"
                )
                parent = f" (child of #{g['parent_goal_id']})" if g.get("parent_goal_id") else ""
                prio = f" P{g['priority']}" if g.get("priority") else ""
                lines.append(f"{status_icon} **#{g['id']}**{prio} {g['title']}{parent}")
                if g.get("description"):
                    lines.append(f"    {g['description'][:100]}")
            return mcp_response("\n".join(lines))

        elif action == "get":
            goal_id = arguments.get("goal_id")
            if goal_id is None:
                return mcp_error("goal_id is required for get")

            goal = mgr.get_goal(int(goal_id))
            if not goal:
                return mcp_error(f"Goal #{goal_id} not found")

            lines = [f"## Goal #{goal['id']}: {goal['title']}"]
            lines.append(f"Status: {goal['status']} | Project: {goal['project']} | Priority: {goal['priority']}")
            lines.append(f"Description: {goal['description'] or 'none'}")
            lines.append(f"Original anchor: {goal['original_description'][:200]}")
            if goal.get("target_files"):
                lines.append(f"Target files: {', '.join(goal['target_files'])}")
            if goal.get("success_criteria"):
                lines.append(f"Success criteria: {', '.join(goal['success_criteria'])}")
            if goal.get("evolved_from_id"):
                lines.append(f"Evolved from: #{goal['evolved_from_id']} ({goal.get('evolution_reason', '')})")
            if goal.get("tasks"):
                lines.append(f"\nTasks ({len(goal['tasks'])}):")
                for t in goal["tasks"]:
                    lines.append(f"  #{t['id']} {t['title']} ({t['status']}, {t['progress']}%)")
            if goal.get("children"):
                lines.append(f"\nChild goals ({len(goal['children'])}):")
                for c in goal["children"]:
                    lines.append(f"  #{c['id']} {c['title']} ({c['status']})")
            return mcp_response("\n".join(lines))

        else:
            return mcp_error(f"Unknown action: {action}. Use create, evolve, complete, list, or get.")

    except Exception as e:
        logger.error("omega_goal failed: %s", e, exc_info=True)
        return mcp_error(f"Goal operation failed: {e}")


# ============================================================================
# Handler: omega_goal_link
# ============================================================================


async def handle_goal_link(arguments: dict) -> dict:
    """Link a task to a goal."""
    task_id = arguments.get("task_id")
    goal_id = arguments.get("goal_id")
    if task_id is None:
        return mcp_error("task_id is required")
    if goal_id is None:
        return mcp_error("goal_id is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.link_task_to_goal(int(task_id), int(goal_id))
        if result.get("success"):
            return mcp_response(f"Task #{task_id} linked to goal #{goal_id}")
        return mcp_error(result.get("error", "Link failed"))
    except Exception as e:
        logger.error("omega_goal_link failed: %s", e, exc_info=True)
        return mcp_error(f"Goal link failed: {e}")


# ============================================================================
# Handler: omega_drift_check
# ============================================================================


async def handle_drift_check(arguments: dict) -> dict:
    """Check drift for a goal or all active goals in a project."""
    goal_id = arguments.get("goal_id")
    project = arguments.get("project")

    if goal_id is None and not project:
        return mcp_error("Provide goal_id or project")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()

        if goal_id is not None:
            drift = mgr.check_drift(int(goal_id))
            lines = [f"## Drift Check: Goal #{drift['goal_id']}"]
            lines.append(f"Score: {drift['drift_score']:.1%} ({drift['alert_level']})")
            lines.append("Signals:")
            for name, score in drift["signals"].items():
                bar = "#" * int(score * 10)
                lines.append(f"  {name}: {score:.0%} {bar}")
            return mcp_response("\n".join(lines))

        # Project-wide check
        goals = mgr.list_goals(project=project, status="active")
        if not goals:
            return mcp_response(f"No active goals in {project}")

        lines = [f"## Drift Report: {project} ({len(goals)} active goals)\n"]
        for g in goals:
            drift = mgr.check_drift(g["id"])
            alert = drift["alert_level"]
            icon = {"none": ".", "watch": "~", "warning": "!", "critical": "!!"}
            lines.append(
                f"[{icon.get(alert, '?')}] #{g['id']} {g['title']}: "
                f"{drift['drift_score']:.0%} ({alert})"
            )
        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("omega_drift_check failed: %s", e, exc_info=True)
        return mcp_error(f"Drift check failed: {e}")


# ============================================================================
# Handler: omega_smart_route
# ============================================================================


async def handle_smart_route(arguments: dict) -> dict:
    """Drift-aware task routing."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    project = arguments.get("project")
    goal_id = arguments.get("goal_id")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.smart_route_task(
            session_id=session_id,
            project=project,
            goal_id=int(goal_id) if goal_id is not None else None,
        )

        if result.get("success"):
            task_id = result["task_id"]
            title = result.get("title", "")
            priority = result.get("priority", 0)
            score = result.get("effective_score", 0)
            prio_str = f" (P{priority})" if priority else ""

            msg = f"Routed to task #{task_id}{prio_str}: {title} (score: {score})"

            drift_ctx = result.get("drift_context")
            if drift_ctx:
                msg += (
                    f"\n  Drift: {drift_ctx['goal_drift_score']:.0%} ({drift_ctx['alert_level']}) "
                    f"type={drift_ctx['drift_type']} reason={drift_ctx['routed_reason']}"
                )

            _audit_log("smart_route", session_id, f"routed to #{task_id} (score={score})")
            return mcp_response(msg)
        return mcp_response(result.get("message", "No claimable tasks"))
    except Exception as e:
        logger.error("smart_route failed: %s", e, exc_info=True)
        return mcp_error(f"Smart route failed: {e}")


# ============================================================================
# Handler: omega_decision_register / omega_decision_query / omega_decision_revoke
# ============================================================================


async def handle_decision_register(arguments: dict) -> dict:
    """Register an authoritative decision for a domain."""
    session_id = arguments.get("session_id", "").strip()
    project = arguments.get("project", "").strip()
    domain = arguments.get("domain", "").strip()
    decision = arguments.get("decision", "").strip()

    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")
    if not project:
        return mcp_error("project is required")
    if not domain:
        return mcp_error("domain is required")
    if not decision:
        return mcp_error("decision is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.register_decision(
            session_id=session_id,
            project=project,
            domain=domain,
            decision=decision,
            rationale=arguments.get("rationale"),
            goal_id=arguments.get("goal_id"),
            metadata=arguments.get("metadata"),
        )

        lines = [f"Decision #{result['decision_id']} registered for domain '{domain}'."]
        if result.get("superseded"):
            lines.append(f"Superseded: {result['superseded']}")
        if result.get("contradiction_warnings"):
            lines.append("Contradiction warnings:")
            for w in result["contradiction_warnings"]:
                lines.append(f"  - {w}")
        msg = "\n".join(lines)
        _audit_log("decision_register", session_id, msg.split("\n")[0])
        return mcp_response(msg)
    except Exception as e:
        logger.error("decision_register failed: %s", e, exc_info=True)
        return mcp_error(f"Decision registration failed: {e}")


async def handle_decision_query(arguments: dict) -> dict:
    """Query decisions for a project, optionally filtered by domain prefix."""
    project = arguments.get("project", "").strip()
    if not project:
        return mcp_error("project is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        decisions = mgr.query_decisions(
            project=project,
            domain=arguments.get("domain"),
            status=arguments.get("status", "active"),
            goal_id=arguments.get("goal_id"),
            limit=arguments.get("limit", 20),
        )

        if not decisions:
            domain_filter = arguments.get("domain", "all domains")
            return mcp_response(f"No decisions found for {domain_filter} in {project}.")

        lines = [f"{len(decisions)} decision(s):"]
        for d in decisions:
            status_tag = f" [{d['status']}]" if d["status"] != "active" else ""
            lines.append(
                f"  #{d['id']} [{d['domain']}]{status_tag}: {d['decision'][:120]}"
            )
            if d.get("rationale"):
                lines.append(f"    Rationale: {d['rationale'][:100]}")
        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error("decision_query failed: %s", e, exc_info=True)
        return mcp_error(f"Decision query failed: {e}")


async def handle_decision_revoke(arguments: dict) -> dict:
    """Revoke an active decision."""
    decision_id = arguments.get("decision_id")
    session_id = arguments.get("session_id", "").strip()

    if decision_id is None:
        return mcp_error("decision_id is required")
    if not session_id:
        return mcp_error("session_id is required")
    session_id = _validate_session_id(session_id)
    if not session_id:
        return mcp_error("Invalid session_id")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.revoke_decision(
            decision_id=int(decision_id),
            session_id=session_id,
            reason=arguments.get("reason"),
        )

        if result.get("success"):
            msg = f"Decision #{decision_id} revoked."
            _audit_log("decision_revoke", session_id, msg)
            return mcp_response(msg)
        return mcp_error(result.get("error", "Revocation failed"))
    except Exception as e:
        logger.error("decision_revoke failed: %s", e, exc_info=True)
        return mcp_error(f"Decision revocation failed: {e}")


# ============================================================================
# Handler: omega_update_task
# ============================================================================


async def handle_update_task(arguments: dict) -> dict:
    """Update the task description for the current session."""
    session_id = arguments.get("session_id", "").strip()
    task = arguments.get("task", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    if not task:
        return mcp_error("task is required")

    try:
        from omega.coordination import get_manager

        mgr = get_manager()
        result = mgr.update_session_task(session_id, task)

        if result.get("updated"):
            _audit_log("update_task", session_id, f"task: {task[:80]}")
            return mcp_response(f"Task updated: {task[:100]}")
        return mcp_error(result.get("reason", "Update failed"))
    except Exception as e:
        logger.error("update_task failed: %s", e, exc_info=True)
        return mcp_error(f"Update task failed: {e}")


# ============================================================================
# Handler: omega_council
# ============================================================================


async def handle_council(arguments: dict) -> dict:
    """Run a self-audit council analysis."""
    domain = arguments.get("domain", "").strip()
    project = arguments.get("project")

    if domain not in ("platform_health", "security", "innovation"):
        return mcp_error("domain must be: platform_health, security, or innovation")

    try:
        from omega.council import Council

        council = Council(domain=domain)
        signals = council.gather_signals(project=project)
        prompt = council.format_prompt(signals)

        # Store the finding
        try:
            from omega.bridge import auto_capture

            auto_capture(
                content=f"[Council: {domain}] Signals gathered for analysis:\n{json.dumps(signals, default=str)[:2000]}",
                event_type="council_finding",
                metadata={"domain": domain, "project": project or "all"},
                project=project,
            )
        except Exception as e:
            logger.debug("Council auto_capture failed: %s", e)

        return mcp_response(
            f"## Council: {domain}\n\n"
            f"Signals gathered. Use the following prompt with your preferred model "
            f"to generate the analysis:\n\n```\n{prompt[:3000]}\n```\n\n"
            f"After review, store accepted findings with omega_store (event_type='decision') "
            f"or rejected ones with event_type='lesson_learned'."
        )
    except FileNotFoundError:
        return mcp_error(f"No template found for domain '{domain}'. Check config/councils/")
    except Exception as e:
        return mcp_error(f"Council failed: {e}")


# ============================================================================
# Handler Registry
# ============================================================================

COORD_HANDLERS: Dict[str, Any] = {
    "omega_session_register": handle_session_register,
    "omega_session_heartbeat": handle_session_heartbeat,
    "omega_session_deregister": handle_session_deregister,
    "omega_sessions_list": handle_sessions_list,
    "omega_file_claim": handle_file_claim,
    "omega_file_release": handle_file_release,
    "omega_file_check": handle_file_check,
    "omega_branch_claim": handle_branch_claim,
    "omega_branch_release": handle_branch_release,
    "omega_intent_announce": handle_intent_announce,
    "omega_intent_check": handle_intent_check,
    "omega_coord_status": handle_coord_status,
    "omega_session_snapshot": handle_session_snapshot,
    "omega_session_recover": handle_session_recover,
    "omega_task_create": handle_task_create,
    "omega_task_claim": handle_task_claim,
    "omega_task_next": handle_task_next,
    "omega_task_resolve": handle_task_resolve,
    "omega_task_complete": lambda args: handle_task_resolve({**args, "status": "completed"}),  # Alias
    "omega_task_fail": lambda args: handle_task_resolve({**args, "status": "failed"}),  # Alias
    "omega_tasks_list": handle_tasks_list,
    "omega_audit": handle_audit,
    "omega_task_cancel": lambda args: handle_task_resolve({**args, "status": "canceled"}),  # Alias
    "omega_send_message": handle_send_message,
    "omega_inbox": handle_inbox,
    "omega_task_progress": handle_task_progress,
    "omega_find_agents": handle_find_agents,
    "omega_task_deps": handle_task_deps,
    "omega_git_events": handle_git_events,
    "omega_branch_check": handle_branch_check,
    "omega_coord_metrics": handle_coord_metrics,
    "omega_handoff": handle_handoff,
    "omega_action_check": handle_action_check,
    "omega_action_claim": handle_action_claim,
    "omega_action_complete": handle_action_complete,
    "omega_goal": handle_goal,
    "omega_goal_link": handle_goal_link,
    "omega_drift_check": handle_drift_check,
    "omega_smart_route": handle_smart_route,
    "omega_decision_register": handle_decision_register,
    "omega_decision_query": handle_decision_query,
    "omega_decision_revoke": handle_decision_revoke,
    "omega_update_task": handle_update_task,
    "omega_council": handle_council,
}
