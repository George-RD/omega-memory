"""OMEGA Oracle Tool Schemas -- 4 tools for prediction intelligence."""

ORACLE_TOOL_SCHEMAS = [
    {
        "name": "omega_oracle_record",
        "description": (
            "Record a prediction, wallet score, regime change, or signal snapshot "
            "into OMEGA's Oracle prediction intelligence layer. Stores structured "
            "metadata for compounding calibration memory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {
                    "type": "string",
                    "enum": ["prediction", "wallet_score", "regime_change", "signal_snapshot"],
                    "description": "Type of oracle record to store.",
                },
                "content": {
                    "type": "string",
                    "description": "Human-readable summary of the record.",
                },
                "data": {
                    "type": "object",
                    "description": (
                        "Structured metadata. For prediction: market_id, our_probability, "
                        "market_price, edge, confidence, signals_present, regime, "
                        "ensemble_strategies, sp_signal, time_horizon_days, target_price. "
                        "For wallet_score: address, brier_score, trade_count, win_rate, "
                        "is_informed. For regime_change: from_regime, to_regime, confidence. "
                        "For signal_snapshot: signal data."
                    ),
                },
                "market_type": {
                    "type": "string",
                    "description": "Market type (default: btc).",
                    "default": "btc",
                },
            },
            "required": ["record_type", "content", "data"],
        },
    },
    {
        "name": "omega_oracle_resolve",
        "description": (
            "Mark a prediction as resolved with its outcome. Finds the matching "
            "oracle_prediction memory by market_id and updates its metadata with "
            "the outcome and P&L."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "market_id": {
                    "type": "string",
                    "description": "The market_id of the prediction to resolve.",
                },
                "outcome": {
                    "type": "string",
                    "enum": ["yes", "no"],
                    "description": "How the market resolved.",
                },
                "resolution_price": {
                    "type": "number",
                    "description": "Final resolution price (optional).",
                },
            },
            "required": ["market_id", "outcome"],
        },
    },
    {
        "name": "omega_oracle_analyze",
        "description": (
            "Compute analytical views over prediction history. Views: "
            "calibration (Brier score, calibration curve), signals (per-signal "
            "accuracy), wallets (top wallets by accuracy), bias (systematic "
            "mispricings), playbook (optimal strategy per regime), briefing "
            "(composite of all views for probability estimator context)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view": {
                    "type": "string",
                    "enum": ["calibration", "signals", "wallets", "bias", "playbook", "briefing"],
                    "description": "Which analytical view to compute.",
                },
                "market_type": {
                    "type": "string",
                    "description": "Filter by market type (default: btc).",
                    "default": "btc",
                },
                "regime": {
                    "type": "string",
                    "description": "Current regime for playbook view.",
                },
                "days": {
                    "type": "integer",
                    "description": "Limit analysis to last N days.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results for wallet rankings.",
                    "default": 20,
                },
            },
            "required": ["view"],
        },
    },
    {
        "name": "omega_oracle_status",
        "description": (
            "Oracle dashboard: prediction count, resolved count, current "
            "Brier score, active regime, wallet coverage, signal coverage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]
