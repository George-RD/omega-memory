"""Tests for retrieval quality feedback at session stop."""
import re


def test_extracts_memory_ids_from_result_summary():
    """Should extract mem-xxxxxxxxxxxx IDs from result_summary."""
    from omega.server.hook_server.session import _extract_retrieved_ids

    summary = "## 1. [decision] `mem-5d5ef8d37340` (str: 1.00)\nSome content\n## 2. [lesson] `mem-abc123def456`"
    ids = _extract_retrieved_ids(summary)
    assert "mem-5d5ef8d37340" in ids
    assert "mem-abc123def456" in ids


def test_no_ids_from_empty_summary():
    """Should return empty set from None or empty summary."""
    from omega.server.hook_server.session import _extract_retrieved_ids

    assert _extract_retrieved_ids(None) == set()
    assert _extract_retrieved_ids("") == set()


def test_feedback_records_helpful_for_reused_ids():
    """Should call record_feedback('helpful') for IDs that reappear later."""
    from omega.server.hook_server.session import _compute_retrieval_feedback

    audit_rows = [
        {"tool_name": "omega_query", "result_summary": "## 1. `mem-aaa111222333` content\n## 2. `mem-bbb444555666`", "call_index": 5, "result_status": "ok"},
        {"tool_name": "Bash", "result_summary": "using mem-aaa111222333 in output", "call_index": 10, "result_status": "ok"},
        {"tool_name": "Edit", "result_summary": "edited file successfully", "call_index": 15, "result_status": "ok"},
    ]

    feedback = _compute_retrieval_feedback(audit_rows)
    assert ("mem-aaa111222333", "helpful", "retrieval_used") in feedback
    assert not any(f[0] == "mem-bbb444555666" for f in feedback)


def test_no_feedback_without_omega_query():
    """Should return empty list when no omega_query calls in session."""
    from omega.server.hook_server.session import _compute_retrieval_feedback

    audit_rows = [
        {"tool_name": "Edit", "result_summary": "edited foo.py", "call_index": 1, "result_status": "ok"},
        {"tool_name": "Bash", "result_summary": "pytest passed", "call_index": 2, "result_status": "ok"},
    ]

    feedback = _compute_retrieval_feedback(audit_rows)
    assert feedback == []
