"""Tests for OMEGA Coordination Goals + Drift Detection (Phase 6)."""
from datetime import datetime, timedelta, timezone


class TestGoalCRUD:
    """Goal create, evolve, complete, list, get tests."""

    def test_create_goal(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        result = coord_mgr.create_goal(
            session_id="sess-1",
            title="Implement auth",
            description="Add JWT authentication to API",
            project="/proj/a",
            target_files=["src/auth.py", "src/middleware.py"],
            target_modules=["auth", "middleware"],
            success_criteria=["All endpoints require auth", "Tests pass"],
        )
        assert result["success"] is True
        assert result["goal_id"] is not None
        assert result["title"] == "Implement auth"
        assert result["parent_goal_id"] is None

    def test_create_goal_auto_registers(self, coord_mgr):
        result = coord_mgr.create_goal(
            session_id="unregistered",
            title="Test goal",
            description="Auto-register test",
            project="/proj/a",
        )
        assert result["success"] is True

    def test_create_child_goal(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        parent = coord_mgr.create_goal(
            session_id="sess-1", title="Parent", description="Parent goal", project="/proj/a"
        )
        child = coord_mgr.create_goal(
            session_id="sess-1",
            title="Child",
            description="Child goal",
            project="/proj/a",
            parent_goal_id=parent["goal_id"],
        )
        assert child["success"] is True
        assert child["parent_goal_id"] == parent["goal_id"]

    def test_create_child_invalid_parent(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        result = coord_mgr.create_goal(
            session_id="sess-1",
            title="Orphan",
            description="Bad parent",
            project="/proj/a",
            parent_goal_id=999,
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_evolve_goal(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        original = coord_mgr.create_goal(
            session_id="sess-1",
            title="Feature X",
            description="Build feature X with approach A",
            project="/proj/a",
            target_files=["src/x.py"],
        )
        result = coord_mgr.evolve_goal(
            goal_id=original["goal_id"],
            session_id="sess-1",
            new_description="Build feature X with approach B instead",
            reason="Approach A had scaling issues",
        )
        assert result["success"] is True
        assert result["evolved_from_id"] == original["goal_id"]
        assert result["new_goal_id"] != original["goal_id"]

        # Old goal should be abandoned
        old = coord_mgr.get_goal(original["goal_id"])
        assert old["status"] == "abandoned"

        # New goal preserves original description anchor
        new = coord_mgr.get_goal(result["new_goal_id"])
        assert new["status"] == "active"
        assert new["original_description"] == "Build feature X with approach A"
        assert new["description"] == "Build feature X with approach B instead"
        assert new["evolution_reason"] == "Approach A had scaling issues"
        assert new["target_files"] == ["src/x.py"]

    def test_evolve_reassigns_tasks(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G1", description="Goal 1", project="/proj/a"
        )
        task = coord_mgr.create_task(created_by="sess-1", title="Task 1", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])

        evolved = coord_mgr.evolve_goal(goal["goal_id"], "sess-1", "New desc", "reason")

        # Task should now be linked to the new goal
        new_goal = coord_mgr.get_goal(evolved["new_goal_id"])
        assert len(new_goal["tasks"]) == 1
        assert new_goal["tasks"][0]["id"] == task["task_id"]

    def test_complete_goal(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G1", description="Goal 1", project="/proj/a"
        )
        result = coord_mgr.complete_goal(goal["goal_id"], "sess-1")
        assert result["success"] is True
        assert result["parent_completed"] is False

        completed = coord_mgr.get_goal(goal["goal_id"])
        assert completed["status"] == "completed"
        assert completed["completed_at"] is not None

    def test_complete_goal_cascades_parent(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        parent = coord_mgr.create_goal(
            session_id="sess-1", title="Parent", description="Parent", project="/proj/a"
        )
        child1 = coord_mgr.create_goal(
            session_id="sess-1", title="Child1", description="C1", project="/proj/a",
            parent_goal_id=parent["goal_id"],
        )
        child2 = coord_mgr.create_goal(
            session_id="sess-1", title="Child2", description="C2", project="/proj/a",
            parent_goal_id=parent["goal_id"],
        )

        # Complete first child — parent should NOT auto-complete
        r1 = coord_mgr.complete_goal(child1["goal_id"], "sess-1")
        assert r1["parent_completed"] is False
        assert coord_mgr.get_goal(parent["goal_id"])["status"] == "active"

        # Complete second child — parent SHOULD auto-complete
        r2 = coord_mgr.complete_goal(child2["goal_id"], "sess-1")
        assert r2["parent_completed"] is True
        assert coord_mgr.get_goal(parent["goal_id"])["status"] == "completed"

    def test_complete_nonexistent_goal(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        result = coord_mgr.complete_goal(999, "sess-1")
        assert result["success"] is False

    def test_complete_already_completed(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="G", project="/proj/a"
        )
        coord_mgr.complete_goal(goal["goal_id"], "sess-1")
        result = coord_mgr.complete_goal(goal["goal_id"], "sess-1")
        assert result["success"] is False

    def test_list_goals(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        coord_mgr.create_goal(session_id="sess-1", title="G1", description="D1", project="/proj/a")
        coord_mgr.create_goal(session_id="sess-1", title="G2", description="D2", project="/proj/a")
        coord_mgr.create_goal(session_id="sess-1", title="G3", description="D3", project="/proj/b")

        goals = coord_mgr.list_goals(project="/proj/a")
        assert len(goals) == 2

        all_goals = coord_mgr.list_goals()
        assert len(all_goals) == 3

    def test_list_goals_excludes_children_by_default(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        parent = coord_mgr.create_goal(
            session_id="sess-1", title="Parent", description="P", project="/proj/a"
        )
        coord_mgr.create_goal(
            session_id="sess-1", title="Child", description="C", project="/proj/a",
            parent_goal_id=parent["goal_id"],
        )

        without_children = coord_mgr.list_goals(project="/proj/a")
        assert len(without_children) == 1
        assert without_children[0]["title"] == "Parent"

        with_children = coord_mgr.list_goals(project="/proj/a", include_children=True)
        assert len(with_children) == 2

    def test_get_goal_with_tasks_and_children(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        parent = coord_mgr.create_goal(
            session_id="sess-1", title="Parent", description="P", project="/proj/a"
        )
        coord_mgr.create_goal(
            session_id="sess-1", title="Child", description="C", project="/proj/a",
            parent_goal_id=parent["goal_id"],
        )
        task = coord_mgr.create_task(created_by="sess-1", title="Task", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], parent["goal_id"])

        goal = coord_mgr.get_goal(parent["goal_id"])
        assert goal is not None
        assert len(goal["tasks"]) == 1
        assert goal["tasks"][0]["title"] == "Task"
        assert len(goal["children"]) == 1
        assert goal["children"][0]["title"] == "Child"

    def test_get_nonexistent_goal(self, coord_mgr):
        assert coord_mgr.get_goal(999) is None


class TestGoalTaskLink:
    """Link task to goal tests."""

    def test_link_task_to_goal(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        result = coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        assert result["success"] is True

        # Verify via get_goal
        g = coord_mgr.get_goal(goal["goal_id"])
        assert len(g["tasks"]) == 1

    def test_link_nonexistent_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        result = coord_mgr.link_task_to_goal(999, goal["goal_id"])
        assert result["success"] is False

    def test_link_nonexistent_goal(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        result = coord_mgr.link_task_to_goal(task["task_id"], 999)
        assert result["success"] is False


class TestDriftFileScope:
    """File scope divergence signal tests."""

    def test_no_target_files_returns_zero(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        assert coord_mgr._drift_file_scope(goal["goal_id"]) == 0.0

    def test_perfect_overlap(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a",
            target_files=["/proj/a/foo.py"],
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        coord_mgr.claim_task(task["task_id"], "sess-1")
        coord_mgr.claim_file("sess-1", "/proj/a/foo.py")

        score = coord_mgr._drift_file_scope(goal["goal_id"])
        assert score == 0.0  # Perfect overlap = no drift

    def test_complete_divergence(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a",
            target_files=["/proj/a/expected.py"],
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        coord_mgr.claim_task(task["task_id"], "sess-1")
        coord_mgr.claim_file("sess-1", "/proj/a/unexpected.py")

        score = coord_mgr._drift_file_scope(goal["goal_id"])
        assert score == 1.0  # No overlap = full drift


class TestDriftTaskSprawl:
    """Task sprawl signal tests."""

    def test_no_tasks_returns_zero(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        assert coord_mgr._drift_task_sprawl(goal["goal_id"]) == 0.0

    def test_balanced_tasks(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        # 1 completed, 1 pending — ratio = 1/1/3 = 0.333
        t1 = coord_mgr.create_task(created_by="sess-1", title="T1", project="/proj/a")
        coord_mgr.link_task_to_goal(t1["task_id"], goal["goal_id"])
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.complete_task(t1["task_id"], "sess-1")

        t2 = coord_mgr.create_task(created_by="sess-1", title="T2", project="/proj/a")
        coord_mgr.link_task_to_goal(t2["task_id"], goal["goal_id"])

        score = coord_mgr._drift_task_sprawl(goal["goal_id"])
        assert 0.0 < score < 0.5

    def test_heavy_sprawl(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        # 1 completed + 4 pending: ratio = 4/1/3 = 1.333 -> capped at 1.0
        t1 = coord_mgr.create_task(created_by="sess-1", title="Done", project="/proj/a")
        coord_mgr.link_task_to_goal(t1["task_id"], goal["goal_id"])
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.complete_task(t1["task_id"], "sess-1")

        for i in range(4):
            t = coord_mgr.create_task(created_by="sess-1", title=f"Open{i}", project="/proj/a")
            coord_mgr.link_task_to_goal(t["task_id"], goal["goal_id"])

        score = coord_mgr._drift_task_sprawl(goal["goal_id"])
        assert score == 1.0


class TestDriftEvolutionDepth:
    """Evolution depth signal tests."""

    def test_no_evolution(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        assert coord_mgr._drift_evolution_depth(goal["goal_id"]) == 0.0

    def test_triple_evolution(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        g1 = coord_mgr.create_goal(
            session_id="sess-1", title="G1", description="V1", project="/proj/a"
        )
        g2 = coord_mgr.evolve_goal(g1["goal_id"], "sess-1", "V2", "reason 1")
        g3 = coord_mgr.evolve_goal(g2["new_goal_id"], "sess-1", "V3", "reason 2")
        g4 = coord_mgr.evolve_goal(g3["new_goal_id"], "sess-1", "V4", "reason 3")

        # The latest goal has depth 3 (evolved 3 times)
        score = coord_mgr._drift_evolution_depth(g4["new_goal_id"])
        assert score == 1.0  # 3+ evolutions = full drift


class TestDriftStall:
    """Stall detection signal tests."""

    def test_no_tasks_returns_zero(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        assert coord_mgr._drift_stall(goal["goal_id"]) == 0.0

    def test_active_task_no_stall(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        coord_mgr.claim_task(task["task_id"], "sess-1")
        # Claim a file so there's recent file activity
        coord_mgr.claim_file("sess-1", "/proj/a/foo.py")

        score = coord_mgr._drift_stall(goal["goal_id"])
        assert score == 0.0  # Recent activity = no stall

    def test_stalled_task(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        task = coord_mgr.create_task(created_by="sess-1", title="T", project="/proj/a")
        coord_mgr.link_task_to_goal(task["task_id"], goal["goal_id"])
        coord_mgr.claim_task(task["task_id"], "sess-1")

        # Manually backdate file activity to 20 minutes ago
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        coord_mgr._conn.execute(
            "INSERT OR REPLACE INTO coord_file_claims (file_path, session_id, claimed_at, last_activity) VALUES (?, ?, ?, ?)",
            ("/proj/a/old.py", "sess-1", old_time, old_time),
        )
        coord_mgr._conn.commit()

        score = coord_mgr._drift_stall(goal["goal_id"])
        assert score == 1.0  # Stalled


class TestDriftComposite:
    """Composite drift score tests."""

    def test_zero_drift(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        drift = coord_mgr.check_drift(goal["goal_id"])
        assert drift["goal_id"] == goal["goal_id"]
        assert drift["drift_score"] == 0.0
        assert drift["alert_level"] == "none"
        assert "file_scope" in drift["signals"]
        assert "task_sprawl" in drift["signals"]
        assert "evolution_depth" in drift["signals"]
        assert "stall" in drift["signals"]
        assert "tool_pattern_shift" in drift["signals"]
        assert "inter_agent_divergence" in drift["signals"]
        assert "drift_type" in drift

    def test_high_drift_critical_alert(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        g1 = coord_mgr.create_goal(
            session_id="sess-1", title="G1", description="V1", project="/proj/a",
            target_files=["/proj/a/expected.py"],
        )
        # Evolve 3 times (evolution_depth = 1.0)
        g2 = coord_mgr.evolve_goal(g1["goal_id"], "sess-1", "V2", "r1")
        g3 = coord_mgr.evolve_goal(g2["new_goal_id"], "sess-1", "V3", "r2")
        g4 = coord_mgr.evolve_goal(g3["new_goal_id"], "sess-1", "V4", "r3")

        goal_id = g4["new_goal_id"]

        # Create 1 completed + 4 pending tasks (task_sprawl = 1.0)
        t1 = coord_mgr.create_task(created_by="sess-1", title="Done", project="/proj/a")
        coord_mgr.link_task_to_goal(t1["task_id"], goal_id)
        coord_mgr.claim_task(t1["task_id"], "sess-1")
        coord_mgr.complete_task(t1["task_id"], "sess-1")
        for i in range(4):
            t = coord_mgr.create_task(created_by="sess-1", title=f"Open{i}", project="/proj/a")
            coord_mgr.link_task_to_goal(t["task_id"], goal_id)

        drift = coord_mgr.check_drift(goal_id)
        # evolution_depth=1.0 (0.10) + task_sprawl=1.0 (0.20) = 0.30 minimum
        assert drift["drift_score"] >= 0.3
        assert drift["alert_level"] in ("watch", "warning", "critical")

    def test_drift_caching(self, coord_mgr):
        coord_mgr.register_session("sess-1", pid=1234, project="/proj/a")
        goal = coord_mgr.create_goal(
            session_id="sess-1", title="G", description="D", project="/proj/a"
        )
        # First call
        d1 = coord_mgr.check_drift(goal["goal_id"])
        # Second call should be cached (same result object)
        d2 = coord_mgr.check_drift(goal["goal_id"])
        assert d1 is d2


class TestBehavioralCompareAgents:
    """Cross-agent comparison tests."""

    def test_compare_agents_identical(self, coord_mgr):
        from omega.behavioral import BehavioralAnalyzer

        conn = coord_mgr._conn
        # Create audit table and insert identical tool usage for two sessions
        now = datetime.now(timezone.utc).isoformat()
        for sess in ("sess-a", "sess-b"):
            for tool, count in [("grep", 10), ("read", 5), ("edit", 3)]:
                for _ in range(count):
                    conn.execute(
                        "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                        (sess, tool, now),
                    )
        conn.commit()

        analyzer = BehavioralAnalyzer(conn=conn)
        result = analyzer.compare_agents("sess-a", "sess-b")
        assert result["alignment"] == 1.0
        assert result["divergent_tools"] == []

    def test_compare_agents_different(self, coord_mgr):
        from omega.behavioral import BehavioralAnalyzer

        conn = coord_mgr._conn
        now = datetime.now(timezone.utc).isoformat()
        # sess-a uses grep heavily
        for _ in range(10):
            conn.execute(
                "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                ("sess-a", "grep", now),
            )
        # sess-b uses bash heavily
        for _ in range(10):
            conn.execute(
                "INSERT INTO coord_audit (session_id, tool_name, created_at) VALUES (?, ?, ?)",
                ("sess-b", "bash", now),
            )
        conn.commit()

        analyzer = BehavioralAnalyzer(conn=conn)
        result = analyzer.compare_agents("sess-a", "sess-b")
        assert result["alignment"] == 0.0
        assert "grep" in result["divergent_tools"]
        assert "bash" in result["divergent_tools"]

    def test_compare_agents_no_data(self, coord_mgr):
        from omega.behavioral import BehavioralAnalyzer

        analyzer = BehavioralAnalyzer(conn=coord_mgr._conn)
        result = analyzer.compare_agents("nonexistent-a", "nonexistent-b")
        assert result["alignment"] == 0.0
        assert "error" in result
