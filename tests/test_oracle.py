"""Tests for OMEGA Oracle module -- prediction intelligence layer."""

import json
import pytest


def seed_resolved_predictions(engine, n=20):
    """Create N resolved predictions for testing."""
    import random
    import uuid
    random.seed(42)
    targets = [60000, 65000, 70000, 75000, 80000, 85000, 90000, 95000, 100000, 105000]
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october"]
    for i in range(n):
        prob = 0.5 + random.uniform(-0.3, 0.3)
        market_id = f"test-market-{uuid.uuid4().hex[:8]}"
        target = targets[i % len(targets)]
        month = months[i % len(months)]
        engine.record_prediction(
            content=f"BTC above ${target:,} by {month} 2026. Prediction #{i} with probability {prob:.2f} based on regime analysis and signal convergence. Market ID: {market_id}",
            data={
                "market_id": market_id,
                "our_probability": round(prob, 4),
                "market_price": round(prob - 0.05, 4),
                "edge": 0.05,
                "regime": "trending" if i % 2 == 0 else "low_vol",
                "signals_present": [
                    {"name": "etf_flows"},
                    {"name": "mvrv" if i % 3 == 0 else "sopr"},
                ],
            },
        )
        # Resolve: YES if prob > 0.5, NO otherwise (not perfectly calibrated)
        outcome = "yes" if random.random() < prob else "no"
        engine.resolve_prediction(market_id, outcome)


# ============================================================================
# Types Tests
# ============================================================================

class TestOracleTypes:
    """Test oracle event types are registered."""

    def test_event_types_in_ttl_map(self):
        from omega.types import EVENT_TYPE_TTL, TTLCategory, AutoCaptureEventType
        assert EVENT_TYPE_TTL[AutoCaptureEventType.ORACLE_PREDICTION] == TTLCategory.LONG_TERM
        assert EVENT_TYPE_TTL[AutoCaptureEventType.ORACLE_WALLET_SCORE] == TTLCategory.LONG_TERM
        assert EVENT_TYPE_TTL[AutoCaptureEventType.ORACLE_REGIME_CHANGE] == TTLCategory.PERMANENT
        assert EVENT_TYPE_TTL[AutoCaptureEventType.ORACLE_SIGNAL_SNAPSHOT] == TTLCategory.LONG_TERM

    def test_ttl_for_event_type(self):
        from omega.types import TTLCategory
        assert TTLCategory.for_event_type("oracle_prediction") == 7776000  # LONG_TERM (90 days)
        assert TTLCategory.for_event_type("oracle_wallet_score") == 7776000  # 90 days
        assert TTLCategory.for_event_type("oracle_regime_change") is None
        assert TTLCategory.for_event_type("oracle_signal_snapshot") == 7776000


# ============================================================================
# Engine Record Tests
# ============================================================================

class TestOracleRecord:
    """Test recording oracle memories."""

    def test_record_prediction(self, oracle_engine):
        result = oracle_engine.record_prediction(
            content="BTC above 66k prediction",
            data={
                "market_id": "bitcoin-above-66k-february-19",
                "our_probability": 0.82,
                "market_price": 0.75,
                "edge": 0.07,
                "confidence": 0.6,
                "regime": "trending",
                "signals_present": [
                    {"name": "etf_flows", "value": 245000000, "interpretation": "bullish"}
                ],
            },
            market_type="btc",
        )
        assert result  # Returns memory ID

    def test_record_wallet_score(self, oracle_engine):
        result = oracle_engine.record_wallet_score(
            content="Wallet 0xabc scored as informed trader",
            data={
                "address": "0xabc123",
                "brier_score": 0.12,
                "trade_count": 47,
                "win_rate": 0.71,
                "is_informed": True,
            },
        )
        assert result

    def test_record_regime_change(self, oracle_engine):
        result = oracle_engine.record_regime_change(
            content="Regime changed from low_vol to trending",
            data={
                "from_regime": "low_vol",
                "to_regime": "trending",
                "confidence": 0.82,
            },
        )
        assert result

    def test_record_signal_snapshot(self, oracle_engine):
        result = oracle_engine.record_signal_snapshot(
            content="Signal snapshot: ETF flows at 245M",
            data={
                "etf_flows": 245000000,
                "mvrv_z_score": 2.1,
            },
        )
        assert result


# ============================================================================
# Engine Resolve Tests
# ============================================================================

class TestOracleResolve:
    """Test resolving predictions."""

    def test_resolve_existing_prediction(self, oracle_engine):
        # Record a prediction first
        oracle_engine.record_prediction(
            content="BTC above 66k",
            data={
                "market_id": "btc-66k-test",
                "our_probability": 0.82,
                "market_price": 0.75,
                "edge": 0.07,
            },
        )

        # Resolve it
        result = oracle_engine.resolve_prediction("btc-66k-test", "yes")
        assert result["success"] is True
        assert result["outcome"] == "yes"
        assert result["market_id"] == "btc-66k-test"

    def test_resolve_nonexistent_prediction(self, oracle_engine):
        result = oracle_engine.resolve_prediction("nonexistent-market", "no")
        assert result["success"] is False
        assert "not found" in result["error"].lower() or "No unresolved" in result["error"]

    def test_resolve_twice_fails(self, oracle_engine):
        oracle_engine.record_prediction(
            content="BTC above 70k",
            data={
                "market_id": "btc-70k-test",
                "our_probability": 0.60,
                "market_price": 0.55,
                "edge": 0.05,
            },
        )
        # First resolve succeeds
        r1 = oracle_engine.resolve_prediction("btc-70k-test", "yes")
        assert r1["success"] is True

        # Second resolve should fail (already resolved)
        r2 = oracle_engine.resolve_prediction("btc-70k-test", "no")
        assert r2["success"] is False


# ============================================================================
# Calibration Tests
# ============================================================================

class TestCalibration:
    """Test calibration computation."""

    def test_calibration_no_data(self, oracle_engine):
        result = oracle_engine.compute_calibration()
        assert result["total_resolved"] == 0
        assert result["brier_score"] is None

    def test_calibration_with_data(self, oracle_engine):
        seed_resolved_predictions(oracle_engine, n=20)
        result = oracle_engine.compute_calibration()
        assert result["total_resolved"] == 20
        assert result["brier_score"] is not None
        assert 0 <= result["brier_score"] <= 1.0
        assert len(result["calibration_curve"]) > 0
        assert result["brier_interpretation"] in ("excellent", "good", "acceptable", "mediocre", "poor")

    def test_calibration_curve_structure(self, oracle_engine):
        seed_resolved_predictions(oracle_engine, n=20)
        result = oracle_engine.compute_calibration()
        for point in result["calibration_curve"]:
            assert "bin_center" in point
            assert "avg_predicted" in point
            assert "avg_actual" in point
            assert "count" in point
            assert "calibration_error" in point


# ============================================================================
# Signal Attribution Tests
# ============================================================================

class TestSignalAttribution:
    """Test signal attribution computation."""

    def test_signals_no_data(self, oracle_engine):
        result = oracle_engine.compute_signal_attribution()
        assert result["signals"] == []

    def test_signals_with_data(self, oracle_engine):
        # Seed data (reuse calibration seeder)
        seed_resolved_predictions(oracle_engine, n=20)
        result = oracle_engine.compute_signal_attribution(min_samples=3)
        assert len(result["signals"]) > 0
        for sig in result["signals"]:
            assert "name" in sig
            assert "accuracy" in sig
            assert 0 <= sig["accuracy"] <= 1.0
            assert "total" in sig


# ============================================================================
# Wallet Rankings Tests
# ============================================================================

class TestWalletRankings:
    """Test wallet ranking computation."""

    def test_wallets_no_data(self, oracle_engine):
        result = oracle_engine.get_wallet_rankings()
        assert result["total_wallets"] == 0

    def test_wallets_with_data(self, oracle_engine):
        for i in range(5):
            oracle_engine.record_wallet_score(
                content=f"Wallet {i} score",
                data={
                    "address": f"0xwallet{i}",
                    "brier_score": 0.1 + i * 0.05,
                    "trade_count": 10 + i * 5,
                    "win_rate": 0.8 - i * 0.05,
                    "is_informed": i < 3,
                },
            )
        result = oracle_engine.get_wallet_rankings(min_trades=5)
        assert result["total_wallets"] == 5
        assert len(result["top_wallets"]) == 5
        # Should be sorted by brier_score ascending
        scores = [w["brier_score"] for w in result["top_wallets"]]
        assert scores == sorted(scores)

    def test_wallet_follow_fade(self, oracle_engine):
        # Informed wallet (follow)
        oracle_engine.record_wallet_score(
            content="Informed wallet",
            data={
                "address": "0xfollow",
                "brier_score": 0.10,
                "trade_count": 50,
                "win_rate": 0.80,
                "is_informed": True,
            },
        )
        # Bad wallet (fade)
        oracle_engine.record_wallet_score(
            content="Bad wallet",
            data={
                "address": "0xfade",
                "brier_score": 0.40,
                "trade_count": 30,
                "win_rate": 0.35,
                "is_informed": False,
            },
        )
        result = oracle_engine.get_wallet_rankings(min_trades=5)
        assert "0xfollow" in result["follow_recommendations"]
        assert "0xfade" in result["fade_recommendations"]


# ============================================================================
# Market Bias Tests
# ============================================================================

class TestMarketBias:
    """Test market bias computation."""

    def test_bias_no_data(self, oracle_engine):
        result = oracle_engine.get_market_bias()
        assert result["biases"] == []

    def test_bias_with_data(self, oracle_engine):
        seed_resolved_predictions(oracle_engine, n=20)
        result = oracle_engine.get_market_bias()
        assert result["total_resolved"] == 20
        # Should have biases grouped by regime
        assert len(result["biases"]) > 0
        for b in result["biases"]:
            assert "regime" in b
            assert "count" in b
            assert "avg_edge" in b
            assert "direction" in b


# ============================================================================
# Regime Playbook Tests
# ============================================================================

class TestRegimePlaybook:
    """Test regime playbook computation."""

    def test_playbook_no_data(self, oracle_engine):
        result = oracle_engine.get_regime_playbook()
        assert result["playbooks"] == {}

    def test_playbook_with_data(self, oracle_engine):
        seed_resolved_predictions(oracle_engine, n=20)
        result = oracle_engine.get_regime_playbook()
        assert len(result["playbooks"]) > 0
        for regime, pb in result["playbooks"].items():
            assert "count" in pb
            assert "brier_score" in pb
            assert "recommended_kelly" in pb
            assert pb["recommended_kelly"] > 0

    def test_playbook_current_regime(self, oracle_engine):
        seed_resolved_predictions(oracle_engine, n=20)
        result = oracle_engine.get_regime_playbook(current_regime="trending")
        if "trending" in result["playbooks"]:
            assert result.get("current_regime") == "trending"
            assert result.get("current_playbook") is not None


# ============================================================================
# Briefing Tests
# ============================================================================

class TestBriefing:
    """Test composite briefing."""

    def test_briefing_empty(self, oracle_engine):
        result = oracle_engine.get_briefing()
        assert "briefing_text" in result
        assert "calibration" in result
        assert "signals" in result
        assert "wallets" in result
        assert "bias" in result
        assert "playbook" in result

    def test_briefing_with_data(self, oracle_engine):
        seed_resolved_predictions(oracle_engine, n=20)
        result = oracle_engine.get_briefing()
        text = result["briefing_text"]
        assert "Oracle Briefing" in text
        assert "Brier" in text


# ============================================================================
# Status Tests
# ============================================================================

class TestStatus:
    """Test status dashboard."""

    def test_status_empty(self, oracle_engine):
        status = oracle_engine.get_status()
        assert status["prediction_count"] == 0
        assert status["resolved_count"] == 0

    def test_status_with_data(self, oracle_engine):
        oracle_engine.record_prediction(
            content="Test",
            data={"market_id": "test-1", "our_probability": 0.7, "market_price": 0.6, "edge": 0.1},
        )
        oracle_engine.record_prediction(
            content="Test 2",
            data={"market_id": "test-2", "our_probability": 0.8, "market_price": 0.7, "edge": 0.1},
        )
        oracle_engine.resolve_prediction("test-1", "yes")

        status = oracle_engine.get_status()
        assert status["prediction_count"] >= 1
        assert status["resolved_count"] >= 1


# ============================================================================
# Handler Tests
# ============================================================================

class TestHandlers:
    """Test MCP handler round-trips."""

    @pytest.fixture(autouse=True)
    def setup(self, oracle_engine):
        """Ensure engine singleton is set for handlers."""
        pass

    @pytest.mark.asyncio
    async def test_record_prediction(self):
        from omega.oracle.handlers import handle_omega_oracle_record
        result = await handle_omega_oracle_record({
            "record_type": "prediction",
            "content": "BTC above 100k prediction",
            "data": {
                "market_id": "btc-100k-test",
                "our_probability": 0.45,
                "market_price": 0.40,
                "edge": 0.05,
            },
        })
        assert not result.get("isError")
        assert "Recorded oracle prediction" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_record_missing_type(self):
        from omega.oracle.handlers import handle_omega_oracle_record
        result = await handle_omega_oracle_record({
            "content": "Test",
            "data": {"market_id": "x"},
        })
        assert result.get("isError")

    @pytest.mark.asyncio
    async def test_record_invalid_type(self):
        from omega.oracle.handlers import handle_omega_oracle_record
        result = await handle_omega_oracle_record({
            "record_type": "invalid",
            "content": "Test",
            "data": {"market_id": "x"},
        })
        assert result.get("isError")

    @pytest.mark.asyncio
    async def test_record_prediction_missing_market_id(self):
        from omega.oracle.handlers import handle_omega_oracle_record
        result = await handle_omega_oracle_record({
            "record_type": "prediction",
            "content": "Test",
            "data": {"our_probability": 0.5},
        })
        assert result.get("isError")
        assert "market_id" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_resolve_handler(self):
        from omega.oracle.handlers import handle_omega_oracle_record, handle_omega_oracle_resolve
        # Record first
        await handle_omega_oracle_record({
            "record_type": "prediction",
            "content": "BTC test",
            "data": {"market_id": "resolve-test", "our_probability": 0.7, "market_price": 0.6, "edge": 0.1},
        })
        # Then resolve
        result = await handle_omega_oracle_resolve({
            "market_id": "resolve-test",
            "outcome": "yes",
        })
        assert not result.get("isError")
        assert "Resolved" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_resolve_invalid_outcome(self):
        from omega.oracle.handlers import handle_omega_oracle_resolve
        result = await handle_omega_oracle_resolve({
            "market_id": "x",
            "outcome": "maybe",
        })
        assert result.get("isError")

    @pytest.mark.asyncio
    async def test_analyze_calibration(self):
        from omega.oracle.handlers import handle_omega_oracle_analyze
        result = await handle_omega_oracle_analyze({
            "view": "calibration",
            "market_type": "btc",
        })
        assert not result.get("isError")
        text = result["content"][0]["text"]
        # Should be valid JSON
        parsed = json.loads(text)
        assert "total_resolved" in parsed

    @pytest.mark.asyncio
    async def test_analyze_briefing(self):
        from omega.oracle.handlers import handle_omega_oracle_analyze
        result = await handle_omega_oracle_analyze({
            "view": "briefing",
        })
        assert not result.get("isError")
        assert "Oracle Briefing" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_analyze_invalid_view(self):
        from omega.oracle.handlers import handle_omega_oracle_analyze
        result = await handle_omega_oracle_analyze({
            "view": "invalid",
        })
        assert result.get("isError")

    @pytest.mark.asyncio
    async def test_status_handler(self):
        from omega.oracle.handlers import handle_omega_oracle_status
        result = await handle_omega_oracle_status({})
        assert not result.get("isError")
        parsed = json.loads(result["content"][0]["text"])
        assert "prediction_count" in parsed


# ============================================================================
# Tool Schema Tests
# ============================================================================

class TestToolSchemas:
    """Test tool schema definitions."""

    def test_schemas_defined(self):
        from omega.oracle.tool_schemas import ORACLE_TOOL_SCHEMAS
        assert len(ORACLE_TOOL_SCHEMAS) >= 4
        names = {s["name"] for s in ORACLE_TOOL_SCHEMAS}
        assert names == {
            "omega_oracle_record",
            "omega_oracle_resolve",
            "omega_oracle_analyze",
            "omega_oracle_status",
        }

    def test_schemas_have_required_fields(self):
        from omega.oracle.tool_schemas import ORACLE_TOOL_SCHEMAS
        for schema in ORACLE_TOOL_SCHEMAS:
            assert "name" in schema
            assert "description" in schema
            assert "inputSchema" in schema
            assert schema["inputSchema"]["type"] == "object"

    def test_handler_registry_matches_schemas(self):
        from omega.oracle.tool_schemas import ORACLE_TOOL_SCHEMAS
        from omega.oracle.handlers import ORACLE_HANDLERS
        schema_names = {s["name"] for s in ORACLE_TOOL_SCHEMAS}
        handler_names = set(ORACLE_HANDLERS.keys())
        assert schema_names == handler_names


# ============================================================================
# Round-Trip Integration Tests
# ============================================================================

class TestRoundTrip:
    """Test full record -> resolve -> analyze cycle."""

    @pytest.fixture(autouse=True)
    def setup(self, oracle_engine):
        pass

    @pytest.mark.asyncio
    async def test_full_prediction_lifecycle(self):
        from omega.oracle.handlers import (
            handle_omega_oracle_record,
            handle_omega_oracle_resolve,
            handle_omega_oracle_analyze,
        )

        # 1. Record a prediction
        r1 = await handle_omega_oracle_record({
            "record_type": "prediction",
            "content": "BTC above 95k by Feb 28",
            "data": {
                "market_id": "btc-95k-feb28",
                "our_probability": 0.72,
                "market_price": 0.65,
                "edge": 0.07,
                "confidence": 0.6,
                "regime": "trending",
                "signals_present": [{"name": "etf_flows", "value": 300000000}],
                "ensemble_strategies": {"base_rate": 0.70, "causal": 0.75},
            },
        })
        assert not r1.get("isError")

        # 2. Resolve it
        r2 = await handle_omega_oracle_resolve({
            "market_id": "btc-95k-feb28",
            "outcome": "yes",
        })
        assert not r2.get("isError")

        # 3. Analyze calibration
        r3 = await handle_omega_oracle_analyze({
            "view": "calibration",
        })
        assert not r3.get("isError")
        cal = json.loads(r3["content"][0]["text"])
        assert cal["total_resolved"] >= 1
        assert cal["brier_score"] is not None
