"""Tests for mid-session memory context push in insights.py."""


def test_memory_push_fires_after_50_calls(monkeypatch):
    """Should return [MEMORY_CONTEXT] block when call count >= 50."""
    from omega.server.hook_server import insights
    from omega.server.hook_server.trace import _call_counters

    session_id = "test-session-push"
    _call_counters[session_id] = 60

    def mock_query(query_text, limit=10, event_type=None, **kwargs):
        return [
            {"node_id": "mem-aaa111222333", "content": "Prior decision about auth", "event_type": "decision", "metadata": {}},
            {"node_id": "mem-bbb444555666", "content": "Lesson about error handling", "event_type": "lesson_learned", "metadata": {}},
        ]

    monkeypatch.setattr("omega.bridge.query_structured", mock_query)

    payload = {
        "tool_name": "Edit",
        "tool_input": '{"file_path": "/tmp/test_auth.py", "old_string": "a", "new_string": "b"}',
        "session_id": session_id,
    }

    result = insights.handle_pre_insight_surface(payload)
    output = result.get("output", "")
    assert "[MEMORY_CONTEXT]" in output
    assert "mem-aaa111222333" in output

    # Cleanup
    _call_counters.pop(session_id, None)
    insights._session_memory_pushed.pop(session_id, None)


def test_memory_push_skips_below_50_calls(monkeypatch):
    """Should NOT push when call count < 50."""
    from omega.server.hook_server import insights
    from omega.server.hook_server.trace import _call_counters

    session_id = "test-session-low"
    _call_counters[session_id] = 10

    payload = {
        "tool_name": "Edit",
        "tool_input": '{"file_path": "/tmp/test.py", "old_string": "a", "new_string": "b"}',
        "session_id": session_id,
    }

    result = insights.handle_pre_insight_surface(payload)
    output = result.get("output", "")
    assert "[MEMORY_CONTEXT]" not in output

    _call_counters.pop(session_id, None)


def test_memory_push_no_duplicate_per_file(monkeypatch):
    """Should push once per file per session, not twice."""
    from omega.server.hook_server import insights
    from omega.server.hook_server.trace import _call_counters

    session_id = "test-session-dedup"
    _call_counters[session_id] = 60

    def mock_query(query_text, limit=10, event_type=None, **kwargs):
        return [
            {"node_id": "mem-ccc777888999", "content": "Some memory", "event_type": "decision", "metadata": {}},
        ]

    monkeypatch.setattr("omega.bridge.query_structured", mock_query)

    payload = {
        "tool_name": "Edit",
        "tool_input": '{"file_path": "/tmp/dedup_test.py", "old_string": "a", "new_string": "b"}',
        "session_id": session_id,
    }

    result1 = insights.handle_pre_insight_surface(payload)
    assert "[MEMORY_CONTEXT]" in result1.get("output", "")

    result2 = insights.handle_pre_insight_surface(payload)
    assert "[MEMORY_CONTEXT]" not in result2.get("output", "")

    _call_counters.pop(session_id, None)
    insights._session_memory_pushed.pop(session_id, None)


def test_memory_push_skips_non_edit_tools():
    """Should not fire for Bash, Read, etc."""
    from omega.server.hook_server import insights

    payload = {
        "tool_name": "Bash",
        "tool_input": '{"command": "ls"}',
        "session_id": "test-session",
    }

    result = insights.handle_pre_insight_surface(payload)
    assert "[MEMORY_CONTEXT]" not in result.get("output", "")
