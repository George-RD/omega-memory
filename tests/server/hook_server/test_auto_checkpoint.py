"""Tests for enhanced auto-checkpoint trigger logic in handle_session_stop."""
import contextlib
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store_mock(has_manual_checkpoint: bool = False, captured_counts: dict = None):
    """Return a mock store simulating the needed DB interactions."""
    store = MagicMock()
    # get_session_event_counts returns the captured dict
    store.get_session_event_counts.return_value = captured_counts or {}
    # _conn.execute for the checkpoint skip query and coord_handoffs cleanup
    store._conn.execute.return_value.fetchone.return_value = (1,) if has_manual_checkpoint else None
    return store


def _two_decisions():
    """Return a list of 2 fake decision memories so _has_activity=True."""
    return [
        {"id": f"d{i}", "content": f"decision {i}", "event_type": "decision",
         "metadata": {}, "relevance_score": 0.9, "session_id": "ignored"}
        for i in range(2)
    ]


def _query_structured_side_effect(two_decisions):
    """Return decisions on first call, empty on subsequent calls."""
    calls = {"count": 0}

    def _side_effect(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return two_decisions  # decisions query
        return []  # errors and tasks queries

    return _side_effect


def _checkpoint_calls(mock_capture):
    """Filter auto_capture calls to only those with event_type='checkpoint'."""
    return [
        c for c in mock_capture.call_args_list
        if c[1].get("event_type") == "checkpoint"
    ]


@contextlib.contextmanager
def _session_stop_patches(mock_capture, store_mock, decisions=None):
    """Patch all external dependencies needed by handle_session_stop."""
    if decisions is None:
        decisions = _two_decisions()
    mock_coord_mgr = MagicMock()
    mock_coord_mgr._conn.execute.return_value.fetchone.return_value = None

    with patch("omega.bridge.query_structured",
               side_effect=_query_structured_side_effect(decisions)), \
         patch("omega.bridge.session_stats", return_value={}), \
         patch("omega.bridge.type_stats", return_value={}), \
         patch("omega.bridge.auto_capture", mock_capture), \
         patch("omega.bridge._get_store", return_value=store_mock), \
         patch("omega.coordination.get_manager", return_value=mock_coord_mgr):
        yield


# ---------------------------------------------------------------------------
# Test 1: Checkpoint fires when tool_calls >= 30 but stores < 3
# ---------------------------------------------------------------------------

def test_checkpoint_fires_on_high_tool_calls():
    """Auto-checkpoint should fire when session has 30+ tool calls even with < 3 stores."""
    from omega.server.hook_server import handle_session_stop
    from omega.server.hook_server import trace

    session_id = "high-tool-calls-session"
    original_count = trace._call_counters.get(session_id)
    # Seed 30 tool calls; stores count = 1 (below threshold of 3)
    trace._call_counters[session_id] = 30
    store_mock = _make_store_mock(
        has_manual_checkpoint=False,
        captured_counts={"memory": 1},  # captured = 1, below 3
    )
    mock_capture = MagicMock(return_value="# Captured")

    try:
        with _session_stop_patches(mock_capture, store_mock):
            handle_session_stop({"session_id": session_id, "project": "/tmp"})

        ckpt_calls = _checkpoint_calls(mock_capture)
        assert len(ckpt_calls) == 1, f"Expected 1 checkpoint call, got {len(ckpt_calls)}"
        call_kwargs = ckpt_calls[0][1]
        assert call_kwargs["metadata"]["source"] == "session_stop_auto_checkpoint"
        assert call_kwargs["metadata"]["tool_calls"] == 30
        assert "tool_calls=30" in call_kwargs["content"]
    finally:
        if original_count is None:
            trace._call_counters.pop(session_id, None)
        else:
            trace._call_counters[session_id] = original_count


# ---------------------------------------------------------------------------
# Test 2: Checkpoint skips when agent already checkpointed manually
# ---------------------------------------------------------------------------

def test_checkpoint_skips_when_manual_checkpoint_exists():
    """Auto-checkpoint should be skipped if a manual checkpoint exists for the session."""
    from omega.server.hook_server import handle_session_stop
    from omega.server.hook_server import trace

    session_id = "manual-ckpt-session"
    original_count = trace._call_counters.get(session_id)
    # High tool calls to trigger the condition check
    trace._call_counters[session_id] = 30
    # Manual checkpoint exists in DB
    store_mock = _make_store_mock(
        has_manual_checkpoint=True,
        captured_counts={"memory": 1},
    )
    mock_capture = MagicMock(return_value="# Captured")

    try:
        with _session_stop_patches(mock_capture, store_mock):
            handle_session_stop({"session_id": session_id, "project": "/tmp"})

        ckpt_calls = _checkpoint_calls(mock_capture)
        assert ckpt_calls == [], (
            f"Expected no checkpoint calls, but got: {ckpt_calls}"
        )
    finally:
        if original_count is None:
            trace._call_counters.pop(session_id, None)
        else:
            trace._call_counters[session_id] = original_count


# ---------------------------------------------------------------------------
# Test 3: Existing behavior preserved — checkpoint fires on stores >= 3
# ---------------------------------------------------------------------------

def test_checkpoint_fires_on_three_or_more_stores():
    """Existing behavior: auto-checkpoint fires when 3+ stores happen."""
    from omega.server.hook_server import handle_session_stop
    from omega.server.hook_server import trace

    session_id = "three-stores-session"
    original_count = trace._call_counters.get(session_id)
    # Tool calls below threshold — trigger should come from stores alone
    trace._call_counters[session_id] = 5
    store_mock = _make_store_mock(
        has_manual_checkpoint=False,
        captured_counts={"memory": 3},  # captured = 3, meets threshold
    )
    mock_capture = MagicMock(return_value="# Captured")

    try:
        with _session_stop_patches(mock_capture, store_mock):
            handle_session_stop({"session_id": session_id, "project": "/tmp"})

        ckpt_calls = _checkpoint_calls(mock_capture)
        assert len(ckpt_calls) == 1, f"Expected 1 checkpoint call, got {len(ckpt_calls)}"
        call_kwargs = ckpt_calls[0][1]
        assert call_kwargs["metadata"]["source"] == "session_stop_auto_checkpoint"
        assert call_kwargs["metadata"]["stores"] >= 3
    finally:
        if original_count is None:
            trace._call_counters.pop(session_id, None)
        else:
            trace._call_counters[session_id] = original_count


# ---------------------------------------------------------------------------
# Test 4: No checkpoint when activity is below both thresholds
# ---------------------------------------------------------------------------

def test_checkpoint_does_not_fire_below_thresholds():
    """No auto-checkpoint when tool_calls < 30 and stores < 3."""
    from omega.server.hook_server import handle_session_stop
    from omega.server.hook_server import trace

    session_id = "low-activity-session"
    original_count = trace._call_counters.get(session_id)
    trace._call_counters[session_id] = 2  # below 30
    store_mock = _make_store_mock(
        has_manual_checkpoint=False,
        captured_counts={"memory": 1},  # captured = 1, below 3
    )
    mock_capture = MagicMock(return_value="# Captured")

    try:
        with _session_stop_patches(mock_capture, store_mock):
            handle_session_stop({"session_id": session_id, "project": "/tmp"})

        ckpt_calls = _checkpoint_calls(mock_capture)
        assert ckpt_calls == [], (
            f"Expected no checkpoint calls below thresholds, but got: {ckpt_calls}"
        )
    finally:
        if original_count is None:
            trace._call_counters.pop(session_id, None)
        else:
            trace._call_counters[session_id] = original_count
