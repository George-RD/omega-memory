"""Tests for OMEGA Router -- intent classification, routing, context affinity."""

import json
import os
import time
import importlib.util
import pytest
from pathlib import Path

from omega.router.classifier import (
    IntentClassifier,
    ClassificationResult,
    classify_intent,
    classify_intent_detailed,
    classify_intent_keywords,
    INTENT_DEFINITIONS,
)
from omega.router.engine import (
    OmegaRouter,
    RoutingResult,
    PriorityMode,
    ModelConfig,
    SessionContext,
    route_prompt,
    get_litellm_model_string,
)
from omega.router.tool_schemas import ROUTER_TOOL_SCHEMAS
from omega.router.handlers import ROUTER_HANDLERS


# ============================================================================
# Intent Classifier Tests
# ============================================================================


@pytest.mark.skipif(
    not importlib.util.find_spec("onnxruntime"),
    reason="onnxruntime not installed"
)
class TestIntentClassifier:
    """Test prototype-based intent classification."""

    def test_classify_coding(self):
        intent, confidence = classify_intent("write a python function to sort a list")
        assert intent == "coding"
        assert confidence > 0.5

    def test_classify_creative(self):
        intent, confidence = classify_intent("draft an email to the team")
        assert intent == "creative"
        assert confidence > 0.5

    def test_classify_logic(self):
        intent, confidence = classify_intent("analyze the architecture of this system")
        assert intent == "logic"
        assert confidence > 0.5

    def test_classify_exploration(self):
        intent, confidence = classify_intent("find where the config is defined")
        assert intent == "exploration"
        assert confidence > 0.5

    def test_classify_simple_edit(self):
        intent, confidence = classify_intent("fix the typo in the comment")
        assert intent == "simple_edit"
        assert confidence > 0.5

    def test_classify_returns_all_scores(self):
        result = classify_intent_detailed("write a function")
        assert "all_scores" in result
        assert len(result["all_scores"]) == 5
        assert all(intent in result["all_scores"] for intent in INTENT_DEFINITIONS)

    def test_classify_latency_under_10ms(self):
        # First call may include prototype loading; warm up first
        classify_intent("warmup")
        result = classify_intent_detailed("test prompt")
        assert result["latency_ms"] < 10.0

    def test_classifier_singleton(self):
        from omega.router.classifier import get_classifier
        c1 = get_classifier()
        c2 = get_classifier()
        assert c1 is c2

    def test_classifier_batch(self):
        classifier = IntentClassifier(use_cache=False)
        results = classifier.classify_batch(["write code", "find files", "fix typo"])
        assert len(results) == 3
        assert all(isinstance(r, ClassificationResult) for r in results)


class TestKeywordFallback:
    """Test keyword-based fallback classifier."""

    def test_keyword_coding(self):
        intent, conf = classify_intent_keywords("debug the function")
        assert intent == "coding"

    def test_keyword_creative(self):
        intent, conf = classify_intent_keywords("write a story about AI")
        assert intent == "creative"

    def test_keyword_unknown(self):
        intent, conf = classify_intent_keywords("xyz123")
        assert intent == "coding"  # default
        assert conf == 0.5

    def test_keyword_confidence_capped(self):
        _, conf = classify_intent_keywords("code function class debug test")
        assert conf <= 0.9


# ============================================================================
# Router Engine Tests
# ============================================================================


class TestOmegaRouter:
    """Test the routing engine."""

    @pytest.fixture
    def router(self):
        return OmegaRouter()

    def test_route_coding(self, router):
        result = router.route("write a python function to sort a list")
        assert isinstance(result, RoutingResult)
        assert result.intent == "coding"
        assert result.model
        assert result.provider

    def test_route_creative(self, router):
        result = router.route("draft a blog post about machine learning")
        assert result.intent == "creative"

    def test_route_with_priority_cost(self, router):
        result = router.route("write a function", priority="cost")
        assert result.priority_mode == "cost"

    def test_route_with_priority_quality(self, router):
        result = router.route("analyze this system", priority="quality")
        assert result.priority_mode == "quality"

    def test_route_with_force_intent(self, router):
        result = router.route("anything", force_intent="logic")
        assert result.intent == "logic"
        assert result.confidence == 1.0

    def test_route_large_context_override(self, router):
        result = router.route("analyze code", estimated_tokens=150000)
        assert result.context_override is True
        assert result.provider == "google"

    def test_route_small_context_no_override(self, router):
        result = router.route("analyze code", estimated_tokens=50000)
        assert result.context_override is False

    def test_route_latency_measured(self, router):
        result = router.route("test prompt")
        assert result.latency_ms > 0

    def test_route_all_scores_present(self, router):
        result = router.route("write a function")
        assert len(result.all_scores) >= 1


@pytest.mark.skipif(
    not importlib.util.find_spec("onnxruntime"),
    reason="onnxruntime not installed"
)
class TestSessionContext:
    """Test context affinity and session tracking."""

    @pytest.fixture
    def router(self):
        return OmegaRouter()

    def test_update_and_get_context(self, router):
        ctx = router.update_session_context("sess1", "gpt-4o", "openai", 5000, 3)
        assert isinstance(ctx, SessionContext)
        assert ctx.current_model == "gpt-4o"

        retrieved = router.get_session_context("sess1")
        assert retrieved is not None
        assert retrieved.current_model == "gpt-4o"

    def test_missing_session_returns_none(self, router):
        assert router.get_session_context("nonexistent") is None

    def test_context_affinity_same_provider(self, router):
        router.update_session_context(
            "sess2", "claude-sonnet-4-5-20250929", "anthropic", 50000, 5
        )
        result = router.route("refactor the database module", session_id="sess2")
        # Should prefer anthropic model due to affinity (coding intent → anthropic primary)
        assert result.provider == "anthropic"

    def test_no_affinity_without_session(self, router):
        result1 = router.route("find where config is defined")
        # Without session, should use default routing (exploration → xai)
        assert result1.intent == "exploration"

    def test_context_affinity_no_penalty_below_threshold(self, router):
        router.update_session_context("sess3", "gpt-4o", "openai", 500, 1)
        # 500 tokens < min_context_for_affinity (1000), so no affinity
        penalty = router._calculate_switch_penalty(
            router.get_session_context("sess3"), "claude-sonnet-4-5-20250929", "anthropic"
        )
        assert penalty == 0.0


class TestProviderStatus:
    """Test provider detection and status."""

    @pytest.fixture
    def router(self):
        return OmegaRouter()

    def test_get_provider_status(self, router):
        status = router.get_provider_status()
        assert "anthropic" in status
        assert status["anthropic"] in ("available", "no_api_key")

    def test_get_routing_stats(self, router):
        stats = router.get_routing_stats()
        assert "intents_configured" in stats
        assert "coding" in stats["intents_configured"]
        assert "priority_modes" in stats
        assert "providers" in stats


class TestModelSwitch:
    """Test model switching with OMEGA memory."""

    @pytest.fixture
    def router(self):
        return OmegaRouter()

    def test_switch_model_basic(self, router):
        router.update_session_context("sess-switch", "gpt-4o", "openai")
        result = router.switch_model(
            session_id="sess-switch",
            target_provider="anthropic",
            target_model="claude-sonnet-4-5-20250929",
            retrieve_context=False,
        )
        assert result["success"] is True
        assert result["previous_model"] == "gpt-4o"
        assert result["target_model"] == "claude-sonnet-4-5-20250929"

    def test_switch_updates_context(self, router):
        router.update_session_context("sess-switch2", "gpt-4o", "openai")
        router.switch_model(
            session_id="sess-switch2",
            target_provider="anthropic",
            target_model="claude-sonnet-4-5-20250929",
            retrieve_context=False,
        )
        ctx = router.get_session_context("sess-switch2")
        assert ctx.current_model == "claude-sonnet-4-5-20250929"
        assert ctx.current_provider == "anthropic"


class TestPriorityMode:
    """Test priority mode enum."""

    def test_all_modes_exist(self):
        assert PriorityMode.COST.value == "cost"
        assert PriorityMode.SPEED.value == "speed"
        assert PriorityMode.QUALITY.value == "quality"
        assert PriorityMode.BALANCED.value == "balanced"


class TestModelConfig:
    """Test model configuration dataclass."""

    def test_defaults(self):
        config = ModelConfig(provider="anthropic", model="test", reason="test")
        assert config.context_window == 200000
        assert config.cost_per_1m_input == 0.0

    def test_custom_values(self):
        config = ModelConfig(
            provider="openai", model="gpt-4o", reason="test",
            context_window=128000, cost_per_1m_input=2.5
        )
        assert config.context_window == 128000


class TestLiteLLMModelString:
    """Test LiteLLM model string generation."""

    def test_anthropic(self):
        result = RoutingResult(
            model="claude-sonnet-4-5-20250929", provider="anthropic",
            intent="coding", confidence=0.9, reason="test"
        )
        assert get_litellm_model_string(result) == "anthropic/claude-sonnet-4-5-20250929"

    def test_openai(self):
        result = RoutingResult(
            model="gpt-4o", provider="openai",
            intent="coding", confidence=0.9, reason="test"
        )
        assert get_litellm_model_string(result) == "openai/gpt-4o"

    def test_google(self):
        result = RoutingResult(
            model="gemini-2.5-pro", provider="google",
            intent="logic", confidence=0.9, reason="test"
        )
        assert get_litellm_model_string(result) == "gemini/gemini-2.5-pro"


# ============================================================================
# MCP Tool Schema Tests
# ============================================================================


class TestToolSchemas:
    """Test MCP tool schemas and handler registration."""

    def test_tool_count(self):
        assert len(ROUTER_TOOL_SCHEMAS) >= 10

    def test_handler_count(self):
        assert len(ROUTER_HANDLERS) >= 10

    def test_all_tools_have_handlers(self):
        for schema in ROUTER_TOOL_SCHEMAS:
            assert schema["name"] in ROUTER_HANDLERS, f"Missing handler: {schema['name']}"

    def test_all_handlers_have_schemas(self):
        tool_names = {s["name"] for s in ROUTER_TOOL_SCHEMAS}
        for handler_name in ROUTER_HANDLERS:
            assert handler_name in tool_names, f"Missing schema: {handler_name}"

    def test_schema_structure(self):
        for schema in ROUTER_TOOL_SCHEMAS:
            assert "name" in schema
            assert "description" in schema
            assert "inputSchema" in schema
            assert schema["inputSchema"]["type"] == "object"

    def test_tool_names_prefixed(self):
        for schema in ROUTER_TOOL_SCHEMAS:
            assert schema["name"].startswith("omega_"), f"Bad prefix: {schema['name']}"


# ============================================================================
# Config File Tests
# ============================================================================


class TestDefaultsConfig:
    """Test the defaults.json configuration."""

    @pytest.fixture
    def config(self):
        config_path = Path(__file__).parent.parent / "src" / "omega" / "router" / "defaults.json"
        return json.loads(config_path.read_text())

    def test_has_models(self, config):
        assert "models" in config
        assert len(config["models"]) >= 5

    def test_has_intent_routing(self, config):
        assert "intent_routing" in config
        expected_intents = {"coding", "creative", "logic", "exploration", "simple_edit", "image"}
        assert set(config["intent_routing"].keys()) == expected_intents

    def test_has_priority_modes(self, config):
        assert "priority_modes" in config
        expected_modes = {"cost", "speed", "quality", "balanced"}
        assert set(config["priority_modes"].keys()) == expected_modes

    def test_has_providers(self, config):
        assert "providers" in config
        assert "anthropic" in config["providers"]

    def test_intent_routes_have_primary(self, config):
        for intent, route in config["intent_routing"].items():
            assert "primary" in route, f"Missing primary for {intent}"
            assert "provider" in route["primary"]
            assert "model" in route["primary"]

    def test_context_override(self, config):
        assert "context_overrides" in config
        large = config["context_overrides"]["large_context"]
        assert large["threshold_tokens"] == 100000

    def test_context_affinity(self, config):
        assert "context_affinity" in config
        assert config["context_affinity"]["enabled"] is True


# ============================================================================
# Convenience Function Tests
# ============================================================================


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_route_prompt(self):
        result = route_prompt("write a function")
        assert isinstance(result, dict)
        assert "model" in result
        assert "provider" in result
        assert "intent" in result

    def test_classify_intent(self):
        intent, confidence = classify_intent("debug this error")
        assert isinstance(intent, str)
        assert isinstance(confidence, float)
        assert 0 <= confidence <= 1


# ============================================================================
# Priority Mode Fix Tests
# ============================================================================


@pytest.mark.skipif(
    not importlib.util.find_spec("onnxruntime"),
    reason="onnxruntime not installed"
)
class TestPriorityModePreferModels:
    """Test that priority modes include all intent-routed models."""

    @pytest.fixture
    def config(self):
        config_path = Path(__file__).parent.parent / "src" / "omega" / "router" / "defaults.json"
        return json.loads(config_path.read_text())

    def test_balanced_includes_grok(self, config):
        """grok-4-latest must be in balanced prefer_models to prevent exploration downgrade."""
        balanced = config["priority_modes"]["balanced"]["prefer_models"]
        assert "grok-4-latest" in balanced

    def test_cost_includes_groq_8b(self, config):
        """llama-3.1-8b-instant must be in cost prefer_models for simple_edit."""
        cost = config["priority_modes"]["cost"]["prefer_models"]
        assert "llama-3.1-8b-instant" in cost

    def test_exploration_keeps_grok_in_balanced(self):
        """Exploration intent should keep grok-4 primary in balanced mode."""
        router = OmegaRouter()
        result = router.route("find where the config is defined", priority="balanced")
        # Exploration primary is grok-4-latest, and it's now in balanced prefer_models
        # so _apply_priority_mode should NOT swap it out
        assert result.intent == "exploration"
        assert result.model == "grok-4-latest"

    def test_simple_edit_keeps_groq_in_cost(self):
        """simple_edit intent should keep groq primary in cost mode."""
        router = OmegaRouter()
        result = router.route("fix the typo in the comment", priority="cost")
        assert result.intent == "simple_edit"
        assert result.model == "llama-3.1-8b-instant"


class TestPriorityModePersistence:
    """Test that priority mode persists to disk."""

    def test_save_and_load(self, tmp_path):
        """Priority mode round-trips through file."""
        from omega.router import handlers
        original_file = handlers._PRIORITY_FILE
        handlers._PRIORITY_FILE = tmp_path / "router_priority.txt"
        try:
            handlers._save_priority_mode("quality")
            loaded = handlers._load_priority_mode()
            assert loaded == "quality"
        finally:
            handlers._PRIORITY_FILE = original_file

    def test_load_default_when_missing(self, tmp_path):
        """Returns balanced when file doesn't exist."""
        from omega.router import handlers
        original_file = handlers._PRIORITY_FILE
        handlers._PRIORITY_FILE = tmp_path / "nonexistent.txt"
        try:
            loaded = handlers._load_priority_mode()
            assert loaded == "balanced"
        finally:
            handlers._PRIORITY_FILE = original_file

    def test_load_ignores_invalid(self, tmp_path):
        """Returns balanced when file has invalid content."""
        from omega.router import handlers
        original_file = handlers._PRIORITY_FILE
        handlers._PRIORITY_FILE = tmp_path / "router_priority.txt"
        handlers._PRIORITY_FILE.write_text("invalid_mode")
        try:
            loaded = handlers._load_priority_mode()
            assert loaded == "balanced"
        finally:
            handlers._PRIORITY_FILE = original_file


# ============================================================================
# Config Hot-Reload Tests
# ============================================================================


class TestConfigHotReload:
    """Test mtime-based config hot-reload."""

    @pytest.fixture
    def config_file(self, tmp_path):
        """Create a temporary config file from defaults."""
        defaults = Path(__file__).parent.parent / "src" / "omega" / "router" / "defaults.json"
        config = json.loads(defaults.read_text())
        config_path = tmp_path / "router_config.json"
        config_path.write_text(json.dumps(config))
        return config_path, config

    def test_modified_config_picked_up(self, config_file):
        """Config changes on disk are detected on next _load_config() call."""
        config_path, config = config_file
        router = OmegaRouter(config_path=str(config_path))

        # Initial load
        router._load_config()
        original_threshold = config["context_overrides"]["large_context"]["threshold_tokens"]
        assert router.config["context_overrides"]["large_context"]["threshold_tokens"] == original_threshold

        # Mutate config on disk — change the large context threshold
        config["context_overrides"]["large_context"]["threshold_tokens"] = 42
        # Ensure mtime advances (some filesystems have 1s resolution)
        time.sleep(0.05)
        config_path.write_text(json.dumps(config))
        os.utime(str(config_path), (time.time() + 1, time.time() + 1))

        # Next _load_config() call should pick up the change
        router._load_config()
        assert router.config["context_overrides"]["large_context"]["threshold_tokens"] == 42

    def test_unchanged_config_no_reread(self, config_file):
        """Unchanged file (same mtime) does not trigger re-read."""
        config_path, config = config_file
        router = OmegaRouter(config_path=str(config_path))

        # Initial load
        router._load_config()
        mtime_after_load = router._config_mtime

        # Mutate in-memory config (but NOT on disk)
        router.config["context_overrides"]["large_context"]["threshold_tokens"] = 999999

        # Next _load_config() should NOT re-read because mtime hasn't changed
        router._load_config()
        assert router.config["context_overrides"]["large_context"]["threshold_tokens"] == 999999
        assert router._config_mtime == mtime_after_load

    def test_deleted_config_keeps_loaded(self, config_file):
        """If config file is deleted after initial load, router keeps working."""
        config_path, config = config_file
        router = OmegaRouter(config_path=str(config_path))

        # Initial load
        result1 = router.route("write a function", force_intent="coding")
        assert result1.model

        # Delete the file
        config_path.unlink()

        # Should still work with cached config
        result2 = router.route("write a function", force_intent="coding")
        assert result2.model == result1.model
