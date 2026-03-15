"""Tests for procedural learning extraction at session stop."""


def test_detects_recovery_pattern():
    """Should detect error→success recovery on same tool_name."""
    from omega.server.hook_server.session import _detect_patterns

    rows = [
        {"tool_name": "Bash", "result_status": "error", "result_summary": "FAILED test_auth", "call_index": i}
        for i in range(1, 4)
    ] + [
        {"tool_name": "Bash", "result_status": "ok", "result_summary": "All tests passed", "call_index": 4},
    ]

    recoveries, stuck = _detect_patterns(rows)
    assert len(recoveries) >= 1
    assert recoveries[0]["tool_name"] == "Bash"
    assert recoveries[0]["attempts"] == 3
    assert "FAILED" in recoveries[0]["error_context"]
    assert "passed" in recoveries[0]["success_context"]


def test_detects_stuck_pattern():
    """Should detect 5+ consecutive errors on same tool_name."""
    from omega.server.hook_server.session import _detect_patterns

    rows = [
        {"tool_name": "Edit", "result_status": "error", "result_summary": f"Edit failed attempt {i}", "call_index": i}
        for i in range(1, 7)
    ]

    recoveries, stuck = _detect_patterns(rows)
    assert len(stuck) >= 1
    assert stuck[0]["tool_name"] == "Edit"
    assert stuck[0]["consecutive_errors"] >= 5


def test_no_patterns_with_all_ok():
    """Should return empty when all tools succeed."""
    from omega.server.hook_server.session import _detect_patterns

    rows = [
        {"tool_name": "Bash", "result_status": "ok", "result_summary": "ok", "call_index": i}
        for i in range(1, 10)
    ]

    recoveries, stuck = _detect_patterns(rows)
    assert recoveries == []
    assert stuck == []


def test_skips_short_sessions():
    """Should not extract learnings from sessions with <20 tool calls."""
    from omega.server.hook_server.session import _should_extract_learnings

    assert _should_extract_learnings(19) is False
    assert _should_extract_learnings(20) is True
    assert _should_extract_learnings(100) is True


def test_max_3_learnings():
    """Should cap learnings at 3 per session."""
    from omega.server.hook_server.session import _detect_patterns

    rows = []
    idx = 1
    for tool in ["Bash", "Edit", "Write", "Grep", "Read"]:
        rows.append({"tool_name": tool, "result_status": "error", "result_summary": f"{tool} failed", "call_index": idx})
        idx += 1
        rows.append({"tool_name": tool, "result_status": "ok", "result_summary": f"{tool} ok", "call_index": idx})
        idx += 1

    recoveries, stuck = _detect_patterns(rows)
    assert len(recoveries) >= 3
