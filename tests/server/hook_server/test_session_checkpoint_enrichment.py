"""Tests for enriched auto-checkpoint content at session stop."""
import re


def test_checkpoint_includes_files_touched(tmp_path):
    """Auto-checkpoint should include files from coord_audit Edit/Write entries."""
    from omega.server.hook_server.session import _enrich_checkpoint_content

    audit_rows = [
        {"tool_name": "Edit", "result_summary": "Updated /tmp/foo.py successfully", "call_index": 1, "result_status": "ok"},
        {"tool_name": "Write", "result_summary": "Created /tmp/bar.py successfully", "call_index": 2, "result_status": "ok"},
        {"tool_name": "Bash", "result_summary": "pytest passed", "call_index": 3, "result_status": "ok"},
    ]

    result = _enrich_checkpoint_content("Base checkpoint", audit_rows, handoff_content=None)
    assert "files_touched" in result.lower() or "foo.py" in result or "bar.py" in result


def test_checkpoint_includes_next_steps_from_handoff(tmp_path):
    """Auto-checkpoint should include next_steps from handoff content."""
    from omega.server.hook_server.session import _enrich_checkpoint_content

    handoff = "## Open issues\n- Fix auth bug in login flow\n- Update tests for new API"

    result = _enrich_checkpoint_content("Base checkpoint", [], handoff_content=handoff)
    assert "next_steps" in result.lower() or "auth bug" in result.lower()


def test_checkpoint_graceful_with_no_enrichment(tmp_path):
    """Checkpoint should return base content when no enrichment data available."""
    from omega.server.hook_server.session import _enrich_checkpoint_content

    result = _enrich_checkpoint_content("Base checkpoint", [], handoff_content=None)
    assert result == "Base checkpoint"
