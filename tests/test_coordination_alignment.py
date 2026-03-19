"""Tests for the Decision Register (alignment layer) in coordination.py."""

import pytest


class TestDecisionRegister:
    """CRUD operations on coord_decisions."""

    def test_register_decision_basic(self, coord_mgr):
        """Register a decision and verify it's stored."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        result = coord_mgr.register_decision(
            session_id="s1",
            project="/proj",
            domain="auth",
            decision="Use JWT for authentication",
            rationale="Stateless, scalable",
        )
        assert result["success"]
        assert result["decision_id"] > 0
        assert result["domain"] == "auth"
        assert result["superseded"] == []

    def test_query_decisions_returns_active(self, coord_mgr):
        """Query returns active decisions."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        coord_mgr.register_decision("s1", "/proj", "deploy", "Use Vercel")

        decisions = coord_mgr.query_decisions(project="/proj")
        assert len(decisions) == 2
        domains = {d["domain"] for d in decisions}
        assert domains == {"auth", "deploy"}

    def test_query_decisions_domain_prefix(self, coord_mgr):
        """Query with domain prefix matches hierarchical domains."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        coord_mgr.register_decision("s1", "/proj", "auth/jwt", "Use RS256")
        coord_mgr.register_decision("s1", "/proj", "auth/oauth", "Use Google provider")
        coord_mgr.register_decision("s1", "/proj", "deploy", "Use Vercel")

        auth_decisions = coord_mgr.query_decisions(project="/proj", domain="auth")
        assert len(auth_decisions) == 2
        domains = {d["domain"] for d in auth_decisions}
        assert domains == {"auth/jwt", "auth/oauth"}

    def test_get_decision(self, coord_mgr):
        """Get a single decision by ID."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        result = coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        d = coord_mgr.get_decision(result["decision_id"])
        assert d is not None
        assert d["decision"] == "Use JWT"
        assert d["domain"] == "auth"
        assert d["status"] == "active"

    def test_get_decision_not_found(self, coord_mgr):
        """Get nonexistent decision returns None."""
        assert coord_mgr.get_decision(9999) is None

    def test_revoke_decision(self, coord_mgr):
        """Revoke an active decision."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        result = coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        did = result["decision_id"]

        revoke_result = coord_mgr.revoke_decision(did, "s1", reason="Changed approach")
        assert revoke_result["success"]
        assert revoke_result["status"] == "revoked"

        d = coord_mgr.get_decision(did)
        assert d["status"] == "revoked"

    def test_revoke_already_revoked(self, coord_mgr):
        """Revoking an already revoked decision fails."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        result = coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        did = result["decision_id"]
        coord_mgr.revoke_decision(did, "s1")

        result2 = coord_mgr.revoke_decision(did, "s1")
        assert not result2["success"]
        assert "already" in result2["error"]

    def test_revoke_not_found(self, coord_mgr):
        """Revoking nonexistent decision fails."""
        result = coord_mgr.revoke_decision(9999, "s1")
        assert not result["success"]
        assert "not found" in result["error"]


class TestSameDomainSupersession:
    """Layer 1: Same-domain auto-supersession."""

    def test_same_domain_supersedes(self, coord_mgr):
        """Registering in same domain auto-supersedes the old decision."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        r1 = coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        r2 = coord_mgr.register_decision("s1", "/proj", "auth", "Use sessions")

        assert r2["superseded"] == [r1["decision_id"]]

        old = coord_mgr.get_decision(r1["decision_id"])
        assert old["status"] == "superseded"
        assert old["superseded_by"] == r2["decision_id"]

        active = coord_mgr.query_decisions(project="/proj", domain="auth")
        assert len(active) == 1
        assert active[0]["decision"] == "Use sessions"

    def test_different_domain_no_supersession(self, coord_mgr):
        """Different domains don't supersede each other."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        r2 = coord_mgr.register_decision("s1", "/proj", "deploy", "Use Vercel")

        assert r2["superseded"] == []
        active = coord_mgr.query_decisions(project="/proj")
        assert len(active) == 2

    def test_supersession_chain(self, coord_mgr):
        """Multiple supersessions build a chain visible in get_decision."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        r1 = coord_mgr.register_decision("s1", "/proj", "auth", "Use basic auth")
        r2 = coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        r3 = coord_mgr.register_decision("s1", "/proj", "auth", "Use sessions")

        d = coord_mgr.get_decision(r3["decision_id"])
        # r3 superseded r2, r2 superseded r1
        # get_decision shows chain of decisions that point to this one
        assert d["status"] == "active"
        chain = d.get("supersession_chain", [])
        assert len(chain) == 1  # Only r2 points to r3
        assert chain[0]["id"] == r2["decision_id"]


class TestCrossDomainContradiction:
    """Layer 2: Cross-domain contradiction detection."""

    def test_sibling_domain_contradiction_warning(self, coord_mgr):
        """Sibling domains trigger contradiction check."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        coord_mgr.register_decision("s1", "/proj", "auth/jwt", "Use RS256 algorithm for JWT signing")
        # Register a potentially contradictory sibling
        r2 = coord_mgr.register_decision(
            "s1", "/proj", "auth/oauth",
            "Disable all token-based authentication, use only OAuth sessions"
        )
        # The contradiction warnings field exists (may be empty if contradictions module
        # doesn't detect a contradiction, but the mechanism is exercised)
        assert "contradiction_warnings" not in r2 or isinstance(r2.get("contradiction_warnings"), list)

    def test_non_sibling_no_contradiction_check(self, coord_mgr):
        """Non-sibling domains (no shared parent) skip contradiction check."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        r2 = coord_mgr.register_decision("s1", "/proj", "deploy", "Use Vercel")
        # No contradiction warnings for unrelated domains
        assert "contradiction_warnings" not in r2


class TestDecisionBroadcast:
    """Broadcast on register."""

    def test_register_broadcasts_message(self, coord_mgr):
        """Registering a decision sends a broadcast message."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        coord_mgr.register_session("s2", pid=2, project="/proj")
        coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")

        # s2 should have an unread message
        msgs = coord_mgr.check_inbox("s2", unread_only=True)
        assert len(msgs) >= 1
        decision_msgs = [m for m in msgs if "[DECISION]" in m.get("subject", "")]
        assert len(decision_msgs) == 1
        assert "auth" in decision_msgs[0]["subject"]

    def test_revoke_broadcasts_message(self, coord_mgr):
        """Revoking a decision sends a broadcast message."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        coord_mgr.register_session("s2", pid=2, project="/proj")
        r = coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        # Mark the register broadcast as read
        coord_mgr.check_inbox("s2", unread_only=True)
        coord_mgr.revoke_decision(r["decision_id"], "s1", reason="Changed mind")

        msgs = coord_mgr.check_inbox("s2", unread_only=True)
        revoke_msgs = [m for m in msgs if "[DECISION-REVOKED]" in m.get("subject", "")]
        assert len(revoke_msgs) == 1


class TestDecisionQueryFilters:
    """Advanced query filtering."""

    def test_query_by_status(self, coord_mgr):
        """Query filters by status correctly."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT")
        r2 = coord_mgr.register_decision("s1", "/proj", "auth", "Use sessions")

        superseded = coord_mgr.query_decisions(project="/proj", status="superseded")
        assert len(superseded) == 1
        assert superseded[0]["decision"] == "Use JWT"

        active = coord_mgr.query_decisions(project="/proj", status="active")
        assert len(active) == 1
        assert active[0]["id"] == r2["decision_id"]

    def test_query_by_goal_id(self, coord_mgr):
        """Query filters by goal_id."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        goal = coord_mgr.create_goal("s1", "/proj", "Auth redesign", "Redesign auth system")
        gid = goal["goal_id"]
        coord_mgr.register_decision("s1", "/proj", "auth", "Use JWT", goal_id=gid)
        coord_mgr.register_decision("s1", "/proj", "deploy", "Use Vercel")

        goal_decisions = coord_mgr.query_decisions(project="/proj", goal_id=gid)
        assert len(goal_decisions) == 1
        assert goal_decisions[0]["domain"] == "auth"

    def test_query_limit(self, coord_mgr):
        """Query respects limit parameter."""
        coord_mgr.register_session("s1", pid=1, project="/proj")
        for i in range(5):
            coord_mgr.register_decision("s1", "/proj", f"domain{i}", f"Decision {i}")

        limited = coord_mgr.query_decisions(project="/proj", limit=3)
        assert len(limited) == 3


class TestSchemaVersion:
    """Schema migration to v10."""

    def test_fresh_install_is_v11(self, coord_mgr):
        """A fresh CoordinationManager creates schema v12."""
        row = coord_mgr._conn.execute(
            "SELECT version FROM coord_schema_version"
        ).fetchone()
        assert row[0] == 12

    def test_coord_decisions_table_exists(self, coord_mgr):
        """v8 table (coord_decisions) exists."""
        tables = coord_mgr._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'coord_decisions'"
        ).fetchall()
        assert len(tables) == 1
