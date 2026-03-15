"""Tests for background coordination loop in mcp_server.py."""
from unittest.mock import patch, MagicMock


class TestCoordinationTick:
    """Background _run_coordination_tick() tests."""

    def test_coordination_tick_calls_stale_cleanup(self):
        """Tick triggers _maybe_clean_stale on the coordination manager."""
        from omega.server.mcp_server import _run_coordination_tick
        import omega.server.mcp_server as mcp_mod

        mock_mgr = MagicMock()

        # Reset tick count to avoid deadlock detection path
        mcp_mod._coord_tick_count = 0

        with patch("omega.coordination.get_manager", return_value=mock_mgr):
            _run_coordination_tick()

        mock_mgr._maybe_clean_stale.assert_called_once()

    def test_coordination_tick_detects_deadlocks(self):
        """On 5th tick, detects deadlocks and pushes alerts."""
        from omega.server.mcp_server import _run_coordination_tick
        import omega.server.mcp_server as mcp_mod
        import omega.server.hook_server as hs

        mock_mgr = MagicMock()
        mock_mgr.detect_deadlocks.return_value = [["sess-a", "sess-b", "sess-a"]]

        # Set tick count so next call is 5th tick
        mcp_mod._coord_tick_count = 4

        saved_push = dict(hs._last_deadlock_push)
        hs._last_deadlock_push.clear()

        with patch("omega.coordination.get_manager", return_value=mock_mgr):
            _run_coordination_tick()

        mock_mgr.detect_deadlocks.assert_called_once()
        # send_message should have been called for peers in the cycle
        assert mock_mgr.send_message.call_count >= 1

        hs._last_deadlock_push.clear()
        hs._last_deadlock_push.update(saved_push)

    def test_coordination_tick_fail_open(self):
        """Exception in tick doesn't propagate — loop stays alive."""
        from omega.server.mcp_server import _run_coordination_tick
        import omega.server.mcp_server as mcp_mod

        mcp_mod._coord_tick_count = 0

        with patch("omega.coordination.get_manager", side_effect=RuntimeError("boom")):
            # Should NOT raise
            _run_coordination_tick()
