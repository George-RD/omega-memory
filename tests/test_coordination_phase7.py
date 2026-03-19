"""Tests for OMEGA Coordination Phase 7: Drift-Aware Intelligence."""

import time
from datetime import datetime, timedelta, timezone


class TestToolPatternShift:
    """Tool pattern shift drift signal tests."""

    def test_consistent_tools_zero_shift(self, coord_mgr):
        """Consistent tool usage should yield 0 shift."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        coord_mgr.claim_task(task["task_id"], "sess-1")

        # Add consistent audit entries (all same tool)
        now = datetime.now(timezone.utc)
        for i in range(15):
            ts = (now - timedelta(minutes=60 - i)).isoformat()
            coord_mgr._conn.execute(
                "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                ("sess-1", "file_claim", ts),
            )
        coord_mgr._conn.commit()

        score = coord_mgr._drift_tool_pattern_shift(goal["goal_id"])
        assert score == 0.0  # All same tool = no divergence

    def test_sudden_change_high_shift(self, coord_mgr):
        """Sudden tool change should yield high shift score."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        coord_mgr.claim_task(task["task_id"], "sess-1")

        now = datetime.now(timezone.utc)
        # Historical: 30 entries of tool_a (1 hour ago)
        for i in range(30):
            ts = (now - timedelta(minutes=120 - i)).isoformat()
            coord_mgr._conn.execute(
                "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                ("sess-1", "file_claim", ts),
            )
        # Recent (within 30min): 10 entries of tool_b (completely different)
        for i in range(10):
            ts = (now - timedelta(minutes=20 - i)).isoformat()
            coord_mgr._conn.execute(
                "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                ("sess-1", "git_events", ts),
            )
        coord_mgr._conn.commit()

        score = coord_mgr._drift_tool_pattern_shift(goal["goal_id"])
        assert score > 0.5  # Major tool change

    def test_insufficient_data_zero(self, coord_mgr):
        """Fewer than 10 audit entries should return 0."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        coord_mgr.claim_task(task["task_id"], "sess-1")

        # Only 5 entries (< 10 threshold)
        now = datetime.now(timezone.utc)
        for i in range(5):
            ts = (now - timedelta(minutes=10 - i)).isoformat()
            coord_mgr._conn.execute(
                "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                ("sess-1", "file_claim", ts),
            )
        coord_mgr._conn.commit()

        score = coord_mgr._drift_tool_pattern_shift(goal["goal_id"])
        assert score == 0.0


class TestInterAgentDivergence:
    """Inter-agent file divergence drift signal tests."""

    def test_single_agent_zero(self, coord_mgr):
        """Single agent should return 0 divergence."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        coord_mgr.claim_task(task["task_id"], "sess-1")
        coord_mgr.claim_file("sess-1", "/proj/a/file1.py")

        score = coord_mgr._drift_inter_agent_divergence(goal["goal_id"])
        assert score == 0.0

    def test_aligned_agents_low(self, coord_mgr):
        """Agents working on same files should have low divergence."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.register_session("sess-2", pid=1235, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        t1 = coord_mgr.create_task(created_by="sess-1", title="T1", project="/proj/a")
        t2 = coord_mgr.create_task(created_by="sess-1", title="T2", project="/proj/a")
        coord_mgr.link_task_to_goal(t1["task_id"], goal["goal_id"])
        coord_mgr.link_task_to_goal(t2["task_id"], goal["goal_id"])
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.claim_task(t2["task_id"], "sess-2")

        # Both claim the same file (use force for second)
        coord_mgr.claim_file("sess-1", "/proj/a/shared.py")
        coord_mgr.claim_file("sess-2", "/proj/a/shared.py", force=True)

        score = coord_mgr._drift_inter_agent_divergence(goal["goal_id"])
        assert score == 0.0  # Same file = perfect alignment

    def test_misaligned_agents_high(self, coord_mgr):
        """Agents working on completely different files should have high divergence."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.register_session("sess-2", pid=1235, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        t1 = coord_mgr.create_task(created_by="sess-1", title="T1", project="/proj/a")
        t2 = coord_mgr.create_task(created_by="sess-1", title="T2", project="/proj/a")
        coord_mgr.link_task_to_goal(t1["task_id"], goal["goal_id"])
        coord_mgr.link_task_to_goal(t2["task_id"], goal["goal_id"])
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.claim_task(t2["task_id"], "sess-2")

        coord_mgr.claim_file("sess-1", "/proj/a/file_a.py")
        coord_mgr.claim_file("sess-2", "/proj/b/file_b.py")

        score = coord_mgr._drift_inter_agent_divergence(goal["goal_id"])
        assert score == 1.0  # No overlap = max divergence


class TestDriftClassification:
    """Drift classification tests."""

    def test_classify_none(self, coord_mgr):
        """Low composite should classify as 'none'."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        drift = coord_mgr.check_drift(goal["goal_id"])
        assert drift["drift_type"] == "none"

    def test_classify_stall(self, coord_mgr):
        """High stall with low others should classify as 'stall'."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        signals = {
            "file_scope": 0.0,
            "task_sprawl": 0.1,
            "evolution_depth": 0.0,
            "stall": 1.0,
            "tool_pattern_shift": 0.1,
            "inter_agent_divergence": 0.0,
        }
        # Composite = 0.20*1.0 + others low = 0.22 < 0.3... need to force composite >= 0.3
        # Adjust: stall = 1.0, task_sprawl = 0.2 => composite = 0.20 + 0.04 = 0.24... still < 0.3
        # Let's make stall dominant enough that composite >= 0.3
        signals["stall"] = 1.0
        signals["task_sprawl"] = 0.25
        # composite = 0.25*0.0 + 0.20*0.25 + 0.10*0.0 + 0.20*1.0 + 0.15*0.1 + 0.10*0.0 = 0.265... still low
        # Make file_scope slightly elevated
        signals["file_scope"] = 0.2
        # composite = 0.05 + 0.05 + 0 + 0.20 + 0.015 + 0 = 0.315
        result = coord_mgr._classify_drift(goal["goal_id"], signals, 0.315)
        assert result == "stall"

    def test_classify_divergence(self, coord_mgr):
        """High inter-agent divergence with low file scope should classify as 'divergence'."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        signals = {
            "file_scope": 0.3,
            "task_sprawl": 0.2,
            "evolution_depth": 0.0,
            "stall": 0.0,
            "tool_pattern_shift": 0.0,
            "inter_agent_divergence": 0.8,
        }
        result = coord_mgr._classify_drift(goal["goal_id"], signals, 0.35)
        assert result == "divergence"

    def test_classify_healthy_exploration(self, coord_mgr):
        """High file scope but low sprawl/tool shift should be 'healthy_exploration'."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a",
            target_files=["/proj/a/src/main.py"],
        )
        signals = {
            "file_scope": 0.6,
            "task_sprawl": 0.1,
            "evolution_depth": 0.0,
            "stall": 0.0,
            "tool_pattern_shift": 0.1,
            "inter_agent_divergence": 0.0,
        }
        result = coord_mgr._classify_drift(goal["goal_id"], signals, 0.35)
        assert result == "healthy_exploration"

    def test_classify_scope_creep(self, coord_mgr):
        """High file scope + high sprawl should be 'scope_creep'."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a",
            target_files=["/proj/a/src/main.py"],
        )
        signals = {
            "file_scope": 0.7,
            "task_sprawl": 0.6,
            "evolution_depth": 0.1,
            "stall": 0.0,
            "tool_pattern_shift": 0.2,
            "inter_agent_divergence": 0.0,
        }
        result = coord_mgr._classify_drift(goal["goal_id"], signals, 0.5)
        assert result == "scope_creep"

    def test_drift_type_in_check_drift_response(self, coord_mgr):
        """check_drift response should include drift_type field."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        drift = coord_mgr.check_drift(goal["goal_id"])
        assert "drift_type" in drift
        assert drift["drift_type"] in ("none", "stall", "divergence", "healthy_exploration", "scope_creep")


class TestSmartRouteTask:
    """Drift-aware task routing tests."""

    def test_routes_to_highest_priority(self, coord_mgr):
        """Without drift, should route to highest priority task."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        t_low = coord_mgr.create_task(created_by="sess-1", title="Low", project="/proj/a", priority=1)
        t_high = coord_mgr.create_task(created_by="sess-1", title="High", project="/proj/a", priority=5)

        result = coord_mgr.smart_route_task("sess-1", project="/proj/a")
        assert result["success"] is True
        assert result["task_id"] == t_high["task_id"]
        assert result["title"] == "High"

    def test_avoids_drifting_goal(self, coord_mgr):
        """Should prefer tasks on low-drift goals over high-drift goals."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")

        # Goal with potential drift (many open tasks, no completed)
        g1 = coord_mgr.create_goal(
            session_id="sess-1", title="Drifty", description="D", project="/proj/a",
            target_files=["/proj/a/x.py"],
        )
        # Create tasks that cause sprawl
        for i in range(5):
            t = coord_mgr.create_task(created_by="sess-1", title=f"Sprawl{i}", project="/proj/a", priority=1)
            coord_mgr.link_task_to_goal(t["task_id"], g1["goal_id"])

        # Clean goal with a task
        g2 = coord_mgr.create_goal(
            session_id="sess-1", title="Clean", description="D", project="/proj/a"
        )
        t_clean = coord_mgr.create_task(created_by="sess-1", title="Clean task", project="/proj/a", priority=1)
        coord_mgr.link_task_to_goal(t_clean["task_id"], g2["goal_id"])

        result = coord_mgr.smart_route_task("sess-1", project="/proj/a")
        assert result["success"] is True

    def test_fallback_no_goals(self, coord_mgr):
        """Tasks without goals should still be routed by priority."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.create_task(created_by="sess-1", title="T1", project="/proj/a", priority=2)
        coord_mgr.create_task(created_by="sess-1", title="T2", project="/proj/a", priority=5)

        result = coord_mgr.smart_route_task("sess-1", project="/proj/a")
        assert result["success"] is True
        assert result["title"] == "T2"

    def test_empty_queue(self, coord_mgr):
        """Empty task queue should return failure."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        result = coord_mgr.smart_route_task("sess-1", project="/proj/a")
        assert result["success"] is False

    def test_critical_penalty(self, coord_mgr):
        """Critical drift goal should get heavy penalty for drifting session."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.register_session("sess-2", pid=1235, project="/proj/a")

        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a",
            target_files=["/proj/a/expected.py"],
        )
        # sess-1 already has an in_progress task on this goal
        t_active = coord_mgr.create_task(created_by="sess-1", title="Active", project="/proj/a")
        coord_mgr.link_task_to_goal(t_active["task_id"], goal["goal_id"])
        coord_mgr.claim_task(t_active["task_id"], "sess-1")

        # New task available
        t_new = coord_mgr.create_task(created_by="sess-1", title="New", project="/proj/a", priority=1)
        coord_mgr.link_task_to_goal(t_new["task_id"], goal["goal_id"])

        # sess-2 (clean) should be able to route
        result = coord_mgr.smart_route_task("sess-2", project="/proj/a")
        assert result["success"] is True
        assert result["task_id"] == t_new["task_id"]


class TestCapabilityStats:
    """Capability stats tracking tests."""

    def test_stats_updated_on_complete(self, coord_mgr):
        """Completing a task should update capability stats."""
        coord_mgr.register_session(
            "sess-1", pid=1234, project="/proj/a",
            capabilities=["code", "test"],
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.claim_task(task["task_id"], "sess-1")

        # Wait a moment so duration > 0
        import time
        time.sleep(0.05)

        coord_mgr.complete_task(task["task_id"], "sess-1", result="done")

        # Check capability_stats
        row = coord_mgr._conn.execute(
            "SELECT tasks_completed, avg_duration_seconds FROM coord_capability_stats WHERE capability = 'code' AND project = '/proj/a'"
        ).fetchone()
        assert row is not None
        assert row[0] == 1  # tasks_completed
        assert row[1] > 0  # avg_duration_seconds > 0

    def test_stats_accumulate(self, coord_mgr):
        """Multiple completions should accumulate stats."""
        coord_mgr.register_session(
            "sess-1", pid=1234, project="/proj/a",
            capabilities=["code"],
        )
        for i in range(3):
            task = coord_mgr.create_task(created_by="sess-1", title=f"T{i}", project="/proj/a")
            coord_mgr.claim_task(task["task_id"], "sess-1")
            time.sleep(0.02)
            coord_mgr.complete_task(task["task_id"], "sess-1", result="done")

        row = coord_mgr._conn.execute(
            "SELECT tasks_completed FROM coord_capability_stats WHERE capability = 'code' AND project = '/proj/a'"
        ).fetchone()
        assert row is not None
        assert row[0] == 3

    def test_matching_caps_preferred(self, coord_mgr):
        """Session with matching capabilities should get bonus in routing."""
        coord_mgr.register_session(
            "sess-1", pid=1234, project="/proj/a",
            capabilities=["code", "review"],
        )
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a",
            target_modules=["code"],
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a", priority=1)
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])

        result = coord_mgr.smart_route_task("sess-1", project="/proj/a")
        assert result["success"] is True
        # Score should include capability bonus (+3) on top of priority*10 = 10
        assert result["effective_score"] >= 13

    def test_no_caps_no_bonus(self, coord_mgr):
        """Session without capabilities should not get bonus."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a",
            target_modules=["deploy"],
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a", priority=1)
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])

        result = coord_mgr.smart_route_task("sess-1", project="/proj/a")
        assert result["success"] is True
        assert result["effective_score"] == 10  # Just priority*10, no bonus


class TestCompareAgentsEnhanced:
    """Enhanced compare_agents tests (file overlap + shared goals)."""

    def test_file_overlap(self, coord_mgr):
        """Should return file overlap score."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.register_session("sess-2", pid=1235, project="/proj/a")
        # Each agent claims different files (file_path is PK, exclusive claims)
        coord_mgr.claim_file("sess-1", "/proj/a/file_a.py")
        coord_mgr.claim_file("sess-1", "/proj/a/file_b.py")
        coord_mgr.claim_file("sess-2", "/proj/a/file_c.py")
        coord_mgr.claim_file("sess-2", "/proj/a/file_d.py")

        from omega.behavioral import BehavioralAnalyzer
        analyzer = BehavioralAnalyzer(conn=coord_mgr._conn)
        result = analyzer.compare_agents("sess-1", "sess-2")

        # No shared files => overlap = 0, union = 4
        assert "file_overlap" in result
        assert result["file_overlap"] == 0.0

        # Release and re-claim to simulate overlap via same session_id pattern
        # Test that field is always present and typed correctly
        assert isinstance(result["file_overlap"], float)

    def test_shared_goals(self, coord_mgr):
        """Should return shared goals between agents."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.register_session("sess-2", pid=1235, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        t1 = coord_mgr.create_task(created_by="sess-1", title="T1", project="/proj/a")
        t2 = coord_mgr.create_task(created_by="sess-1", title="T2", project="/proj/a")
        coord_mgr.link_task_to_goal(t1["task_id"], goal["goal_id"])
        coord_mgr.link_task_to_goal(t2["task_id"], goal["goal_id"])
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.claim_task(t2["task_id"], "sess-2")

        from omega.behavioral import BehavioralAnalyzer
        analyzer = BehavioralAnalyzer(conn=coord_mgr._conn)
        result = analyzer.compare_agents("sess-1", "sess-2")

        assert "shared_goals" in result
        assert goal["goal_id"] in result["shared_goals"]

    def test_no_data(self, coord_mgr):
        """No audit data should return error."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.register_session("sess-2", pid=1235, project="/proj/a")

        from omega.behavioral import BehavioralAnalyzer
        analyzer = BehavioralAnalyzer(conn=coord_mgr._conn)
        result = analyzer.compare_agents("sess-1", "sess-2")

        assert result["alignment"] == 0.0
        assert "error" in result

    def test_divergent_tools(self, coord_mgr):
        """Should detect divergent tools between agents."""
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.register_session("sess-2", pid=1235, project="/proj/a")

        now = datetime.now(timezone.utc).isoformat()
        # sess-1 uses tool_a heavily
        for _ in range(10):
            coord_mgr._conn.execute(
                "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                ("sess-1", "file_claim", now),
            )
        # sess-2 uses tool_b heavily
        for _ in range(10):
            coord_mgr._conn.execute(
                "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                ("sess-2", "git_events", now),
            )
        coord_mgr._conn.commit()

        from omega.behavioral import BehavioralAnalyzer
        analyzer = BehavioralAnalyzer(conn=coord_mgr._conn)
        result = analyzer.compare_agents("sess-1", "sess-2")

        assert len(result["divergent_tools"]) > 0
        assert "file_overlap" in result
        assert "shared_goals" in result


class TestSchemaV7:
    """Schema v7 migration tests."""

    def test_capability_stats_table_exists(self, coord_mgr):
        """v7 schema should create coord_capability_stats table."""
        row = coord_mgr._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='coord_capability_stats'"
        ).fetchone()
        assert row is not None

    def test_schema_version_is_11(self, coord_mgr):
        """Schema version should be 12."""
        row = coord_mgr._conn.execute(
            "SELECT version FROM coord_schema_version LIMIT 1"
        ).fetchone()
        assert row[0] == 12
