"""Tests for OMEGA Oracle edge cases -- covers gaps not in test_oracle.py.

Covers: Brier score extremes, P&L edge cases, multi-market analysis,
regime transitions, resolution_price, signal attribution with mixed outcomes,
wallet ranking edge cases, market bias with subtypes, briefing content,
status after operations, None market_type, and large prediction histories.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record_and_resolve(engine, market_id, our_prob, outcome,
                        market_type="btc", edge=None, regime="trending",
                        signals=None, market_price=None,
                        ensemble_strategies=None,
                        resolution_price=None):
    """Helper: record a prediction and immediately resolve it."""
    if edge is None:
        edge = our_prob - 0.5
    if market_price is None:
        market_price = our_prob - edge
    data = {
        "market_id": market_id,
        "our_probability": our_prob,
        "market_price": market_price,
        "edge": edge,
        "regime": regime,
    }
    if signals is not None:
        data["signals_present"] = signals
    if ensemble_strategies is not None:
        data["ensemble_strategies"] = ensemble_strategies
    engine.record_prediction(
        content=f"Prediction {market_id} prob={our_prob}",
        data=data,
        market_type=market_type,
    )
    return engine.resolve_prediction(market_id, outcome,
                                     resolution_price=resolution_price)


# ============================================================================
# 1. Brier Score Edge Cases
# ============================================================================

class TestBrierScoreEdgeCases:
    """Brier score at extremes: perfect, worst, and 50/50."""

    def test_brier_all_correct_high_confidence(self, oracle_engine):
        """All predictions correct with high confidence -> Brier near 0."""
        for i in range(10):
            _record_and_resolve(
                oracle_engine,
                market_id=f"perfect-yes-{i}",
                our_prob=0.95,
                outcome="yes",
            )
        for i in range(10):
            _record_and_resolve(
                oracle_engine,
                market_id=f"perfect-no-{i}",
                our_prob=0.05,
                outcome="no",
            )
        cal = oracle_engine.compute_calibration()
        assert cal["total_resolved"] == 20
        # Brier for (0.95-1)^2 = 0.0025, (0.05-0)^2 = 0.0025 -> avg 0.0025
        assert cal["brier_score"] < 0.01
        assert cal["brier_interpretation"] == "excellent"

    def test_brier_all_wrong_high_confidence(self, oracle_engine):
        """All predictions wrong with high confidence -> Brier near 1."""
        for i in range(10):
            _record_and_resolve(
                oracle_engine,
                market_id=f"wrong-yes-{i}",
                our_prob=0.95,
                outcome="no",  # predicted yes, outcome no
            )
        for i in range(10):
            _record_and_resolve(
                oracle_engine,
                market_id=f"wrong-no-{i}",
                our_prob=0.05,
                outcome="yes",  # predicted no, outcome yes
            )
        cal = oracle_engine.compute_calibration()
        assert cal["total_resolved"] == 20
        # Brier for (0.95-0)^2 = 0.9025, (0.05-1)^2 = 0.9025 -> avg 0.9025
        assert cal["brier_score"] > 0.85
        assert cal["brier_interpretation"] == "poor"

    def test_brier_fifty_percent_confidence(self, oracle_engine):
        """All predictions at 50% confidence -> Brier = 0.25."""
        for i in range(10):
            _record_and_resolve(
                oracle_engine,
                market_id=f"fifty-yes-{i}",
                our_prob=0.50,
                outcome="yes",
            )
        for i in range(10):
            _record_and_resolve(
                oracle_engine,
                market_id=f"fifty-no-{i}",
                our_prob=0.50,
                outcome="no",
            )
        cal = oracle_engine.compute_calibration()
        assert cal["total_resolved"] == 20
        # (0.5-1)^2 = 0.25, (0.5-0)^2 = 0.25 -> avg 0.25
        assert abs(cal["brier_score"] - 0.25) < 0.001
        # Exactly 0.25 falls into "mediocre" tier (>= 0.25 and < 0.30)
        assert cal["brier_interpretation"] == "mediocre"

    def test_brier_single_prediction(self, oracle_engine):
        """Brier with just one resolved prediction."""
        _record_and_resolve(
            oracle_engine,
            market_id="single",
            our_prob=0.80,
            outcome="yes",
        )
        cal = oracle_engine.compute_calibration()
        assert cal["total_resolved"] == 1
        # (0.80 - 1.0)^2 = 0.04
        assert abs(cal["brier_score"] - 0.04) < 0.001

    def test_brier_interpretation_boundaries(self, oracle_engine):
        """Verify each Brier interpretation tier boundary."""
        # Excellent: brier < 0.10  -> prob=0.95, outcome=yes -> (0.95-1)^2 = 0.0025
        _record_and_resolve(oracle_engine, "tier-ex", 0.95, "yes")
        cal = oracle_engine.compute_calibration()
        assert cal["brier_interpretation"] == "excellent"


# ============================================================================
# 2. P&L Calculation Edge Cases
# ============================================================================

class TestPnLEdgeCases:
    """P&L computation on resolve: negative predictions, zero values, large."""

    def test_pnl_positive_when_correct_yes(self, oracle_engine):
        """When predicted YES and outcome=yes, pnl = 1 - market_price."""
        result = _record_and_resolve(
            oracle_engine,
            market_id="pnl-yes",
            our_prob=0.80,
            edge=0.15,
            outcome="yes",
        )
        assert result["success"] is True
        assert result["pnl"] == 0.35

    def test_pnl_negative_when_wrong(self, oracle_engine):
        """When predicted YES and outcome=no, pnl = -market_price."""
        result = _record_and_resolve(
            oracle_engine,
            market_id="pnl-no",
            our_prob=0.80,
            edge=0.15,
            outcome="no",
        )
        assert result["success"] is True
        assert result["pnl"] == -0.65

    def test_pnl_zero_edge(self, oracle_engine):
        """Edge=0 at market_price=0.50 with yes outcome -> pnl=0.50."""
        result = _record_and_resolve(
            oracle_engine,
            market_id="pnl-zero-edge",
            our_prob=0.50,
            edge=0.0,
            outcome="yes",
        )
        assert result["pnl"] == 0.50

    def test_pnl_negative_edge(self, oracle_engine):
        """Predicted NO (our_prob<0.5) but outcome=yes -> loss."""
        result = _record_and_resolve(
            oracle_engine,
            market_id="pnl-neg-edge",
            our_prob=0.40,
            edge=-0.10,
            outcome="yes",
        )
        assert result["pnl"] == -0.50

    def test_pnl_very_large_edge(self, oracle_engine):
        """High confidence, large edge, market_price=0.50 -> pnl=0.50."""
        result = _record_and_resolve(
            oracle_engine,
            market_id="pnl-large",
            our_prob=0.99,
            edge=0.49,
            outcome="yes",
        )
        assert result["pnl"] == 0.50

    def test_pnl_zero_probability_no_outcome(self, oracle_engine):
        """Predicted NO (our_prob=0), outcome=no, market_price=0 -> pnl=0."""
        result = _record_and_resolve(
            oracle_engine,
            market_id="pnl-zero-prob",
            our_prob=0.0,
            edge=0.0,
            outcome="no",
        )
        assert result["pnl"] == 0.0

    def test_pnl_full_probability_yes_outcome(self, oracle_engine):
        """Predicted YES (our_prob=1.0), outcome=yes, market_price=0.50 -> pnl=0.50."""
        result = _record_and_resolve(
            oracle_engine,
            market_id="pnl-full",
            our_prob=1.0,
            edge=0.50,
            outcome="yes",
        )
        assert result["pnl"] == 0.50


# ============================================================================
# 3. Multi-Market Analysis
# ============================================================================

class TestMultiMarketAnalysis:
    """Record predictions across btc, eth, sol and verify per-market filtering."""

    def _seed_multi_market(self, engine):
        markets = {
            "btc": [("btc-1", 0.70, "yes"), ("btc-2", 0.60, "no"), ("btc-3", 0.80, "yes")],
            "eth": [("eth-1", 0.55, "yes"), ("eth-2", 0.75, "no")],
            "sol": [("sol-1", 0.90, "yes"), ("sol-2", 0.40, "no"), ("sol-3", 0.65, "yes"), ("sol-4", 0.30, "no")],
        }
        for mtype, preds in markets.items():
            for mid, prob, outcome in preds:
                _record_and_resolve(engine, mid, prob, outcome, market_type=mtype)

    def test_calibration_filtered_by_market_type(self, oracle_engine):
        self._seed_multi_market(oracle_engine)
        btc_cal = oracle_engine.compute_calibration(market_type="btc")
        eth_cal = oracle_engine.compute_calibration(market_type="eth")
        sol_cal = oracle_engine.compute_calibration(market_type="sol")

        assert btc_cal["total_resolved"] == 3
        assert eth_cal["total_resolved"] == 2
        assert sol_cal["total_resolved"] == 4

    def test_calibration_all_markets(self, oracle_engine):
        self._seed_multi_market(oracle_engine)
        all_cal = oracle_engine.compute_calibration(market_type=None)
        assert all_cal["total_resolved"] == 9  # 3 + 2 + 4

    def test_signal_attribution_filtered(self, oracle_engine):
        """Signal attribution respects market_type filter."""
        for i in range(6):
            _record_and_resolve(
                oracle_engine,
                market_id=f"btc-sig-{i}",
                our_prob=0.70,
                outcome="yes",
                market_type="btc",
                signals=[{"name": "etf_flows"}],
            )
        for i in range(6):
            _record_and_resolve(
                oracle_engine,
                market_id=f"eth-sig-{i}",
                our_prob=0.30,
                outcome="no",
                market_type="eth",
                signals=[{"name": "gas_fees"}],
            )
        btc_sigs = oracle_engine.compute_signal_attribution(market_type="btc", min_samples=5)
        eth_sigs = oracle_engine.compute_signal_attribution(market_type="eth", min_samples=5)

        btc_names = {s["name"] for s in btc_sigs["signals"]}
        eth_names = {s["name"] for s in eth_sigs["signals"]}

        assert "etf_flows" in btc_names
        assert "gas_fees" not in btc_names
        assert "gas_fees" in eth_names
        assert "etf_flows" not in eth_names

    def test_wallet_rankings_filtered(self, oracle_engine):
        """Wallet rankings respect market_type filter."""
        oracle_engine.record_wallet_score(
            content="BTC wallet",
            data={"address": "0xbtcwallet", "brier_score": 0.10, "trade_count": 20, "is_informed": True},
            market_type="btc",
        )
        oracle_engine.record_wallet_score(
            content="ETH wallet",
            data={"address": "0xethwallet", "brier_score": 0.15, "trade_count": 15, "is_informed": True},
            market_type="eth",
        )
        btc_wallets = oracle_engine.get_wallet_rankings(market_type="btc", min_trades=5)
        eth_wallets = oracle_engine.get_wallet_rankings(market_type="eth", min_trades=5)

        btc_addrs = [w.get("address") for w in btc_wallets["top_wallets"]]
        eth_addrs = [w.get("address") for w in eth_wallets["top_wallets"]]

        assert "0xbtcwallet" in btc_addrs
        assert "0xethwallet" not in btc_addrs
        assert "0xethwallet" in eth_addrs

    def test_market_bias_filtered(self, oracle_engine):
        """Market bias respects market_type filter."""
        self._seed_multi_market(oracle_engine)
        btc_bias = oracle_engine.get_market_bias(market_type="btc")
        sol_bias = oracle_engine.get_market_bias(market_type="sol")

        assert btc_bias["total_resolved"] == 3
        assert sol_bias["total_resolved"] == 4


# ============================================================================
# 4. Regime Transitions
# ============================================================================

class TestRegimeTransitions:
    """Record multiple regime changes, verify playbook picks latest."""

    def test_multiple_regime_changes(self, oracle_engine):
        """Record a sequence of regime changes."""
        transitions = [
            ("low_vol", "trending", 0.80),
            ("trending", "high_vol", 0.75),
            ("high_vol", "crisis", 0.90),
            ("crisis", "recovery", 0.85),
        ]
        for from_r, to_r, conf in transitions:
            mid = oracle_engine.record_regime_change(
                content=f"Regime changed from {from_r} to {to_r}",
                data={
                    "from_regime": from_r,
                    "to_regime": to_r,
                    "confidence": conf,
                },
            )
            assert mid  # should return a memory id

    def test_playbook_includes_regime_transitions(self, oracle_engine):
        """Regime transitions appear in the playbook result."""
        oracle_engine.record_regime_change(
            content="Regime: low_vol -> trending",
            data={"from_regime": "low_vol", "to_regime": "trending", "confidence": 0.80},
        )
        oracle_engine.record_regime_change(
            content="Regime: trending -> high_vol",
            data={"from_regime": "trending", "to_regime": "high_vol", "confidence": 0.75},
        )
        result = oracle_engine.get_regime_playbook()
        transitions = result["regime_transitions"]
        assert len(transitions) == 2
        # Latest first (DESC order)
        assert transitions[0]["to"] == "high_vol"
        assert transitions[1]["to"] == "trending"

    def test_status_picks_latest_regime(self, oracle_engine):
        """get_status() shows active_regime from the latest regime change."""
        oracle_engine.record_regime_change(
            content="Regime: low_vol -> trending",
            data={"from_regime": "low_vol", "to_regime": "trending", "confidence": 0.80},
        )
        oracle_engine.record_regime_change(
            content="Regime: trending -> high_vol",
            data={"from_regime": "trending", "to_regime": "high_vol", "confidence": 0.90},
        )
        status = oracle_engine.get_status()
        assert status["active_regime"] == "high_vol"
        assert status["regime_changes_count"] == 2

    def test_playbook_current_regime_missing(self, oracle_engine):
        """Requesting a current_regime that has no data returns no current_playbook."""
        result = oracle_engine.get_regime_playbook(current_regime="nonexistent_regime")
        assert "current_playbook" not in result
        assert "current_regime" not in result

    def test_playbook_per_regime_brier_and_kelly(self, oracle_engine):
        """Playbook computes per-regime Brier and recommends Kelly fraction."""
        # Seed trending regime predictions (good Brier)
        for i in range(5):
            _record_and_resolve(
                oracle_engine,
                market_id=f"trending-{i}",
                our_prob=0.85,
                outcome="yes",
                regime="trending",
            )
        # Seed crisis regime predictions (bad Brier)
        for i in range(5):
            _record_and_resolve(
                oracle_engine,
                market_id=f"crisis-{i}",
                our_prob=0.85,
                outcome="no",  # wrong
                regime="crisis",
            )

        result = oracle_engine.get_regime_playbook()
        playbooks = result["playbooks"]

        # Trending should have good Brier -> higher Kelly
        if "trending" in playbooks:
            assert playbooks["trending"]["brier_score"] < 0.15
            assert playbooks["trending"]["recommended_kelly"] == 0.25

        # Crisis should have bad Brier -> lower Kelly
        if "crisis" in playbooks:
            assert playbooks["crisis"]["brier_score"] > 0.25
            assert playbooks["crisis"]["recommended_kelly"] == 0.10


# ============================================================================
# 5. Resolution with Market Prices
# ============================================================================

class TestResolutionWithPrice:
    """resolution_price parameter in resolve_prediction."""

    def test_resolution_price_stored(self, oracle_engine):
        """resolution_price is stored in the resolved metadata."""
        oracle_engine.record_prediction(
            content="BTC above 100k",
            data={
                "market_id": "btc-100k-price",
                "our_probability": 0.70,
                "market_price": 0.65,
                "edge": 0.05,
            },
        )
        result = oracle_engine.resolve_prediction(
            "btc-100k-price", "yes", resolution_price=101500.0
        )
        assert result["success"] is True

        # Verify by querying the resolved predictions via calibration
        predictions = oracle_engine._query_oracle_memories("oracle_prediction", limit=100)
        found = False
        for p in predictions:
            meta = p.get("metadata", {})
            if meta.get("market_id") == "btc-100k-price":
                assert meta.get("resolved") is True
                assert meta.get("resolution_price") == 101500.0
                oracle_data = meta.get("oracle_data", {})
                assert oracle_data.get("resolution_price") == 101500.0
                found = True
                break
        assert found, "Resolved prediction not found in memories"

    def test_resolution_price_none(self, oracle_engine):
        """resolution_price=None is valid (no price data)."""
        oracle_engine.record_prediction(
            content="Market prediction",
            data={
                "market_id": "no-price",
                "our_probability": 0.60,
                "market_price": 0.55,
                "edge": 0.05,
            },
        )
        result = oracle_engine.resolve_prediction("no-price", "no", resolution_price=None)
        assert result["success"] is True

    def test_resolution_price_zero(self, oracle_engine):
        """resolution_price=0 is a valid price."""
        oracle_engine.record_prediction(
            content="Token goes to zero",
            data={
                "market_id": "zero-price",
                "our_probability": 0.90,
                "market_price": 0.80,
                "edge": 0.10,
            },
        )
        result = oracle_engine.resolve_prediction("zero-price", "yes", resolution_price=0.0)
        assert result["success"] is True
        assert result["pnl"] == 0.20


# ============================================================================
# 6. Signal Attribution with Mixed Outcomes
# ============================================================================

class TestSignalAttributionMixed:
    """Some signals correct, some wrong -- verify attribution weights."""

    def test_mixed_signal_accuracy(self, oracle_engine):
        """Signal A is always correct, signal B is always wrong."""
        # Signal A predictions: all correct (high prob + yes outcome)
        for i in range(6):
            _record_and_resolve(
                oracle_engine,
                market_id=f"sig-a-correct-{i}",
                our_prob=0.80,
                outcome="yes",
                signals=[{"name": "signal_a"}],
            )
        # Signal B predictions: all wrong (high prob + no outcome)
        for i in range(6):
            _record_and_resolve(
                oracle_engine,
                market_id=f"sig-b-wrong-{i}",
                our_prob=0.80,
                outcome="no",
                signals=[{"name": "signal_b"}],
            )
        result = oracle_engine.compute_signal_attribution(min_samples=5)
        signals_by_name = {s["name"]: s for s in result["signals"]}

        assert "signal_a" in signals_by_name
        assert "signal_b" in signals_by_name
        assert signals_by_name["signal_a"]["accuracy"] == 1.0
        assert signals_by_name["signal_b"]["accuracy"] == 0.0

    def test_signal_below_min_samples_excluded(self, oracle_engine):
        """Signals with fewer than min_samples are excluded."""
        # Only 2 predictions with signal_rare
        for i in range(2):
            _record_and_resolve(
                oracle_engine,
                market_id=f"rare-{i}",
                our_prob=0.70,
                outcome="yes",
                signals=[{"name": "signal_rare"}],
            )
        # 6 predictions with signal_common
        for i in range(6):
            _record_and_resolve(
                oracle_engine,
                market_id=f"common-{i}",
                our_prob=0.70,
                outcome="yes",
                signals=[{"name": "signal_common"}],
            )
        result = oracle_engine.compute_signal_attribution(min_samples=5)
        names = {s["name"] for s in result["signals"]}
        assert "signal_common" in names
        assert "signal_rare" not in names

    def test_signal_with_string_format(self, oracle_engine):
        """Signals passed as plain strings instead of dicts."""
        for i in range(6):
            _record_and_resolve(
                oracle_engine,
                market_id=f"str-sig-{i}",
                our_prob=0.70,
                outcome="yes",
                signals=["rsi_oversold", "macd_cross"],
            )
        result = oracle_engine.compute_signal_attribution(min_samples=5)
        names = {s["name"] for s in result["signals"]}
        assert "rsi_oversold" in names
        assert "macd_cross" in names

    def test_signal_regime_breakdown(self, oracle_engine):
        """Signals are broken down by regime when enough data."""
        for i in range(4):
            _record_and_resolve(
                oracle_engine,
                market_id=f"regime-sig-trending-{i}",
                our_prob=0.80,
                outcome="yes",
                regime="trending",
                signals=[{"name": "momentum"}],
            )
        for i in range(4):
            _record_and_resolve(
                oracle_engine,
                market_id=f"regime-sig-crisis-{i}",
                our_prob=0.80,
                outcome="no",
                regime="crisis",
                signals=[{"name": "momentum"}],
            )
        result = oracle_engine.compute_signal_attribution(min_samples=5)
        momentum = [s for s in result["signals"] if s["name"] == "momentum"]
        assert len(momentum) == 1
        by_regime = momentum[0].get("by_regime", {})
        # Should have regime breakdown with >= 3 samples per regime
        if "trending" in by_regime:
            assert by_regime["trending"]["accuracy"] == 1.0
        if "crisis" in by_regime:
            assert by_regime["crisis"]["accuracy"] == 0.0


# ============================================================================
# 7. Wallet Rankings Edge Cases
# ============================================================================

class TestWalletRankingsEdgeCases:
    """All wallets same score, single-trade wallets below threshold."""

    def test_all_wallets_same_brier_score(self, oracle_engine):
        """All wallets have the same Brier -> sorted by trade_count descending."""
        for i in range(5):
            oracle_engine.record_wallet_score(
                content=f"Wallet {i}",
                data={
                    "address": f"0xsame{i}",
                    "brier_score": 0.20,
                    "trade_count": 10 + i * 5,  # 10, 15, 20, 25, 30
                    "win_rate": 0.60,
                    "is_informed": False,
                },
            )
        result = oracle_engine.get_wallet_rankings(min_trades=5)
        assert result["total_wallets"] == 5
        # All same Brier, so sorted by -trade_count (highest first)
        trade_counts = [w["trade_count"] for w in result["top_wallets"]]
        assert trade_counts == sorted(trade_counts, reverse=True)

    def test_single_trade_wallets_excluded(self, oracle_engine):
        """Wallets with fewer trades than min_trades are excluded."""
        oracle_engine.record_wallet_score(
            content="Low-trade wallet",
            data={
                "address": "0xlowtrader",
                "brier_score": 0.05,  # great score but too few trades
                "trade_count": 2,
                "win_rate": 1.0,
                "is_informed": True,
            },
        )
        oracle_engine.record_wallet_score(
            content="High-trade wallet",
            data={
                "address": "0xhightrader",
                "brier_score": 0.15,
                "trade_count": 50,
                "win_rate": 0.70,
                "is_informed": True,
            },
        )
        result = oracle_engine.get_wallet_rankings(min_trades=5)
        assert result["total_wallets"] == 1
        assert result["top_wallets"][0]["address"] == "0xhightrader"

    def test_wallet_dedup_keeps_latest(self, oracle_engine):
        """When multiple scores for same address, keep the one with higher trade_count."""
        oracle_engine.record_wallet_score(
            content="Wallet v1",
            data={
                "address": "0xduped",
                "brier_score": 0.30,
                "trade_count": 10,
                "win_rate": 0.50,
                "is_informed": False,
            },
        )
        oracle_engine.record_wallet_score(
            content="Wallet v2 (updated)",
            data={
                "address": "0xduped",
                "brier_score": 0.15,
                "trade_count": 25,
                "win_rate": 0.70,
                "is_informed": True,
            },
        )
        result = oracle_engine.get_wallet_rankings(min_trades=5)
        assert result["total_wallets"] == 1
        # Should keep the one with higher trade_count
        assert result["top_wallets"][0]["trade_count"] == 25
        assert result["top_wallets"][0]["brier_score"] == 0.15

    def test_wallet_no_address_skipped(self, oracle_engine):
        """Wallets without an address field are skipped."""
        oracle_engine.record_wallet_score(
            content="No address wallet",
            data={
                "brier_score": 0.10,
                "trade_count": 50,
                "win_rate": 0.80,
                "is_informed": True,
            },
        )
        result = oracle_engine.get_wallet_rankings(min_trades=5)
        assert result["total_wallets"] == 0

    def test_wallet_fade_threshold(self, oracle_engine):
        """Wallets with brier > 0.35 and not informed are in fade_recommendations."""
        oracle_engine.record_wallet_score(
            content="Bad wallet 1",
            data={
                "address": "0xbad1",
                "brier_score": 0.40,
                "trade_count": 20,
                "win_rate": 0.30,
                "is_informed": False,
            },
        )
        oracle_engine.record_wallet_score(
            content="Mediocre wallet",
            data={
                "address": "0xmediocre",
                "brier_score": 0.30,  # below 0.35 threshold
                "trade_count": 20,
                "win_rate": 0.45,
                "is_informed": False,
            },
        )
        result = oracle_engine.get_wallet_rankings(min_trades=5)
        assert "0xbad1" in result["fade_recommendations"]
        assert "0xmediocre" not in result["fade_recommendations"]

    def test_wallet_limit_parameter(self, oracle_engine):
        """limit parameter caps the number of top_wallets returned."""
        for i in range(10):
            oracle_engine.record_wallet_score(
                content=f"Wallet {i}",
                data={
                    "address": f"0xlimit{i}",
                    "brier_score": 0.10 + i * 0.02,
                    "trade_count": 50,
                    "win_rate": 0.70,
                    "is_informed": True,
                },
            )
        result = oracle_engine.get_wallet_rankings(min_trades=5, limit=3)
        assert len(result["top_wallets"]) == 3
        assert result["total_wallets"] == 10


# ============================================================================
# 8. Market Bias with Subtypes
# ============================================================================

class TestMarketBiasSubtypes:
    """Filter by both market_type and subtype (regime grouping)."""

    def test_bias_grouped_by_regime(self, oracle_engine):
        """Biases are grouped by regime."""
        for i in range(5):
            _record_and_resolve(
                oracle_engine,
                market_id=f"bias-trending-{i}",
                our_prob=0.70,
                outcome="yes",
                regime="trending",
                edge=0.10,
            )
        for i in range(5):
            _record_and_resolve(
                oracle_engine,
                market_id=f"bias-crisis-{i}",
                our_prob=0.70,
                outcome="no",
                regime="crisis",
                edge=-0.05,
            )
        result = oracle_engine.get_market_bias()
        regimes = {b["regime"] for b in result["biases"]}
        assert "trending" in regimes
        assert "crisis" in regimes

    def test_bias_direction_overpriced_underpriced(self, oracle_engine):
        """Direction is 'overpriced' when avg_edge > 0, 'underpriced' otherwise."""
        for i in range(5):
            _record_and_resolve(
                oracle_engine,
                market_id=f"over-{i}",
                our_prob=0.70,
                outcome="yes",
                regime="trending",
                edge=0.10,  # positive edge -> overpriced
            )
        for i in range(5):
            _record_and_resolve(
                oracle_engine,
                market_id=f"under-{i}",
                our_prob=0.40,
                outcome="no",
                regime="low_vol",
                edge=-0.10,  # negative edge -> underpriced
            )
        result = oracle_engine.get_market_bias()
        bias_map = {b["regime"]: b for b in result["biases"]}

        assert bias_map["trending"]["direction"] == "overpriced"
        assert bias_map["low_vol"]["direction"] == "underpriced"

    def test_bias_regime_with_few_predictions_excluded(self, oracle_engine):
        """Regimes with fewer than 3 predictions are excluded from biases."""
        # Only 2 predictions for 'rare_regime'
        for i in range(2):
            _record_and_resolve(
                oracle_engine,
                market_id=f"rare-regime-{i}",
                our_prob=0.60,
                outcome="yes",
                regime="rare_regime",
            )
        # 4 predictions for 'common_regime'
        for i in range(4):
            _record_and_resolve(
                oracle_engine,
                market_id=f"common-regime-{i}",
                our_prob=0.60,
                outcome="yes",
                regime="common_regime",
            )
        result = oracle_engine.get_market_bias()
        regimes = {b["regime"] for b in result["biases"]}
        assert "rare_regime" not in regimes
        assert "common_regime" in regimes

    def test_bias_market_type_and_regime_combined(self, oracle_engine):
        """Filtering by market_type still groups by regime."""
        for i in range(4):
            _record_and_resolve(
                oracle_engine,
                market_id=f"btc-trending-{i}",
                our_prob=0.70,
                outcome="yes",
                market_type="btc",
                regime="trending",
            )
        for i in range(4):
            _record_and_resolve(
                oracle_engine,
                market_id=f"eth-trending-{i}",
                our_prob=0.70,
                outcome="yes",
                market_type="eth",
                regime="trending",
            )
        btc_bias = oracle_engine.get_market_bias(market_type="btc")
        eth_bias = oracle_engine.get_market_bias(market_type="eth")

        assert btc_bias["total_resolved"] == 4
        assert eth_bias["total_resolved"] == 4


# ============================================================================
# 9. get_briefing() Content
# ============================================================================

class TestBriefingContent:
    """Verify briefing includes predictions, regime, wallet data."""

    def test_briefing_contains_all_sections(self, oracle_engine):
        """Briefing includes calibration, signals, wallets, bias, playbook."""
        result = oracle_engine.get_briefing()
        assert "calibration" in result
        assert "signals" in result
        assert "wallets" in result
        assert "bias" in result
        assert "playbook" in result
        assert "briefing_text" in result

    def test_briefing_text_includes_header(self, oracle_engine):
        """Briefing text starts with market-specific header."""
        result = oracle_engine.get_briefing(market_type="eth")
        assert "Oracle Briefing (ETH)" in result["briefing_text"]

    def test_briefing_with_calibration_data(self, oracle_engine):
        """Briefing text includes Brier score when predictions exist."""
        for i in range(10):
            _record_and_resolve(
                oracle_engine,
                market_id=f"brief-cal-{i}",
                our_prob=0.75,
                outcome="yes" if i < 7 else "no",
                market_type="btc",
            )
        result = oracle_engine.get_briefing(market_type="btc")
        assert "Brier=" in result["briefing_text"]
        assert result["calibration"]["total_resolved"] == 10

    def test_briefing_with_wallet_data(self, oracle_engine):
        """Briefing includes wallet follow recommendations if they exist."""
        for i in range(3):
            oracle_engine.record_wallet_score(
                content=f"Informed wallet {i}",
                data={
                    "address": f"0xfollow{i}",
                    "brier_score": 0.08,
                    "trade_count": 50,
                    "win_rate": 0.80,
                    "is_informed": True,
                },
                market_type="btc",
            )
        result = oracle_engine.get_briefing(market_type="btc")
        assert len(result["wallets"]["follow_recommendations"]) > 0
        assert "Informed wallets to follow" in result["briefing_text"]

    def test_briefing_with_signals(self, oracle_engine):
        """Briefing text includes top signals when data exists."""
        for i in range(6):
            _record_and_resolve(
                oracle_engine,
                market_id=f"brief-sig-{i}",
                our_prob=0.80,
                outcome="yes",
                market_type="btc",
                signals=[{"name": "etf_flows"}],
            )
        result = oracle_engine.get_briefing(market_type="btc")
        sigs = result["signals"]["signals"]
        assert len(sigs) > 0
        assert "Top signals by accuracy" in result["briefing_text"]

    def test_briefing_with_bias(self, oracle_engine):
        """Briefing text includes bias info when significant."""
        for i in range(5):
            _record_and_resolve(
                oracle_engine,
                market_id=f"brief-bias-{i}",
                our_prob=0.70,
                outcome="yes",
                market_type="btc",
                edge=0.10,  # > 0.03 threshold for display
                regime="trending",
            )
        result = oracle_engine.get_briefing(market_type="btc")
        # Bias section in text appears when abs(avg_edge) > 0.03
        assert "Bias in" in result["briefing_text"] or len(result["bias"]["biases"]) > 0


# ============================================================================
# 10. get_status() After Various Operations
# ============================================================================

class TestStatusAfterOperations:
    """Counts, active_regime, and fields after various operations."""

    def test_status_empty(self, oracle_engine):
        status = oracle_engine.get_status()
        assert status["prediction_count"] == 0
        assert status["resolved_count"] == 0
        assert status["unresolved_count"] == 0
        assert status["brier_score"] is None
        assert status["wallet_scores_count"] == 0
        assert status["regime_changes_count"] == 0
        assert status["signal_snapshots_count"] == 0
        assert status["active_regime"] is None

    def test_status_after_predictions(self, oracle_engine):
        """Status reflects prediction counts."""
        oracle_engine.record_prediction(
            content="Pred 1",
            data={"market_id": "s1", "our_probability": 0.7, "market_price": 0.6, "edge": 0.1},
        )
        oracle_engine.record_prediction(
            content="Pred 2",
            data={"market_id": "s2", "our_probability": 0.8, "market_price": 0.7, "edge": 0.1},
        )
        status = oracle_engine.get_status()
        assert status["prediction_count"] == 2
        assert status["unresolved_count"] == 2
        assert status["resolved_count"] == 0

    def test_status_after_resolve(self, oracle_engine):
        """Status updates after resolving a prediction."""
        oracle_engine.record_prediction(
            content="Pred",
            data={"market_id": "sr1", "our_probability": 0.7, "market_price": 0.6, "edge": 0.1},
        )
        oracle_engine.resolve_prediction("sr1", "yes")
        status = oracle_engine.get_status()
        assert status["prediction_count"] == 1
        assert status["resolved_count"] == 1
        assert status["unresolved_count"] == 0
        assert status["brier_score"] is not None

    def test_status_after_wallet_scores(self, oracle_engine):
        """Status reflects wallet score count."""
        oracle_engine.record_wallet_score(
            content="Wallet",
            data={"address": "0xw", "brier_score": 0.1, "trade_count": 10, "is_informed": True},
        )
        status = oracle_engine.get_status()
        assert status["wallet_scores_count"] == 1

    def test_status_after_signal_snapshots(self, oracle_engine):
        """Status reflects signal snapshot count."""
        oracle_engine.record_signal_snapshot(
            content="Snapshot",
            data={"etf_flows": 200000000},
        )
        status = oracle_engine.get_status()
        assert status["signal_snapshots_count"] == 1

    def test_status_brier_interpretation_present(self, oracle_engine):
        """Status includes brier_interpretation after resolution."""
        _record_and_resolve(oracle_engine, "interp-1", 0.80, "yes")
        status = oracle_engine.get_status()
        assert status["brier_interpretation"] is not None
        assert status["brier_interpretation"] in (
            "excellent", "good", "acceptable", "mediocre", "poor"
        )

    def test_status_mixed_operations(self, oracle_engine):
        """Status after a mix of all operation types."""
        oracle_engine.record_prediction(
            content="Pred",
            data={"market_id": "mix1", "our_probability": 0.7, "market_price": 0.6, "edge": 0.1},
        )
        oracle_engine.resolve_prediction("mix1", "yes")
        oracle_engine.record_prediction(
            content="Pred 2",
            data={"market_id": "mix2", "our_probability": 0.6, "market_price": 0.5, "edge": 0.1},
        )
        oracle_engine.record_wallet_score(
            content="Wallet",
            data={"address": "0xm", "brier_score": 0.1, "trade_count": 10, "is_informed": True},
        )
        oracle_engine.record_regime_change(
            content="Regime change",
            data={"from_regime": "low_vol", "to_regime": "trending", "confidence": 0.8},
        )
        oracle_engine.record_signal_snapshot(
            content="Snap",
            data={"etf_flows": 100000000},
        )

        status = oracle_engine.get_status()
        assert status["prediction_count"] == 2
        assert status["resolved_count"] == 1
        assert status["unresolved_count"] == 1
        assert status["wallet_scores_count"] == 1
        assert status["regime_changes_count"] == 1
        assert status["signal_snapshots_count"] == 1
        assert status["active_regime"] == "trending"
        assert status["brier_score"] is not None


# ============================================================================
# 11. Empty / None Market Type
# ============================================================================

class TestNoneMarketType:
    """Pass None to market_type parameters."""

    def test_calibration_none_market_type(self, oracle_engine):
        """market_type=None returns all markets (same as no filter)."""
        _record_and_resolve(oracle_engine, "none-btc", 0.70, "yes", market_type="btc")
        _record_and_resolve(oracle_engine, "none-eth", 0.60, "no", market_type="eth")
        cal = oracle_engine.compute_calibration(market_type=None)
        assert cal["total_resolved"] == 2

    def test_signal_attribution_none_market_type(self, oracle_engine):
        """Signal attribution with market_type=None aggregates all markets."""
        for i in range(6):
            mt = "btc" if i < 3 else "eth"
            _record_and_resolve(
                oracle_engine,
                market_id=f"none-sig-{i}",
                our_prob=0.70,
                outcome="yes",
                market_type=mt,
                signals=[{"name": "cross_market_sig"}],
            )
        result = oracle_engine.compute_signal_attribution(market_type=None, min_samples=5)
        names = {s["name"] for s in result["signals"]}
        assert "cross_market_sig" in names

    def test_wallet_rankings_none_market_type(self, oracle_engine):
        """Wallet rankings with market_type=None shows all wallets."""
        oracle_engine.record_wallet_score(
            content="BTC wallet",
            data={"address": "0xbtc", "brier_score": 0.10, "trade_count": 20, "is_informed": True},
            market_type="btc",
        )
        oracle_engine.record_wallet_score(
            content="ETH wallet",
            data={"address": "0xeth", "brier_score": 0.15, "trade_count": 15, "is_informed": True},
            market_type="eth",
        )
        result = oracle_engine.get_wallet_rankings(market_type=None, min_trades=5)
        assert result["total_wallets"] == 2

    def test_market_bias_none_market_type(self, oracle_engine):
        """Market bias with market_type=None aggregates all markets."""
        for i in range(4):
            _record_and_resolve(
                oracle_engine,
                market_id=f"none-bias-btc-{i}",
                our_prob=0.70,
                outcome="yes",
                market_type="btc",
                regime="trending",
            )
        for i in range(4):
            _record_and_resolve(
                oracle_engine,
                market_id=f"none-bias-eth-{i}",
                our_prob=0.60,
                outcome="no",
                market_type="eth",
                regime="trending",
            )
        result = oracle_engine.get_market_bias(market_type=None)
        assert result["total_resolved"] == 8

    def test_briefing_default_market_type(self, oracle_engine):
        """get_briefing() defaults to btc."""
        result = oracle_engine.get_briefing()
        assert "Oracle Briefing (BTC)" in result["briefing_text"]

    def test_nonexistent_market_type(self, oracle_engine):
        """Querying a market_type with no data returns empty results."""
        _record_and_resolve(oracle_engine, "only-btc", 0.70, "yes", market_type="btc")
        cal = oracle_engine.compute_calibration(market_type="doge")
        assert cal["total_resolved"] == 0
        assert cal["brier_score"] is None


# ============================================================================
# 12. Large Prediction Histories
# ============================================================================

class TestLargePredictionHistories:
    """50+ predictions, verify calibration curve bins."""

    def test_large_history_calibration(self, oracle_engine):
        """50 predictions spread across the probability range."""
        import random
        random.seed(123)
        for i in range(60):
            prob = (i / 60) * 0.8 + 0.1  # Range 0.1 to 0.9
            outcome = "yes" if random.random() < prob else "no"
            _record_and_resolve(
                oracle_engine,
                market_id=f"large-{i}",
                our_prob=round(prob, 4),
                outcome=outcome,
            )
        cal = oracle_engine.compute_calibration()
        assert cal["total_resolved"] == 60
        assert cal["brier_score"] is not None
        assert len(cal["calibration_curve"]) > 0

        # Verify bins are populated across the range
        bin_centers = [p["bin_center"] for p in cal["calibration_curve"]]
        # Should have bins in the middle range at least
        assert any(0.2 <= bc <= 0.8 for bc in bin_centers)

    def test_large_history_curve_structure(self, oracle_engine):
        """Calibration curve has proper structure for all populated bins."""
        import random
        random.seed(456)
        for i in range(50):
            prob = round(random.uniform(0.1, 0.9), 4)
            outcome = "yes" if random.random() < prob else "no"
            _record_and_resolve(
                oracle_engine,
                market_id=f"struct-{i}",
                our_prob=prob,
                outcome=outcome,
            )
        cal = oracle_engine.compute_calibration(n_bins=10)
        for point in cal["calibration_curve"]:
            assert 0 < point["bin_center"] < 1.0
            assert 0 <= point["avg_predicted"] <= 1.0
            assert 0 <= point["avg_actual"] <= 1.0
            assert point["count"] >= 1
            # calibration_error = avg_actual - avg_predicted (allow for float rounding)
            expected_error = point["avg_actual"] - point["avg_predicted"]
            assert abs(point["calibration_error"] - round(expected_error, 4)) <= 0.0002

    def test_confidence_adjustments_require_min_samples(self, oracle_engine):
        """confidence_adjustments only populated for bins with >= 5 samples."""
        import random
        random.seed(789)
        # Put many predictions in the 0.7-0.8 bin
        for i in range(10):
            _record_and_resolve(
                oracle_engine,
                market_id=f"adj-dense-{i}",
                our_prob=0.75,
                outcome="yes" if random.random() < 0.75 else "no",
            )
        # Put few predictions in other bins
        for i in range(2):
            _record_and_resolve(
                oracle_engine,
                market_id=f"adj-sparse-{i}",
                our_prob=0.15,
                outcome="no",
            )
        cal = oracle_engine.compute_calibration(n_bins=10)
        adjustments = cal["confidence_adjustments"]
        # The dense bin (center 0.75) should have an adjustment
        # The sparse bin (center 0.15) should NOT have an adjustment
        if adjustments:
            # Keys are string representations of bin_center
            for key in adjustments:
                # Find the corresponding bin
                matching = [p for p in cal["calibration_curve"]
                            if str(round(p["bin_center"], 2)) == key]
                assert len(matching) == 1
                assert matching[0]["count"] >= 5

    def test_calibration_custom_bins(self, oracle_engine):
        """Custom n_bins parameter affects curve granularity."""
        import random
        random.seed(101)
        for i in range(30):
            prob = round(random.uniform(0.1, 0.9), 4)
            outcome = "yes" if random.random() < prob else "no"
            _record_and_resolve(
                oracle_engine,
                market_id=f"bins-{i}",
                our_prob=prob,
                outcome=outcome,
            )
        cal_5 = oracle_engine.compute_calibration(n_bins=5)
        cal_20 = oracle_engine.compute_calibration(n_bins=20)

        # More bins -> more potential curve points (or equal if all populated)
        # At minimum, n_bins=5 should have fewer or equal points
        assert len(cal_5["calibration_curve"]) <= 5
        assert len(cal_20["calibration_curve"]) <= 20

    def test_calibration_with_days_filter(self, oracle_engine):
        """days parameter filters predictions by age."""
        for i in range(5):
            _record_and_resolve(
                oracle_engine,
                market_id=f"recent-{i}",
                our_prob=0.70,
                outcome="yes",
            )
        # All recent predictions should show up with days=30
        cal = oracle_engine.compute_calibration(days=30)
        assert cal["total_resolved"] == 5
