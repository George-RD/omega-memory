"""OMEGA Oracle Handlers -- MCP handlers for prediction intelligence."""

import logging
from typing import Any, Dict

logger = logging.getLogger("omega.oracle.handlers")


from omega.server.responses import mcp_response, mcp_error


async def handle_omega_oracle_record(arguments: dict) -> dict:
    """Record a prediction, wallet score, regime change, or signal snapshot."""
    record_type = arguments.get("record_type", "").strip()
    content = arguments.get("content", "").strip()
    data = arguments.get("data")
    market_type = arguments.get("market_type", "btc").strip()

    if not record_type:
        return mcp_error("record_type is required")
    if not content:
        return mcp_error("content is required")
    if not data or not isinstance(data, dict):
        return mcp_error("data must be a non-empty object")

    valid_types = ("prediction", "wallet_score", "regime_change", "signal_snapshot")
    if record_type not in valid_types:
        return mcp_error(f"record_type must be one of: {', '.join(valid_types)}")

    try:
        from omega.oracle.engine import get_oracle_engine
        engine = get_oracle_engine()

        if record_type == "prediction":
            if not data.get("market_id"):
                return mcp_error("data.market_id is required for predictions")
            result_id = engine.record_prediction(content, data, market_type)
        elif record_type == "wallet_score":
            if not data.get("address"):
                return mcp_error("data.address is required for wallet scores")
            result_id = engine.record_wallet_score(content, data, market_type)
        elif record_type == "regime_change":
            if not data.get("to_regime"):
                return mcp_error("data.to_regime is required for regime changes")
            result_id = engine.record_regime_change(content, data)
        elif record_type == "signal_snapshot":
            result_id = engine.record_signal_snapshot(content, data, market_type)

        return mcp_response(f"Recorded oracle {record_type}: {result_id}")
    except ImportError as e:
        return mcp_error(str(e))
    except Exception as e:
        logger.error("omega_oracle_record failed: %s", e, exc_info=True)
        return mcp_error(f"Failed to record: {e}")


async def handle_omega_oracle_resolve(arguments: dict) -> dict:
    """Resolve a prediction with its outcome."""
    market_id = arguments.get("market_id", "").strip()
    outcome = arguments.get("outcome", "").strip()
    resolution_price = arguments.get("resolution_price")

    if not market_id:
        return mcp_error("market_id is required")
    if outcome not in ("yes", "no"):
        return mcp_error("outcome must be 'yes' or 'no'")

    try:
        from omega.oracle.engine import get_oracle_engine
        engine = get_oracle_engine()

        result = engine.resolve_prediction(market_id, outcome, resolution_price)
        if result.get("success"):
            pnl = result.get("pnl")
            pnl_str = f", P&L: {pnl:+.4f}" if pnl is not None else ""
            return mcp_response(
                f"Resolved {market_id} as {outcome}{pnl_str} "
                f"(memory: {result['memory_id'][:12]})"
            )
        return mcp_error(result.get("error", "Unknown error"))
    except ImportError as e:
        return mcp_error(str(e))
    except Exception as e:
        logger.error("omega_oracle_resolve failed: %s", e, exc_info=True)
        return mcp_error(f"Failed to resolve: {e}")


async def handle_omega_oracle_analyze(arguments: dict) -> dict:
    """Compute analytical views over prediction history."""
    view = arguments.get("view", "").strip()
    market_type = arguments.get("market_type", "btc").strip()
    regime = arguments.get("regime")
    days = arguments.get("days")
    limit = arguments.get("limit", 20)

    valid_views = ("calibration", "signals", "wallets", "bias", "playbook", "briefing")
    if view not in valid_views:
        return mcp_error(f"view must be one of: {', '.join(valid_views)}")

    try:
        from omega.oracle.engine import get_oracle_engine
        from omega import json_compat as json
        engine = get_oracle_engine()

        if view == "calibration":
            result = engine.compute_calibration(market_type=market_type, days=days)
        elif view == "signals":
            result = engine.compute_signal_attribution(market_type=market_type)
        elif view == "wallets":
            result = engine.get_wallet_rankings(market_type=market_type, limit=limit)
        elif view == "bias":
            result = engine.get_market_bias(market_type=market_type)
        elif view == "playbook":
            result = engine.get_regime_playbook(current_regime=regime)
        elif view == "briefing":
            result = engine.get_briefing(market_type=market_type)
            # For briefing, return the text directly
            return mcp_response(result.get("briefing_text", json.dumps(result, indent=2)))

        return mcp_response(json.dumps(result, indent=2))
    except ImportError as e:
        return mcp_error(str(e))
    except Exception as e:
        logger.error("omega_oracle_analyze failed: %s", e, exc_info=True)
        return mcp_error(f"Failed to analyze: {e}")


async def handle_omega_oracle_status(arguments: dict) -> dict:
    """Oracle dashboard."""
    try:
        from omega.oracle.engine import get_oracle_engine
        from omega import json_compat as json
        engine = get_oracle_engine()

        status = engine.get_status()
        return mcp_response(json.dumps(status, indent=2))
    except ImportError as e:
        return mcp_error(str(e))
    except Exception as e:
        logger.error("omega_oracle_status failed: %s", e, exc_info=True)
        return mcp_error(f"Failed to get status: {e}")


ORACLE_HANDLERS: Dict[str, Any] = {
    "omega_oracle_record": handle_omega_oracle_record,
    "omega_oracle_resolve": handle_omega_oracle_resolve,
    "omega_oracle_analyze": handle_omega_oracle_analyze,
    "omega_oracle_status": handle_omega_oracle_status,
}
