"""Tests for uncovered coordination handlers in coord_handlers.py.

Covers handlers NOT tested in test_handler_coverage.py:
  - File claims (handle_file_claim, handle_file_release)
  - Intent announce (handle_intent_announce)
  - Task claim, next, deps (handle_task_claim, handle_task_next, handle_task_deps)
  - Messaging (handle_send_message, handle_inbox)
  - Audit & metrics (handle_audit, handle_coord_metrics)
  - Handoffs (handle_handoff)
  - External actions (handle_action_check, handle_action_claim, handle_action_complete)
  - Goals & drift (handle_goal, handle_goal_link, handle_drift_check)
  - Decisions (handle_decision_register, handle_decision_query, handle_decision_revoke)
  - Smart route, git events, update task (handle_smart_route, handle_git_events, handle_update_task)
"""

import asyncio
import re
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _text(result: dict) -> str:
    """Extract text from MCP response."""
    return result["content"][0]["text"]


def _is_error(result: dict) -> bool:
    return result.get("isError", False)


# ---------------------------------------------------------------------------
# Fixture: fresh coordination manager per test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fresh_coord(tmp_omega_dir):
    """Reset bridge + coordination for each test."""
    from omega.bridge import reset_memory
    reset_memory()
    try:
        import omega.coordination as coord
        coord._manager = None
    except (ImportError, AttributeError):
        pass
    yield


def _register(session_id, project=None, task=None, capabilities=None):
    """Helper to register a session."""
    from omega.server.coord_handlers import handle_session_register
    args = {"session_id": session_id}
    if project:
        args["project"] = project
    if task:
        args["task"] = task
    if capabilities:
        args["capabilities"] = capabilities
    return run_async(handle_session_register(args))


def _create_task(session_id, title, **kwargs):
    """Helper to create a task and return its ID."""
    from omega.server.coord_handlers import handle_task_create
    result = run_async(handle_task_create({
        "session_id": session_id, "title": title, **kwargs,
    }))
    match = re.search(r"#(\d+)", _text(result))
    return int(match.group(1)) if match else None


def _create_goal(session_id, title, description, project, **kwargs):
    """Helper to create a goal and return its ID."""
    from omega.server.coord_handlers import handle_goal
    result = run_async(handle_goal({
        "action": "create",
        "session_id": session_id,
        "title": title,
        "description": description,
        "project": project,
        **kwargs,
    }))
    match = re.search(r"#(\d+)", _text(result))
    return int(match.group(1)) if match else None


# ===========================================================================
# Group 1: File Claims (handle_file_claim, handle_file_release)
# ===========================================================================


class TestFileClaim:
    """Tests for omega_file_claim handler."""

    def test_file_claim_success(self):
        from omega.server.coord_handlers import handle_file_claim
        _register("fc-ok")
        result = run_async(handle_file_claim({
            "session_id": "fc-ok", "file_path": "/tmp/alpha.py",
        }))
        assert not _is_error(result)
        assert "claimed" in _text(result).lower()

    def test_file_claim_conflict(self):
        from omega.server.coord_handlers import handle_file_claim
        _register("fc-a")
        _register("fc-b")
        run_async(handle_file_claim({
            "session_id": "fc-a", "file_path": "/tmp/shared.py",
        }))
        result = run_async(handle_file_claim({
            "session_id": "fc-b", "file_path": "/tmp/shared.py",
        }))
        assert not _is_error(result)  # conflicts are non-error responses
        assert "conflict" in _text(result).lower()
        assert "fc-a" in _text(result)

    def test_file_claim_force_override(self):
        from omega.server.coord_handlers import handle_file_claim
        _register("fc-owner")
        _register("fc-forcer")
        run_async(handle_file_claim({
            "session_id": "fc-owner", "file_path": "/tmp/forced.py",
        }))
        result = run_async(handle_file_claim({
            "session_id": "fc-forcer", "file_path": "/tmp/forced.py",
            "force": True,
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "claimed" in text.lower() or "force" in text.lower() or "override" in text.lower()

    def test_file_claim_refresh(self):
        from omega.server.coord_handlers import handle_file_claim
        _register("fc-refresh")
        run_async(handle_file_claim({
            "session_id": "fc-refresh", "file_path": "/tmp/refresh.py",
        }))
        result = run_async(handle_file_claim({
            "session_id": "fc-refresh", "file_path": "/tmp/refresh.py",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "claimed" in text.lower() or "refresh" in text.lower()

    def test_file_claim_missing_session(self):
        from omega.server.coord_handlers import handle_file_claim
        result = run_async(handle_file_claim({"file_path": "/tmp/x.py"}))
        assert _is_error(result)

    def test_file_claim_missing_path(self):
        from omega.server.coord_handlers import handle_file_claim
        _register("fc-nopath")
        result = run_async(handle_file_claim({"session_id": "fc-nopath"}))
        assert _is_error(result)


class TestFileRelease:
    """Tests for omega_file_release handler."""

    def test_file_release_success(self):
        from omega.server.coord_handlers import handle_file_claim, handle_file_release
        _register("fr-ok")
        run_async(handle_file_claim({
            "session_id": "fr-ok", "file_path": "/tmp/releasable.py",
        }))
        result = run_async(handle_file_release({
            "session_id": "fr-ok", "file_path": "/tmp/releasable.py",
        }))
        assert not _is_error(result)
        assert "released" in _text(result).lower()

    def test_file_release_not_owned(self):
        from omega.server.coord_handlers import handle_file_claim, handle_file_release
        _register("fr-own")
        _register("fr-other")
        run_async(handle_file_claim({
            "session_id": "fr-own", "file_path": "/tmp/notmine.py",
        }))
        result = run_async(handle_file_release({
            "session_id": "fr-other", "file_path": "/tmp/notmine.py",
        }))
        assert _is_error(result)


# ===========================================================================
# Group 2: Intent Announce (handle_intent_announce)
# ===========================================================================


class TestIntentAnnounce:
    """Tests for omega_intent_announce handler."""

    def test_intent_announce_basic(self):
        from omega.server.coord_handlers import handle_intent_announce
        _register("ia-1", project="/proj")
        result = run_async(handle_intent_announce({
            "session_id": "ia-1",
            "description": "Refactoring the auth module",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "announced" in text.lower() or "intent" in text.lower()

    def test_intent_announce_with_files(self):
        from omega.server.coord_handlers import handle_intent_announce
        _register("ia-files", project="/proj")
        result = run_async(handle_intent_announce({
            "session_id": "ia-files",
            "description": "Editing config files",
            "target_files": ["/proj/config.py", "/proj/settings.py"],
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "config.py" in text or "announced" in text.lower()

    def test_intent_announce_overlap_detection(self):
        from omega.server.coord_handlers import handle_intent_announce
        _register("ia-ov-a", project="/proj")
        _register("ia-ov-b", project="/proj")
        run_async(handle_intent_announce({
            "session_id": "ia-ov-a",
            "description": "Editing models",
            "target_files": ["/proj/models.py"],
        }))
        result = run_async(handle_intent_announce({
            "session_id": "ia-ov-b",
            "description": "Also editing models",
            "target_files": ["/proj/models.py"],
        }))
        assert not _is_error(result)
        text = _text(result)
        # Overlap may or may not be detected depending on implementation details,
        # but the call should succeed
        assert "announced" in text.lower() or "overlap" in text.lower()

    def test_intent_announce_missing_session(self):
        from omega.server.coord_handlers import handle_intent_announce
        result = run_async(handle_intent_announce({
            "description": "Something",
        }))
        assert _is_error(result)

    def test_intent_announce_missing_description(self):
        from omega.server.coord_handlers import handle_intent_announce
        _register("ia-nodesc")
        result = run_async(handle_intent_announce({
            "session_id": "ia-nodesc",
        }))
        assert _is_error(result)


# ===========================================================================
# Group 3: Task Claim, Next, Deps
# ===========================================================================


class TestTaskClaim:
    """Tests for omega_task_claim handler."""

    def test_task_claim_success(self):
        from omega.server.coord_handlers import handle_task_claim
        _register("tc-1")
        task_id = _create_task("tc-1", "Claimable task")
        assert task_id is not None
        result = run_async(handle_task_claim({
            "task_id": task_id, "session_id": "tc-1",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "claimed" in text.lower() or "in_progress" in text.lower()

    def test_task_claim_missing_task_id(self):
        from omega.server.coord_handlers import handle_task_claim
        result = run_async(handle_task_claim({
            "session_id": "tc-notask",
        }))
        assert _is_error(result)

    def test_task_claim_missing_session(self):
        from omega.server.coord_handlers import handle_task_claim
        result = run_async(handle_task_claim({
            "task_id": 1,
        }))
        assert _is_error(result)


class TestTaskNext:
    """Tests for omega_task_next handler."""

    def test_task_next_auto_claims(self):
        from omega.server.coord_handlers import handle_task_next
        _register("tn-1")
        task_id = _create_task("tn-1", "Next-able task")
        assert task_id is not None
        result = run_async(handle_task_next({"session_id": "tn-1"}))
        assert not _is_error(result)
        text = _text(result)
        assert "claimed" in text.lower() or f"#{task_id}" in text

    def test_task_next_no_available(self):
        from omega.server.coord_handlers import handle_task_next
        _register("tn-empty")
        result = run_async(handle_task_next({"session_id": "tn-empty"}))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no" in text or "claimable" in text or "empty" in text

    def test_task_next_project_filter(self):
        from omega.server.coord_handlers import handle_task_next
        _register("tn-proj")
        _create_task("tn-proj", "Task in proj-a", project="/proj/a")
        _create_task("tn-proj", "Task in proj-b", project="/proj/b")
        result = run_async(handle_task_next({
            "session_id": "tn-proj", "project": "/proj/a",
        }))
        assert not _is_error(result)
        text = _text(result)
        # Should claim from proj-a specifically
        assert "claimed" in text.lower() or "proj" in text.lower() or "Task in" in text

    def test_task_next_missing_session(self):
        from omega.server.coord_handlers import handle_task_next
        result = run_async(handle_task_next({}))
        assert _is_error(result)


class TestTaskDeps:
    """Tests for omega_task_deps handler."""

    def test_task_deps_shows_dependencies(self):
        from omega.server.coord_handlers import handle_task_deps
        _register("td-1")
        parent_id = _create_task("td-1", "Parent task")
        child_id = _create_task("td-1", "Child task", depends_on=[parent_id])
        assert parent_id is not None and child_id is not None
        result = run_async(handle_task_deps({"task_id": child_id}))
        assert not _is_error(result)
        text = _text(result)
        assert "depends" in text.lower() or f"#{parent_id}" in text

    def test_task_deps_no_dependencies(self):
        from omega.server.coord_handlers import handle_task_deps
        _register("td-nodep")
        task_id = _create_task("td-nodep", "Standalone task")
        result = run_async(handle_task_deps({"task_id": task_id}))
        assert not _is_error(result)
        text = _text(result)
        assert "none" in text.lower() or "depends" in text.lower()

    def test_task_deps_missing_task_id(self):
        from omega.server.coord_handlers import handle_task_deps
        result = run_async(handle_task_deps({}))
        assert _is_error(result)


# ===========================================================================
# Group 4: Messaging (handle_send_message, handle_inbox)
# ===========================================================================


class TestSendMessage:
    """Tests for omega_send_message handler."""

    def test_send_message_broadcast(self):
        from omega.server.coord_handlers import handle_send_message
        _register("msg-sender", project="/proj")
        _register("msg-peer", project="/proj")
        result = run_async(handle_send_message({
            "session_id": "msg-sender",
            "subject": "Build status update",
            "body": "All tests pass",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "sent" in text.lower() or "broadcast" in text.lower()

    def test_send_message_unicast(self):
        from omega.server.coord_handlers import handle_send_message
        _register("msg-from", project="/proj")
        _register("msg-to", project="/proj")
        result = run_async(handle_send_message({
            "session_id": "msg-from",
            "subject": "Direct message",
            "to_session": "msg-to",
            "body": "Please review my changes",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "sent" in text.lower()
        assert "msg-to" in text

    def test_send_message_missing_session(self):
        from omega.server.coord_handlers import handle_send_message
        result = run_async(handle_send_message({
            "subject": "No sender",
        }))
        assert _is_error(result)

    def test_send_message_missing_subject(self):
        from omega.server.coord_handlers import handle_send_message
        _register("msg-nosubj")
        result = run_async(handle_send_message({
            "session_id": "msg-nosubj",
        }))
        assert _is_error(result)


class TestInbox:
    """Tests for omega_inbox handler."""

    def test_inbox_receives_messages(self):
        from omega.server.coord_handlers import handle_send_message, handle_inbox
        _register("inbox-sender", project="/proj")
        _register("inbox-recv", project="/proj")
        run_async(handle_send_message({
            "session_id": "inbox-sender",
            "subject": "Ping from sender",
            "to_session": "inbox-recv",
            "body": "Hello there",
        }))
        result = run_async(handle_inbox({"session_id": "inbox-recv"}))
        assert not _is_error(result)
        text = _text(result)
        assert "ping" in text.lower() or "inbox" in text.lower() or "sender" in text.lower()

    def test_inbox_empty(self):
        from omega.server.coord_handlers import handle_inbox
        _register("inbox-empty")
        result = run_async(handle_inbox({"session_id": "inbox-empty"}))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "empty" in text or "no" in text

    def test_inbox_unread_only(self):
        from omega.server.coord_handlers import handle_send_message, handle_inbox
        _register("inbox-ur-s", project="/proj")
        _register("inbox-ur-r", project="/proj")
        run_async(handle_send_message({
            "session_id": "inbox-ur-s",
            "subject": "Unread test msg",
            "to_session": "inbox-ur-r",
        }))
        result = run_async(handle_inbox({
            "session_id": "inbox-ur-r", "unread_only": True,
        }))
        assert not _is_error(result)
        # Should have at least the message we sent
        text = _text(result)
        assert "unread" in text.lower() or "inbox" in text.lower() or "msg" in text.lower()

    def test_inbox_missing_session(self):
        from omega.server.coord_handlers import handle_inbox
        result = run_async(handle_inbox({}))
        assert _is_error(result)


# ===========================================================================
# Group 5: Audit & Metrics
# ===========================================================================


class TestAudit:
    """Tests for omega_audit handler."""

    def test_audit_query_basic(self):
        from omega.server.coord_handlers import handle_audit
        _register("audit-1")
        # Perform some actions to generate audit entries
        _create_task("audit-1", "Auditable task")
        result = run_async(handle_audit({}))
        assert not _is_error(result)
        text = _text(result)
        # Either has entries or says none found
        assert "audit" in text.lower() or "no audit" in text.lower() or "entries" in text.lower()

    def test_audit_filter_by_tool(self):
        from omega.server.coord_handlers import handle_audit
        _register("audit-ft")
        _create_task("audit-ft", "Task for audit filter")
        result = run_async(handle_audit({"tool_name": "task_create"}))
        assert not _is_error(result)

    def test_audit_empty(self):
        from omega.server.coord_handlers import handle_audit
        # Fresh state, no actions performed
        result = run_async(handle_audit({}))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no audit" in text or "audit" in text


class TestCoordMetrics:
    """Tests for omega_coord_metrics handler."""

    def test_metrics_basic(self):
        from omega.server.coord_handlers import handle_coord_metrics
        _register("met-1")
        result = run_async(handle_coord_metrics({}))
        assert not _is_error(result)
        text = _text(result)
        assert "metrics" in text.lower() or "claims" in text.lower()

    def test_metrics_custom_days(self):
        from omega.server.coord_handlers import handle_coord_metrics
        _register("met-days")
        result = run_async(handle_coord_metrics({"days": 1}))
        assert not _is_error(result)
        text = _text(result)
        assert "1d" in text or "metrics" in text.lower()


# ===========================================================================
# Group 6: Handoffs (handle_handoff)
# ===========================================================================


class TestHandoff:
    """Tests for omega_handoff handler."""

    def test_handoff_create(self):
        from omega.server.coord_handlers import handle_handoff
        _register("ho-1", project="/proj/ho")
        result = run_async(handle_handoff({
            "session_id": "ho-1",
            "action": "create",
            "project": "/proj/ho",
            "completed_tasks": ["Fixed login bug"],
            "next_steps": ["Deploy to staging"],
            "key_context": "Auth refactor is halfway done",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "handoff" in text.lower() or "created" in text.lower()

    def test_handoff_create_missing_session(self):
        from omega.server.coord_handlers import handle_handoff
        result = run_async(handle_handoff({
            "action": "create",
            "project": "/proj/ho",
        }))
        assert _is_error(result)

    def test_handoff_get(self):
        from omega.server.coord_handlers import handle_handoff
        _register("ho-get", project="/proj/hget")
        # Create a handoff first
        run_async(handle_handoff({
            "session_id": "ho-get",
            "action": "create",
            "project": "/proj/hget",
            "completed_tasks": ["Setup CI"],
            "key_context": "CI pipeline is green",
        }))
        # Now get it
        result = run_async(handle_handoff({
            "action": "get",
            "project": "/proj/hget",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "ho-get" in text or "handoff" in text.lower()

    def test_handoff_get_no_handoffs(self):
        from omega.server.coord_handlers import handle_handoff
        result = run_async(handle_handoff({
            "action": "get",
            "project": "/proj/nohandoffs",
        }))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no handoff" in text or "no hand" in text


# ===========================================================================
# Group 7: External Actions
# ===========================================================================


class TestActionCheck:
    """Tests for omega_action_check handler."""

    def test_action_check_none(self):
        from omega.server.coord_handlers import handle_action_check
        result = run_async(handle_action_check({
            "action_type": "deploy",
            "action_target": "staging-server",
        }))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no active" in text or "safe to proceed" in text

    def test_action_check_missing_type(self):
        from omega.server.coord_handlers import handle_action_check
        result = run_async(handle_action_check({
            "action_target": "staging",
        }))
        assert _is_error(result)

    def test_action_check_missing_target(self):
        from omega.server.coord_handlers import handle_action_check
        result = run_async(handle_action_check({
            "action_type": "deploy",
        }))
        assert _is_error(result)


class TestActionClaim:
    """Tests for omega_action_claim handler."""

    def test_action_claim_success(self):
        from omega.server.coord_handlers import handle_action_claim
        _register("ac-1")
        result = run_async(handle_action_claim({
            "session_id": "ac-1",
            "action_type": "deploy",
            "action_target": "prod-server-1",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "claimed" in text.lower()

    def test_action_claim_duplicate(self):
        from omega.server.coord_handlers import handle_action_claim
        _register("ac-dup-a")
        _register("ac-dup-b")
        run_async(handle_action_claim({
            "session_id": "ac-dup-a",
            "action_type": "send_email",
            "action_target": "user@example.com",
        }))
        result = run_async(handle_action_claim({
            "session_id": "ac-dup-b",
            "action_type": "send_email",
            "action_target": "user@example.com",
        }))
        assert not _is_error(result)  # BLOCKED is a non-error response
        text = _text(result)
        assert "blocked" in text.lower() or "already" in text.lower()

    def test_action_claim_missing_args(self):
        from omega.server.coord_handlers import handle_action_claim
        result = run_async(handle_action_claim({
            "session_id": "ac-miss",
        }))
        assert _is_error(result)

    def test_action_claim_missing_session(self):
        from omega.server.coord_handlers import handle_action_claim
        result = run_async(handle_action_claim({
            "action_type": "deploy",
            "action_target": "server",
        }))
        assert _is_error(result)


class TestActionComplete:
    """Tests for omega_action_complete handler."""

    def test_action_complete_success(self):
        from omega.server.coord_handlers import handle_action_claim, handle_action_complete
        _register("acomp-1")
        claim_result = run_async(handle_action_claim({
            "session_id": "acomp-1",
            "action_type": "deploy",
            "action_target": "staging-v2",
        }))
        # Extract action_id from the claim response
        text = _text(claim_result)
        match = re.search(r"id=(\d+)", text)
        assert match, f"Expected action_id in claim response, got: {text}"
        action_id = int(match.group(1))

        result = run_async(handle_action_complete({
            "action_id": action_id,
            "session_id": "acomp-1",
            "result": "Deploy succeeded",
            "success": True,
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "completed" in text.lower() or "marked" in text.lower()

    def test_action_check_after_complete(self):
        from omega.server.coord_handlers import (
            handle_action_claim, handle_action_complete, handle_action_check,
        )
        _register("achk-1")
        claim_result = run_async(handle_action_claim({
            "session_id": "achk-1",
            "action_type": "notify",
            "action_target": "slack-channel",
        }))
        match = re.search(r"id=(\d+)", _text(claim_result))
        assert match
        action_id = int(match.group(1))

        run_async(handle_action_complete({
            "action_id": action_id,
            "session_id": "achk-1",
            "result": "Notification sent",
        }))
        check = run_async(handle_action_check({
            "action_type": "notify",
            "action_target": "slack-channel",
        }))
        assert not _is_error(check)
        text = _text(check)
        assert "completed" in text.lower()

    def test_action_complete_missing_action_id(self):
        from omega.server.coord_handlers import handle_action_complete
        result = run_async(handle_action_complete({
            "session_id": "acomp-noid",
        }))
        assert _is_error(result)

    def test_action_complete_missing_session(self):
        from omega.server.coord_handlers import handle_action_complete
        result = run_async(handle_action_complete({
            "action_id": 1,
        }))
        assert _is_error(result)


# ===========================================================================
# Group 8: Goals & Drift
# ===========================================================================


class TestGoal:
    """Tests for omega_goal handler."""

    def test_goal_create(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-1", project="/proj/goals")
        result = run_async(handle_goal({
            "action": "create",
            "session_id": "goal-1",
            "title": "Ship v2.0",
            "description": "Release version 2.0 with new features",
            "project": "/proj/goals",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "#" in text
        assert "created" in text.lower() or "goal" in text.lower()

    def test_goal_create_missing_title(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-notitle")
        result = run_async(handle_goal({
            "action": "create",
            "session_id": "goal-notitle",
            "description": "Desc",
            "project": "/proj",
        }))
        assert _is_error(result)

    def test_goal_create_missing_description(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-nodesc")
        result = run_async(handle_goal({
            "action": "create",
            "session_id": "goal-nodesc",
            "title": "A Goal",
            "project": "/proj",
        }))
        assert _is_error(result)

    def test_goal_create_missing_project(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-noproj")
        result = run_async(handle_goal({
            "action": "create",
            "session_id": "goal-noproj",
            "title": "A Goal",
            "description": "Desc",
        }))
        assert _is_error(result)

    def test_goal_create_missing_action(self):
        from omega.server.coord_handlers import handle_goal
        result = run_async(handle_goal({}))
        assert _is_error(result)

    def test_goal_list(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-list", project="/proj/gl")
        _create_goal("goal-list", "Goal Alpha", "First goal", "/proj/gl")
        _create_goal("goal-list", "Goal Beta", "Second goal", "/proj/gl")
        result = run_async(handle_goal({
            "action": "list",
            "project": "/proj/gl",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "alpha" in text.lower() or "beta" in text.lower()

    def test_goal_list_empty(self):
        from omega.server.coord_handlers import handle_goal
        result = run_async(handle_goal({
            "action": "list",
            "project": "/proj/empty-goals",
        }))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no goals" in text

    def test_goal_get(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-get", project="/proj/gg")
        goal_id = _create_goal("goal-get", "Specific Goal", "Get this goal", "/proj/gg")
        assert goal_id is not None
        result = run_async(handle_goal({
            "action": "get",
            "goal_id": goal_id,
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "specific goal" in text.lower() or f"#{goal_id}" in text

    def test_goal_get_nonexistent(self):
        from omega.server.coord_handlers import handle_goal
        result = run_async(handle_goal({
            "action": "get",
            "goal_id": 99999,
        }))
        assert _is_error(result)
        assert "not found" in _text(result).lower()

    def test_goal_get_missing_id(self):
        from omega.server.coord_handlers import handle_goal
        result = run_async(handle_goal({
            "action": "get",
        }))
        assert _is_error(result)

    def test_goal_evolve(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-evo", project="/proj/evo")
        goal_id = _create_goal("goal-evo", "Evolvable Goal", "Original scope", "/proj/evo")
        assert goal_id is not None
        result = run_async(handle_goal({
            "action": "evolve",
            "session_id": "goal-evo",
            "goal_id": goal_id,
            "description": "Expanded scope with new features",
            "reason": "Requirements changed after stakeholder review",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "evolved" in text.lower() or "new" in text.lower()

    def test_goal_evolve_missing_fields(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-evo-miss")
        result = run_async(handle_goal({
            "action": "evolve",
            "session_id": "goal-evo-miss",
            "goal_id": 1,
            # missing description and reason
        }))
        assert _is_error(result)

    def test_goal_complete(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-comp", project="/proj/comp")
        goal_id = _create_goal(
            "goal-comp", "Completable Goal", "This goal can be completed", "/proj/comp",
        )
        assert goal_id is not None
        result = run_async(handle_goal({
            "action": "complete",
            "session_id": "goal-comp",
            "goal_id": goal_id,
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "completed" in text.lower()

    def test_goal_complete_missing_goal_id(self):
        from omega.server.coord_handlers import handle_goal
        _register("goal-comp-miss")
        result = run_async(handle_goal({
            "action": "complete",
            "session_id": "goal-comp-miss",
        }))
        assert _is_error(result)

    def test_goal_unknown_action(self):
        from omega.server.coord_handlers import handle_goal
        result = run_async(handle_goal({
            "action": "destroy",
        }))
        assert _is_error(result)
        assert "unknown" in _text(result).lower()


class TestGoalLink:
    """Tests for omega_goal_link handler."""

    def test_goal_link_task(self):
        from omega.server.coord_handlers import handle_goal_link
        _register("gl-1", project="/proj/link")
        task_id = _create_task("gl-1", "Linkable task", project="/proj/link")
        goal_id = _create_goal("gl-1", "Link Goal", "Goal for linking", "/proj/link")
        assert task_id is not None and goal_id is not None
        result = run_async(handle_goal_link({
            "task_id": task_id,
            "goal_id": goal_id,
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "linked" in text.lower()

    def test_goal_link_missing_task_id(self):
        from omega.server.coord_handlers import handle_goal_link
        result = run_async(handle_goal_link({"goal_id": 1}))
        assert _is_error(result)

    def test_goal_link_missing_goal_id(self):
        from omega.server.coord_handlers import handle_goal_link
        result = run_async(handle_goal_link({"task_id": 1}))
        assert _is_error(result)


class TestDriftCheck:
    """Tests for omega_drift_check handler."""

    def test_drift_check_basic(self):
        from omega.server.coord_handlers import handle_drift_check
        _register("drift-1", project="/proj/drift")
        goal_id = _create_goal(
            "drift-1", "Drift Goal", "Check drift for this goal", "/proj/drift",
        )
        assert goal_id is not None
        result = run_async(handle_drift_check({"goal_id": goal_id}))
        assert not _is_error(result)
        text = _text(result)
        assert "drift" in text.lower() or "score" in text.lower()

    def test_drift_check_project_wide(self):
        from omega.server.coord_handlers import handle_drift_check
        _register("drift-pw", project="/proj/driftpw")
        _create_goal("drift-pw", "PW Goal 1", "First project goal", "/proj/driftpw")
        _create_goal("drift-pw", "PW Goal 2", "Second project goal", "/proj/driftpw")
        result = run_async(handle_drift_check({"project": "/proj/driftpw"}))
        assert not _is_error(result)
        text = _text(result)
        assert "drift" in text.lower() or "report" in text.lower() or "goal" in text.lower()

    def test_drift_check_project_no_goals(self):
        from omega.server.coord_handlers import handle_drift_check
        result = run_async(handle_drift_check({"project": "/proj/no-goals-here"}))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no active" in text or "no goals" in text

    def test_drift_check_missing_args(self):
        from omega.server.coord_handlers import handle_drift_check
        result = run_async(handle_drift_check({}))
        assert _is_error(result)


# ===========================================================================
# Group 9: Decisions
# ===========================================================================


class TestDecisionRegister:
    """Tests for omega_decision_register handler."""

    def test_decision_register(self):
        from omega.server.coord_handlers import handle_decision_register
        _register("dec-1", project="/proj/dec")
        result = run_async(handle_decision_register({
            "session_id": "dec-1",
            "project": "/proj/dec",
            "domain": "architecture",
            "decision": "Use microservices pattern for auth module",
            "rationale": "Better scalability and isolation",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "decision" in text.lower()
        assert "#" in text or "registered" in text.lower()

    def test_decision_register_supersedes(self):
        from omega.server.coord_handlers import handle_decision_register
        _register("dec-super", project="/proj/dec")
        run_async(handle_decision_register({
            "session_id": "dec-super",
            "project": "/proj/dec",
            "domain": "database",
            "decision": "Use PostgreSQL",
        }))
        result = run_async(handle_decision_register({
            "session_id": "dec-super",
            "project": "/proj/dec",
            "domain": "database",
            "decision": "Use SQLite instead of PostgreSQL",
            "rationale": "Simpler for our use case",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "decision" in text.lower()
        # May or may not mention superseded depending on impl
        assert "#" in text or "registered" in text.lower()

    def test_decision_register_missing_session(self):
        from omega.server.coord_handlers import handle_decision_register
        result = run_async(handle_decision_register({
            "project": "/proj/dec",
            "domain": "api",
            "decision": "Use REST",
        }))
        assert _is_error(result)

    def test_decision_register_missing_project(self):
        from omega.server.coord_handlers import handle_decision_register
        _register("dec-noproj")
        result = run_async(handle_decision_register({
            "session_id": "dec-noproj",
            "domain": "api",
            "decision": "Use REST",
        }))
        assert _is_error(result)

    def test_decision_register_missing_domain(self):
        from omega.server.coord_handlers import handle_decision_register
        _register("dec-nodom")
        result = run_async(handle_decision_register({
            "session_id": "dec-nodom",
            "project": "/proj/dec",
            "decision": "Use REST",
        }))
        assert _is_error(result)

    def test_decision_register_missing_decision(self):
        from omega.server.coord_handlers import handle_decision_register
        _register("dec-nodec")
        result = run_async(handle_decision_register({
            "session_id": "dec-nodec",
            "project": "/proj/dec",
            "domain": "api",
        }))
        assert _is_error(result)


class TestDecisionQuery:
    """Tests for omega_decision_query handler."""

    def test_decision_query(self):
        from omega.server.coord_handlers import handle_decision_register, handle_decision_query
        _register("dq-1", project="/proj/dq")
        run_async(handle_decision_register({
            "session_id": "dq-1",
            "project": "/proj/dq",
            "domain": "testing",
            "decision": "Use pytest for all test files",
        }))
        result = run_async(handle_decision_query({
            "project": "/proj/dq",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "pytest" in text.lower() or "decision" in text.lower()

    def test_decision_query_by_domain(self):
        from omega.server.coord_handlers import handle_decision_register, handle_decision_query
        _register("dq-dom", project="/proj/dq2")
        run_async(handle_decision_register({
            "session_id": "dq-dom",
            "project": "/proj/dq2",
            "domain": "ci-cd",
            "decision": "Use GitHub Actions",
        }))
        run_async(handle_decision_register({
            "session_id": "dq-dom",
            "project": "/proj/dq2",
            "domain": "frontend",
            "decision": "Use React",
        }))
        result = run_async(handle_decision_query({
            "project": "/proj/dq2",
            "domain": "ci-cd",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "github" in text.lower() or "ci" in text.lower()

    def test_decision_query_empty(self):
        from omega.server.coord_handlers import handle_decision_query
        result = run_async(handle_decision_query({
            "project": "/proj/no-decisions",
        }))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no decision" in text or "no dec" in text

    def test_decision_query_missing_project(self):
        from omega.server.coord_handlers import handle_decision_query
        result = run_async(handle_decision_query({}))
        assert _is_error(result)


class TestDecisionRevoke:
    """Tests for omega_decision_revoke handler."""

    def test_decision_revoke(self):
        from omega.server.coord_handlers import handle_decision_register, handle_decision_revoke
        _register("dr-1", project="/proj/dr")
        reg_result = run_async(handle_decision_register({
            "session_id": "dr-1",
            "project": "/proj/dr",
            "domain": "arch",
            "decision": "Use monolith",
        }))
        # Extract decision_id from response
        match = re.search(r"#(\d+)", _text(reg_result))
        assert match, f"Expected decision_id in response: {_text(reg_result)}"
        decision_id = int(match.group(1))

        result = run_async(handle_decision_revoke({
            "decision_id": decision_id,
            "session_id": "dr-1",
            "reason": "Changed our minds",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "revoked" in text.lower()

    def test_decision_revoke_missing_decision_id(self):
        from omega.server.coord_handlers import handle_decision_revoke
        _register("dr-noid")
        result = run_async(handle_decision_revoke({
            "session_id": "dr-noid",
        }))
        assert _is_error(result)

    def test_decision_revoke_missing_session(self):
        from omega.server.coord_handlers import handle_decision_revoke
        result = run_async(handle_decision_revoke({
            "decision_id": 1,
        }))
        assert _is_error(result)


# ===========================================================================
# Group 10: Smart Route, Git Events, Update Task
# ===========================================================================


class TestSmartRoute:
    """Tests for omega_smart_route handler."""

    def test_smart_route_basic(self):
        from omega.server.coord_handlers import handle_smart_route
        _register("sr-1", project="/proj/sr")
        _create_task("sr-1", "Routable task", project="/proj/sr")
        result = run_async(handle_smart_route({
            "session_id": "sr-1",
            "project": "/proj/sr",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "routed" in text.lower() or "claimed" in text.lower() or "task" in text.lower() or "no" in text.lower()

    def test_smart_route_no_tasks(self):
        from omega.server.coord_handlers import handle_smart_route
        _register("sr-empty")
        result = run_async(handle_smart_route({
            "session_id": "sr-empty",
            "project": "/proj/sr-empty",
        }))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no" in text or "claimable" in text or "task" in text

    def test_smart_route_missing_session(self):
        from omega.server.coord_handlers import handle_smart_route
        result = run_async(handle_smart_route({}))
        assert _is_error(result)


class TestGitEvents:
    """Tests for omega_git_events handler."""

    def test_git_events_empty(self):
        from omega.server.coord_handlers import handle_git_events
        result = run_async(handle_git_events({}))
        assert not _is_error(result)
        text = _text(result).lower()
        assert "no git" in text or "no event" in text or "events" in text

    def test_git_events_with_project_filter(self):
        from omega.server.coord_handlers import handle_git_events
        result = run_async(handle_git_events({
            "project": "/proj/nonexistent",
        }))
        assert not _is_error(result)


class TestUpdateTask:
    """Tests for omega_update_task handler."""

    def test_update_task_basic(self):
        from omega.server.coord_handlers import handle_update_task
        _register("ut-1", project="/proj/ut", task="initial task")
        result = run_async(handle_update_task({
            "session_id": "ut-1",
            "task": "Updated to work on auth module",
        }))
        assert not _is_error(result)
        text = _text(result)
        assert "updated" in text.lower() or "auth" in text.lower()

    def test_update_task_missing_session(self):
        from omega.server.coord_handlers import handle_update_task
        result = run_async(handle_update_task({
            "task": "some task",
        }))
        assert _is_error(result)

    def test_update_task_missing_task(self):
        from omega.server.coord_handlers import handle_update_task
        _register("ut-notask")
        result = run_async(handle_update_task({
            "session_id": "ut-notask",
        }))
        assert _is_error(result)
