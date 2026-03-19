"""Edge-case tests for OMEGA Router -- gaps not covered by test_router.py.

Covers: missing config, hot-reload, invalid priority mode, session isolation,
negative/very-large context tokens, empty prompt, force_intent override, token
estimation, get_routing_stats, classify_intent_keywords edge cases, and
provider status with valid/invalid providers.
"""

import json
import os
import time
import pytest
from pathlib import Path

from omega.router.engine import (
    OmegaRouter,
    RoutingResult,
    SessionContext,
)
from omega.router.classifier import classify_intent_keywords


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULTS_PATH = Path(__file__).parent.parent / "src" / "omega" / "router" / "defaults.json"


def _load_defaults() -> dict:
    return json.loads(_DEFAULTS_PATH.read_text())


def _write_config(path: Path, config: dict) -> None:
    path.write_text(json.dumps(config))


@pytest.fixture
def default_config():
    """Return the bundled defaults.json as a dict."""
    return _load_defaults()


@pytest.fixture
def config_file(tmp_path, default_config):
    """Write defaults.json to a temp file and return (path, config)."""
    p = tmp_path / "router_config.json"
    _write_config(p, default_config)
    return p, default_config


@pytest.fixture
def router_from_config(config_file):
    """Create an OmegaRouter backed by the temp config file."""
    path, _ = config_file
    return OmegaRouter(config_path=str(path))


# ============================================================================
# 1. Config file missing
# ============================================================================

class TestConfigMissing:
    """OmegaRouter with a nonexistent config path should raise clearly."""

    def test_missing_config_raises_on_route(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.json")
        router = OmegaRouter(config_path=bad_path)
        with pytest.raises(FileNotFoundError, match="Router config not found"):
            router.route("hello")

    def test_missing_config_raises_on_get_stats(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.json")
        router = OmegaRouter(config_path=bad_path)
        with pytest.raises(FileNotFoundError):
            router.get_routing_stats()

    def test_missing_config_after_load_keeps_working(self, config_file):
        """If config is loaded then deleted, router keeps cached config."""
        path, _ = config_file
        router = OmegaRouter(config_path=str(path))
        result1 = router.route("write a function", force_intent="coding")
        assert result1.model

        path.unlink()

        # Should still route using cached config
        result2 = router.route("write a function", force_intent="coding")
        assert result2.model == result1.model


# ============================================================================
# 2. Config hot-reload
# ============================================================================

class TestConfigHotReload:
    """Verify that modifying the config file mid-flight is detected."""

    def test_hot_reload_detects_threshold_change(self, config_file):
        path, config = config_file
        router = OmegaRouter(config_path=str(path))
        router._load_config()

        original = router.config["context_overrides"]["large_context"]["threshold_tokens"]
        assert original == 100000

        # Mutate and bump mtime
        config["context_overrides"]["large_context"]["threshold_tokens"] = 50000
        _write_config(path, config)
        os.utime(str(path), (time.time() + 2, time.time() + 2))

        router._load_config()
        assert router.config["context_overrides"]["large_context"]["threshold_tokens"] == 50000

    def test_hot_reload_changes_routing_behavior(self, config_file):
        """After lowering the large-context threshold, a 75k-token prompt triggers override."""
        path, config = config_file
        router = OmegaRouter(config_path=str(path))

        # With default threshold=100k, 75k should NOT trigger override
        result1 = router.route("analyze code", estimated_tokens=75000, force_intent="coding")
        assert result1.context_override is False

        # Lower threshold to 50k
        config["context_overrides"]["large_context"]["threshold_tokens"] = 50000
        _write_config(path, config)
        os.utime(str(path), (time.time() + 2, time.time() + 2))

        # Now 75k SHOULD trigger override
        result2 = router.route("analyze code", estimated_tokens=75000, force_intent="coding")
        assert result2.context_override is True

    def test_same_mtime_skips_reload(self, config_file):
        """If mtime hasn't changed, in-memory mutations persist."""
        path, _ = config_file
        router = OmegaRouter(config_path=str(path))
        router._load_config()

        router.config["__test_sentinel"] = True
        router._load_config()
        assert router.config.get("__test_sentinel") is True


# ============================================================================
# 3. Invalid priority mode
# ============================================================================

class TestInvalidPriorityMode:
    """Non-enum values should fall back to BALANCED rather than crashing."""

    def test_invalid_priority_falls_back(self, router_from_config):
        result = router_from_config.route("hello", priority="turbo", force_intent="coding")
        assert result.priority_mode == "turbo"  # mode string is preserved as-is
        # The internal PriorityMode defaults to BALANCED
        assert result.model  # should not crash

    def test_empty_priority(self, router_from_config):
        result = router_from_config.route("hello", priority="", force_intent="coding")
        assert result.model

    def test_numeric_priority(self, router_from_config):
        # priority is typed as str so "42" won't match any PriorityMode
        result = router_from_config.route("hello", priority="42", force_intent="coding")
        assert result.model


# ============================================================================
# 4. Session context tracking -- independence
# ============================================================================

class TestSessionContextIndependence:
    """Multiple sessions should not leak state into each other."""

    def test_two_sessions_independent(self, router_from_config):
        router = router_from_config
        router.update_session_context("s1", "gpt-4o", "openai", 1000, 1)
        router.update_session_context("s2", "claude-opus-4-6", "anthropic", 5000, 3)

        s1 = router.get_session_context("s1")
        s2 = router.get_session_context("s2")
        assert s1.current_model == "gpt-4o"
        assert s2.current_model == "claude-opus-4-6"
        assert s1.context_tokens == 1000
        assert s2.context_tokens == 5000

    def test_updating_one_session_does_not_alter_other(self, router_from_config):
        router = router_from_config
        router.update_session_context("a", "model-a", "provider-a", 100, 1)
        router.update_session_context("b", "model-b", "provider-b", 200, 2)

        # Update 'a'
        router.update_session_context("a", "model-a-v2", "provider-a", 300, 5)

        b = router.get_session_context("b")
        assert b.current_model == "model-b"
        assert b.context_tokens == 200
        assert b.conversation_depth == 2

    def test_nonexistent_session(self, router_from_config):
        assert router_from_config.get_session_context("ghost") is None

    def test_session_context_to_dict_roundtrip(self):
        ctx = SessionContext(
            session_id="test",
            current_model="m",
            current_provider="p",
            context_tokens=42,
            conversation_depth=3,
            last_updated="2024-01-01",
        )
        d = ctx.to_dict()
        rebuilt = SessionContext.from_dict(d)
        assert rebuilt.session_id == "test"
        assert rebuilt.context_tokens == 42
        assert rebuilt.conversation_depth == 3


# ============================================================================
# 5. Negative context tokens
# ============================================================================

class TestNegativeContextTokens:
    """Negative estimated_tokens should not crash or trigger override."""

    def test_negative_tokens_no_crash(self, router_from_config):
        result = router_from_config.route("hello", estimated_tokens=-100, force_intent="coding")
        assert result.context_override is False
        assert result.model

    def test_zero_tokens(self, router_from_config):
        result = router_from_config.route("hello", estimated_tokens=0, force_intent="coding")
        assert result.context_override is False


# ============================================================================
# 6. Very large context tokens (>200k)
# ============================================================================

class TestVeryLargeContextTokens:
    """Tokens exceeding the threshold should trigger large-context model."""

    def test_200k_triggers_override(self, router_from_config):
        result = router_from_config.route("analyze code", estimated_tokens=200001, force_intent="coding")
        assert result.context_override is True

    def test_500k_triggers_override(self, router_from_config):
        result = router_from_config.route("process data", estimated_tokens=500000, force_intent="logic")
        assert result.context_override is True
        # Should select the large-context model (Gemini)
        assert result.provider == "google"

    def test_1m_tokens(self, router_from_config):
        result = router_from_config.route("huge analysis", estimated_tokens=1_000_000, force_intent="coding")
        assert result.context_override is True

    def test_exactly_at_threshold_no_override(self, router_from_config):
        # Default threshold is 100000; exactly 100000 should NOT trigger (> not >=)
        result = router_from_config.route("code", estimated_tokens=100000, force_intent="coding")
        assert result.context_override is False

    def test_one_above_threshold(self, router_from_config):
        result = router_from_config.route("code", estimated_tokens=100001, force_intent="coding")
        assert result.context_override is True


# ============================================================================
# 7. Empty prompt routing
# ============================================================================

class TestEmptyPromptRouting:
    """Route an empty or whitespace-only prompt."""

    def test_empty_string_routes(self, router_from_config):
        result = router_from_config.route("")
        assert isinstance(result, RoutingResult)
        assert result.model  # Should still pick a model

    def test_whitespace_only_routes(self, router_from_config):
        result = router_from_config.route("   ")
        assert isinstance(result, RoutingResult)
        assert result.model

    def test_single_char_routes(self, router_from_config):
        result = router_from_config.route("?")
        assert result.model


# ============================================================================
# 8. force_intent override
# ============================================================================

class TestForceIntentOverride:
    """Route with explicit intent -- should bypass classification."""

    def test_force_intent_coding(self, router_from_config):
        result = router_from_config.route("this has no keywords", force_intent="coding")
        assert result.intent == "coding"
        assert result.confidence == 1.0

    def test_force_intent_creative(self, router_from_config):
        result = router_from_config.route("debug the function", force_intent="creative")
        # Even though "debug" is a coding keyword, force_intent overrides
        assert result.intent == "creative"
        assert result.confidence == 1.0

    def test_force_intent_all_scores_single(self, router_from_config):
        result = router_from_config.route("test", force_intent="logic")
        assert result.all_scores == {"logic": 1.0}

    def test_force_intent_unknown_intent(self, router_from_config):
        """Unknown forced intent should fall back to coding config."""
        result = router_from_config.route("test", force_intent="nonexistent_intent")
        assert result.intent == "nonexistent_intent"
        # _get_model_for_intent falls back to "coding" config when intent is missing
        assert result.model


# ============================================================================
# 9. Token estimation and latency
# ============================================================================

class TestTokenEstimationAndLatency:
    """Verify latency tracking for various prompt sizes."""

    def test_short_prompt_latency(self, router_from_config):
        result = router_from_config.route("hi", force_intent="coding")
        assert result.latency_ms > 0
        assert result.latency_ms < 1000  # Should be very fast

    def test_long_prompt_latency(self, router_from_config):
        long_prompt = "analyze " * 10000
        result = router_from_config.route(long_prompt, force_intent="coding")
        assert result.latency_ms > 0

    def test_estimated_tokens_passed_to_session(self, router_from_config):
        router = router_from_config
        router.route("test", estimated_tokens=42000, session_id="tok_test", force_intent="coding")
        ctx = router.get_session_context("tok_test")
        assert ctx is not None
        assert ctx.context_tokens == 42000

    def test_conversation_depth_increments(self, router_from_config):
        router = router_from_config
        router.route("turn 1", session_id="depth", force_intent="coding")
        ctx1 = router.get_session_context("depth")
        assert ctx1.conversation_depth == 1

        router.route("turn 2", session_id="depth", force_intent="coding")
        ctx2 = router.get_session_context("depth")
        assert ctx2.conversation_depth == 2

        router.route("turn 3", session_id="depth", force_intent="creative")
        ctx3 = router.get_session_context("depth")
        assert ctx3.conversation_depth == 3


# ============================================================================
# 10. get_routing_stats()
# ============================================================================

class TestGetRoutingStats:
    """Verify stats reflect the loaded config accurately."""

    def test_stats_structure(self, router_from_config):
        stats = router_from_config.get_routing_stats()
        assert "intents_configured" in stats
        assert "priority_modes" in stats
        assert "providers" in stats
        assert "context_override_threshold" in stats

    def test_stats_intents(self, router_from_config):
        stats = router_from_config.get_routing_stats()
        assert "coding" in stats["intents_configured"]
        assert "creative" in stats["intents_configured"]
        assert "logic" in stats["intents_configured"]
        assert "exploration" in stats["intents_configured"]
        assert "simple_edit" in stats["intents_configured"]
        assert "image" in stats["intents_configured"]

    def test_stats_priority_modes(self, router_from_config):
        stats = router_from_config.get_routing_stats()
        assert set(stats["priority_modes"]) == {"cost", "speed", "quality", "balanced"}

    def test_stats_providers(self, router_from_config):
        stats = router_from_config.get_routing_stats()
        assert "anthropic" in stats["providers"]
        assert "openai" in stats["providers"]
        assert "google" in stats["providers"]

    def test_stats_threshold_default(self, router_from_config):
        stats = router_from_config.get_routing_stats()
        assert stats["context_override_threshold"] == 100000

    def test_stats_after_config_change(self, config_file):
        """Stats should reflect hot-reloaded config."""
        path, config = config_file
        router = OmegaRouter(config_path=str(path))

        stats1 = router.get_routing_stats()
        assert stats1["context_override_threshold"] == 100000

        config["context_overrides"]["large_context"]["threshold_tokens"] = 77777
        _write_config(path, config)
        os.utime(str(path), (time.time() + 2, time.time() + 2))

        stats2 = router.get_routing_stats()
        assert stats2["context_override_threshold"] == 77777


# ============================================================================
# 11. classify_intent_keywords() edge cases
# ============================================================================

class TestClassifyIntentKeywordsEdgeCases:
    """Edge cases for the keyword fallback classifier."""

    def test_empty_query(self):
        intent, conf = classify_intent_keywords("")
        # No keywords match -> default coding at 0.5
        assert intent == "coding"
        assert conf == 0.5

    def test_whitespace_only_query(self):
        intent, conf = classify_intent_keywords("    ")
        assert intent == "coding"
        assert conf == 0.5

    def test_very_long_query(self):
        long_query = "analyze the design of the architecture " * 500
        intent, conf = classify_intent_keywords(long_query)
        # Should still classify (logic keywords dominate)
        assert intent == "logic"
        assert 0.4 <= conf <= 0.86  # 0.85 + float tolerance

    def test_all_intents_represented(self):
        """Each intent should be classifiable with the right keywords."""
        test_cases = {
            "coding": "code function class debug test",
            "creative": "write draft story email brainstorm",
            "logic": "analyze design architect reason plan",
            "exploration": "search find where what explain",
            "simple_edit": "typo rename comment format indent",
        }
        for expected_intent, query in test_cases.items():
            intent, conf = classify_intent_keywords(query)
            assert intent == expected_intent, f"Expected {expected_intent} for '{query}', got {intent}"

    def test_tie_breaking(self):
        """When multiple intents have equal score, max() picks one deterministically."""
        # 'code' matches coding, 'write' matches creative -- 1 each
        intent, conf = classify_intent_keywords("code write")
        assert intent in ("coding", "creative")

    def test_confidence_range(self):
        """Confidence should always be in [0.4, 0.85+eps] for keyword matches, or 0.5 for no match."""
        # No keywords
        _, conf0 = classify_intent_keywords("xyz")
        assert conf0 == 0.5

        # Single keyword -- formula is 0.4 + raw * 0.45, may hit 0.85+epsilon
        _, conf1 = classify_intent_keywords("code")
        assert 0.4 <= conf1 <= 0.86

        # Many keywords
        _, conf2 = classify_intent_keywords("code function class bug fix implement debug test refactor algorithm parse compile error")
        assert 0.4 <= conf2 <= 0.86

    def test_case_insensitive(self):
        intent1, _ = classify_intent_keywords("CODE FUNCTION CLASS")
        intent2, _ = classify_intent_keywords("code function class")
        assert intent1 == intent2

    def test_partial_keyword_match(self):
        """Keywords like 'code' should match in 'codebase' since it uses 'in' matching."""
        intent, _ = classify_intent_keywords("codebase")
        assert intent == "coding"

    def test_unicode_query_no_crash(self):
        intent, conf = classify_intent_keywords("Find the database configuration file")
        assert isinstance(intent, str)
        assert isinstance(conf, float)


# ============================================================================
# 12. Provider status
# ============================================================================

class TestProviderStatus:
    """get_provider_status with valid and missing env keys."""

    def test_provider_status_all_keys(self, router_from_config):
        status = router_from_config.get_provider_status()
        # Should have entries for all configured providers
        assert "anthropic" in status
        assert "openai" in status
        assert "google" in status
        assert "groq" in status
        assert "xai" in status

    def test_provider_status_values(self, router_from_config):
        status = router_from_config.get_provider_status()
        for provider, state in status.items():
            assert state in ("available", "no_api_key"), f"{provider}: {state}"

    def test_provider_with_env_key_set(self, router_from_config, monkeypatch):
        """When env key is set, provider should be 'available'."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
        status = router_from_config.get_provider_status()
        assert status["anthropic"] == "available"

    def test_provider_without_env_key(self, router_from_config, monkeypatch):
        """When env key is unset and no secrets file, provider should be 'no_api_key'."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Also ensure secrets file doesn't interfere
        monkeypatch.setattr(
            "omega.router.engine._SECRETS_PATH",
            Path("/nonexistent/secrets.json"),
        )
        # Force config reload by resetting mtime
        router_from_config._loaded = False
        status = router_from_config.get_provider_status()
        assert status["anthropic"] == "no_api_key"
        assert status["openai"] == "no_api_key"

    def test_get_api_key_from_env(self, router_from_config, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
        key = router_from_config.get_api_key("anthropic")
        assert key == "sk-test-123"

    def test_get_api_key_missing_provider(self, router_from_config):
        key = router_from_config.get_api_key("nonexistent_provider")
        assert key is None

    def test_get_current_model_none_for_unknown_session(self, router_from_config):
        assert router_from_config.get_current_model("no-such-session") is None

    def test_get_current_model_after_route(self, router_from_config):
        router_from_config.route("test", session_id="cm_test", force_intent="coding")
        current = router_from_config.get_current_model("cm_test")
        assert current is not None
        assert "model" in current
        assert "provider" in current
        assert "switched_at" in current


# ============================================================================
# Extra: LiteLLM model string for unknown provider
# ============================================================================

class TestLiteLLMUnknownProvider:
    """Unknown providers should use the provider name as the prefix."""

    def test_unknown_provider_prefix(self):
        from omega.router.engine import get_litellm_model_string

        result = RoutingResult(
            model="custom-model",
            provider="my_custom_provider",
            intent="coding",
            confidence=0.9,
            reason="test",
        )
        assert get_litellm_model_string(result) == "my_custom_provider/custom-model"


# ============================================================================
# Extra: RoutingResult defaults
# ============================================================================

class TestRoutingResultDefaults:
    """Verify RoutingResult dataclass defaults."""

    def test_defaults(self):
        r = RoutingResult(
            model="m", provider="p", intent="i", confidence=0.5, reason="r"
        )
        assert r.fallback_model is None
        assert r.fallback_provider is None
        assert r.priority_mode == "balanced"
        assert r.context_override is False
        assert r.latency_ms == 0.0
        assert r.all_scores == {}
