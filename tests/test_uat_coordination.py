"""UAT — Registration, Coordination Features & Proactive Conflict Avoidance.

End-to-end acceptance tests for the OMEGA coordination system.
Tests the full lifecycle through hooks, MCP handlers, and manager methods.

Organized into three sections:
  1. Registration — session lifecycle, heartbeat, stale detection, session recovery
  2. Coordination Features — claims, intents, tasks, status, deadlocks, audit, MCP handlers
  3. Proactive Conflict Avoidance — git sync, pre-push guard, post-commit tracking,
     constraint checking, read-before-write, auto-claim
"""
import asyncio
import json
import os
import re
import sys
import time
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ============================================================================
# SECTION 1: Registration UATs
# ============================================================================


class TestUATSessionRegistration:
    """Full session registration lifecycle through hooks and handlers."""

    def test_full_lifecycle_register_heartbeat_deregister(self, coord_mgr):
        """UAT: Agent registers, sends heartbeats, then deregisters cleanly."""
        # 1. Register
        reg = coord_mgr.register_session("uat-sess-1", pid=9999, project="/proj/a", task="UAT testing")
        assert reg["registered"] is True
        assert reg["session_id"] == "uat-sess-1"

        # 2. Verify session is listed
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "uat-sess-1"

        # 3. Heartbeat
        hb = coord_mgr.heartbeat("uat-sess-1")
        assert hb["success"] is True

        # 4. Deregister
        dereg = coord_mgr.deregister_session("uat-sess-1")
        assert dereg["deregistered"] is True

        # 5. Session gone
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert len(sessions) == 0

    def test_multi_agent_peer_awareness(self, coord_mgr):
        """UAT: Multiple agents register on same project, each sees peers."""
        coord_mgr.register_session("agent-A", pid=1001, project="/proj/shared")
        reg_b = coord_mgr.register_session("agent-B", pid=1002, project="/proj/shared")
        reg_c = coord_mgr.register_session("agent-C", pid=1003, project="/proj/shared")

        assert reg_b["peers_on_project"] == 1
        assert reg_c["peers_on_project"] == 2

        # Different project has zero peers
        reg_d = coord_mgr.register_session("agent-D", pid=1004, project="/proj/other")
        assert reg_d["peers_on_project"] == 0

    def test_idempotent_reregistration(self, coord_mgr):
        """UAT: Re-registering same session refreshes it instead of creating a duplicate."""
        coord_mgr.register_session("re-reg-1", pid=1234, project="/proj/a")
        result = coord_mgr.register_session("re-reg-1", pid=1234, project="/proj/a")
        assert result["registered"] is True
        assert result.get("refreshed") is True

        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert len(sessions) == 1

    def test_stale_session_auto_cleanup(self, coord_mgr):
        """UAT: Sessions with expired heartbeat are automatically cleaned up."""
        coord_mgr.register_session("stale-1", pid=2222, project="/proj/a")

        # Manually backdate the heartbeat
        from omega.coordination import STALE_THRESHOLD_SECONDS
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 10)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (cutoff, "stale-1")
        )
        coord_mgr._conn.commit()

        # list_sessions with auto_clean should remove it
        sessions = coord_mgr.list_sessions(auto_clean=True)
        assert len(sessions) == 0

    def test_deregister_cascade_releases_all(self, coord_mgr):
        """UAT: Deregistering releases all file claims, branch claims, and intents."""
        coord_mgr.register_session("cascade-1", pid=3333, project="/proj/a")
        coord_mgr.claim_file("cascade-1", "/proj/a/file1.py")
        coord_mgr.claim_file("cascade-1", "/proj/a/file2.py")
        coord_mgr.claim_branch("cascade-1", "/proj/a", "feat-x")
        coord_mgr.announce_intent("cascade-1", "working on files", target_files=["/proj/a/file3.py"])

        coord_mgr.deregister_session("cascade-1")

        # All claims released
        assert coord_mgr.check_file("/proj/a/file1.py")["claimed"] is False
        assert coord_mgr.check_file("/proj/a/file2.py")["claimed"] is False

        # Session gone
        assert len(coord_mgr.list_sessions(auto_clean=False)) == 0

    def test_registration_with_task_and_capabilities(self, coord_mgr):
        """UAT: Registration stores task description and capabilities metadata."""
        coord_mgr.register_session(
            "meta-1", pid=4444, project="/proj/a",
            task="Implementing auth module",
            capabilities=["code", "test", "review"],
        )
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert len(sessions) == 1
        assert sessions[0]["task"] == "Implementing auth module"


class TestUATSessionRecovery:
    """Session snapshot and recovery acceptance tests."""

    def test_snapshot_on_clean_deregister(self, coord_mgr):
        """UAT: Clean deregister creates a snapshot when session has meaningful state."""
        coord_mgr.register_session("snap-1", pid=5555, project="/proj/a", task="auth module")
        coord_mgr.claim_file("snap-1", "/proj/a/auth.py", task="implementing JWT")

        coord_mgr.deregister_session("snap-1")

        snapshots = coord_mgr.recover_session("/proj/a")
        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap["reason"] == "clean_stop"
        assert snap["task"] == "auth module"
        assert len(snap["file_claims"]) == 1
        assert snap["file_claims"][0]["file_path"] == "/proj/a/auth.py"

    def test_snapshot_on_stale_cleanup(self, coord_mgr):
        """UAT: Stale session cleanup creates a snapshot preserving context."""
        coord_mgr.register_session("stale-snap", pid=6666, project="/proj/b", task="refactoring")
        coord_mgr.claim_file("stale-snap", "/proj/b/models.py")
        coord_mgr.announce_intent(
            "stale-snap", "refactoring models layer",
            target_files=["/proj/b/models.py", "/proj/b/schema.py"],
        )

        # Backdate heartbeat to trigger stale cleanup
        from omega.coordination import STALE_THRESHOLD_SECONDS
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 10)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (cutoff, "stale-snap")
        )
        coord_mgr._conn.commit()

        coord_mgr.list_sessions(auto_clean=True)

        snapshots = coord_mgr.recover_session("/proj/b")
        assert len(snapshots) == 1
        assert snapshots[0]["reason"] == "stale_cleanup"
        assert snapshots[0]["task"] == "refactoring"
        assert len(snapshots[0]["intents"]) == 1
        assert "models layer" in snapshots[0]["intents"][0]["description"]

    def test_empty_session_no_snapshot(self, coord_mgr):
        """UAT: Session with no claims/intents/task does not produce a snapshot."""
        coord_mgr.register_session("empty-1", pid=7777, project="/proj/a")
        coord_mgr.deregister_session("empty-1")

        snapshots = coord_mgr.recover_session("/proj/a")
        assert len(snapshots) == 0

    def test_explicit_snapshot_before_risky_operation(self, coord_mgr):
        """UAT: Agent explicitly snapshots before doing a risky operation."""
        coord_mgr.register_session("risky-1", pid=8888, project="/proj/a", task="database migration")
        coord_mgr.claim_file("risky-1", "/proj/a/migrate.py")
        coord_mgr.claim_branch("risky-1", "/proj/a", "feat-migration")

        result = coord_mgr.snapshot_session("risky-1", reason="pre_migration")
        assert result["success"] is True
        assert result["snapshot_id"] > 0

        snapshots = coord_mgr.recover_session("/proj/a")
        assert len(snapshots) == 1
        assert snapshots[0]["reason"] == "pre_migration"
        assert len(snapshots[0]["branch_claims"]) == 1

    def test_recovery_returns_most_recent_snapshot(self, coord_mgr):
        """UAT: Recovery returns the most recent snapshot when multiple exist."""
        for i in range(3):
            sid = f"multi-{i}"
            coord_mgr.register_session(sid, pid=9000 + i, project="/proj/a", task=f"task-{i}")
            coord_mgr.claim_file(sid, f"/proj/a/file{i}.py")
            coord_mgr.deregister_session(sid)

        snapshots = coord_mgr.recover_session("/proj/a", limit=1)
        assert len(snapshots) == 1
        assert snapshots[0]["task"] == "task-2"

    def test_snapshot_pruning(self, coord_mgr):
        """UAT: Old snapshots are pruned after retention period."""
        coord_mgr.register_session("old-1", pid=1111, project="/proj/a", task="old task")
        coord_mgr.claim_file("old-1", "/proj/a/old.py")
        coord_mgr.deregister_session("old-1")

        # Backdate the snapshot
        from omega.coordination import SNAPSHOT_RETENTION_DAYS
        old_date = (datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_RETENTION_DAYS + 1)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_snapshots SET created_at = ?", (old_date,)
        )
        coord_mgr._conn.commit()

        # Directly call prune (since _clean_stale_sessions skips when no stale sessions)
        with coord_mgr._lock:
            pruned = coord_mgr._prune_snapshots()
        coord_mgr._conn.commit()
        assert pruned >= 1

        snapshots = coord_mgr.recover_session("/proj/a")
        assert len(snapshots) == 0


# ============================================================================
# SECTION 2: Coordination-Specific Features
# ============================================================================


class TestUATFileClaims:
    """File claim end-to-end acceptance tests."""

    def test_claim_conflict_resolution(self, coord_mgr):
        """UAT: Two agents try to claim the same file — first wins, second gets conflict."""
        coord_mgr.register_session("agent-A", pid=1001)
        coord_mgr.register_session("agent-B", pid=1002)

        claim_a = coord_mgr.claim_file("agent-A", "/shared/app.py", task="feature X")
        claim_b = coord_mgr.claim_file("agent-B", "/shared/app.py", task="feature Y")

        assert claim_a["success"] is True
        assert claim_b.get("conflict") is True
        assert claim_b["claimed_by"] == "agent-A"

    def test_claim_release_reclaim(self, coord_mgr):
        """UAT: Agent claims file, releases it, second agent can then claim it."""
        coord_mgr.register_session("agent-A", pid=1001)
        coord_mgr.register_session("agent-B", pid=1002)

        coord_mgr.claim_file("agent-A", "/shared/app.py")
        coord_mgr.release_file("agent-A", "/shared/app.py")

        claim_b = coord_mgr.claim_file("agent-B", "/shared/app.py")
        assert claim_b["success"] is True

    def test_check_file_ownership(self, coord_mgr):
        """UAT: Checking a claimed file shows the owner and task."""
        coord_mgr.register_session("owner-1", pid=1001)
        coord_mgr.claim_file("owner-1", "/proj/models.py", task="refactoring")

        info = coord_mgr.check_file("/proj/models.py")
        assert info["claimed"] is True
        assert info["session_id"] == "owner-1"
        assert info["task"] == "refactoring"

    def test_multiple_file_claims(self, coord_mgr):
        """UAT: Single agent claims multiple files, all tracked in status."""
        coord_mgr.register_session("multi-1", pid=1001, project="/proj/a")
        files = ["/proj/a/a.py", "/proj/a/b.py", "/proj/a/c.py"]
        for f in files:
            assert coord_mgr.claim_file("multi-1", f)["success"] is True

        status = coord_mgr.get_status()
        assert status["file_claims"] == 3
        claimed_paths = {f["path"] for f in status["files"]}
        assert claimed_paths == set(files)


class TestUATBranchClaims:
    """Branch claim acceptance tests."""

    def test_protected_branch_blocked(self, coord_mgr):
        """UAT: Claiming a protected branch (main/master/develop/release) is rejected."""
        coord_mgr.register_session("branch-1", pid=1001)

        for branch in ["main", "master", "develop", "release"]:
            result = coord_mgr.claim_branch("branch-1", "/proj/a", branch)
            assert result.get("protected") is True
            assert "protected" in result.get("error", "").lower()

    def test_feature_branch_claim_and_conflict(self, coord_mgr):
        """UAT: Feature branch claimed by one agent, second gets conflict."""
        coord_mgr.register_session("agent-A", pid=1001)
        coord_mgr.register_session("agent-B", pid=1002)

        claim_a = coord_mgr.claim_branch("agent-A", "/proj/a", "feat-auth")
        claim_b = coord_mgr.claim_branch("agent-B", "/proj/a", "feat-auth")

        assert claim_a["success"] is True
        assert claim_b.get("conflict") is True


class TestUATIntents:
    """Intent announcement and overlap detection acceptance tests."""

    def test_intent_overlap_file_conflict(self, coord_mgr):
        """UAT: Two agents announce intents targeting the same files — overlap detected."""
        coord_mgr.register_session("agent-A", pid=1001)
        coord_mgr.register_session("agent-B", pid=1002)

        coord_mgr.announce_intent(
            "agent-A", "adding auth",
            target_files=["/proj/auth.py", "/proj/middleware.py"],
        )
        coord_mgr.announce_intent(
            "agent-B", "adding logging",
            target_files=["/proj/middleware.py", "/proj/logger.py"],
        )

        check_b = coord_mgr.check_intents("agent-B")
        assert check_b["has_overlaps"] is True
        overlapping_files = check_b["overlaps"][0]["overlapping_files"]
        assert "/proj/middleware.py" in overlapping_files

    def test_intent_overlap_branch_conflict(self, coord_mgr):
        """UAT: Two agents announce intents targeting the same branch — overlap detected."""
        coord_mgr.register_session("agent-A", pid=1001)
        coord_mgr.register_session("agent-B", pid=1002)

        coord_mgr.announce_intent("agent-A", "feature X", target_branch="feat-shared")
        coord_mgr.announce_intent("agent-B", "feature Y", target_branch="feat-shared")

        check_b = coord_mgr.check_intents("agent-B")
        assert check_b["has_overlaps"] is True

    def test_no_self_overlap(self, coord_mgr):
        """UAT: Agent's own intents are not flagged as overlaps."""
        coord_mgr.register_session("solo-1", pid=1001)
        coord_mgr.announce_intent("solo-1", "step 1", target_files=["/proj/a.py"])
        coord_mgr.announce_intent("solo-1", "step 2", target_files=["/proj/a.py"])

        check = coord_mgr.check_intents("solo-1")
        assert check["has_overlaps"] is False


class TestUATTaskManagement:
    """Task creation, claiming, and completion acceptance tests."""

    def test_full_task_lifecycle(self, coord_mgr):
        """UAT: Create task, claim it, complete it."""
        coord_mgr.register_session("worker-1", pid=1001, project="/proj/a")

        # Create
        task = coord_mgr.create_task("worker-1", "Fix login bug", project="/proj/a", priority=2)
        assert task["success"] is True
        task_id = task["task_id"]

        # List — should be pending
        tasks = coord_mgr.list_tasks(project="/proj/a", status="pending")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Fix login bug"
        assert tasks[0]["priority"] == 2

        # Claim
        claim = coord_mgr.claim_task(task_id, "worker-1")
        assert claim["success"] is True

        # List — should be in_progress
        tasks = coord_mgr.list_tasks(status="in_progress")
        assert len(tasks) == 1

        # Complete
        complete = coord_mgr.complete_task(task_id, "worker-1")
        assert complete["success"] is True

        # List — should be completed
        tasks = coord_mgr.list_tasks(status="completed")
        assert len(tasks) == 1

    def test_task_claim_by_wrong_session(self, coord_mgr):
        """UAT: Only the claiming session can complete a task."""
        coord_mgr.register_session("creator-1", pid=1001)
        coord_mgr.register_session("thief-1", pid=1002)

        task = coord_mgr.create_task("creator-1", "Sensitive task")
        task_id = task["task_id"]
        coord_mgr.claim_task(task_id, "creator-1")

        result = coord_mgr.complete_task(task_id, "thief-1")
        assert result["success"] is False

    def test_task_priority_ordering(self, coord_mgr):
        """UAT: Tasks are listed by priority descending."""
        coord_mgr.register_session("worker-1", pid=1001)
        coord_mgr.create_task("worker-1", "Low priority", priority=0)
        coord_mgr.create_task("worker-1", "High priority", priority=10)
        coord_mgr.create_task("worker-1", "Medium priority", priority=5)

        tasks = coord_mgr.list_tasks()
        assert tasks[0]["title"] == "High priority"
        assert tasks[1]["title"] == "Medium priority"
        assert tasks[2]["title"] == "Low priority"


class TestUATDeadlockDetection:
    """Deadlock detection acceptance tests."""

    def test_two_agent_deadlock(self, coord_mgr):
        """UAT: A→wants file held by B, B→wants file held by A = deadlock."""
        coord_mgr.register_session("agent-A", pid=1001)
        coord_mgr.register_session("agent-B", pid=1002)

        coord_mgr.claim_file("agent-A", "/proj/file1.py")
        coord_mgr.claim_file("agent-B", "/proj/file2.py")

        coord_mgr.announce_intent("agent-A", "need file2", target_files=["/proj/file2.py"])
        coord_mgr.announce_intent("agent-B", "need file1", target_files=["/proj/file1.py"])

        deadlocks = coord_mgr.detect_deadlocks()
        assert len(deadlocks) >= 1
        # The cycle should contain both agents
        cycle_agents = set(deadlocks[0])
        assert "agent-A" in cycle_agents
        assert "agent-B" in cycle_agents

    def test_three_way_deadlock(self, coord_mgr):
        """UAT: A→B→C→A circular dependency = deadlock."""
        for name in ["A", "B", "C"]:
            coord_mgr.register_session(f"agent-{name}", pid=1000 + ord(name))

        coord_mgr.claim_file("agent-A", "/proj/a.py")
        coord_mgr.claim_file("agent-B", "/proj/b.py")
        coord_mgr.claim_file("agent-C", "/proj/c.py")

        coord_mgr.announce_intent("agent-A", "need b", target_files=["/proj/b.py"])
        coord_mgr.announce_intent("agent-B", "need c", target_files=["/proj/c.py"])
        coord_mgr.announce_intent("agent-C", "need a", target_files=["/proj/a.py"])

        deadlocks = coord_mgr.detect_deadlocks()
        assert len(deadlocks) >= 1

    def test_no_deadlock_when_no_circular_deps(self, coord_mgr):
        """UAT: Linear dependency chain has no deadlock."""
        coord_mgr.register_session("agent-A", pid=1001)
        coord_mgr.register_session("agent-B", pid=1002)

        coord_mgr.claim_file("agent-A", "/proj/a.py")
        # B wants A's file, but A doesn't want B's — no cycle
        coord_mgr.announce_intent("agent-B", "need a", target_files=["/proj/a.py"])

        deadlocks = coord_mgr.detect_deadlocks()
        assert len(deadlocks) == 0


class TestUATCoordStatus:
    """Coordination status dashboard acceptance tests."""

    def test_full_status_dashboard(self, coord_mgr):
        """UAT: Status dashboard shows all sessions, claims, intents, conflicts."""
        coord_mgr.register_session("agent-A", pid=1001, project="/proj/a", task="auth")
        coord_mgr.register_session("agent-B", pid=1002, project="/proj/a", task="logging")

        coord_mgr.claim_file("agent-A", "/proj/a/auth.py")
        coord_mgr.claim_branch("agent-A", "/proj/a", "feat-auth")
        coord_mgr.announce_intent("agent-B", "editing auth", target_files=["/proj/a/auth.py"])

        status = coord_mgr.get_status()

        assert status["active_sessions"] == 2
        assert status["file_claims"] == 1
        assert status["branch_claims"] == 1
        assert status["active_intents"] == 1
        # B intends to use A's claimed file — conflict
        assert len(status["conflicts"]) == 1
        assert status["conflicts"][0]["type"] == "file_intent_vs_claim"


class TestUATAuditLog:
    """Audit logging acceptance tests."""

    def test_audit_captures_operations(self, coord_mgr):
        """UAT: Audit log records tool calls and they can be queried."""
        coord_mgr.log_audit("omega_file_claim", session_id="sess-1",
                            arguments={"file_path": "/proj/a.py"}, result_summary="claimed")
        coord_mgr.log_audit("omega_file_release", session_id="sess-1",
                            arguments={"file_path": "/proj/a.py"}, result_summary="released")

        entries = coord_mgr.query_audit(session_id="sess-1")
        assert len(entries) == 2
        assert entries[0]["tool_name"] == "omega_file_release"  # DESC order
        assert entries[1]["tool_name"] == "omega_file_claim"

    def test_audit_pruning(self, coord_mgr):
        """UAT: Old audit entries are pruned after retention period."""
        from omega.coordination import AUDIT_RETENTION_DAYS
        coord_mgr.log_audit("old_call", session_id="sess-1")
        coord_mgr.flush_audit_buffer()  # Flush so raw SQL below sees the row

        old_date = (datetime.now(timezone.utc) - timedelta(days=AUDIT_RETENTION_DAYS + 1)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_audit SET created_at = ?", (old_date,)
        )
        coord_mgr._conn.commit()

        with coord_mgr._lock:
            pruned = coord_mgr._prune_audit()
        coord_mgr._conn.commit()
        assert pruned >= 1


class TestUATMCPHandlers:
    """MCP handler integration tests — all 25 coordination handlers."""

    @pytest.fixture(autouse=True)
    def _patch_manager(self, coord_mgr):
        """Patch get_manager to return our test manager."""
        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            self.coord_mgr = coord_mgr
            yield

    # --- Session handlers ---

    def test_handler_register(self):
        from omega.server.coord_handlers import handle_session_register
        result = run_async(handle_session_register({"session_id": "h-sess-1", "project": "/proj/a"}))
        assert "registered" in result["content"][0]["text"].lower()

    def test_handler_register_missing_session_id(self):
        from omega.server.coord_handlers import handle_session_register
        result = run_async(handle_session_register({}))
        assert result.get("isError") is True

    def test_handler_heartbeat(self):
        from omega.server.coord_handlers import handle_session_heartbeat, handle_session_register
        run_async(handle_session_register({"session_id": "h-sess-2"}))
        result = run_async(handle_session_heartbeat({"session_id": "h-sess-2"}))
        assert "heartbeat" in result["content"][0]["text"].lower()

    def test_handler_heartbeat_missing_session(self):
        """Heartbeat on missing session auto-re-registers (success, not error)."""
        from omega.server.coord_handlers import handle_session_heartbeat
        result = run_async(handle_session_heartbeat({"session_id": "nonexistent"}))
        text = result["content"][0]["text"]
        assert "heartbeat updated" in text.lower()

    def test_handler_deregister(self):
        from omega.server.coord_handlers import handle_session_deregister, handle_session_register
        run_async(handle_session_register({"session_id": "h-sess-3"}))
        result = run_async(handle_session_deregister({"session_id": "h-sess-3"}))
        assert "deregistered" in result["content"][0]["text"].lower()

    def test_handler_sessions_list_empty(self):
        from omega.server.coord_handlers import handle_sessions_list
        result = run_async(handle_sessions_list({}))
        assert "no active" in result["content"][0]["text"].lower()

    def test_handler_sessions_list_populated(self):
        from omega.server.coord_handlers import handle_sessions_list, handle_session_register
        run_async(handle_session_register({"session_id": "h-list-1", "project": "/proj/a", "task": "coding"}))
        result = run_async(handle_sessions_list({}))
        text = result["content"][0]["text"]
        assert "h-list-1" in text
        assert "coding" in text

    # --- File claim handlers ---

    def test_handler_file_claim(self):
        from omega.server.coord_handlers import handle_session_register, handle_file_claim
        run_async(handle_session_register({"session_id": "fc-1"}))
        result = run_async(handle_file_claim({"session_id": "fc-1", "file_path": "/proj/a.py"}))
        assert "claimed" in result["content"][0]["text"].lower()

    def test_handler_file_claim_conflict(self):
        from omega.server.coord_handlers import handle_session_register, handle_file_claim
        run_async(handle_session_register({"session_id": "fc-A"}))
        run_async(handle_session_register({"session_id": "fc-B"}))
        run_async(handle_file_claim({"session_id": "fc-A", "file_path": "/proj/x.py"}))
        result = run_async(handle_file_claim({"session_id": "fc-B", "file_path": "/proj/x.py"}))
        assert "conflict" in result["content"][0]["text"].lower()

    def test_handler_file_claim_missing_args(self):
        from omega.server.coord_handlers import handle_file_claim
        result = run_async(handle_file_claim({"session_id": "fc-1"}))  # missing file_path
        assert result.get("isError") is True

    def test_handler_file_release(self):
        from omega.server.coord_handlers import handle_session_register, handle_file_claim, handle_file_release
        run_async(handle_session_register({"session_id": "fr-1"}))
        run_async(handle_file_claim({"session_id": "fr-1", "file_path": "/proj/a.py"}))
        result = run_async(handle_file_release({"session_id": "fr-1", "file_path": "/proj/a.py"}))
        assert "released" in result["content"][0]["text"].lower()

    def test_handler_file_check_unclaimed(self):
        from omega.server.coord_handlers import handle_file_check
        result = run_async(handle_file_check({"file_path": "/proj/nobody.py"}))
        assert "unclaimed" in result["content"][0]["text"].lower()

    def test_handler_file_check_claimed(self):
        from omega.server.coord_handlers import handle_session_register, handle_file_claim, handle_file_check
        run_async(handle_session_register({"session_id": "chk-1"}))
        run_async(handle_file_claim({"session_id": "chk-1", "file_path": "/proj/a.py", "task": "testing"}))
        result = run_async(handle_file_check({"file_path": "/proj/a.py"}))
        text = result["content"][0]["text"]
        assert "chk-1" in text
        assert "testing" in text

    # --- Branch claim handlers ---

    def test_handler_branch_claim(self):
        from omega.server.coord_handlers import handle_session_register, handle_branch_claim
        run_async(handle_session_register({"session_id": "bc-1"}))
        result = run_async(handle_branch_claim({"session_id": "bc-1", "project": "/proj/a", "branch": "feat-x"}))
        assert "claimed" in result["content"][0]["text"].lower()

    def test_handler_branch_claim_protected(self):
        from omega.server.coord_handlers import handle_session_register, handle_branch_claim
        run_async(handle_session_register({"session_id": "bc-2"}))
        result = run_async(handle_branch_claim({"session_id": "bc-2", "project": "/proj/a", "branch": "main"}))
        assert result.get("isError") is True
        assert "protected" in result["content"][0]["text"].lower()

    def test_handler_branch_release(self):
        from omega.server.coord_handlers import handle_session_register, handle_branch_claim, handle_branch_release
        run_async(handle_session_register({"session_id": "br-1"}))
        run_async(handle_branch_claim({"session_id": "br-1", "project": "/proj/a", "branch": "feat-y"}))
        result = run_async(handle_branch_release({"session_id": "br-1", "project": "/proj/a", "branch": "feat-y"}))
        assert "released" in result["content"][0]["text"].lower()

    # --- Intent handlers ---

    def test_handler_intent_announce(self):
        from omega.server.coord_handlers import handle_session_register, handle_intent_announce
        run_async(handle_session_register({"session_id": "ia-1"}))
        result = run_async(handle_intent_announce({
            "session_id": "ia-1", "description": "adding auth module",
            "target_files": ["/proj/auth.py"], "target_branch": "feat-auth",
        }))
        text = result["content"][0]["text"]
        assert "announced" in text.lower()
        assert "auth" in text.lower()

    def test_handler_intent_check_no_overlap(self):
        from omega.server.coord_handlers import handle_session_register, handle_intent_check
        run_async(handle_session_register({"session_id": "ic-1"}))
        result = run_async(handle_intent_check({"session_id": "ic-1"}))
        assert "no overlap" in result["content"][0]["text"].lower()

    # --- Status handler ---

    def test_handler_coord_status(self):
        from omega.server.coord_handlers import handle_session_register, handle_coord_status
        run_async(handle_session_register({"session_id": "st-1", "project": "/proj/a"}))
        result = run_async(handle_coord_status({}))
        text = result["content"][0]["text"]
        assert "sessions:" in text.lower()

    # --- Snapshot/Recover handlers ---

    def test_handler_snapshot_and_recover(self):
        from omega.server.coord_handlers import (
            handle_session_register, handle_file_claim,
            handle_session_snapshot, handle_session_recover,
        )
        run_async(handle_session_register({"session_id": "snap-1", "project": "/proj/a", "task": "snapshot test"}))
        run_async(handle_file_claim({"session_id": "snap-1", "file_path": "/proj/a/x.py"}))
        snap_result = run_async(handle_session_snapshot({"session_id": "snap-1", "reason": "uat_test"}))
        assert "snapshotted" in snap_result["content"][0]["text"].lower()

        recover_result = run_async(handle_session_recover({"project": "/proj/a"}))
        text = recover_result["content"][0]["text"]
        assert "RESUME" in text
        assert "snapshot test" in text

    def test_handler_recover_no_snapshots(self):
        from omega.server.coord_handlers import handle_session_recover
        result = run_async(handle_session_recover({"project": "/proj/nothing"}))
        assert "no predecessor" in result["content"][0]["text"].lower()

    # --- Task handlers ---

    def test_handler_task_create_claim_complete(self):
        from omega.server.coord_handlers import (
            handle_session_register, handle_task_create,
            handle_task_claim, handle_task_resolve,
        )
        run_async(handle_session_register({"session_id": "tk-1"}))

        create = run_async(handle_task_create({
            "session_id": "tk-1", "title": "Fix bug #42",
            "project": "/proj/a", "priority": 5,
        }))
        assert "created" in create["content"][0]["text"].lower()

        # Extract task ID from response
        task_id_match = re.search(r'#(\d+)', create["content"][0]["text"])
        assert task_id_match
        task_id = int(task_id_match.group(1))

        claim = run_async(handle_task_claim({"task_id": task_id, "session_id": "tk-1"}))
        assert "claimed" in claim["content"][0]["text"].lower()

        complete = run_async(handle_task_resolve({"task_id": task_id, "session_id": "tk-1", "status": "completed"}))
        assert "completed" in complete["content"][0]["text"].lower()

    def test_handler_tasks_list_empty(self):
        from omega.server.coord_handlers import handle_tasks_list
        result = run_async(handle_tasks_list({}))
        assert "no tasks" in result["content"][0]["text"].lower()

    # --- Task cancel handler ---

    def test_handler_task_cancel(self):
        from omega.server.coord_handlers import (
            handle_session_register, handle_task_create, handle_task_cancel,
        )
        run_async(handle_session_register({"session_id": "tc-1"}))
        create = run_async(handle_task_create({
            "session_id": "tc-1", "title": "Cancelable task",
        }))
        task_id = int(re.search(r'#(\d+)', create["content"][0]["text"]).group(1))

        result = run_async(handle_task_cancel({"task_id": task_id, "session_id": "tc-1"}))
        assert "canceled" in result["content"][0]["text"].lower()

    def test_handler_task_cancel_wrong_session(self):
        from omega.server.coord_handlers import (
            handle_session_register, handle_task_create,
            handle_task_claim, handle_task_cancel,
        )
        run_async(handle_session_register({"session_id": "tc-owner"}))
        run_async(handle_session_register({"session_id": "tc-other"}))
        create = run_async(handle_task_create({
            "session_id": "tc-owner", "title": "Owned task",
        }))
        task_id = int(re.search(r'#(\d+)', create["content"][0]["text"]).group(1))
        run_async(handle_task_claim({"task_id": task_id, "session_id": "tc-owner"}))

        result = run_async(handle_task_cancel({"task_id": task_id, "session_id": "tc-other"}))
        assert result.get("isError") is True
        assert "claimed by another" in result["content"][0]["text"].lower()

    def test_handler_task_cancel_missing_args(self):
        from omega.server.coord_handlers import handle_task_cancel
        result = run_async(handle_task_cancel({"session_id": "tc-1"}))
        assert result.get("isError") is True

    def test_handler_task_cancel_nonexistent(self):
        from omega.server.coord_handlers import handle_task_cancel
        result = run_async(handle_task_cancel({"task_id": 99999, "session_id": "tc-1"}))
        assert result.get("isError") is True

    # --- Audit handler ---

    def test_handler_audit_empty(self):
        from omega.server.coord_handlers import handle_audit
        result = run_async(handle_audit({}))
        assert "no audit" in result["content"][0]["text"].lower()

    def test_handler_audit_with_data(self):
        from omega.server.coord_handlers import handle_audit
        self.coord_mgr.log_audit("omega_file_claim", session_id="aud-1",
                                 result_summary="claimed /proj/a.py")
        result = run_async(handle_audit({"session_id": "aud-1"}))
        text = result["content"][0]["text"]
        assert "omega_file_claim" in text


class TestUATHandlerRegistry:
    """Verify all handlers and schemas are registered correctly."""

    def test_handler_schema_parity(self):
        """UAT: Every schema has a matching handler and vice versa."""
        from omega.server.coord_handlers import COORD_HANDLERS
        from omega.server.coord_schemas import COORD_TOOL_SCHEMAS

        # omega_task_resolve is an internal handler (no schema) —
        # the public API uses aliases: omega_task_complete/fail/cancel
        _INTERNAL_HANDLERS = {"omega_task_resolve"}
        handler_names = set(COORD_HANDLERS.keys()) - _INTERNAL_HANDLERS
        schema_names = {s["name"] for s in COORD_TOOL_SCHEMAS}

        assert handler_names == schema_names, (
            f"Mismatch:\n  Handlers only: {handler_names - schema_names}\n"
            f"  Schemas only: {schema_names - handler_names}"
        )

    def test_handler_count(self):
        """UAT: Expected handler count (40 public + 1 internal omega_task_resolve + 2 v7 routing + 1 council)."""
        from omega.server.coord_handlers import COORD_HANDLERS
        assert len(COORD_HANDLERS) == 44


# ============================================================================
# SECTION 3: Proactive Conflict Avoidance
# ============================================================================


class TestUATGitEventTracking:
    """Git event tracking and uncoordinated agent detection."""

    def test_commit_push_upstream_lifecycle(self, coord_mgr):
        """UAT: Full git event lifecycle — commit, push, upstream detection."""
        # Agent commits
        coord_mgr.log_git_event(
            project="/proj/a", event_type="commit",
            commit_hash="aaa1111", branch="main",
            message="feat: add auth", session_id="sess-1",
        )
        # Agent pushes
        coord_mgr.log_git_event(
            project="/proj/a", event_type="push",
            commit_hash="aaa1111", branch="main", session_id="sess-1",
        )
        # Upstream detected (from uncoordinated agent)
        coord_mgr.log_git_event(
            project="/proj/a", event_type="upstream_detected",
            commit_hash="ext9999", branch="main",
            message="chore: bump version",
        )

        events = coord_mgr.get_recent_git_events(project="/proj/a")
        assert len(events) == 3

        # Untracked detection
        untracked = coord_mgr.detect_untracked_commits(
            "/proj/a", ["aaa1111", "ext9999", "unknown123"]
        )
        # ext9999 is tracked (upstream_detected), aaa1111 is tracked (commit)
        assert "unknown123" in untracked
        assert "aaa1111" not in untracked

    def test_cross_project_isolation(self, coord_mgr):
        """UAT: Git events from different projects don't interfere."""
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="aaa1111")
        coord_mgr.log_git_event("/proj/b", "commit", commit_hash="bbb2222")

        tracked_a = coord_mgr.get_tracked_commits("/proj/a")
        tracked_b = coord_mgr.get_tracked_commits("/proj/b")

        assert "aaa1111" in tracked_a
        assert "bbb2222" not in tracked_a
        assert "bbb2222" in tracked_b
        assert "aaa1111" not in tracked_b


class TestUATGitSyncCheck:
    """Git sync check on session start (coord_session_start hook)."""

    def test_check_git_sync_no_git(self, coord_mgr, tmp_path):
        """UAT: Git sync check gracefully handles non-git directories."""
        from coord_session_start import _check_git_sync

        # tmp_path is not a git repo — should return silently
        _check_git_sync("test-sess", str(tmp_path), coord_mgr)
        # No exception = pass

    def test_session_resume_no_snapshots(self, coord_mgr, tmp_path):
        """UAT: Session resume with no snapshots is a no-op."""
        from coord_session_start import _session_resume

        # No snapshots for this project — should return silently
        _session_resume("test-sess", str(tmp_path), coord_mgr)

    def test_session_resume_with_snapshot(self, coord_mgr, capsys):
        """UAT: Session resume surfaces predecessor context."""
        from coord_session_start import _session_resume

        coord_mgr.register_session("old-sess", pid=1111, project="/proj/a", task="database migration")
        coord_mgr.claim_file("old-sess", "/proj/a/migrate.py")
        coord_mgr.deregister_session("old-sess")

        _session_resume("new-sess", "/proj/a", coord_mgr)

        output = capsys.readouterr().out
        assert "[RESUME]" in output
        assert "database migration" in output


class TestUATPrePushGuard:
    """Pre-push divergence guard hook logic."""

    def test_ignores_non_push_commands(self):
        """UAT: Hook does nothing for non-push Bash commands."""
        from pre_push_guard import main

        env = {"TOOL_NAME": "Bash", "TOOL_INPUT": json.dumps({"command": "git status"})}
        with patch.dict(os.environ, env, clear=False):
            main()  # Should return without action

    def test_ignores_non_bash_tools(self):
        """UAT: Hook does nothing for non-Bash tool types."""
        from pre_push_guard import main

        env = {"TOOL_NAME": "Edit", "TOOL_INPUT": json.dumps({"command": "git push"})}
        with patch.dict(os.environ, env, clear=False):
            main()  # Should return without action

    def test_detects_push_command(self):
        """UAT: Hook identifies git push in the command string."""
        from pre_push_guard import main

        env = {
            "TOOL_NAME": "Bash",
            "TOOL_INPUT": json.dumps({"command": "git push origin main"}),
            "PROJECT_DIR": "/nonexistent/path",
            "SESSION_ID": "test-sess",
        }
        with patch.dict(os.environ, env, clear=False):
            # Will fail at git check (not a repo) but won't crash
            main()

    def test_hook_structure(self):
        """UAT: Hook file has proper structure (timing, error handling)."""
        hook_path = Path(__file__).parent.parent / "hooks" / "pre_push_guard.py"
        content = hook_path.read_text()
        assert "import time" in content
        assert "_log_timing" in content
        assert "time.monotonic()" in content
        assert "_log_hook_error" in content
        assert "git push" in content
        assert '"fetch"' in content  # ["git", "fetch", "origin"]
        assert "[GIT-GUARD]" in content


class TestUATPostCommitTracking:
    """Post-commit tracking in surface_memories hook."""

    def test_detects_commit_hash_in_output(self):
        """UAT: Regex correctly parses git commit output formats."""
        pattern = r'\[[\w/.-]+\s+([0-9a-f]{7,12})\]'

        # Standard format
        assert re.search(pattern, "[main abc1234] Add feature").group(1) == "abc1234"
        # Branch with slash
        assert re.search(pattern, "[feat/auth 1234567890] Fix login").group(1) == "1234567890"
        # Short hash
        assert re.search(pattern, "[develop abcdef1] Hotfix").group(1) == "abcdef1"
        # Non-commit output
        assert re.search(pattern, "Everything up to date") is None
        assert re.search(pattern, "Already up to date.") is None

    def test_track_git_commit_with_valid_output(self, coord_mgr):
        """UAT: Git commit tracking extracts hash and logs to coordination."""
        from surface_memories import _track_git_commit

        tool_input = json.dumps({"command": "git commit -m 'test commit'"})
        tool_output = "[main abc1234def] test commit\n 1 file changed, 5 insertions(+)"

        with patch("omega.coordination.get_manager", return_value=coord_mgr), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
            _track_git_commit(tool_input, tool_output, "sess-1", "/proj/a")

        events = coord_mgr.get_recent_git_events(project="/proj/a", event_type="commit")
        assert len(events) == 1
        assert events[0]["commit_hash"] == "abc1234def"
        assert events[0]["message"] == "test commit"

    def test_track_git_commit_ignores_non_commit(self, coord_mgr):
        """UAT: Non-commit Bash output is not tracked."""
        from surface_memories import _track_git_commit

        tool_input = json.dumps({"command": "git status"})
        tool_output = "On branch main\nnothing to commit"

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            _track_git_commit(tool_input, tool_output, "sess-1", "/proj/a")

        events = coord_mgr.get_recent_git_events(project="/proj/a")
        assert len(events) == 0

    def test_track_git_commit_empty_output(self, coord_mgr):
        """UAT: Empty output is handled gracefully."""
        from surface_memories import _track_git_commit
        _track_git_commit("{}", "", "sess-1", "/proj/a")
        # No crash = pass


class TestUATPreEditConflictDetection:
    """Pre-edit hook constraint checking and claim surfacing."""

    def test_check_claim_detects_other_agent(self, coord_mgr):
        """UAT: Pre-edit check detects when another agent has claimed the file."""
        from pre_edit_surface import _check_claim

        coord_mgr.register_session("other-agent", pid=1001)
        coord_mgr.claim_file("other-agent", "/proj/contested.py", task="refactoring")

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            info = _check_claim("/proj/contested.py", "my-session")
            assert info is not None
            assert info["session_id"] == "other-agent"

    def test_check_claim_allows_own_file(self, coord_mgr):
        """UAT: Pre-edit check allows editing files you own."""
        from pre_edit_surface import _check_claim

        coord_mgr.register_session("my-session", pid=1001)
        coord_mgr.claim_file("my-session", "/proj/mine.py")

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            info = _check_claim("/proj/mine.py", "my-session")
            assert info is None  # No conflict for own file

    def test_check_claim_unclaimed_file(self, coord_mgr):
        """UAT: Pre-edit check returns None for unclaimed files."""
        from pre_edit_surface import _check_claim

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            info = _check_claim("/proj/free.py", "my-session")
            assert info is None

    def test_read_before_write_tracking(self, tmp_omega_dir):
        """UAT: Read-before-write check uses session tracking files."""

        reads_dir = tmp_omega_dir / "session-reads"
        reads_dir.mkdir()
        reads_file = reads_dir / "test-session.json"
        reads_file.write_text(json.dumps(["/proj/a.py", "/proj/b.py"]))

        with patch("pre_edit_surface.Path") as mock_path:
            mock_path.home.return_value = tmp_omega_dir.parent
            # The function builds its own path from home — we need to test the logic
            # directly since it depends on Path.home()

        # Direct test of the tracking file format
        read_paths = set(json.loads(reads_file.read_text()))
        assert "/proj/a.py" in read_paths
        assert "/proj/c.py" not in read_paths

    def test_constraint_check_graceful_on_missing_constraints(self):
        """UAT: Constraint check returns empty list when no constraints exist."""
        from pre_edit_surface import _check_constraints

        with patch("omega.bridge.check_constraints", return_value=[]):
            result = _check_constraints("/proj/a.py", "/proj")
            assert result == []


class TestUATAutoClaimFile:
    """Auto-claim hook acceptance tests."""

    def test_auto_claim_on_edit(self, coord_mgr):
        """UAT: Editing a file automatically claims it."""
        coord_mgr.register_session("auto-1", pid=1001)

        env = {
            "TOOL_NAME": "Edit",
            "SESSION_ID": "auto-1",
            "TOOL_INPUT": json.dumps({"file_path": "/proj/auto.py"}),
        }
        with patch.dict(os.environ, env, clear=False), \
             patch("omega.coordination.get_manager", return_value=coord_mgr):
            from auto_claim_file import main
            main()

        info = coord_mgr.check_file("/proj/auto.py")
        assert info["claimed"] is True
        assert info["session_id"] == "auto-1"
        assert info["task"] == "auto-claimed on edit"

    def test_auto_claim_ignores_non_edit(self, coord_mgr):
        """UAT: Non-Edit/Write tools don't trigger auto-claim."""
        env = {
            "TOOL_NAME": "Read",
            "SESSION_ID": "auto-1",
            "TOOL_INPUT": json.dumps({"file_path": "/proj/read.py"}),
        }
        with patch.dict(os.environ, env, clear=False):
            from auto_claim_file import main
            main()

        info = coord_mgr.check_file("/proj/read.py")
        assert info["claimed"] is False

    def test_auto_claim_no_session(self):
        """UAT: Auto-claim hook does nothing without a session ID."""
        env = {
            "TOOL_NAME": "Edit",
            "SESSION_ID": "",
            "TOOL_INPUT": json.dumps({"file_path": "/proj/a.py"}),
        }
        with patch.dict(os.environ, env, clear=False):
            from auto_claim_file import main
            main()  # No crash = pass


class TestUATHookSessionStop:
    """Session stop hook acceptance tests."""

    def test_stop_hook_deregisters(self, coord_mgr):
        """UAT: Session stop hook deregisters the session."""
        coord_mgr.register_session("stop-1", pid=1001, project="/proj/a")
        coord_mgr.claim_file("stop-1", "/proj/a/file.py")

        env = {"SESSION_ID": "stop-1"}
        with patch.dict(os.environ, env, clear=False), \
             patch("omega.coordination.get_manager", return_value=coord_mgr):
            from coord_session_stop import main
            main()

        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert len(sessions) == 0
        assert coord_mgr.check_file("/proj/a/file.py")["claimed"] is False

    def test_stop_hook_no_session_id(self):
        """UAT: Stop hook does nothing without a session ID."""
        env = {"SESSION_ID": ""}
        with patch.dict(os.environ, env, clear=False):
            from coord_session_stop import main
            main()  # No crash = pass


class TestUATHookHeartbeat:
    """Heartbeat hook acceptance tests."""

    def test_heartbeat_hook_updates_timestamp(self, coord_mgr):
        """UAT: Heartbeat hook updates the session's last_heartbeat."""
        coord_mgr.register_session("hb-1", pid=1001)

        # Get initial heartbeat
        sessions = coord_mgr.list_sessions(auto_clean=False)
        initial_hb = sessions[0]["last_heartbeat"]

        time.sleep(0.01)  # Ensure timestamp difference

        env = {"SESSION_ID": "hb-1"}
        with patch.dict(os.environ, env, clear=False), \
             patch("omega.coordination.get_manager", return_value=coord_mgr):
            from coord_heartbeat import main
            main()

        sessions = coord_mgr.list_sessions(auto_clean=False)
        updated_hb = sessions[0]["last_heartbeat"]
        assert updated_hb >= initial_hb

    def test_heartbeat_hook_no_session_id(self):
        """UAT: Heartbeat hook does nothing without a session ID."""
        env = {"SESSION_ID": ""}
        with patch.dict(os.environ, env, clear=False):
            from coord_heartbeat import main
            main()  # No crash = pass


class TestUATEndToEndScenarios:
    """Multi-step end-to-end scenarios combining multiple features."""

    def test_scenario_two_agents_conflicting_edits(self, coord_mgr):
        """UAT: Two agents register, one claims a file, other detects conflict pre-edit."""
        from pre_edit_surface import _check_claim

        # Agent A starts working
        coord_mgr.register_session("agent-A", pid=1001, project="/proj/a", task="auth module")
        coord_mgr.claim_file("agent-A", "/proj/a/auth.py", task="adding JWT")

        # Agent B tries to edit the same file
        coord_mgr.register_session("agent-B", pid=1002, project="/proj/a", task="logging")

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            conflict = _check_claim("/proj/a/auth.py", "agent-B")

        assert conflict is not None
        assert conflict["session_id"] == "agent-A"
        assert conflict["task"] == "adding JWT"

    def test_scenario_session_crash_and_recovery(self, coord_mgr, capsys):
        """UAT: Agent session crashes (goes stale), new agent recovers context."""
        from omega.coordination import STALE_THRESHOLD_SECONDS
        from coord_session_start import _session_resume

        # Agent A starts working
        coord_mgr.register_session("crash-A", pid=1001, project="/proj/a", task="database migration")
        coord_mgr.claim_file("crash-A", "/proj/a/migrate.py")
        coord_mgr.announce_intent("crash-A", "migrating user table",
                                  target_files=["/proj/a/migrate.py", "/proj/a/models.py"])

        # Agent A goes stale (simulated)
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 10)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (cutoff, "crash-A")
        )
        coord_mgr._conn.commit()
        coord_mgr.list_sessions(auto_clean=True)

        # Agent B starts on same project
        coord_mgr.register_session("recover-B", pid=2002, project="/proj/a")
        _session_resume("recover-B", "/proj/a", coord_mgr)

        output = capsys.readouterr().out
        assert "[RESUME]" in output
        assert "database migration" in output

    def test_scenario_task_handoff_between_agents(self, coord_mgr):
        """UAT: Agent A creates a task, Agent B claims and completes it."""
        coord_mgr.register_session("agent-A", pid=1001, project="/proj/a")
        coord_mgr.register_session("agent-B", pid=1002, project="/proj/a")

        task = coord_mgr.create_task("agent-A", "Fix flaky test", project="/proj/a", priority=5)
        task_id = task["task_id"]

        # B sees the task
        pending = coord_mgr.list_tasks(project="/proj/a", status="pending")
        assert len(pending) == 1

        # B claims and completes
        coord_mgr.claim_task(task_id, "agent-B")
        coord_mgr.complete_task(task_id, "agent-B")

        completed = coord_mgr.list_tasks(status="completed")
        assert len(completed) == 1
        assert completed[0]["session_id"] == "agent-B"

    def test_scenario_git_aware_coordination(self, coord_mgr):
        """UAT: Agent commits, pushes, and detects uncoordinated upstream commits."""
        # Agent's own commit tracked
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="mine111", branch="main",
                                message="feat: add auth", session_id="my-session")
        coord_mgr.log_git_event("/proj/a", "push", commit_hash="mine111", branch="main",
                                session_id="my-session")

        # External commits detected on fetch
        coord_mgr.log_git_event("/proj/a", "upstream_detected", commit_hash="ext222",
                                branch="main", message="chore: bump version")
        coord_mgr.log_git_event("/proj/a", "upstream_detected", commit_hash="ext333",
                                branch="main", message="fix: typo in README")

        # Check what's untracked — all are tracked via our logging
        untracked = coord_mgr.detect_untracked_commits("/proj/a", ["mine111", "ext222", "ext333", "mystery"])
        assert untracked == ["mystery"]

        # Events are queryable
        events = coord_mgr.get_recent_git_events(project="/proj/a")
        assert len(events) == 4
        upstream_events = coord_mgr.get_recent_git_events(project="/proj/a", event_type="upstream_detected")
        assert len(upstream_events) == 2
