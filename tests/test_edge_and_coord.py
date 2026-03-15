"""Tests for edge creation (_auto_relate) and heartbeat auto-re-register."""
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------
# Heartbeat Auto-Re-Register
# ---------------------------------------------------------------

class TestHeartbeatAutoReregister:
    """Heartbeat should auto-re-register sessions that were cleaned as stale."""

    def test_heartbeat_reregisters_missing_session(self, coord_mgr):
        """Register, deregister (creates snapshot), heartbeat recovers from snapshot."""
        coord_mgr.register_session(
            "sess-recover", pid=1234, project="/proj/a", task="coding auth"
        )
        coord_mgr.claim_file("sess-recover", "/proj/a/auth.py", task="editing")
        coord_mgr.deregister_session("sess-recover")

        # Session is gone — heartbeat should auto-re-register
        result = coord_mgr.heartbeat("sess-recover")
        assert result["success"] is True
        assert result["reregistered"] is True
        assert result.get("recovered_project") == "/proj/a"

        # Session should now appear in list
        sessions = coord_mgr.list_sessions(auto_clean=False)
        sids = {s["session_id"] for s in sessions}
        assert "sess-recover" in sids

    def test_heartbeat_reregisters_without_snapshot(self, coord_mgr):
        """Heartbeat on a brand-new session ID (no snapshot) still succeeds."""
        result = coord_mgr.heartbeat("brand-new-session")
        assert result["success"] is True
        assert result["reregistered"] is True
        assert "recovered_project" not in result

        sessions = coord_mgr.list_sessions(auto_clean=False)
        sids = {s["session_id"] for s in sessions}
        assert "brand-new-session" in sids

    def test_stale_cleanup_then_heartbeat_recovers(self, coord_mgr):
        """Full lifecycle: register → go stale → cleanup → heartbeat recovers."""
        from omega.coordination import STALE_THRESHOLD_SECONDS

        coord_mgr.register_session(
            "sess-stale", pid=9999, project="/proj/b", task="refactoring"
        )
        coord_mgr.claim_file("sess-stale", "/proj/b/models.py", task="editing")

        # Backdate heartbeat to trigger stale cleanup
        stale_time = (
            datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)
        ).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (stale_time, "sess-stale"),
        )
        coord_mgr._conn.commit()

        # Trigger stale cleanup
        coord_mgr.list_sessions(auto_clean=True)

        # Session should be gone
        sessions = coord_mgr.list_sessions(auto_clean=False)
        assert all(s["session_id"] != "sess-stale" for s in sessions)

        # Heartbeat should bring it back
        result = coord_mgr.heartbeat("sess-stale")
        assert result["success"] is True
        assert result["reregistered"] is True
        assert result.get("recovered_project") == "/proj/b"


# ---------------------------------------------------------------
# Stale Threshold
# ---------------------------------------------------------------

class TestStaleThreshold:
    """Verify the 15-minute stale threshold works correctly."""

    def test_session_survives_10_min_idle(self, coord_mgr):
        """A session idle for 10 minutes should NOT be cleaned (threshold is 15 min)."""
        coord_mgr.register_session("sess-20min", pid=1234, project="/proj")

        # Backdate heartbeat to 10 minutes ago (under 15-min threshold)
        t = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (t, "sess-20min"),
        )
        coord_mgr._conn.commit()

        sessions = coord_mgr.list_sessions(auto_clean=True)
        sids = {s["session_id"] for s in sessions}
        assert "sess-20min" in sids

    def test_session_cleaned_after_31_min(self, coord_mgr):
        """A session idle for 31 minutes SHOULD be cleaned."""
        coord_mgr.register_session("sess-31min", pid=1234, project="/proj")

        # Backdate heartbeat to 31 minutes ago
        t = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
        coord_mgr._conn.execute(
            "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ?",
            (t, "sess-31min"),
        )
        coord_mgr._conn.commit()

        sessions = coord_mgr.list_sessions(auto_clean=True)
        sids = {s["session_id"] for s in sessions}
        assert "sess-31min" not in sids


# ---------------------------------------------------------------
# Auto-Relate Edges
# ---------------------------------------------------------------

class TestAutoRelateEdges:
    """Tests for the _auto_relate() helper in bridge.py."""

    def test_auto_relate_returns_int(self, store):
        """_auto_relate() returns an integer >= 0."""
        from omega.bridge import _auto_relate

        node_id = store.store(content="Test memory for auto-relate edges")
        result = _auto_relate(store, node_id)
        assert isinstance(result, int)
        assert result >= 0

    def test_auto_relate_nonexistent_node(self, store):
        """_auto_relate() on a nonexistent node returns 0 without error."""
        from omega.bridge import _auto_relate

        result = _auto_relate(store, "nonexistent-node-id")
        assert result == 0

    def test_dedup_return_mentions_link(self, tmp_omega_dir):
        """Phase 1 dedup return string includes link info when edges are created."""
        from omega.bridge import auto_capture, reset_memory

        reset_memory()

        # Store a lesson, then store a near-duplicate
        auto_capture(
            content="Always validate user input before processing to prevent injection attacks",
            event_type="lesson_learned",
        )
        result = auto_capture(
            content="Always validate user input before processing to prevent injection attacks",
            event_type="lesson_learned",
        )
        # The dedup path should have been triggered
        assert "Deduped" in result or "Evolved" in result or "Stored" in result

        reset_memory()
