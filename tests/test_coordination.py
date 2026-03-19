"""Tests for OMEGA Coordination Layer — multi-agent awareness."""
import os
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone


class TestSessionLifecycle:
    """Session register/deregister/heartbeat tests."""

    def test_register_session(self, coord_mgr):
        result = coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        assert result["registered"] is True
        assert result["session_id"] == "sess-1"
        assert result["peers_on_project"] == 0

    def test_register_idempotent(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        result = coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        assert result["registered"] is True
        assert result.get("refreshed") is True

    def test_register_shows_peers(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        result = coord_mgr.register_session("sess-2", pid=5678, project="/proj/a")
        assert result["peers_on_project"] == 1

    def test_heartbeat(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.heartbeat("sess-1")
        assert result["success"] is True
        assert "timestamp" in result

    def test_heartbeat_nonexistent(self, coord_mgr):
        result = coord_mgr.heartbeat("nonexistent")
        assert result["success"] is True
        assert result.get("reregistered") is True

    def test_deregister(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.deregister_session("sess-1")
        assert result["deregistered"] is True

    def test_deregister_nonexistent(self, coord_mgr):
        result = coord_mgr.deregister_session("nonexistent")
        assert result["deregistered"] is False

    def test_deregister_releases_claims(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_file("sess-1", "/foo/bar.py")
        coord_mgr.claim_branch("sess-1", "/proj", "feat-1")

        coord_mgr.deregister_session("sess-1")

        # File should be free
        assert coord_mgr.check_file("/foo/bar.py")["claimed"] is False
        # Session gone from list
        assert len(coord_mgr.list_sessions(auto_clean=False)) == 0

    def test_list_sessions(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.register_session("sess-2", pid=5678, project="/proj/b")
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert len(sessions) == 2
        sids = {s["session_id"] for s in sessions}
        assert sids == {"sess-1", "sess-2"}


class TestWorktreePeerDiscovery:
    """Worktree-aware peer discovery via repo_root in metadata."""

    def test_same_repo_root_detected_as_peers(self, coord_mgr):
        """Agents in different worktrees of the same repo should see each other."""
        repo_root = "/Users/test/Projects/omega"
        coord_mgr.register_session(
            "agent-main", pid=100, project=repo_root,
            metadata={"repo_root": repo_root},
        )
        result = coord_mgr.register_session(
            "agent-worktree", pid=200,
            project="/tmp/worktrees/omega-feature-x",
            metadata={"repo_root": repo_root},
        )
        assert result["peers_on_project"] == 1

    def test_different_repos_not_peers(self, coord_mgr):
        """Agents on different repos should NOT see each other as peers."""
        coord_mgr.register_session(
            "agent-a", pid=100, project="/proj/alpha",
            metadata={"repo_root": "/proj/alpha"},
        )
        result = coord_mgr.register_session(
            "agent-b", pid=200, project="/proj/beta",
            metadata={"repo_root": "/proj/beta"},
        )
        assert result["peers_on_project"] == 0

    def test_worktree_file_claims_independent(self, coord_mgr):
        """File claims in different worktrees should NOT conflict (different abs paths)."""
        repo_root = "/Users/test/Projects/omega"
        coord_mgr.register_session(
            "agent-main", pid=100, project=repo_root,
            metadata={"repo_root": repo_root},
        )
        coord_mgr.register_session(
            "agent-wt", pid=200,
            project="/tmp/worktrees/omega-feat",
            metadata={"repo_root": repo_root},
        )
        r1 = coord_mgr.claim_file("agent-main", f"{repo_root}/src/foo.py")
        assert r1["success"] is True
        # Same logical file, different abs path -- no conflict
        r2 = coord_mgr.claim_file("agent-wt", "/tmp/worktrees/omega-feat/src/foo.py")
        assert r2["success"] is True
        assert r2.get("conflict") is not True

    def test_repo_root_stored_in_metadata(self, coord_mgr):
        """register_session should store repo_root in session metadata."""
        coord_mgr.register_session(
            "sess-meta", pid=100, project="/proj/a",
            metadata={"repo_root": "/proj/a", "extra": "kept"},
        )
        sessions = coord_mgr.list_sessions(auto_clean=False)
        sess = [s for s in sessions if s["session_id"] == "sess-meta"][0]
        assert sess["metadata"]["repo_root"] == "/proj/a"
        assert sess["metadata"]["extra"] == "kept"

    def test_no_repo_root_falls_back_to_project_match(self, coord_mgr):
        """Without repo_root, peer matching should still work via project path."""
        coord_mgr.register_session("sess-1", pid=100, project="/proj/a")
        result = coord_mgr.register_session("sess-2", pid=200, project="/proj/a")
        assert result["peers_on_project"] == 1


class TestFileClaims:
    """File claim/release/conflict tests."""

    def test_claim_file(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.claim_file("sess-1", "/proj/foo.py", task="editing")
        assert result["success"] is True

    def test_claim_file_auto_registers(self, coord_mgr):
        """Claiming a file with an unregistered session auto-registers it."""
        result = coord_mgr.claim_file("unregistered", "/proj/foo.py")
        assert result["success"] is True
        # Session should now be registered
        sessions = coord_mgr.list_sessions(auto_clean=False)
        sids = {s["session_id"] for s in sessions}
        assert "unregistered" in sids

    def test_claim_conflict(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.claim_file("sess-1", "/proj/foo.py", task="editing")
        result = coord_mgr.claim_file("sess-2", "/proj/foo.py", task="also editing")

        assert result["success"] is False
        assert result["conflict"] is True
        assert result["claimed_by"] == "sess-1"

    def test_claim_refresh_own(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_file("sess-1", "/proj/foo.py")
        result = coord_mgr.claim_file("sess-1", "/proj/foo.py")
        assert result["success"] is True
        assert result.get("refreshed") is True

    def test_release_file(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_file("sess-1", "/proj/foo.py")
        result = coord_mgr.release_file("sess-1", "/proj/foo.py")
        assert result["released"] is True

        # Now another session can claim it
        coord_mgr.register_session("sess-2", pid=5678)
        result = coord_mgr.claim_file("sess-2", "/proj/foo.py")
        assert result["success"] is True

    def test_release_wrong_session(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        coord_mgr.claim_file("sess-1", "/proj/foo.py")

        result = coord_mgr.release_file("sess-2", "/proj/foo.py")
        assert result["released"] is False

    def test_check_file_unclaimed(self, coord_mgr):
        result = coord_mgr.check_file("/proj/foo.py")
        assert result["claimed"] is False

    def test_check_file_claimed(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_file("sess-1", "/proj/foo.py", task="editing")
        result = coord_mgr.check_file("/proj/foo.py")
        assert result["claimed"] is True
        assert result["session_id"] == "sess-1"
        assert result["task"] == "editing"


class TestBranchClaims:
    """Branch claim/release/protection tests."""

    def test_claim_branch(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.claim_branch("sess-1", "/proj", "feat-auth")
        assert result["success"] is True

    def test_protected_branch_main(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.claim_branch("sess-1", "/proj", "main")
        assert result["success"] is False
        assert result.get("protected") is True

    def test_protected_branch_master(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.claim_branch("sess-1", "/proj", "master")
        assert result["success"] is False
        assert result.get("protected") is True

    def test_protected_branch_develop(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.claim_branch("sess-1", "/proj", "develop")
        assert result["success"] is False

    def test_protected_branch_release(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.claim_branch("sess-1", "/proj", "release")
        assert result["success"] is False

    def test_branch_conflict(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.claim_branch("sess-1", "/proj", "feat-auth")
        result = coord_mgr.claim_branch("sess-2", "/proj", "feat-auth")

        assert result["success"] is False
        assert result["conflict"] is True
        assert result["claimed_by"] == "sess-1"

    def test_branch_refresh_own(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_branch("sess-1", "/proj", "feat-auth")
        result = coord_mgr.claim_branch("sess-1", "/proj", "feat-auth")
        assert result["success"] is True
        assert result.get("refreshed") is True

    def test_release_branch(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_branch("sess-1", "/proj", "feat-auth")
        result = coord_mgr.release_branch("sess-1", "/proj", "feat-auth")
        assert result["released"] is True

    def test_branch_auto_registers(self, coord_mgr):
        """Claiming a branch with an unregistered session auto-registers it."""
        result = coord_mgr.claim_branch("unregistered", "/proj", "feat-x")
        assert result["success"] is True
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert any(s["session_id"] == "unregistered" for s in sessions)


class TestIntents:
    """Intent announce/check tests."""

    def test_announce_intent(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.announce_intent(
            "sess-1", "refactoring auth module",
            target_files=["/proj/auth.py", "/proj/login.py"],
            target_branch="feat-auth",
        )
        assert result["success"] is True

    def test_announce_auto_registers(self, coord_mgr):
        """Announcing intent with an unregistered session auto-registers it."""
        result = coord_mgr.announce_intent("unregistered", "some work")
        assert result["success"] is True
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert any(s["session_id"] == "unregistered" for s in sessions)

    def test_check_no_overlap(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.announce_intent("sess-1", "auth work", target_files=["/proj/auth.py"])
        coord_mgr.announce_intent("sess-2", "ui work", target_files=["/proj/ui.py"])

        result = coord_mgr.check_intents("sess-1")
        assert result["has_overlaps"] is False

    def test_check_file_overlap(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.announce_intent("sess-1", "auth work", target_files=["/proj/auth.py", "/proj/shared.py"])
        coord_mgr.announce_intent("sess-2", "config work", target_files=["/proj/shared.py", "/proj/config.py"])

        result = coord_mgr.check_intents("sess-1")
        assert result["has_overlaps"] is True
        assert len(result["overlaps"]) == 1
        assert "/proj/shared.py" in result["overlaps"][0]["overlapping_files"]

    def test_check_branch_overlap(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.announce_intent("sess-1", "auth work", target_branch="feat-x")
        coord_mgr.announce_intent("sess-2", "other work", target_branch="feat-x")

        result = coord_mgr.check_intents("sess-1")
        assert result["has_overlaps"] is True
        assert "feat-x" in result["overlaps"][0]["overlapping_branches"]


class TestStaleCleanup:
    """Stale session detection and CASCADE cleanup."""

    def test_stale_cleanup(self, coord_mgr):
        from omega.coordination import STALE_THRESHOLD_SECONDS

        # Register session with a stale heartbeat
        coord_mgr.register_session("stale-sess", pid=1111)
        coord_mgr.claim_file("stale-sess", "/proj/foo.py")

        # Manually backdate the heartbeat
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "stale-sess")
        )
        coord_mgr._conn.commit()

        # list_sessions with auto_clean should remove it
        sessions = coord_mgr.list_sessions(auto_clean=True)
        assert len(sessions) == 0

        # File claim should be CASCADE-deleted
        assert coord_mgr.check_file("/proj/foo.py")["claimed"] is False

    def test_stale_does_not_affect_fresh(self, coord_mgr):
        from omega.coordination import STALE_THRESHOLD_SECONDS

        coord_mgr.register_session("fresh", pid=1111)
        coord_mgr.register_session("stale", pid=2222)

        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "stale")
        )
        coord_mgr._conn.commit()

        sessions = coord_mgr.list_sessions(auto_clean=True)
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "fresh"


class TestCoordStatus:
    """Status dashboard tests."""

    def test_empty_status(self, coord_mgr):
        status = coord_mgr.get_status()
        assert status["active_sessions"] == 0
        assert status["file_claims"] == 0
        assert status["branch_claims"] == 0

    def test_status_with_data(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj", task="coding")
        coord_mgr.claim_file("sess-1", "/proj/foo.py", task="editing")
        coord_mgr.claim_branch("sess-1", "/proj", "feat-x", task="feature work")

        status = coord_mgr.get_status()
        assert status["active_sessions"] == 1
        assert status["file_claims"] == 1
        assert status["branch_claims"] == 1

    def test_status_detects_conflicts(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.claim_file("sess-1", "/proj/foo.py")
        coord_mgr.announce_intent("sess-2", "editing foo", target_files=["/proj/foo.py"])

        status = coord_mgr.get_status()
        assert len(status["conflicts"]) == 1
        assert status["conflicts"][0]["type"] == "file_intent_vs_claim"


class TestSessionSnapshots:
    """Session recovery: snapshot/recover lifecycle."""

    def test_deregister_creates_snapshot(self, coord_mgr):
        """Deregistering a session with claims creates a snapshot."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a", task="coding auth")
        coord_mgr.claim_file("sess-1", "/proj/a/auth.py", task="editing")
        coord_mgr.claim_branch("sess-1", "/proj/a", "feat-auth", task="feature work")

        coord_mgr.deregister_session("sess-1")

        snapshots = coord_mgr.recover_session("/proj/a")
        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap["session_id"] == "sess-1"
        assert snap["project"] == "/proj/a"
        assert snap["task"] == "coding auth"
        assert snap["reason"] == "clean_stop"
        assert len(snap["file_claims"]) == 1
        assert snap["file_claims"][0]["file_path"] == "/proj/a/auth.py"
        assert len(snap["branch_claims"]) == 1
        assert snap["branch_claims"][0]["branch"] == "feat-auth"

    def test_stale_cleanup_creates_snapshot(self, coord_mgr):
        """Stale session cleanup snapshots before CASCADE delete."""
        from omega.coordination import STALE_THRESHOLD_SECONDS

        coord_mgr.register_session("stale-1", pid=1111, project="/proj/b", task="refactoring")
        coord_mgr.claim_file("stale-1", "/proj/b/models.py", task="editing models")

        # Backdate heartbeat to make it stale
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "stale-1")
        )
        coord_mgr._conn.commit()

        # Trigger stale cleanup
        coord_mgr.list_sessions(auto_clean=True)

        # Session should be gone but snapshot should exist
        assert len(coord_mgr.list_sessions(auto_clean=False)) == 0
        snapshots = coord_mgr.recover_session("/proj/b")
        assert len(snapshots) == 1
        assert snapshots[0]["reason"] == "stale_cleanup"
        assert snapshots[0]["task"] == "refactoring"
        assert len(snapshots[0]["file_claims"]) == 1

    def test_empty_session_no_snapshot(self, coord_mgr):
        """Sessions with no claims/intents/task produce no snapshot."""
        coord_mgr.register_session("empty-sess", pid=1234, project="/proj/c")
        coord_mgr.deregister_session("empty-sess")

        snapshots = coord_mgr.recover_session("/proj/c")
        assert len(snapshots) == 0

    def test_task_only_creates_snapshot(self, coord_mgr):
        """Session with a task but no claims still gets snapshotted."""
        coord_mgr.register_session("task-sess", pid=1234, project="/proj/d", task="investigating bug")
        coord_mgr.deregister_session("task-sess")

        snapshots = coord_mgr.recover_session("/proj/d")
        assert len(snapshots) == 1
        assert snapshots[0]["task"] == "investigating bug"

    def test_explicit_snapshot(self, coord_mgr):
        """Manual snapshot via public API."""
        coord_mgr.register_session("sess-x", pid=1234, project="/proj/e", task="deploying")
        coord_mgr.claim_file("sess-x", "/proj/e/deploy.py")

        result = coord_mgr.snapshot_session("sess-x", reason="pre-deploy")
        assert result["success"] is True
        assert result["reason"] == "pre-deploy"
        assert "snapshot_id" in result

        # Session still exists (snapshot doesn't delete it)
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert len(sessions) == 1

    def test_snapshot_nonexistent_session(self, coord_mgr):
        """Snapshotting a nonexistent session returns failure."""
        result = coord_mgr.snapshot_session("nonexistent")
        assert result["success"] is False

    def test_recover_no_snapshots(self, coord_mgr):
        """Recovering from a project with no snapshots returns empty list."""
        snapshots = coord_mgr.recover_session("/proj/nowhere")
        assert snapshots == []

    def test_recover_returns_most_recent(self, coord_mgr):
        """Multiple snapshots — recover returns the most recent first."""
        coord_mgr.register_session("sess-old", pid=1111, project="/proj/f", task="old task")
        coord_mgr.claim_file("sess-old", "/proj/f/old.py")
        coord_mgr.deregister_session("sess-old")

        coord_mgr.register_session("sess-new", pid=2222, project="/proj/f", task="new task")
        coord_mgr.claim_file("sess-new", "/proj/f/new.py")
        coord_mgr.deregister_session("sess-new")

        snapshots = coord_mgr.recover_session("/proj/f", limit=2)
        assert len(snapshots) == 2
        assert snapshots[0]["task"] == "new task"
        assert snapshots[1]["task"] == "old task"

    def test_prune_snapshots(self, coord_mgr):
        """Old snapshots are pruned during stale cleanup."""
        from omega.coordination import SNAPSHOT_RETENTION_DAYS

        # Create a snapshot by deregistering
        coord_mgr.register_session("sess-prune", pid=1234, project="/proj/g", task="old work")
        coord_mgr.claim_file("sess-prune", "/proj/g/file.py")
        coord_mgr.deregister_session("sess-prune")

        # Backdate the snapshot beyond retention
        old_time = (datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_RETENTION_DAYS + 1)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_snapshots SET created_at = ? WHERE project = ?",
            (old_time, "/proj/g")
        )
        coord_mgr._conn.commit()

        # Register and make a stale session to trigger cleanup (which prunes)
        from omega.coordination import STALE_THRESHOLD_SECONDS
        coord_mgr.register_session("trigger", pid=9999, project="/proj/g", task="trigger")
        coord_mgr.claim_file("trigger", "/proj/g/trigger.py")
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "trigger")
        )
        coord_mgr._conn.commit()

        coord_mgr.list_sessions(auto_clean=True)

        # Old snapshot should be pruned, new one (from trigger cleanup) should exist
        snapshots = coord_mgr.recover_session("/proj/g", limit=10)
        for s in snapshots:
            assert s["task"] != "old work"

    def test_snapshot_with_intents(self, coord_mgr):
        """Snapshot captures intents."""
        coord_mgr.register_session("sess-int", pid=1234, project="/proj/h", task="intent work")
        coord_mgr.announce_intent(
            "sess-int", "refactor models",
            target_files=["/proj/h/models.py", "/proj/h/views.py"],
            target_branch="feat-refactor",
        )
        coord_mgr.deregister_session("sess-int")

        snapshots = coord_mgr.recover_session("/proj/h")
        assert len(snapshots) == 1
        assert len(snapshots[0]["intents"]) == 1
        intent = snapshots[0]["intents"][0]
        assert intent["description"] == "refactor models"
        assert "/proj/h/models.py" in intent["target_files"]
        assert intent["target_branch"] == "feat-refactor"


class TestTaskManagement:
    """Task create/claim/complete lifecycle."""

    def test_create_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.create_task(
            created_by="sess-1", title="Fix login bug",
            description="The login form crashes on empty email",
            project="/proj/a", priority=2,
        )
        assert result["success"] is True
        assert "task_id" in result

    def test_claim_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Write tests")
        task_id = t["task_id"]

        result = coord_mgr.claim_task(task_id, "sess-2")
        assert result["success"] is True

        # Verify it's now in_progress
        tasks = coord_mgr.list_tasks(status="in_progress")
        assert len(tasks) == 1
        assert tasks[0]["session_id"] == "sess-2"

    def test_claim_already_claimed(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Task X")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.claim_task(t["task_id"], "sess-2")
        assert result["success"] is False
        assert "not 'pending'" in result["error"]

    def test_complete_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Deploy")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.complete_task(t["task_id"], "sess-1")
        assert result["success"] is True

        tasks = coord_mgr.list_tasks(status="completed")
        assert len(tasks) == 1
        assert tasks[0]["completed_at"] is not None

    def test_complete_wrong_session(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Task Y")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.complete_task(t["task_id"], "sess-2")
        assert result["success"] is False
        assert "another session" in result["error"]

    def test_complete_unclaimed_task(self, coord_mgr):
        """An unclaimed task can be completed by its creator."""
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Quick fix")

        result = coord_mgr.complete_task(t["task_id"], "sess-1")
        assert result["success"] is True

    def test_complete_unclaimed_task_wrong_session(self, coord_mgr):
        """A non-creator session cannot complete an unclaimed task."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Quick fix")

        result = coord_mgr.complete_task(t["task_id"], "sess-2")
        assert result["success"] is False
        assert "unclaimed" in result["error"].lower()

    def test_complete_unclaimed_task_by_creator(self, coord_mgr):
        """Creator can complete their own unclaimed task (quick-task workflow)."""
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Quick fix")

        result = coord_mgr.complete_task(t["task_id"], "sess-1", result="Done fast")
        assert result["success"] is True
        assert result["task_id"] == t["task_id"]

    def test_list_tasks_filters(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(created_by="sess-1", title="Task A", project="/proj/a")
        coord_mgr.create_task(created_by="sess-1", title="Task B", project="/proj/b")

        all_tasks = coord_mgr.list_tasks()
        assert len(all_tasks) == 2

        filtered = coord_mgr.list_tasks(project="/proj/a")
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Task A"

    def test_list_tasks_priority_order(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(created_by="sess-1", title="Low", priority=0)
        coord_mgr.create_task(created_by="sess-1", title="High", priority=10)
        coord_mgr.create_task(created_by="sess-1", title="Medium", priority=5)

        tasks = coord_mgr.list_tasks()
        assert tasks[0]["title"] == "High"
        assert tasks[1]["title"] == "Medium"
        assert tasks[2]["title"] == "Low"

    def test_task_not_found(self, coord_mgr):
        result = coord_mgr.claim_task(999, "sess-1")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_complete_already_completed(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Done")
        coord_mgr.complete_task(t["task_id"], "sess-1")

        result = coord_mgr.complete_task(t["task_id"], "sess-1")
        assert result["success"] is False
        assert "already completed" in result["error"]


class TestFindSimilarTasks:
    """find_similar_tasks() — detect overlapping tasks before creation."""

    def test_find_similar_basic(self, coord_mgr):
        """Finds tasks with overlapping keywords."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(
            created_by="sess-1", title="Draft RAAIS grant application",
            project="/proj/a",
        )
        similar = coord_mgr.find_similar_tasks("Write RAAIS grant proposal", project="/proj/a")
        assert len(similar) == 1
        assert "raais" in similar[0]["overlap_keywords"]
        assert "grant" in similar[0]["overlap_keywords"]

    def test_find_similar_no_overlap(self, coord_mgr):
        """No results when titles are completely different."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(
            created_by="sess-1", title="Deploy website to production",
        )
        similar = coord_mgr.find_similar_tasks("Fix login bug in auth module")
        assert len(similar) == 0

    def test_find_similar_ignores_completed(self, coord_mgr):
        """Completed tasks are excluded by default."""
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(
            created_by="sess-1", title="Draft RAAIS grant application",
        )
        coord_mgr.complete_task(t["task_id"], "sess-1")

        similar = coord_mgr.find_similar_tasks("Write RAAIS grant proposal")
        assert len(similar) == 0

    def test_find_similar_project_filter(self, coord_mgr):
        """Project filter narrows results."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(
            created_by="sess-1", title="Draft RAAIS grant application",
            project="/proj/a",
        )
        # Different project should not match
        similar = coord_mgr.find_similar_tasks(
            "Draft RAAIS grant proposal", project="/proj/b",
        )
        assert len(similar) == 0

    def test_find_similar_returns_owner_info(self, coord_mgr):
        """Result includes session owner and similarity score."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(
            created_by="sess-1", title="Implement authentication system",
        )
        coord_mgr.claim_task(t["task_id"], "sess-2")

        similar = coord_mgr.find_similar_tasks("Build authentication system")
        assert len(similar) == 1
        assert similar[0]["session_id"] == "sess-2"
        assert similar[0]["similarity"] > 0
        assert "authentication" in similar[0]["overlap_keywords"]
        assert "system" in similar[0]["overlap_keywords"]

    def test_find_similar_empty_title(self, coord_mgr):
        """Empty or stop-word-only titles return nothing."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(created_by="sess-1", title="Fix the bug")

        similar = coord_mgr.find_similar_tasks("the and for")
        assert len(similar) == 0

    def test_find_similar_low_jaccard_excluded(self, coord_mgr):
        """Tasks with < 30% Jaccard similarity are excluded."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(
            created_by="sess-1",
            title="Deploy website staging environment configuration pipeline",
        )
        # Only "website" overlaps out of many words: low Jaccard
        similar = coord_mgr.find_similar_tasks("website")
        assert len(similar) == 0


class TestNextTask:
    """next_task() — find and auto-claim highest-priority unblocked pending task."""

    def test_next_task_basic(self, coord_mgr):
        """next_task claims the highest-priority pending task."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(created_by="sess-1", title="Low priority", priority=1)
        coord_mgr.create_task(created_by="sess-1", title="High priority", priority=10)

        result = coord_mgr.next_task("sess-1")
        assert result["success"] is True
        assert result["title"] == "High priority"
        assert result["priority"] == 10

        # Verify it's claimed (in_progress)
        tasks = coord_mgr.list_tasks(status="in_progress")
        assert len(tasks) == 1
        assert tasks[0]["session_id"] == "sess-1"

    def test_next_task_no_tasks(self, coord_mgr):
        """next_task returns message when no tasks available."""
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.next_task("sess-1")
        assert result["success"] is False
        assert "No claimable" in result["message"]

    def test_next_task_skips_blocked(self, coord_mgr):
        """next_task should skip tasks blocked by incomplete dependencies."""
        coord_mgr.register_session("sess-1", pid=1234)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Build first", priority=1)
        coord_mgr.create_task(
            created_by="sess-1", title="Test after build", priority=10,
            depends_on=[t1["task_id"]],
        )

        # next_task should pick "Build first" (unblocked) not "Test after build" (blocked, higher priority)
        result = coord_mgr.next_task("sess-1")
        assert result["success"] is True
        assert result["title"] == "Build first"

    def test_next_task_project_filter(self, coord_mgr):
        """next_task should filter by project when provided."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.create_task(created_by="sess-1", title="Task A", project="/proj/a", priority=5)
        coord_mgr.create_task(created_by="sess-1", title="Task B", project="/proj/b", priority=10)

        result = coord_mgr.next_task("sess-1", project="/proj/a")
        assert result["success"] is True
        assert result["title"] == "Task A"

    def test_next_task_skips_already_claimed(self, coord_mgr):
        """next_task should not return already-claimed tasks."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Claimed task", priority=10)
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.next_task("sess-2")
        assert result["success"] is False

    def test_next_task_preserves_progress(self, coord_mgr):
        """next_task should return progress from previously reassigned tasks."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Resumed task")
        coord_mgr.claim_task(t["task_id"], "sess-1")
        coord_mgr.update_task_progress(t["task_id"], "sess-1", 42)

        # Reassign (simulates session death)
        coord_mgr.reassign_orphaned_tasks("sess-1")

        result = coord_mgr.next_task("sess-2")
        assert result["success"] is True
        assert result["title"] == "Resumed task"
        assert result["progress"] == 42


class TestReassignOrphanedTasks:
    """reassign_orphaned_tasks() — return incomplete work to the queue."""

    def test_reassign_in_progress_tasks(self, coord_mgr):
        """In-progress tasks should be reset to pending."""
        coord_mgr.register_session("sess-1", pid=1234)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Task 1")
        t2 = coord_mgr.create_task(created_by="sess-1", title="Task 2")
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.claim_task(t2["task_id"], "sess-1")
        coord_mgr.update_task_progress(t1["task_id"], "sess-1", 50)

        reassigned = coord_mgr.reassign_orphaned_tasks("sess-1")
        assert len(reassigned) == 2
        assert reassigned[0]["progress"] == 50

        # Verify tasks are pending again
        pending = coord_mgr.list_tasks(status="pending")
        assert len(pending) == 2
        for t in pending:
            assert t["session_id"] is None

    def test_reassign_no_tasks(self, coord_mgr):
        """No tasks to reassign returns empty list."""
        result = coord_mgr.reassign_orphaned_tasks("nonexistent")
        assert result == []

    def test_reassign_ignores_completed(self, coord_mgr):
        """Completed tasks should not be reassigned."""
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Done task")
        coord_mgr.claim_task(t["task_id"], "sess-1")
        coord_mgr.complete_task(t["task_id"], "sess-1")

        reassigned = coord_mgr.reassign_orphaned_tasks("sess-1")
        assert reassigned == []

    def test_reassign_preserves_progress(self, coord_mgr):
        """Progress should be preserved after reassignment."""
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Partial work")
        coord_mgr.claim_task(t["task_id"], "sess-1")
        coord_mgr.update_task_progress(t["task_id"], "sess-1", 75)

        reassigned = coord_mgr.reassign_orphaned_tasks("sess-1")
        assert len(reassigned) == 1
        assert reassigned[0]["progress"] == 75

        # Progress preserved in DB
        tasks = coord_mgr.list_tasks(status="pending")
        assert tasks[0]["progress"] == 75


class TestDeadlockDetection:
    """Deadlock (circular wait-for) detection."""

    def test_no_deadlock(self, coord_mgr):
        """Two sessions with no circular dependency."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.claim_file("sess-1", "/proj/a.py")
        coord_mgr.announce_intent("sess-2", "work on b", target_files=["/proj/b.py"])

        deadlocks = coord_mgr.detect_deadlocks()
        assert deadlocks == []

    def test_simple_deadlock(self, coord_mgr):
        """A holds X, wants Y. B holds Y, wants X. Classic deadlock."""
        coord_mgr.register_session("sess-A", pid=1111)
        coord_mgr.register_session("sess-B", pid=2222)

        # A holds X
        coord_mgr.claim_file("sess-A", "/proj/x.py")
        # B holds Y
        coord_mgr.claim_file("sess-B", "/proj/y.py")

        # A wants Y
        coord_mgr.announce_intent("sess-A", "need y", target_files=["/proj/y.py"])
        # B wants X
        coord_mgr.announce_intent("sess-B", "need x", target_files=["/proj/x.py"])

        deadlocks = coord_mgr.detect_deadlocks()
        assert len(deadlocks) == 1
        cycle = deadlocks[0]
        assert "sess-A" in cycle
        assert "sess-B" in cycle

    def test_three_way_deadlock(self, coord_mgr):
        """A->B->C->A circular dependency."""
        coord_mgr.register_session("A", pid=1)
        coord_mgr.register_session("B", pid=2)
        coord_mgr.register_session("C", pid=3)

        coord_mgr.claim_file("A", "/a.py")
        coord_mgr.claim_file("B", "/b.py")
        coord_mgr.claim_file("C", "/c.py")

        coord_mgr.announce_intent("A", "need b", target_files=["/b.py"])
        coord_mgr.announce_intent("B", "need c", target_files=["/c.py"])
        coord_mgr.announce_intent("C", "need a", target_files=["/a.py"])

        deadlocks = coord_mgr.detect_deadlocks()
        assert len(deadlocks) >= 1
        # The cycle should contain all three
        cycle = deadlocks[0]
        assert set(cycle[:-1]) == {"A", "B", "C"}

    def test_deadlock_in_status(self, coord_mgr):
        """Deadlocks appear in get_status() output."""
        coord_mgr.register_session("X", pid=1)
        coord_mgr.register_session("Y", pid=2)

        coord_mgr.claim_file("X", "/x.py")
        coord_mgr.claim_file("Y", "/y.py")
        coord_mgr.announce_intent("X", "need y", target_files=["/y.py"])
        coord_mgr.announce_intent("Y", "need x", target_files=["/x.py"])

        status = coord_mgr.get_status()
        assert len(status["deadlocks"]) >= 1

    def test_no_self_deadlock(self, coord_mgr):
        """A session wanting its own file doesn't create a deadlock."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_file("sess-1", "/proj/mine.py")
        coord_mgr.announce_intent("sess-1", "refactor mine", target_files=["/proj/mine.py"])

        deadlocks = coord_mgr.detect_deadlocks()
        assert deadlocks == []


class TestAuditLog:
    """Audit logging and querying."""

    def test_log_and_query(self, coord_mgr):
        coord_mgr.log_audit(
            tool_name="omega_file_claim",
            session_id="sess-1",
            arguments={"file_path": "/proj/foo.py"},
            result_summary="claimed",
        )

        entries = coord_mgr.query_audit()
        assert len(entries) == 1
        assert entries[0]["tool_name"] == "omega_file_claim"
        assert entries[0]["session_id"] == "sess-1"
        assert entries[0]["arguments"]["file_path"] == "/proj/foo.py"

    def test_query_filter_by_session(self, coord_mgr):
        coord_mgr.log_audit(tool_name="tool_a", session_id="sess-1")
        coord_mgr.log_audit(tool_name="tool_b", session_id="sess-2")

        entries = coord_mgr.query_audit(session_id="sess-1")
        assert len(entries) == 1
        assert entries[0]["tool_name"] == "tool_a"

    def test_query_filter_by_tool(self, coord_mgr):
        coord_mgr.log_audit(tool_name="omega_file_claim", session_id="sess-1")
        coord_mgr.log_audit(tool_name="omega_file_release", session_id="sess-1")

        entries = coord_mgr.query_audit(tool_name="omega_file_claim")
        assert len(entries) == 1

    def test_query_limit(self, coord_mgr):
        for i in range(10):
            coord_mgr.log_audit(tool_name=f"tool_{i}", session_id="sess-1")

        entries = coord_mgr.query_audit(limit=3)
        assert len(entries) == 3

    def test_query_order_desc(self, coord_mgr):
        """Most recent entries come first."""
        coord_mgr.log_audit(tool_name="first", session_id="sess-1")
        coord_mgr.log_audit(tool_name="second", session_id="sess-1")

        entries = coord_mgr.query_audit()
        assert entries[0]["tool_name"] == "second"
        assert entries[1]["tool_name"] == "first"

    def test_prune_audit(self, coord_mgr):
        from omega.coordination import AUDIT_RETENTION_DAYS

        coord_mgr.log_audit(tool_name="old_action", session_id="sess-1")
        coord_mgr.flush_audit_buffer()  # Flush so raw SQL below sees the row

        # Backdate beyond retention
        old_time = (datetime.now(timezone.utc) - timedelta(days=AUDIT_RETENTION_DAYS + 1)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_audit SET created_at = ?", (old_time,)
        )
        coord_mgr._conn.commit()

        with coord_mgr._lock:
            pruned = coord_mgr._prune_audit()
        assert pruned == 1

        entries = coord_mgr.query_audit()
        assert len(entries) == 0

    def test_audit_empty(self, coord_mgr):
        entries = coord_mgr.query_audit()
        assert entries == []


class TestConcurrency:
    """Thread-safety tests."""

    def test_concurrent_registrations(self, coord_mgr):
        """Multiple threads registering sessions simultaneously."""
        errors = []

        def register(session_id):
            try:
                coord_mgr.register_session(session_id, pid=os.getpid())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register, args=(f"sess-{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert len(sessions) == 10

    def test_concurrent_file_claims(self, coord_mgr):
        """Multiple sessions trying to claim the same file."""
        coord_mgr.register_session("sess-1", pid=1111)
        coord_mgr.register_session("sess-2", pid=2222)

        results = {}

        def claim(session_id):
            results[session_id] = coord_mgr.claim_file(session_id, "/proj/contested.py")

        t1 = threading.Thread(target=claim, args=("sess-1",))
        t2 = threading.Thread(target=claim, args=("sess-2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one should succeed, one should conflict
        successes = [sid for sid, r in results.items() if r.get("success")]
        conflicts = [sid for sid, r in results.items() if r.get("conflict")]
        assert len(successes) == 1
        assert len(conflicts) == 1


class TestGitEventTracking:
    """Tests for git-aware coordination."""

    def test_log_git_event(self, coord_mgr):
        """Log a git event and retrieve it."""
        event_id = coord_mgr.log_git_event(
            project="/proj/a",
            event_type="commit",
            commit_hash="abc1234",
            branch="main",
            message="test commit",
            session_id="sess-1",
        )
        assert event_id > 0

    def test_get_tracked_commits(self, coord_mgr):
        """Tracked commits returns hashes for a project."""
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="aaa1111")
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="bbb2222")
        coord_mgr.log_git_event("/proj/b", "commit", commit_hash="ccc3333")

        tracked = coord_mgr.get_tracked_commits("/proj/a")
        assert "aaa1111" in tracked
        assert "bbb2222" in tracked
        assert "ccc3333" not in tracked

    def test_get_recent_git_events(self, coord_mgr):
        """Recent events filtered by project and type."""
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="aaa1111")
        coord_mgr.log_git_event("/proj/a", "push", commit_hash="aaa1111", branch="main")
        coord_mgr.log_git_event("/proj/a", "upstream_detected", commit_hash="ddd4444")

        all_events = coord_mgr.get_recent_git_events(project="/proj/a")
        assert len(all_events) == 3

        commits_only = coord_mgr.get_recent_git_events(project="/proj/a", event_type="commit")
        assert len(commits_only) == 1
        assert commits_only[0]["commit_hash"] == "aaa1111"

    def test_detect_untracked_commits(self, coord_mgr):
        """Untracked commits are those not in coord_git_events."""
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="aaa1111")
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="bbb2222")

        untracked = coord_mgr.detect_untracked_commits(
            "/proj/a", ["aaa1111", "bbb2222", "ccc3333", "ddd4444"]
        )
        assert untracked == ["ccc3333", "ddd4444"]

    def test_detect_untracked_empty(self, coord_mgr):
        """Empty input returns empty list."""
        assert coord_mgr.detect_untracked_commits("/proj/a", []) == []

    def test_git_events_without_session(self, coord_mgr):
        """Git events can be logged without a session_id (upstream detection)."""
        event_id = coord_mgr.log_git_event(
            project="/proj/a",
            event_type="upstream_detected",
            commit_hash="ext1234",
            branch="main",
            message="external commit",
        )
        assert event_id > 0
        events = coord_mgr.get_recent_git_events(project="/proj/a")
        assert len(events) == 1
        assert events[0]["session_id"] is None

    def test_git_event_ordering(self, coord_mgr):
        """Events returned in reverse chronological order."""
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="first")
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="second")
        coord_mgr.log_git_event("/proj/a", "commit", commit_hash="third")

        events = coord_mgr.get_recent_git_events(project="/proj/a")
        hashes = [e["commit_hash"] for e in events]
        assert hashes == ["third", "second", "first"]


class TestPrePushGuardHook:
    """Tests for pre-push divergence guard hook logic."""

    def test_hook_imports(self):
        """Pre-push guard hook is importable."""
        hooks_dir = Path(__file__).parent.parent / "hooks"
        path = hooks_dir / "pre_push_guard.py"
        assert path.exists()
        content = path.read_text()
        assert "import time" in content
        assert "_log_timing" in content
        assert "git push" in content

    def test_hook_has_timing(self):
        """Pre-push guard has timing instrumentation."""
        hooks_dir = Path(__file__).parent.parent / "hooks"
        content = (hooks_dir / "pre_push_guard.py").read_text()
        assert "time.monotonic()" in content


class TestPostCommitTracking:
    """Tests for post-commit tracking in surface_memories hook."""

    def test_surface_memories_has_git_tracking(self):
        """surface_memories.py includes git commit tracking."""
        hooks_dir = Path(__file__).parent.parent / "hooks"
        content = (hooks_dir / "surface_memories.py").read_text()
        assert "_track_git_commit" in content
        assert "git commit" in content

    def test_commit_hash_regex(self):
        """The regex used to detect commit hashes works correctly."""
        import re
        pattern = r'\[[\w/.-]+\s+([0-9a-f]{7,12})\]'

        # Standard git commit output
        output1 = "[main abc1234def] Add feature X"
        match1 = re.search(pattern, output1)
        assert match1 is not None
        assert match1.group(1) == "abc1234def"

        # Branch with slash
        output2 = "[feat/auth 1234567] Fix login"
        match2 = re.search(pattern, output2)
        assert match2 is not None
        assert match2.group(1) == "1234567"

        # No match — not a commit output
        output3 = "Everything up to date"
        match3 = re.search(pattern, output3)
        assert match3 is None


# ===========================================================================
# v2 Tests: Message Bus
# ===========================================================================

class TestMessageBus:
    """Message send/receive/broadcast tests."""

    def test_send_direct_message(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("receiver", pid=5678, project="/proj")

        result = coord_mgr.send_message(
            from_session="sender",
            subject="Auth module ready",
            msg_type="inform",
            to_session="receiver",
            body="I finished the auth module. You can start tests.",
        )
        assert result["success"] is True
        assert "message_id" in result
        assert "context_id" in result

    def test_send_broadcast_message(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj/a")

        result = coord_mgr.send_message(
            from_session="sender",
            subject="Starting deploy",
            msg_type="inform",
            project="/proj/a",
        )
        assert result["success"] is True

    def test_send_auto_project_from_session(self, coord_mgr):
        """Broadcast without explicit project uses sender's project."""
        coord_mgr.register_session("sender", pid=1234, project="/proj/b")

        result = coord_mgr.send_message(
            from_session="sender",
            subject="Heads up",
        )
        assert result["success"] is True

    def test_send_requires_target(self, coord_mgr):
        """Broadcast without to_session or project (and no session project) fails."""
        # Session without a project
        coord_mgr.register_session("orphan", pid=1234)

        result = coord_mgr.send_message(
            from_session="orphan",
            subject="Hello",
        )
        assert result["success"] is False
        assert "required" in result["error"]

    def test_send_invalid_msg_type(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")

        result = coord_mgr.send_message(
            from_session="sender",
            subject="Test",
            msg_type="invalid_type",
            to_session="someone",
        )
        assert result["success"] is False
        assert "Invalid msg_type" in result["error"]

    def test_check_inbox_direct(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("receiver", pid=5678, project="/proj")

        coord_mgr.send_message(
            from_session="sender",
            subject="Please review PR",
            msg_type="request",
            to_session="receiver",
            body="PR #42 is ready for review.",
        )

        messages = coord_mgr.check_inbox("receiver")
        assert len(messages) == 1
        assert messages[0]["subject"] == "Please review PR"
        assert messages[0]["msg_type"] == "request"
        assert messages[0]["from_session"] == "sender"
        assert messages[0]["body"] == "PR #42 is ready for review."

    def test_check_inbox_broadcast(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("receiver", pid=5678, project="/proj")

        coord_mgr.send_message(
            from_session="sender",
            subject="Deploy starting",
            project="/proj",
        )

        messages = coord_mgr.check_inbox("receiver")
        assert len(messages) == 1
        assert messages[0]["subject"] == "Deploy starting"
        assert messages[0]["to_session"] is None  # broadcast

    def test_broadcast_excludes_sender(self, coord_mgr):
        """Sender doesn't see their own broadcast."""
        coord_mgr.register_session("sender", pid=1234, project="/proj")

        coord_mgr.send_message(
            from_session="sender",
            subject="Broadcast",
            project="/proj",
        )

        messages = coord_mgr.check_inbox("sender")
        assert len(messages) == 0

    def test_inbox_marks_read(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("receiver", pid=5678, project="/proj")

        coord_mgr.send_message(
            from_session="sender",
            subject="Test",
            to_session="receiver",
        )

        # First check: gets messages
        messages = coord_mgr.check_inbox("receiver", unread_only=True)
        assert len(messages) == 1

        # Second check: already read (direct messages only)
        messages = coord_mgr.check_inbox("receiver", unread_only=True)
        assert len(messages) == 0

        # Show all (including read)
        messages = coord_mgr.check_inbox("receiver", unread_only=False)
        assert len(messages) == 1

    def test_inbox_filter_by_type(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("receiver", pid=5678, project="/proj")

        coord_mgr.send_message(
            from_session="sender", subject="Request",
            msg_type="request", to_session="receiver",
        )
        coord_mgr.send_message(
            from_session="sender", subject="FYI",
            msg_type="inform", to_session="receiver",
        )

        requests = coord_mgr.check_inbox("receiver", msg_type="request")
        assert len(requests) == 1
        assert requests[0]["msg_type"] == "request"

    def test_unread_count(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("receiver", pid=5678, project="/proj")

        assert coord_mgr.get_unread_count("receiver") == 0

        coord_mgr.send_message(
            from_session="sender", subject="Msg 1",
            to_session="receiver",
        )
        coord_mgr.send_message(
            from_session="sender", subject="Msg 2",
            to_session="receiver",
        )

        assert coord_mgr.get_unread_count("receiver") == 2

        # Reading marks them as read
        coord_mgr.check_inbox("receiver")
        assert coord_mgr.get_unread_count("receiver") == 0

    def test_broadcast_marked_read(self, coord_mgr):
        """Broadcast messages are marked read per-session via coord_broadcast_reads."""
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("reader-a", pid=5678, project="/proj")
        coord_mgr.register_session("reader-b", pid=9012, project="/proj")

        # Clear peer-arrival notifications
        coord_mgr.check_inbox("sender")
        coord_mgr.check_inbox("reader-a")
        coord_mgr.check_inbox("reader-b")

        # Send broadcast
        coord_mgr.send_message(
            from_session="sender", subject="Broadcast",
            project="/proj",
        )

        # Both readers see it
        assert coord_mgr.get_unread_count("reader-a") == 1
        assert coord_mgr.get_unread_count("reader-b") == 1

        msgs_a = coord_mgr.check_inbox("reader-a", unread_only=True)
        assert len(msgs_a) == 1

        # reader-a has now read it — should not see it again
        assert coord_mgr.get_unread_count("reader-a") == 0
        msgs_a2 = coord_mgr.check_inbox("reader-a", unread_only=True)
        assert len(msgs_a2) == 0

        # reader-b still sees it as unread
        assert coord_mgr.get_unread_count("reader-b") == 1
        msgs_b = coord_mgr.check_inbox("reader-b", unread_only=True)
        assert len(msgs_b) == 1

        # Now reader-b has also read it
        assert coord_mgr.get_unread_count("reader-b") == 0

    def test_message_context_threading(self, coord_mgr):
        coord_mgr.register_session("a", pid=1, project="/proj")
        coord_mgr.register_session("b", pid=2, project="/proj")

        # Clear peer-arrival notifications from registration
        coord_mgr.check_inbox("a")
        coord_mgr.check_inbox("b")

        result = coord_mgr.send_message(
            from_session="a", subject="Can you test?",
            msg_type="request", to_session="b",
        )
        ctx_id = result["context_id"]

        # Reply in same thread
        coord_mgr.send_message(
            from_session="b", subject="On it!",
            msg_type="acknowledge", to_session="a",
            context_id=ctx_id,
        )

        messages = coord_mgr.check_inbox("a")
        assert len(messages) == 1
        assert messages[0]["context_id"] == ctx_id

    def test_message_with_ttl(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("receiver", pid=5678, project="/proj")

        result = coord_mgr.send_message(
            from_session="sender", subject="Urgent",
            to_session="receiver", ttl_minutes=60,
        )
        assert result["success"] is True

    def test_prune_expired_messages(self, coord_mgr):
        coord_mgr.register_session("sender", pid=1234, project="/proj")
        coord_mgr.register_session("receiver", pid=5678, project="/proj")

        # Clear peer-arrival notifications before counting
        coord_mgr.check_inbox("sender")
        coord_mgr.check_inbox("receiver")

        coord_mgr.send_message(
            from_session="sender", subject="Expires soon",
            to_session="receiver", ttl_minutes=1,
        )

        # Backdate expiry only for non-read messages (the one we just sent)
        from datetime import timedelta
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_messages SET expires_at = ? WHERE subject = 'Expires soon'", (expired,)
        )
        coord_mgr._conn.commit()

        pruned = coord_mgr._prune_expired_messages()
        assert pruned == 1


# ===========================================================================
# v2 Tests: Task Dependencies
# ===========================================================================

class TestTaskDependencies:
    """Task dependency chain tests."""

    def test_create_task_with_deps(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Build")
        t2 = coord_mgr.create_task(
            created_by="sess-1", title="Test",
            depends_on=[t1["task_id"]],
        )
        assert t2["success"] is True
        assert t2["blocked_by"] == [t1["task_id"]]

    def test_create_dep_on_completed_task(self, coord_mgr):
        """Dep on already-completed task doesn't block."""
        coord_mgr.register_session("sess-1", pid=1234)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Build")
        coord_mgr.complete_task(t1["task_id"], "sess-1")

        t2 = coord_mgr.create_task(
            created_by="sess-1", title="Test",
            depends_on=[t1["task_id"]],
        )
        assert t2["success"] is True
        assert "blocked_by" not in t2

    def test_create_dep_on_nonexistent_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.create_task(
            created_by="sess-1", title="Test",
            depends_on=[999],
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_claim_blocked_task_rejected(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        t1 = coord_mgr.create_task(created_by="sess-1", title="Build")
        t2 = coord_mgr.create_task(
            created_by="sess-1", title="Test",
            depends_on=[t1["task_id"]],
        )

        result = coord_mgr.claim_task(t2["task_id"], "sess-2")
        assert result["success"] is False
        assert "blocked_by" in result
        assert t1["task_id"] in result["blocked_by"]

    def test_claim_unblocked_after_dep_complete(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        t1 = coord_mgr.create_task(created_by="sess-1", title="Build")
        t2 = coord_mgr.create_task(
            created_by="sess-1", title="Test",
            depends_on=[t1["task_id"]],
        )

        # Complete the dependency
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.complete_task(t1["task_id"], "sess-1")

        # Now should be claimable
        result = coord_mgr.claim_task(t2["task_id"], "sess-2")
        assert result["success"] is True

    def test_complete_notifies_unblocked(self, coord_mgr):
        """Completing a dep task sends inform message to unblocked task creator."""
        coord_mgr.register_session("creator", pid=1234, project="/proj")
        coord_mgr.register_session("worker", pid=5678, project="/proj")

        t1 = coord_mgr.create_task(created_by="creator", title="Build")
        t2 = coord_mgr.create_task(
            created_by="creator", title="Deploy",
            depends_on=[t1["task_id"]],
        )

        coord_mgr.claim_task(t1["task_id"], "worker")
        result = coord_mgr.complete_task(t1["task_id"], "worker")
        assert result["success"] is True
        assert len(result.get("unblocked_tasks", [])) == 1
        assert result["unblocked_tasks"][0]["task_id"] == t2["task_id"]

        # Creator should have an unread message
        messages = coord_mgr.check_inbox("creator")
        assert len(messages) >= 1
        assert "unblocked" in messages[0]["subject"].lower()

    def test_multi_dep_only_unblocks_when_all_complete(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)

        t1 = coord_mgr.create_task(created_by="sess-1", title="Build frontend")
        t2 = coord_mgr.create_task(created_by="sess-1", title="Build backend")
        t3 = coord_mgr.create_task(
            created_by="sess-1", title="Integration test",
            depends_on=[t1["task_id"], t2["task_id"]],
        )

        # Complete only one dep
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        result1 = coord_mgr.complete_task(t1["task_id"], "sess-1")
        assert len(result1.get("unblocked_tasks", [])) == 0

        # Still blocked
        claim_result = coord_mgr.claim_task(t3["task_id"], "sess-1")
        assert claim_result["success"] is False

        # Complete second dep
        coord_mgr.claim_task(t2["task_id"], "sess-1")
        result2 = coord_mgr.complete_task(t2["task_id"], "sess-1")
        assert len(result2.get("unblocked_tasks", [])) == 1

        # Now claimable
        claim_result = coord_mgr.claim_task(t3["task_id"], "sess-1")
        assert claim_result["success"] is True

    def test_get_task_deps(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Build")
        t2 = coord_mgr.create_task(
            created_by="sess-1", title="Test",
            depends_on=[t1["task_id"]],
        )

        deps = coord_mgr.get_task_deps(t2["task_id"])
        assert len(deps["depends_on"]) == 1
        assert deps["depends_on"][0]["task_id"] == t1["task_id"]
        assert deps["blocked"] is True

        # t1 has no deps but is depended on
        deps1 = coord_mgr.get_task_deps(t1["task_id"])
        assert len(deps1["depends_on"]) == 0
        assert len(deps1["depended_by"]) == 1
        assert deps1["blocked"] is False

    def test_list_tasks_shows_deps(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Build")
        t2 = coord_mgr.create_task(
            created_by="sess-1", title="Test",
            depends_on=[t1["task_id"]],
        )

        tasks = coord_mgr.list_tasks()
        test_task = [t for t in tasks if t["id"] == t2["task_id"]][0]
        assert test_task["blocked"] is True
        assert t1["task_id"] in test_task["depends_on"]

    def test_complete_with_result(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Run tests")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.complete_task(
            t["task_id"], "sess-1", result="All 42 tests passed"
        )
        assert result["success"] is True

        tasks = coord_mgr.list_tasks(status="completed")
        assert tasks[0]["result"] == "All 42 tests passed"


# ===========================================================================
# v2 Tests: Fail / Cancel Tasks
# ===========================================================================

class TestTaskFailCancel:
    """Task fail and cancel tests."""

    def test_fail_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Deploy")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.fail_task(t["task_id"], "sess-1", reason="Deployment timeout")
        assert result["success"] is True
        assert result["status"] == "failed"

        tasks = coord_mgr.list_tasks(status="failed")
        assert len(tasks) == 1
        assert tasks[0]["result"] == "Deployment timeout"

    def test_fail_does_not_unblock_deps(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Build")
        t2 = coord_mgr.create_task(
            created_by="sess-1", title="Test",
            depends_on=[t1["task_id"]],
        )

        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.fail_task(t1["task_id"], "sess-1", reason="Build failed")

        # t2 should still be blocked
        result = coord_mgr.claim_task(t2["task_id"], "sess-1")
        assert result["success"] is False

    def test_cancel_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Obsolete task")

        result = coord_mgr.cancel_task(t["task_id"], "sess-1")
        assert result["success"] is True
        assert result["status"] == "canceled"

    def test_fail_already_completed(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Done")
        coord_mgr.complete_task(t["task_id"], "sess-1")

        result = coord_mgr.fail_task(t["task_id"], "sess-1")
        assert result["success"] is False

    def test_cancel_already_failed(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Failed")
        coord_mgr.claim_task(t["task_id"], "sess-1")
        coord_mgr.fail_task(t["task_id"], "sess-1")

        result = coord_mgr.cancel_task(t["task_id"], "sess-1")
        assert result["success"] is False

    def test_cancel_wrong_session(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Task")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.cancel_task(t["task_id"], "sess-2")
        assert result["success"] is False
        assert "claimed by another" in result["error"]
        assert result["claimed_by"] == "sess-1"

    def test_cancel_unclaimed_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Open task")

        # Only the creator can cancel an unclaimed task
        result = coord_mgr.cancel_task(t["task_id"], "sess-1")
        assert result["success"] is True
        assert result["status"] == "canceled"

    def test_cancel_nonexistent_task(self, coord_mgr):
        result = coord_mgr.cancel_task(99999, "sess-1")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_fail_wrong_session(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Task")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.fail_task(t["task_id"], "sess-2")
        assert result["success"] is False

    def test_fail_unclaimed_task_wrong_session(self, coord_mgr):
        """A non-creator session cannot fail an unclaimed task."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Open task")

        result = coord_mgr.fail_task(t["task_id"], "sess-2", reason="nope")
        assert result["success"] is False
        assert "unclaimed" in result["error"].lower()

    def test_cancel_unclaimed_task_wrong_session(self, coord_mgr):
        """A non-creator session cannot cancel an unclaimed task."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Open task")

        result = coord_mgr.cancel_task(t["task_id"], "sess-2")
        assert result["success"] is False
        assert "unclaimed" in result["error"].lower()


# ===========================================================================
# v2 Tests: Progress Tracking
# ===========================================================================

class TestProgressTracking:
    """Task progress update tests."""

    def test_update_progress(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Run tests")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.update_task_progress(t["task_id"], "sess-1", 50)
        assert result["success"] is True
        assert result["progress"] == 50

    def test_progress_with_status_note(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Run tests")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        coord_mgr.update_task_progress(
            t["task_id"], "sess-1", 75,
            status_note="Running integration tests...",
        )

        tasks = coord_mgr.list_tasks(status="in_progress")
        assert tasks[0]["progress"] == 75
        assert tasks[0]["metadata"]["status_note"] == "Running integration tests..."

    def test_progress_clamped(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Task")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.update_task_progress(t["task_id"], "sess-1", 150)
        assert result["progress"] == 100

        result = coord_mgr.update_task_progress(t["task_id"], "sess-1", -10)
        assert result["progress"] == 0

    def test_progress_only_by_owner(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        t = coord_mgr.create_task(created_by="sess-1", title="Task")
        coord_mgr.claim_task(t["task_id"], "sess-1")

        result = coord_mgr.update_task_progress(t["task_id"], "sess-2", 50)
        assert result["success"] is False

    def test_progress_only_in_progress(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Pending task")

        result = coord_mgr.update_task_progress(t["task_id"], "sess-1", 50)
        assert result["success"] is False


# ===========================================================================
# v2 Tests: Capability Routing
# ===========================================================================

class TestCapabilityRouting:
    """Capability-based agent discovery tests."""

    def test_find_by_capability(self, coord_mgr):
        coord_mgr.register_session(
            "tester", pid=1234, project="/proj",
            capabilities=["test", "review"],
        )
        coord_mgr.register_session(
            "deployer", pid=5678, project="/proj",
            capabilities=["deploy", "infra"],
        )

        matches = coord_mgr.find_capable_sessions("test")
        assert len(matches) == 1
        assert matches[0]["session_id"] == "tester"

    def test_find_case_insensitive(self, coord_mgr):
        coord_mgr.register_session(
            "agent", pid=1234, project="/proj",
            capabilities=["TypeScript", "React"],
        )

        matches = coord_mgr.find_capable_sessions("typescript")
        assert len(matches) == 1

    def test_find_substring_match(self, coord_mgr):
        coord_mgr.register_session(
            "agent", pid=1234, project="/proj",
            capabilities=["code-review", "test-e2e"],
        )

        matches = coord_mgr.find_capable_sessions("review")
        assert len(matches) == 1

    def test_find_no_match(self, coord_mgr):
        coord_mgr.register_session(
            "agent", pid=1234, project="/proj",
            capabilities=["code"],
        )

        matches = coord_mgr.find_capable_sessions("deploy")
        assert len(matches) == 0

    def test_find_filter_by_project(self, coord_mgr):
        coord_mgr.register_session(
            "agent-a", pid=1234, project="/proj/a",
            capabilities=["test"],
        )
        coord_mgr.register_session(
            "agent-b", pid=5678, project="/proj/b",
            capabilities=["test"],
        )

        matches = coord_mgr.find_capable_sessions("test", project="/proj/a")
        assert len(matches) == 1
        assert matches[0]["session_id"] == "agent-a"

    def test_find_shows_current_task(self, coord_mgr):
        coord_mgr.register_session(
            "worker", pid=1234, project="/proj",
            capabilities=["test"],
        )
        t = coord_mgr.create_task(created_by="worker", title="Running unit tests")
        coord_mgr.claim_task(t["task_id"], "worker")

        matches = coord_mgr.find_capable_sessions("test")
        assert len(matches) == 1
        assert matches[0]["current_task"]["title"] == "Running unit tests"


# ===========================================================================
# v2 Tests: Auto-Release Committed Files
# ===========================================================================

class TestAutoReleaseCommittedFiles:
    """release_committed_files tests."""

    def test_release_committed_files(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj")
        coord_mgr.claim_file("sess-1", "/proj/a.py")
        coord_mgr.claim_file("sess-1", "/proj/b.py")
        coord_mgr.claim_file("sess-1", "/proj/c.py")

        result = coord_mgr.release_committed_files(
            "sess-1", "/proj", ["/proj/a.py", "/proj/b.py"]
        )
        assert result["released_count"] == 2
        assert "/proj/a.py" in result["released_files"]
        assert "/proj/b.py" in result["released_files"]

        # c.py should still be claimed
        assert coord_mgr.check_file("/proj/c.py")["claimed"] is True
        # a.py and b.py should be free
        assert coord_mgr.check_file("/proj/a.py")["claimed"] is False
        assert coord_mgr.check_file("/proj/b.py")["claimed"] is False

    def test_release_idempotent(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)

        # Release files that aren't claimed — should not error
        result = coord_mgr.release_committed_files(
            "sess-1", "/proj", ["/proj/nonexistent.py"]
        )
        assert result["released_count"] == 0

    def test_release_only_own_claims(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.claim_file("sess-1", "/proj/a.py")

        # sess-2 can't release sess-1's claim
        result = coord_mgr.release_committed_files(
            "sess-2", "/proj", ["/proj/a.py"]
        )
        assert result["released_count"] == 0

        # File still claimed by sess-1
        assert coord_mgr.check_file("/proj/a.py")["claimed"] is True


# ===========================================================================
# v2 Tests: Schema Migration
# ===========================================================================

class TestSchemaMigration:
    """Schema version migration tests."""

    def test_fresh_install_is_v12(self, coord_mgr):
        """A fresh CoordinationManager creates schema v12."""
        row = coord_mgr._conn.execute(
            "SELECT version FROM coord_schema_version"
        ).fetchone()
        assert row[0] == 12

    def test_v2_tables_exist(self, coord_mgr):
        """v2 tables (coord_messages, coord_task_deps) exist."""
        tables = coord_mgr._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'coord_%'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "coord_messages" in table_names
        assert "coord_task_deps" in table_names

    def test_v3_broadcast_reads_table_exists(self, coord_mgr):
        """v3 table (coord_broadcast_reads) exists."""
        tables = coord_mgr._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'coord_broadcast_reads'"
        ).fetchall()
        assert len(tables) == 1

    def test_coord_tasks_has_v2_columns(self, coord_mgr):
        """coord_tasks has result and progress columns."""
        # Create a task and verify we can set result/progress
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Test")
        coord_mgr.claim_task(t["task_id"], "sess-1")
        coord_mgr.update_task_progress(t["task_id"], "sess-1", 42)
        coord_mgr.complete_task(t["task_id"], "sess-1", result="done")

        tasks = coord_mgr.list_tasks(status="completed")
        assert tasks[0]["progress"] == 42
        assert tasks[0]["result"] == "done"


class TestGetSessionClaims:
    """Tests for get_session_claims() public API."""

    def test_no_claims(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.get_session_claims("sess-1")
        assert result["session_id"] == "sess-1"
        assert result["file_claims"] == []
        assert result["branch_claims"] == []

    def test_file_claims(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_file("sess-1", "/proj/foo.py")
        coord_mgr.claim_file("sess-1", "/proj/bar.py")
        result = coord_mgr.get_session_claims("sess-1")
        assert sorted(result["file_claims"]) == ["/proj/bar.py", "/proj/foo.py"]

    def test_branch_claims(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_branch("sess-1", "/proj", "feat-a")
        result = coord_mgr.get_session_claims("sess-1")
        assert result["branch_claims"] == ["feat-a"]

    def test_nonexistent_session(self, coord_mgr):
        result = coord_mgr.get_session_claims("nonexistent")
        assert result["file_claims"] == []
        assert result["branch_claims"] == []

    def test_session_isolation(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        coord_mgr.claim_file("sess-1", "/proj/foo.py")
        coord_mgr.claim_file("sess-2", "/proj/bar.py")
        result1 = coord_mgr.get_session_claims("sess-1")
        result2 = coord_mgr.get_session_claims("sess-2")
        assert result1["file_claims"] == ["/proj/foo.py"]
        assert result2["file_claims"] == ["/proj/bar.py"]


class TestRefreshFileActivity:
    """Tests for the lightweight refresh_file_activity method."""

    def test_refresh_file_activity(self, coord_mgr):
        """refresh_file_activity updates the timestamp on a valid claim."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.claim_file("sess-1", "/proj/foo.py", task="editing")

        # Read initial last_activity
        check1 = coord_mgr.check_file("/proj/foo.py")
        initial_activity = check1["last_activity"]

        import time
        time.sleep(0.05)  # Ensure timestamp differs

        result = coord_mgr.refresh_file_activity("sess-1", "/proj/foo.py")
        assert result is True

        check2 = coord_mgr.check_file("/proj/foo.py")
        assert check2["last_activity"] >= initial_activity

    def test_refresh_wrong_session(self, coord_mgr):
        """refresh_file_activity returns False for wrong session."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        coord_mgr.claim_file("sess-1", "/proj/foo.py")

        result = coord_mgr.refresh_file_activity("sess-2", "/proj/foo.py")
        assert result is False

    def test_refresh_unclaimed(self, coord_mgr):
        """refresh_file_activity returns False for unclaimed file."""
        result = coord_mgr.refresh_file_activity("sess-1", "/proj/nonexistent.py")
        assert result is False


class TestBranchClaimTTL:
    """Tests for TTL-aware branch claim expiry (matching claim_file pattern)."""

    def test_expired_branch_claim_replaced(self, coord_mgr):
        """Expired branch claims are silently replaced by new claimants."""
        from omega.coordination import BRANCH_CLAIM_TTL_SECONDS
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.claim_branch("sess-1", "/proj", "feat-old")

        # Backdate last_activity to expire the claim
        expired_time = (
            datetime.now(timezone.utc) - timedelta(seconds=BRANCH_CLAIM_TTL_SECONDS + 10)
        ).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_branch_claims SET last_activity = ? WHERE project = ? AND branch = ?",
            (expired_time, "/proj", "feat-old")
        )
        coord_mgr._conn.commit()

        # sess-2 should silently take over
        result = coord_mgr.claim_branch("sess-2", "/proj", "feat-old")
        assert result["success"] is True
        assert result.get("expired_claim_replaced") is True

    def test_active_branch_claim_still_conflicts(self, coord_mgr):
        """Non-expired branch claims still return conflict."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)

        coord_mgr.claim_branch("sess-1", "/proj", "feat-active")

        result = coord_mgr.claim_branch("sess-2", "/proj", "feat-active")
        assert result["success"] is False
        assert result["conflict"] is True


class TestAutoReregisterRace:
    """Tests for _auto_reregister IntegrityError guard."""

    def test_auto_reregister_handles_race(self, coord_mgr):
        """_auto_reregister falls back to UPDATE if session was concurrently registered."""
        # Register and then manually insert to simulate a race
        coord_mgr.register_session("race-sess", pid=1234, project="/proj")

        # Call _auto_reregister directly — should not raise IntegrityError
        now = datetime.now(timezone.utc).isoformat()
        result = coord_mgr._auto_reregister("race-sess", now)
        assert result["success"] is True
        assert result.get("reregistered") is True

        # Session should still be active
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert any(s["session_id"] == "race-sess" for s in sessions)


class TestEnrichSessionMetadata:
    """Tests for enrich_session_metadata."""

    def test_enrich_merges_git_state(self, coord_mgr, monkeypatch):
        """enrich_session_metadata merges git state into session metadata."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj")

        # Mock _capture_git_state to return predictable data
        monkeypatch.setattr(
            coord_mgr, "_capture_git_state",
            lambda project: {"git_branch": "feat-test", "git_dirty_files": ["a.py"]},
        )

        coord_mgr.enrich_session_metadata("sess-1", "/proj")

        # Verify metadata was enriched
        row = coord_mgr._conn.execute(
            "SELECT metadata FROM coord_sessions WHERE session_id = ?", ("sess-1",)
        ).fetchone()
        import json
        meta = json.loads(row[0]) if row[0] else {}
        assert meta["git_branch"] == "feat-test"
        assert meta["git_dirty_files"] == ["a.py"]

    def test_enrich_noop_when_no_project(self, coord_mgr):
        """enrich_session_metadata does nothing when project is empty."""
        coord_mgr.register_session("sess-1", pid=1234)

        # Should not raise
        coord_mgr.enrich_session_metadata("sess-1", "")

    def test_enrich_noop_when_no_git_state(self, coord_mgr, monkeypatch):
        """enrich_session_metadata does nothing when git state is empty."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj")

        monkeypatch.setattr(coord_mgr, "_capture_git_state", lambda project: {})

        coord_mgr.enrich_session_metadata("sess-1", "/proj")

        # Metadata should be unchanged (empty dict from registration)
        row = coord_mgr._conn.execute(
            "SELECT metadata FROM coord_sessions WHERE session_id = ?", ("sess-1",)
        ).fetchone()
        import json
        meta = json.loads(row[0]) if row[0] else {}
        assert "git_branch" not in meta


class TestGetRecentEvents:
    """Tests for get_recent_events() — unified coordination activity feed."""

    def test_recent_file_claims(self, coord_mgr):
        """File claims within time window should appear in events."""
        coord_mgr.register_session("sess-a", pid=1001, project="/proj/x")
        coord_mgr.claim_file("sess-a", "/proj/x/engine.py", task="editing")

        events = coord_mgr.get_recent_events("/proj/x", minutes=5)
        assert len(events) >= 1
        claim_events = [e for e in events if e["type"] == "claim"]
        assert len(claim_events) == 1
        assert "engine.py" in claim_events[0]["summary"]
        assert claim_events[0]["session_id"] == "sess-a"

    def test_recent_task_completed(self, coord_mgr):
        """Completed tasks should appear in events."""
        coord_mgr.register_session("sess-a", pid=1001, project="/proj/x")
        result = coord_mgr.create_task("sess-a", "Write tests", project="/proj/x")
        task_id = result["task_id"]
        coord_mgr.claim_task(task_id, "sess-a")
        coord_mgr.complete_task(task_id, "sess-a", result="all green")

        events = coord_mgr.get_recent_events("/proj/x", minutes=5)
        task_events = [e for e in events if e["type"] == "task"]
        assert len(task_events) >= 1
        assert "completed" in task_events[0]["summary"]
        assert "Write tests" in task_events[0]["summary"]

    def test_recent_messages(self, coord_mgr):
        """Messages should appear in events."""
        coord_mgr.register_session("sess-a", pid=1001, project="/proj/x")
        coord_mgr.send_message(
            from_session="sess-a",
            subject="Overlap: both editing engine.py",
            msg_type="inform",
            project="/proj/x",
        )

        events = coord_mgr.get_recent_events("/proj/x", minutes=5)
        msg_events = [e for e in events if e["type"] == "message"]
        assert len(msg_events) == 1
        assert "Overlap" in msg_events[0]["summary"]

    def test_exclude_session(self, coord_mgr):
        """Events from excluded session should be filtered out."""
        coord_mgr.register_session("sess-a", pid=1001, project="/proj/x")
        coord_mgr.register_session("sess-b", pid=1002, project="/proj/x")
        coord_mgr.claim_file("sess-a", "/proj/x/file1.py")
        coord_mgr.claim_file("sess-b", "/proj/x/file2.py")

        events = coord_mgr.get_recent_events(
            "/proj/x", minutes=5, exclude_session="sess-a"
        )
        for ev in events:
            assert ev["session_id"] != "sess-a"

    def test_empty_project(self, coord_mgr):
        """Project with no activity should return empty list."""
        events = coord_mgr.get_recent_events("/proj/empty", minutes=5)
        assert events == []

    def test_limit_respected(self, coord_mgr):
        """Limit parameter should cap the number of events."""
        coord_mgr.register_session("sess-a", pid=1001, project="/proj/x")
        for i in range(5):
            coord_mgr.claim_file("sess-a", f"/proj/x/file{i}.py")

        events = coord_mgr.get_recent_events("/proj/x", minutes=5, limit=2)
        assert len(events) <= 2

    def test_events_sorted_by_timestamp(self, coord_mgr):
        """Events should be sorted by timestamp descending."""
        coord_mgr.register_session("sess-a", pid=1001, project="/proj/x")
        coord_mgr.claim_file("sess-a", "/proj/x/file1.py")
        coord_mgr.claim_file("sess-a", "/proj/x/file2.py")

        events = coord_mgr.get_recent_events("/proj/x", minutes=5)
        if len(events) >= 2:
            assert events[0]["timestamp"] >= events[1]["timestamp"]


class TestResourceReleaseNotifications:
    """Push [AVAILABLE] notifications when resources are released."""

    def test_release_file_notifies_intent_holder(self, coord_mgr):
        """Releasing a file sends [AVAILABLE] to agents with intents targeting it."""
        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_file("owner", "/proj/auth.py")
        coord_mgr.announce_intent("waiter", "auth refactor", target_files=["/proj/auth.py"])

        coord_mgr.release_file("owner", "/proj/auth.py")

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 1
        assert "auth.py" in available_msgs[0]["subject"]

    def test_release_file_no_intent_no_notification(self, coord_mgr):
        """No intents targeting the file means no notifications sent."""
        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("other", pid=1002, project="/proj")

        coord_mgr.claim_file("owner", "/proj/auth.py")
        coord_mgr.announce_intent("other", "unrelated work", target_files=["/proj/ui.py"])

        coord_mgr.release_file("owner", "/proj/auth.py")

        msgs = coord_mgr.check_inbox("other", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 0

    def test_release_branch_notifies_intent_holder(self, coord_mgr):
        """Releasing a branch sends [AVAILABLE] to agents with matching branch intents."""
        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_branch("owner", "/proj", "feat-auth")
        coord_mgr.announce_intent("waiter", "auth work", target_branch="feat-auth")

        coord_mgr.release_branch("owner", "/proj", "feat-auth")

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 1
        assert "feat-auth" in available_msgs[0]["subject"]

    def test_deregister_notifies_on_released_resources(self, coord_mgr):
        """Deregistering a session notifies agents waiting on its claimed resources."""
        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_file("owner", "/proj/models.py")
        coord_mgr.announce_intent("waiter", "model update", target_files=["/proj/models.py"])

        coord_mgr.deregister_session("owner")

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 1
        assert "models.py" in available_msgs[0]["subject"]

    def test_stale_cleanup_notifies_on_released_resources(self, coord_mgr):
        """Stale session cleanup notifies agents waiting on freed resources."""
        from omega.coordination import STALE_THRESHOLD_SECONDS

        coord_mgr.register_session("stale-owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_file("stale-owner", "/proj/config.py")
        coord_mgr.announce_intent("waiter", "config update", target_files=["/proj/config.py"])

        # Backdate heartbeat to make it stale
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "stale-owner"),
        )
        coord_mgr._conn.commit()

        coord_mgr.list_sessions(auto_clean=True)

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 1
        assert "config.py" in available_msgs[0]["subject"]

    def test_release_does_not_self_notify(self, coord_mgr):
        """Releasing session should NOT receive its own [AVAILABLE] notification."""
        coord_mgr.register_session("owner", pid=1001, project="/proj")

        coord_mgr.claim_file("owner", "/proj/self.py")
        coord_mgr.announce_intent("owner", "self work", target_files=["/proj/self.py"])

        coord_mgr.release_file("owner", "/proj/self.py")

        msgs = coord_mgr.check_inbox("owner", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 0

    def test_release_notification_fail_open(self, coord_mgr):
        """Notification failures should not propagate — release still succeeds."""
        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_file("owner", "/proj/safe.py")
        coord_mgr.announce_intent("waiter", "safe work", target_files=["/proj/safe.py"])

        # Monkey-patch send_message to raise
        original_send = coord_mgr.send_message
        coord_mgr.send_message = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))

        result = coord_mgr.release_file("owner", "/proj/safe.py")
        assert result["released"] is True

        # Restore
        coord_mgr.send_message = original_send


class TestIntentAnnounceOverlaps:
    """Overlap warnings returned inline from announce_intent()."""

    def test_announce_returns_overlaps(self, coord_mgr):
        """Announcing intent with overlapping files returns overlaps in result."""
        coord_mgr.register_session("sess-1", pid=1001, project="/proj")
        coord_mgr.register_session("sess-2", pid=1002, project="/proj")

        coord_mgr.announce_intent("sess-1", "auth work", target_files=["/proj/shared.py"])
        result = coord_mgr.announce_intent("sess-2", "config work", target_files=["/proj/shared.py"])

        assert result["success"] is True
        assert "overlaps" in result
        assert len(result["overlaps"]) == 1
        assert "/proj/shared.py" in result["overlaps"][0]["overlapping_files"]

    def test_announce_no_overlaps_omits_key(self, coord_mgr):
        """No overlaps means no 'overlaps' key in result."""
        coord_mgr.register_session("sess-1", pid=1001, project="/proj")
        coord_mgr.register_session("sess-2", pid=1002, project="/proj")

        coord_mgr.announce_intent("sess-1", "auth work", target_files=["/proj/auth.py"])
        result = coord_mgr.announce_intent("sess-2", "ui work", target_files=["/proj/ui.py"])

        assert result["success"] is True
        assert "overlaps" not in result

    def test_announce_overlap_branch(self, coord_mgr):
        """Branch overlap is detected and returned."""
        coord_mgr.register_session("sess-1", pid=1001, project="/proj")
        coord_mgr.register_session("sess-2", pid=1002, project="/proj")

        coord_mgr.announce_intent("sess-1", "feature A", target_branch="feat-x")
        result = coord_mgr.announce_intent("sess-2", "feature B", target_branch="feat-x")

        assert result["success"] is True
        assert "overlaps" in result
        assert "feat-x" in result["overlaps"][0]["overlapping_branches"]

    def test_handler_intent_announce_shows_overlap_warning(self, coord_mgr):
        """MCP handler formats overlap warning text."""
        import asyncio
        from unittest.mock import patch
        from omega.server.coord_handlers import handle_intent_announce

        coord_mgr.register_session("sess-1", pid=1001, project="/proj")
        coord_mgr.register_session("sess-2", pid=1002, project="/proj")

        coord_mgr.announce_intent("sess-1", "auth work", target_files=["/proj/shared.py"])

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            result = asyncio.run(
                handle_intent_announce({
                    "session_id": "sess-2",
                    "description": "config work",
                    "target_files": ["/proj/shared.py"],
                })
            )

        # The MCP response text should contain the overlap warning
        response_text = ""
        if result.get("content"):
            response_text = result["content"][0].get("text", "")
        assert "[!]" in response_text
        assert "overlap" in response_text.lower()


class TestExpiredClaimNotifications:
    """Phase 2: Notifications when expired claims are cleaned up."""

    def test_expired_file_claim_notifies_intent_holder(self, coord_mgr):
        """Bulk expired file claim cleanup notifies agents with matching intents."""
        from omega.coordination import CLAIM_TTL_SECONDS

        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_file("owner", "/proj/expired.py")
        coord_mgr.announce_intent("waiter", "need expired.py", target_files=["/proj/expired.py"])

        # Backdate the claim to expire it
        expired_time = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_file_claims SET last_activity = ? WHERE file_path = ?",
            (expired_time, "/proj/expired.py"),
        )
        coord_mgr._conn.commit()

        # Trigger stale cleanup (which also cleans expired claims)
        coord_mgr._clean_stale_sessions()

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 1
        assert "expired.py" in available_msgs[0]["subject"]

    def test_expired_branch_claim_notifies_intent_holder(self, coord_mgr):
        """Bulk expired branch claim cleanup notifies agents with matching intents."""
        from omega.coordination import BRANCH_CLAIM_TTL_SECONDS

        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_branch("owner", "/proj", "feat-old")
        coord_mgr.announce_intent("waiter", "need feat-old", target_branch="feat-old")

        # Backdate the branch claim to expire it
        expired_time = (datetime.now(timezone.utc) - timedelta(seconds=BRANCH_CLAIM_TTL_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_branch_claims SET last_activity = ? WHERE project = ? AND branch = ?",
            (expired_time, "/proj", "feat-old"),
        )
        coord_mgr._conn.commit()

        coord_mgr._clean_stale_sessions()

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 1
        assert "feat-old" in available_msgs[0]["subject"]

    def test_check_file_expired_notifies(self, coord_mgr):
        """check_file() expiring a single claim notifies waiting agents."""
        from omega.coordination import CLAIM_TTL_SECONDS

        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_file("owner", "/proj/stale.py")
        coord_mgr.announce_intent("waiter", "need stale.py", target_files=["/proj/stale.py"])

        # Backdate to expire
        expired_time = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_file_claims SET last_activity = ? WHERE file_path = ?",
            (expired_time, "/proj/stale.py"),
        )
        coord_mgr._conn.commit()

        result = coord_mgr.check_file("/proj/stale.py")
        assert result["expired_claim"] is True

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 1
        assert "stale.py" in available_msgs[0]["subject"]

    def test_check_branch_expired_notifies(self, coord_mgr):
        """check_branch() expiring a single claim notifies waiting agents."""
        from omega.coordination import BRANCH_CLAIM_TTL_SECONDS

        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_branch("owner", "/proj", "feat-stale")
        coord_mgr.announce_intent("waiter", "need feat-stale", target_branch="feat-stale")

        expired_time = (datetime.now(timezone.utc) - timedelta(seconds=BRANCH_CLAIM_TTL_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_branch_claims SET last_activity = ? WHERE project = ? AND branch = ?",
            (expired_time, "/proj", "feat-stale"),
        )
        coord_mgr._conn.commit()

        result = coord_mgr.check_branch("/proj", "feat-stale")
        assert result["expired_claim"] is True

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 1
        assert "feat-stale" in available_msgs[0]["subject"]

    def test_expired_no_intent_no_notification(self, coord_mgr):
        """Expired claims with no matching intents send no notifications."""
        from omega.coordination import CLAIM_TTL_SECONDS

        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("other", pid=1002, project="/proj")

        coord_mgr.claim_file("owner", "/proj/lonely.py")
        coord_mgr.announce_intent("other", "unrelated", target_files=["/proj/other.py"])

        expired_time = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_file_claims SET last_activity = ? WHERE file_path = ?",
            (expired_time, "/proj/lonely.py"),
        )
        coord_mgr._conn.commit()

        coord_mgr.check_file("/proj/lonely.py")

        msgs = coord_mgr.check_inbox("other", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 0

    def test_expired_cleanup_multiple_files_grouped(self, coord_mgr):
        """Multiple expired claims from same session are grouped in notifications."""
        from omega.coordination import CLAIM_TTL_SECONDS

        coord_mgr.register_session("owner", pid=1001, project="/proj")
        coord_mgr.register_session("waiter", pid=1002, project="/proj")

        coord_mgr.claim_file("owner", "/proj/a.py")
        coord_mgr.claim_file("owner", "/proj/b.py")
        coord_mgr.announce_intent(
            "waiter", "need both", target_files=["/proj/a.py", "/proj/b.py"]
        )

        expired_time = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_SECONDS + 60)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_file_claims SET last_activity = ?", (expired_time,)
        )
        coord_mgr._conn.commit()

        coord_mgr._clean_stale_sessions()

        msgs = coord_mgr.check_inbox("waiter", unread_only=True)
        available_msgs = [m for m in msgs if "[AVAILABLE]" in m["subject"]]
        assert len(available_msgs) == 2  # one per file


# ===========================================================================
# Phase 3: Deadlock Push to Affected Sessions
# ===========================================================================


class TestDeadlockPush:
    """Push [DEADLOCK] alerts to all sessions in a cycle via send_message."""

    def test_deadlock_detected_pushes_to_all_sessions(self, coord_mgr):
        """Two sessions in deadlock — both get messages via send_message."""
        from unittest.mock import patch
        import omega.server.hook_server as hs

        coord_mgr.register_session("sess-a", pid=1001, project="/proj")
        coord_mgr.register_session("sess-b", pid=1002, project="/proj")

        # Create circular wait: A wants file held by B, B wants file held by A
        coord_mgr.claim_file("sess-a", "/proj/a.py")
        coord_mgr.claim_file("sess-b", "/proj/b.py")
        coord_mgr.announce_intent("sess-a", "need b.py", target_files=["/proj/b.py"])
        coord_mgr.announce_intent("sess-b", "need a.py", target_files=["/proj/a.py"])

        # Clear any existing inbox messages
        coord_mgr.check_inbox("sess-a", unread_only=True)
        coord_mgr.check_inbox("sess-b", unread_only=True)

        # Simulate heartbeat on 10th count from sess-a
        saved_push = dict(hs._last_deadlock_push)
        hs._last_deadlock_push.clear()
        hs._heartbeat_count["sess-a"] = 9  # next will be 10
        hs._last_heartbeat.pop("sess-a", None)  # bypass heartbeat debounce

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            result = hs.handle_coord_heartbeat({
                "session_id": "sess-a",
                "project": "/proj",
            })

        # Detecting session sees deadlock in hook output
        assert "[DEADLOCK]" in result.get("output", "")

        # sess-b should have a [DEADLOCK] message in inbox
        msgs = coord_mgr.check_inbox("sess-b", unread_only=True)
        deadlock_msgs = [m for m in msgs if "[DEADLOCK]" in m["subject"]]
        assert len(deadlock_msgs) >= 1

        # Restore state
        hs._last_deadlock_push.clear()
        hs._last_deadlock_push.update(saved_push)

    def test_deadlock_push_excludes_detecting_session(self, coord_mgr):
        """Detecting session sees hook output, NOT a duplicate inbox message."""
        from unittest.mock import patch
        import omega.server.hook_server as hs

        coord_mgr.register_session("sess-a", pid=1001, project="/proj")
        coord_mgr.register_session("sess-b", pid=1002, project="/proj")

        coord_mgr.claim_file("sess-a", "/proj/a.py")
        coord_mgr.claim_file("sess-b", "/proj/b.py")
        coord_mgr.announce_intent("sess-a", "need b.py", target_files=["/proj/b.py"])
        coord_mgr.announce_intent("sess-b", "need a.py", target_files=["/proj/a.py"])

        coord_mgr.check_inbox("sess-a", unread_only=True)

        saved_push = dict(hs._last_deadlock_push)
        hs._last_deadlock_push.clear()
        hs._heartbeat_count["sess-a"] = 9
        hs._last_heartbeat.pop("sess-a", None)

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            hs.handle_coord_heartbeat({
                "session_id": "sess-a",
                "project": "/proj",
            })

        # sess-a should NOT get a [DEADLOCK] message in inbox (it's the detector)
        msgs = coord_mgr.check_inbox("sess-a", unread_only=True)
        deadlock_msgs = [m for m in msgs if "[DEADLOCK]" in m["subject"]]
        assert len(deadlock_msgs) == 0

        hs._last_deadlock_push.clear()
        hs._last_deadlock_push.update(saved_push)

    def test_deadlock_push_debounced(self, coord_mgr):
        """Same cycle doesn't spam within 10 min."""
        from unittest.mock import patch
        import omega.server.hook_server as hs

        coord_mgr.register_session("sess-a", pid=1001, project="/proj")
        coord_mgr.register_session("sess-b", pid=1002, project="/proj")

        coord_mgr.claim_file("sess-a", "/proj/a.py")
        coord_mgr.claim_file("sess-b", "/proj/b.py")
        coord_mgr.announce_intent("sess-a", "need b.py", target_files=["/proj/b.py"])
        coord_mgr.announce_intent("sess-b", "need a.py", target_files=["/proj/a.py"])

        coord_mgr.check_inbox("sess-b", unread_only=True)

        saved_push = dict(hs._last_deadlock_push)
        hs._last_deadlock_push.clear()
        hs._heartbeat_count["sess-a"] = 9
        hs._last_heartbeat.pop("sess-a", None)

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            # First detection — should push
            hs.handle_coord_heartbeat({"session_id": "sess-a", "project": "/proj"})

        msgs1 = coord_mgr.check_inbox("sess-b", unread_only=True)
        deadlock_msgs1 = [m for m in msgs1 if "[DEADLOCK]" in m["subject"]]
        assert len(deadlock_msgs1) >= 1

        # Second detection — debounced, should NOT push again
        hs._heartbeat_count["sess-a"] = 19  # next will be 20 (multiple of 10)
        hs._last_heartbeat.pop("sess-a", None)

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            hs.handle_coord_heartbeat({"session_id": "sess-a", "project": "/proj"})

        msgs2 = coord_mgr.check_inbox("sess-b", unread_only=True)
        deadlock_msgs2 = [m for m in msgs2 if "[DEADLOCK]" in m["subject"]]
        assert len(deadlock_msgs2) == 0

        hs._last_deadlock_push.clear()
        hs._last_deadlock_push.update(saved_push)

    def test_no_deadlock_no_messages(self, coord_mgr):
        """No cycle, no messages sent."""
        from unittest.mock import patch
        import omega.server.hook_server as hs

        coord_mgr.register_session("sess-a", pid=1001, project="/proj")
        coord_mgr.register_session("sess-b", pid=1002, project="/proj")

        # No circular wait — only one-directional dependency
        coord_mgr.claim_file("sess-a", "/proj/a.py")

        coord_mgr.check_inbox("sess-b", unread_only=True)

        saved_push = dict(hs._last_deadlock_push)
        hs._last_deadlock_push.clear()
        hs._heartbeat_count["sess-a"] = 9
        hs._last_heartbeat.pop("sess-a", None)

        with patch("omega.coordination.get_manager", return_value=coord_mgr):
            hs.handle_coord_heartbeat({"session_id": "sess-a", "project": "/proj"})

        msgs = coord_mgr.check_inbox("sess-b", unread_only=True)
        deadlock_msgs = [m for m in msgs if "[DEADLOCK]" in m["subject"]]
        assert len(deadlock_msgs) == 0

        hs._last_deadlock_push.clear()
        hs._last_deadlock_push.update(saved_push)


# ===========================================================================
# Phase 3: Git Divergence Check
# ===========================================================================


class TestGitDivergenceCheck:
    """Periodic git divergence check on heartbeat."""

    def test_divergence_check_surfaces_behind_count(self, coord_mgr):
        """When behind upstream, surfaces [GIT] warning."""
        from unittest.mock import patch, MagicMock
        import omega.server.hook_server as hs

        coord_mgr.register_session("sess-a", pid=1001, project="/proj")

        hs._heartbeat_count["sess-a"] = 19  # next will be 20 (multiple of 20)
        hs._last_heartbeat.pop("sess-a", None)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "2\t5\n"  # 2 ahead, 5 behind

        with patch("omega.coordination.get_manager", return_value=coord_mgr), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            result = hs.handle_coord_heartbeat({
                "session_id": "sess-a",
                "project": "/proj",
            })

        output = result.get("output", "")
        assert "[GIT]" in output
        assert "5 commit(s) behind" in output
        assert "2 ahead" in output

        # Verify correct git command was called
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "rev-list" in args[0][0]
        assert args[1]["cwd"] == "/proj"


# ===========================================================================
# Coordination Enforcement: Task Reassignment on Session Exit
# ===========================================================================

class TestDeregisterReassignsTasks:
    """deregister_session() should reassign in-progress tasks to pending."""

    def test_deregister_reassigns_tasks(self, coord_mgr):
        """In-progress tasks are reset to pending when session deregisters."""
        coord_mgr.register_session("sess-1", pid=1234)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Task A")
        t2 = coord_mgr.create_task(created_by="sess-1", title="Task B")
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.claim_task(t2["task_id"], "sess-1")
        coord_mgr.update_task_progress(t1["task_id"], "sess-1", 50)

        result = coord_mgr.deregister_session("sess-1")
        assert result["deregistered"] is True
        assert "reassigned_tasks" in result
        assert len(result["reassigned_tasks"]) == 2

        # Tasks should be pending and unowned
        tasks = coord_mgr.list_tasks(status="pending")
        assert len(tasks) == 2
        for t in tasks:
            assert t["session_id"] is None

    def test_deregister_ignores_completed_tasks(self, coord_mgr):
        """Completed tasks are NOT reassigned on deregister."""
        coord_mgr.register_session("sess-1", pid=1234)
        t = coord_mgr.create_task(created_by="sess-1", title="Done task")
        coord_mgr.claim_task(t["task_id"], "sess-1")
        coord_mgr.complete_task(t["task_id"], "sess-1")

        result = coord_mgr.deregister_session("sess-1")
        assert result["deregistered"] is True
        assert "reassigned_tasks" not in result

    def test_deregister_no_tasks(self, coord_mgr):
        """Deregister with no tasks returns no reassigned_tasks key."""
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.deregister_session("sess-1")
        assert result["deregistered"] is True
        assert "reassigned_tasks" not in result


class TestStaleCleanupReassignsTasks:
    """_clean_stale_sessions() should reassign in-progress tasks to pending."""

    def test_stale_cleanup_reassigns_tasks(self, coord_mgr):
        """Stale session cleanup resets in-progress tasks to pending."""
        from omega.coordination import STALE_THRESHOLD_SECONDS

        coord_mgr.register_session("stale-sess", pid=1111)
        t1 = coord_mgr.create_task(created_by="stale-sess", title="Task X")
        t2 = coord_mgr.create_task(created_by="stale-sess", title="Task Y")
        coord_mgr.claim_task(t1["task_id"], "stale-sess")
        coord_mgr.claim_task(t2["task_id"], "stale-sess")
        coord_mgr.update_task_progress(t1["task_id"], "stale-sess", 30)

        # Backdate heartbeat to make session stale
        stale_time = (
            datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)
        ).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "stale-sess"),
        )
        coord_mgr._conn.commit()

        # Trigger stale cleanup via list_sessions
        sessions = coord_mgr.list_sessions(auto_clean=True)
        assert len(sessions) == 0

        # Tasks should be pending and unowned
        tasks = coord_mgr.list_tasks(status="pending")
        assert len(tasks) == 2
        for t in tasks:
            assert t["session_id"] is None


class TestStaleSessionClaimRecovery:
    """Claims from stale sessions should be reclaimable without force."""

    def test_claim_file_reclaims_from_stale_session(self, coord_mgr):
        """Backdated heartbeat → claim_file succeeds without force."""
        from omega.coordination import STALE_THRESHOLD_SECONDS

        coord_mgr.register_session("stale-sess", pid=1000, project="/proj")
        coord_mgr.claim_file("stale-sess", "/proj/foo.py", task="old work")

        # Backdate heartbeat to make session stale
        stale_time = (
            datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)
        ).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "stale-sess"),
        )
        coord_mgr._conn.commit()

        # New session should reclaim without force
        coord_mgr.register_session("new-sess", pid=2000, project="/proj")
        result = coord_mgr.claim_file("new-sess", "/proj/foo.py", task="new work")
        assert result["success"] is True
        assert result.get("expired_claim_replaced") is True
        assert result.get("reason") == "stale_session"

    def test_check_file_expires_stale_session_claim(self, coord_mgr):
        """Backdated heartbeat → check_file returns unclaimed."""
        from omega.coordination import STALE_THRESHOLD_SECONDS

        coord_mgr.register_session("stale-sess", pid=1000, project="/proj")
        coord_mgr.claim_file("stale-sess", "/proj/bar.py", task="old work")

        # Backdate heartbeat
        stale_time = (
            datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)
        ).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "stale-sess"),
        )
        coord_mgr._conn.commit()

        result = coord_mgr.check_file("/proj/bar.py")
        assert result["claimed"] is False
        assert result.get("expired_claim") is True

    def test_active_session_claim_not_reclaimed(self, coord_mgr):
        """Fresh heartbeat → claim_file returns conflict (regression guard)."""
        coord_mgr.register_session("active-sess", pid=1000, project="/proj")
        coord_mgr.claim_file("active-sess", "/proj/baz.py", task="active work")

        coord_mgr.register_session("new-sess", pid=2000, project="/proj")
        result = coord_mgr.claim_file("new-sess", "/proj/baz.py", task="steal attempt")
        assert result["success"] is False
        assert result["conflict"] is True
        assert result["claimed_by"] == "active-sess"


class TestIntentDeduplication:
    """announce_intent() should merge same-session same-type intents."""

    def test_same_session_same_type_merges(self, coord_mgr):
        """Two announces with same session+type → 1 row."""
        coord_mgr.register_session("sess-1", pid=1000)
        coord_mgr.announce_intent("sess-1", "editing A", intent_type="edit", target_files=["/a.py"])
        result = coord_mgr.announce_intent("sess-1", "editing B", intent_type="edit", target_files=["/b.py"])
        assert result.get("refreshed_intent") is True

        # Should be exactly 1 intent row
        rows = coord_mgr._conn.execute(
            "SELECT COUNT(*) FROM coord_intents WHERE session_id = ? AND intent_type = ?",
            ("sess-1", "edit"),
        ).fetchone()
        assert rows[0] == 1

    def test_different_type_creates_new(self, coord_mgr):
        """edit + refactor → 2 rows."""
        coord_mgr.register_session("sess-1", pid=1000)
        coord_mgr.announce_intent("sess-1", "editing", intent_type="edit", target_files=["/a.py"])
        coord_mgr.announce_intent("sess-1", "refactoring", intent_type="refactor", target_files=["/a.py"])

        rows = coord_mgr._conn.execute(
            "SELECT COUNT(*) FROM coord_intents WHERE session_id = ?",
            ("sess-1",),
        ).fetchone()
        assert rows[0] == 2

    def test_different_session_creates_new(self, coord_mgr):
        """2 sessions with same type → 2 rows."""
        coord_mgr.register_session("sess-1", pid=1000)
        coord_mgr.register_session("sess-2", pid=2000)
        coord_mgr.announce_intent("sess-1", "editing", intent_type="edit", target_files=["/a.py"])
        coord_mgr.announce_intent("sess-2", "editing", intent_type="edit", target_files=["/a.py"])

        rows = coord_mgr._conn.execute(
            "SELECT COUNT(*) FROM coord_intents WHERE intent_type = ?",
            ("edit",),
        ).fetchone()
        assert rows[0] == 2

    def test_merged_intent_has_union_of_files(self, coord_mgr):
        """Verify target_files is the union after merge."""
        import json
        coord_mgr.register_session("sess-1", pid=1000)
        coord_mgr.announce_intent("sess-1", "editing A", intent_type="edit", target_files=["/a.py", "/b.py"])
        coord_mgr.announce_intent("sess-1", "editing C", intent_type="edit", target_files=["/b.py", "/c.py"])

        row = coord_mgr._conn.execute(
            "SELECT target_files FROM coord_intents WHERE session_id = ? AND intent_type = ?",
            ("sess-1", "edit"),
        ).fetchone()
        files = set(json.loads(row[0]))
        assert files == {"/a.py", "/b.py", "/c.py"}


class TestActiveSessionCount:
    """active_session_count() caching and accuracy."""

    def test_zero_when_empty(self, coord_mgr):
        assert coord_mgr.active_session_count() == 0

    def test_one_after_register(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1000)
        # Reset cache so fresh count is fetched
        coord_mgr._session_count_cache_time = 0.0
        assert coord_mgr.active_session_count() == 1

    def test_cache_returns_stale_value(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1000)
        # Prime cache
        coord_mgr._session_count_cache_time = 0.0
        assert coord_mgr.active_session_count() == 1

        # Register second session — cache should still return 1
        coord_mgr.register_session("sess-2", pid=2000)
        assert coord_mgr.active_session_count() == 1

        # Invalidate cache — now returns 2
        coord_mgr._session_count_cache_time = 0.0
        assert coord_mgr.active_session_count() == 2


class TestCoordMetrics:
    """Coordination metrics: record, aggregate, prune, instrumentation."""

    def test_record_metric(self, coord_mgr):
        coord_mgr.record_metric("test_metric", session_id="sess-1", project="/proj/a")
        metrics = coord_mgr.get_metrics(days=1)
        assert "test_metric" in metrics["counts"]
        assert metrics["counts"]["test_metric"] == 1

    def test_record_multiple(self, coord_mgr):
        for _ in range(3):
            coord_mgr.record_metric("multi_metric")
        metrics = coord_mgr.get_metrics(days=1)
        assert metrics["counts"]["multi_metric"] == 3

    def test_get_metrics_empty(self, coord_mgr):
        metrics = coord_mgr.get_metrics(days=1)
        assert metrics["counts"] == {}
        assert metrics["rates"]["conflict_rate"] == 0.0

    def test_conflict_rate(self, coord_mgr):
        for _ in range(10):
            coord_mgr.record_metric("file_claimed")
        for _ in range(2):
            coord_mgr.record_metric("conflict_detected")
        metrics = coord_mgr.get_metrics(days=1)
        assert metrics["rates"]["conflict_rate"] == 20.0
        assert metrics["totals"]["total_claims"] == 10
        assert metrics["totals"]["total_conflicts"] == 2

    def test_gate_skip_rate(self, coord_mgr):
        for _ in range(8):
            coord_mgr.record_metric("gate_check_medium")
        for _ in range(2):
            coord_mgr.record_metric("gate_skipped")
        metrics = coord_mgr.get_metrics(days=1)
        assert metrics["rates"]["gate_skip_rate"] == 20.0
        assert metrics["totals"]["total_gate_checks"] == 8

    def test_handoff_read_rate(self, coord_mgr):
        for _ in range(4):
            coord_mgr.record_metric("handoff_written")
        for _ in range(3):
            coord_mgr.record_metric("handoff_read")
        metrics = coord_mgr.get_metrics(days=1)
        assert metrics["rates"]["handoff_read_rate"] == 75.0

    def test_prune_metrics(self, coord_mgr):
        # Insert a metric with old timestamp
        from datetime import datetime, timedelta, timezone
        old_time = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        coord_mgr._conn.execute(
            "INSERT INTO coord_metrics (metric_name, metric_value, created_at) VALUES (?, ?, ?)",
            ("old_metric", 1, old_time),
        )
        coord_mgr._conn.commit()
        # Also insert a recent one
        coord_mgr.record_metric("recent_metric")

        with coord_mgr._lock:
            pruned = coord_mgr._prune_metrics()
        assert pruned == 1

        metrics = coord_mgr.get_metrics(days=365)
        assert "old_metric" not in metrics["counts"]
        assert "recent_metric" in metrics["counts"]

    def test_project_filter(self, coord_mgr):
        coord_mgr.record_metric("proj_a_metric", project="/proj/a")
        coord_mgr.record_metric("proj_b_metric", project="/proj/b")
        metrics = coord_mgr.get_metrics(days=1, project="/proj/a")
        assert "proj_a_metric" in metrics["counts"]
        assert "proj_b_metric" not in metrics["counts"]

    def test_claim_file_records_metrics(self, coord_mgr):
        """Verify claim_file instruments conflict and claim metrics."""
        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        coord_mgr.register_session("sess-2", pid=2000, project="/proj")
        coord_mgr.claim_file("sess-1", "/proj/foo.py")
        # Second claim = conflict
        result = coord_mgr.claim_file("sess-2", "/proj/foo.py")
        assert result.get("conflict") is True

        metrics = coord_mgr.get_metrics(days=1)
        assert metrics["counts"].get("file_claimed", 0) >= 1
        assert metrics["counts"].get("conflict_detected", 0) >= 1

    def test_deadlock_records_metric(self, coord_mgr):
        """Verify deadlock detection records a metric."""
        coord_mgr.register_session("sess-a", pid=100)
        coord_mgr.register_session("sess-b", pid=200)
        coord_mgr.claim_file("sess-a", "/proj/a.py")
        coord_mgr.claim_file("sess-b", "/proj/b.py")
        coord_mgr.announce_intent("sess-a", "need b", target_files=["/proj/b.py"])
        coord_mgr.announce_intent("sess-b", "need a", target_files=["/proj/a.py"])
        cycles = coord_mgr.detect_deadlocks()
        if cycles:
            metrics = coord_mgr.get_metrics(days=1)
            assert metrics["counts"].get("deadlock_cycle", 0) >= 1


class TestStructuredHandoffs:
    """Structured handoff create, retrieve, read-tracking, prune."""

    def test_create_handoff(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        result = coord_mgr.create_handoff(
            session_id="sess-1",
            project="/proj",
            completed_tasks=["Implemented feature X"],
            decisions_made=["Used approach A over B"],
            next_steps=["Write tests"],
        )
        assert result["id"] is not None
        assert result["session_id"] == "sess-1"
        assert result["project"] == "/proj"

    def test_get_latest_handoff(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        coord_mgr.create_handoff(
            session_id="sess-1",
            project="/proj",
            completed_tasks=["Task A"],
            key_context="Important context",
        )
        handoff = coord_mgr.get_latest_handoff(project="/proj")
        assert handoff is not None
        assert handoff["completed_tasks"] == ["Task A"]
        assert handoff["key_context"] == "Important context"
        assert handoff["session_id"] == "sess-1"

    def test_read_tracking(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        coord_mgr.create_handoff(
            session_id="sess-1",
            project="/proj",
            completed_tasks=["Done"],
        )
        # First read by sess-2
        handoff = coord_mgr.get_latest_handoff(project="/proj", reader_session_id="sess-2")
        assert "sess-2" in handoff["read_by"]

        # Read again — should not duplicate
        handoff2 = coord_mgr.get_latest_handoff(project="/proj", reader_session_id="sess-2")
        assert handoff2["read_by"].count("sess-2") == 1

        # Read by sess-3
        handoff3 = coord_mgr.get_latest_handoff(project="/proj", reader_session_id="sess-3")
        assert "sess-2" in handoff3["read_by"]
        assert "sess-3" in handoff3["read_by"]

    def test_handoff_records_metrics(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        coord_mgr.create_handoff(session_id="sess-1", project="/proj")
        coord_mgr.get_latest_handoff(project="/proj", reader_session_id="sess-2")

        metrics = coord_mgr.get_metrics(days=1)
        assert metrics["counts"].get("handoff_written", 0) >= 1
        assert metrics["counts"].get("handoff_read", 0) >= 1

    def test_auto_enrich_file_claims(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        coord_mgr.claim_file("sess-1", "/proj/foo.py")
        coord_mgr.claim_file("sess-1", "/proj/bar.py")
        result = coord_mgr.create_handoff(session_id="sess-1", project="/proj")
        assert "/proj/foo.py" in result["files_modified"]
        assert "/proj/bar.py" in result["files_modified"]

    def test_get_latest_no_handoffs(self, coord_mgr):
        handoff = coord_mgr.get_latest_handoff(project="/proj")
        assert handoff is None

    def test_ordering(self, coord_mgr):
        """Latest handoff is returned, not the first."""
        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        coord_mgr.create_handoff(
            session_id="sess-1", project="/proj", key_context="first",
        )
        coord_mgr.create_handoff(
            session_id="sess-1", project="/proj", key_context="second",
        )
        handoff = coord_mgr.get_latest_handoff(project="/proj")
        assert handoff["key_context"] == "second"

    def test_prune_handoffs(self, coord_mgr):
        from datetime import datetime, timedelta, timezone
        old_time = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        coord_mgr._conn.execute(
            """INSERT INTO coord_handoffs
               (session_id, project, completed_tasks, created_at)
               VALUES (?, ?, ?, ?)""",
            ("old-sess", "/proj", "[]", old_time),
        )
        coord_mgr._conn.commit()

        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        coord_mgr.create_handoff(session_id="sess-1", project="/proj")

        with coord_mgr._lock:
            pruned = coord_mgr._prune_handoffs()
        assert pruned == 1

        # Recent handoff should survive
        handoff = coord_mgr.get_latest_handoff(project="/proj")
        assert handoff is not None
        assert handoff["session_id"] == "sess-1"

    def test_all_fields_roundtrip(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1000, project="/proj")
        coord_mgr.create_handoff(
            session_id="sess-1",
            project="/proj",
            completed_tasks=["task1", "task2"],
            blocked_items=["blocked1"],
            key_context="critical info",
            next_steps=["step1", "step2"],
            files_modified=["/proj/a.py"],
            decisions_made=["decision1"],
        )
        handoff = coord_mgr.get_latest_handoff(project="/proj")
        assert handoff["completed_tasks"] == ["task1", "task2"]
        assert handoff["blocked_items"] == ["blocked1"]
        assert handoff["key_context"] == "critical info"
        assert handoff["next_steps"] == ["step1", "step2"]
        assert handoff["files_modified"] == ["/proj/a.py"]
        assert handoff["decisions_made"] == ["decision1"]


class TestRiskClassification:
    """Risk tier classification for coordination gate."""

    def test_deploy_is_high(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "vercel deploy --prod") == "HIGH"
        assert classify_action_risk("Bash", "vercel --prod") == "HIGH"
        assert classify_action_risk("Bash", "fly deploy") == "HIGH"

    def test_force_push_is_high(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "git push origin main --force") == "HIGH"
        assert classify_action_risk("Bash", "git push -f origin main") == "HIGH"

    def test_destructive_is_high(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "rm -rf /tmp/foo") == "HIGH"
        assert classify_action_risk("Bash", "git reset --hard HEAD~1") == "HIGH"
        assert classify_action_risk("Bash", "git branch -D feature") == "HIGH"

    def test_commit_is_medium(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", 'git commit -m "fix"') == "MEDIUM"

    def test_push_is_medium(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "git push origin main") == "MEDIUM"

    def test_branch_create_is_medium(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "git checkout -b feature") == "MEDIUM"
        assert classify_action_risk("Bash", "git switch -c feature") == "MEDIUM"

    def test_install_is_medium(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "npm install lodash") == "MEDIUM"
        assert classify_action_risk("Bash", "pip install requests") == "MEDIUM"

    def test_pytest_is_low(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "pytest -x tests/") == "LOW"

    def test_git_status_is_low(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "git status") == "LOW"
        assert classify_action_risk("Bash", "git diff") == "LOW"

    def test_non_bash_is_low(self):
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Edit", "") == "LOW"
        assert classify_action_risk("Read", "") == "LOW"
        assert classify_action_risk("Grep", "") == "LOW"

    def test_force_push_beats_regular_push(self):
        """Force push should be HIGH, not MEDIUM (HIGH patterns checked first)."""
        from omega.server.hook_server import classify_action_risk
        assert classify_action_risk("Bash", "git push --force origin main") == "HIGH"


class TestFileReadTracking:
    """Tests for record_file_read() — input side of the pipeline."""

    def test_record_file_read_basic(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        result = coord_mgr.record_file_read("sess-1", "/proj/foo.py")
        assert result["success"] is True
        assert result["file_path"] == "/proj/foo.py"

    def test_record_file_read_increments_count(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.record_file_read("sess-1", "/proj/foo.py")
        coord_mgr.record_file_read("sess-1", "/proj/foo.py")
        coord_mgr.record_file_read("sess-1", "/proj/foo.py")

        # Read the count from the database directly
        row = coord_mgr._conn.execute(
            "SELECT read_count FROM coord_file_reads WHERE session_id = ? AND file_path = ?",
            ("sess-1", "/proj/foo.py"),
        ).fetchone()
        assert row is not None
        assert row[0] == 3

    def test_record_file_read_auto_registers(self, coord_mgr):
        """Recording a file read with an unregistered session auto-registers it."""
        result = coord_mgr.record_file_read("unregistered", "/proj/bar.py")
        assert result["success"] is True
        sessions = coord_mgr.list_sessions(auto_clean=False)
        sids = {s["session_id"] for s in sessions}
        assert "unregistered" in sids

    def test_record_file_read_multiple_sessions(self, coord_mgr):
        """Multiple sessions can read the same file (no exclusive ownership)."""
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.register_session("sess-2", pid=5678)
        r1 = coord_mgr.record_file_read("sess-1", "/proj/shared.py")
        r2 = coord_mgr.record_file_read("sess-2", "/proj/shared.py")
        assert r1["success"] is True
        assert r2["success"] is True

        rows = coord_mgr._conn.execute(
            "SELECT session_id FROM coord_file_reads WHERE file_path = ?",
            ("/proj/shared.py",),
        ).fetchall()
        assert len(rows) == 2

    def test_deregister_releases_file_reads(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234)
        coord_mgr.record_file_read("sess-1", "/proj/foo.py")
        coord_mgr.record_file_read("sess-1", "/proj/bar.py")

        coord_mgr.deregister_session("sess-1")

        rows = coord_mgr._conn.execute(
            "SELECT * FROM coord_file_reads WHERE session_id = ?", ("sess-1",)
        ).fetchall()
        assert len(rows) == 0


def test_coord_messages_has_priority_columns(tmp_path):
    """v11 migration adds priority, batch_id, delivered_at to coord_messages."""
    from omega.coordination import CoordinationManager

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"), cloud_sync=False)
    # Check columns exist
    with mgr._lock:
        cols = [
            row[1]
            for row in mgr._conn.execute("PRAGMA table_info(coord_messages)").fetchall()
        ]
    assert "priority" in cols
    assert "batch_id" in cols
    assert "delivered_at" in cols
    mgr.close()


def test_send_message_critical_delivered_immediately(tmp_path):
    """Critical messages set delivered_at immediately."""
    from omega.coordination import CoordinationManager

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"), cloud_sync=False)
    mgr.register_session("sender", pid=1, project="test")
    mgr.register_session("receiver", pid=2, project="test")

    result = mgr.send_message(
        from_session="sender",
        subject="urgent",
        msg_type="inform",
        to_session="receiver",
        priority="critical",
    )
    assert result["success"]

    # Check delivered_at is set
    with mgr._lock:
        row = mgr._conn.execute(
            "SELECT priority, delivered_at FROM coord_messages WHERE id = ?",
            (result["message_id"],),
        ).fetchone()
    assert row[0] == "critical"
    assert row[1] is not None  # delivered_at is set
    mgr.close()


def test_send_message_medium_not_delivered(tmp_path):
    """Medium priority messages have delivered_at = NULL (pending batch)."""
    from omega.coordination import CoordinationManager

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"), cloud_sync=False)
    mgr.register_session("sender", pid=1, project="test")
    mgr.register_session("receiver", pid=2, project="test")

    result = mgr.send_message(
        from_session="sender",
        subject="routine update",
        msg_type="inform",
        to_session="receiver",
        priority="medium",
    )
    assert result["success"]

    with mgr._lock:
        row = mgr._conn.execute(
            "SELECT priority, delivered_at FROM coord_messages WHERE id = ?",
            (result["message_id"],),
        ).fetchone()
    assert row[0] == "medium"
    assert row[1] is None  # not yet delivered
    mgr.close()


def test_send_message_default_priority_is_medium(tmp_path):
    """Default priority (no param) = medium for backwards compat."""
    from omega.coordination import CoordinationManager

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"), cloud_sync=False)
    mgr.register_session("sender", pid=1, project="test")
    mgr.register_session("receiver", pid=2, project="test")

    result = mgr.send_message(
        from_session="sender",
        subject="no priority specified",
        msg_type="inform",
        to_session="receiver",
    )
    assert result["success"]

    with mgr._lock:
        row = mgr._conn.execute(
            "SELECT priority FROM coord_messages WHERE id = ?",
            (result["message_id"],),
        ).fetchone()
    assert row[0] == "medium"
    mgr.close()


def test_flush_notification_batch(tmp_path):
    """flush_notification_batch delivers pending high-priority messages."""
    from omega.coordination import CoordinationManager
    from datetime import datetime, timezone, timedelta

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"), cloud_sync=False)
    mgr.register_session("sender", pid=1, project="test")
    mgr.register_session("receiver", pid=2, project="test")

    # Send a high-priority message
    result = mgr.send_message(
        from_session="sender",
        subject="high prio update",
        msg_type="inform",
        to_session="receiver",
        priority="high",
    )
    msg_id = result["message_id"]

    # Backdate created_at to 2 hours ago so it's past the 1h cutoff
    two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with mgr._lock:
        mgr._conn.execute(
            "UPDATE coord_messages SET created_at = ? WHERE id = ?",
            (two_hours_ago, msg_id),
        )
        mgr._conn.commit()

    # Flush
    flushed = mgr.flush_notification_batch()
    assert flushed > 0

    # Verify delivered_at is now set
    with mgr._lock:
        row = mgr._conn.execute(
            "SELECT delivered_at, batch_id FROM coord_messages WHERE id = ?",
            (msg_id,),
        ).fetchone()
    assert row[0] is not None
    assert row[1] is not None  # batch_id assigned
    mgr.close()
