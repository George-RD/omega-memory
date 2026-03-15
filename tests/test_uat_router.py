"""UAT — Router Lifecycle, Priority Switching, Context Override & Session Context.

End-to-end acceptance tests for the OMEGA router system.
Tests the full lifecycle through MCP handler interface.

Organized into four sections:
  1. Lifecycle — warm → classify intents → route → status → benchmark → model config
  2. Priority Switching — cost/speed/quality/balanced mode changes
  3. Context Override — large token counts override to Gemini
  4. Session Context — switch model → get current → router context
"""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.router.handlers import ROUTER_HANDLERS
import omega.router.handlers as rh


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def _reset_router():
    """Reset the router priority mode before and after each test."""
    rh._current_priority_mode = "balanced"
    yield
    rh._current_priority_mode = "balanced"


def _text(result: dict) -> str:
    """Extract text from an MCP response."""
    return result["content"][0]["text"]


def _is_error(result: dict) -> bool:
    """Check if an MCP response is an error."""
    return result.get("isError", False)


# ============================================================================
# SECTION 1: Router Lifecycle
# ============================================================================


class TestUATRouterLifecycle:
    """Full router lifecycle through MCP handlers."""

    @pytest.mark.asyncio
    async def test_warm_router(self):
        """UAT: Warming the router pre-loads classifier and config."""
        result = await ROUTER_HANDLERS["omega_warm_router"]({})
        assert not _is_error(result)
        text = _text(result)
        assert "warmed up" in text.lower() or "ms" in text

    @pytest.mark.asyncio
    async def test_classify_coding_intent(self):
        """UAT: Coding prompts are classified as coding intent."""
        result = await ROUTER_HANDLERS["omega_classify_intent"]({
            "prompt": "Write a Python function to sort a list using quicksort algorithm",
        })
        assert not _is_error(result)
        text = _text(result)
        assert "coding" in text.lower()

    @pytest.mark.asyncio
    async def test_classify_creative_intent(self):
        """UAT: Creative prompts are classified as creative intent."""
        result = await ROUTER_HANDLERS["omega_classify_intent"]({
            "prompt": "Draft an email to the team about the quarterly review",
        })
        assert not _is_error(result)
        text = _text(result)
        assert "Intent:" in text
        # Creative classification or a related intent
        assert any(intent in text.lower() for intent in ["creative", "simple_edit", "exploration"])

    @pytest.mark.asyncio
    async def test_classify_exploration_intent(self):
        """UAT: Exploration prompts are classified correctly."""
        result = await ROUTER_HANDLERS["omega_classify_intent"]({
            "prompt": "Find where the configuration files are defined in this project",
        })
        assert not _is_error(result)
        text = _text(result)
        assert "Intent:" in text

    @pytest.mark.asyncio
    async def test_classify_empty_rejected(self):
        """UAT: Empty prompt is rejected."""
        result = await ROUTER_HANDLERS["omega_classify_intent"]({"prompt": ""})
        assert _is_error(result)

    @pytest.mark.asyncio
    async def test_route_prompt_returns_model(self):
        """UAT: Routing a prompt returns a model recommendation."""
        result = await ROUTER_HANDLERS["omega_route_prompt"]({
            "prompt": "Fix the bug in the authentication middleware that causes token expiration",
        })
        assert not _is_error(result)
        text = _text(result)
        assert "Model:" in text
        assert "Intent:" in text

    @pytest.mark.asyncio
    async def test_route_prompt_shows_scores(self):
        """UAT: Route result includes intent scores."""
        result = await ROUTER_HANDLERS["omega_route_prompt"]({
            "prompt": "Analyze the system architecture and propose improvements",
        })
        text = _text(result)
        assert "Intent Scores" in text or "Routing Result" in text

    @pytest.mark.asyncio
    async def test_route_prompt_empty_rejected(self):
        """UAT: Routing an empty prompt is rejected."""
        result = await ROUTER_HANDLERS["omega_route_prompt"]({"prompt": ""})
        assert _is_error(result)

    @pytest.mark.asyncio
    async def test_router_status(self):
        """UAT: Router status shows providers and intents."""
        result = await ROUTER_HANDLERS["omega_router_status"]({})
        assert not _is_error(result)
        text = _text(result)
        assert "Router Status" in text
        assert "Priority Mode:" in text

    @pytest.mark.asyncio
    async def test_get_model_config_all(self):
        """UAT: Getting all model configs returns routing table."""
        result = await ROUTER_HANDLERS["omega_get_model_config"]({})
        assert not _is_error(result)
        text = _text(result)
        assert "Routing Config" in text or "coding" in text.lower()

    @pytest.mark.asyncio
    async def test_get_model_config_by_intent(self):
        """UAT: Getting model config for a specific intent returns details."""
        result = await ROUTER_HANDLERS["omega_get_model_config"]({"intent": "coding"})
        assert not _is_error(result)
        text = _text(result)
        assert "coding" in text.lower()
        assert "Primary:" in text

    @pytest.mark.asyncio
    async def test_get_model_config_unknown_intent(self):
        """UAT: Unknown intent returns error."""
        result = await ROUTER_HANDLERS["omega_get_model_config"]({"intent": "nonexistent_intent"})
        assert _is_error(result)

    @pytest.mark.asyncio
    async def test_benchmark(self):
        """UAT: Benchmark runs sample prompts and reports accuracy."""
        result = await ROUTER_HANDLERS["omega_router_benchmark"]({})
        assert not _is_error(result)
        text = _text(result)
        assert "Benchmark" in text
        assert "Accuracy:" in text

    @pytest.mark.asyncio
    async def test_route_with_force_intent(self):
        """UAT: Routing with force_intent bypasses classification."""
        result = await ROUTER_HANDLERS["omega_route_prompt"]({
            "prompt": "Write a poem about the ocean",
            "force_intent": "coding",
        })
        assert not _is_error(result)
        text = _text(result)
        assert "coding" in text.lower()


# ============================================================================
# SECTION 2: Priority Switching
# ============================================================================


class TestUATRouterPrioritySwitching:
    """Priority mode switching through handlers."""

    @pytest.mark.asyncio
    async def test_set_cost_mode(self):
        """UAT: Setting cost priority mode succeeds."""
        result = await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": "cost"})
        assert not _is_error(result)
        text = _text(result)
        assert "cost" in text.lower()

    @pytest.mark.asyncio
    async def test_set_speed_mode(self):
        """UAT: Setting speed priority mode succeeds."""
        result = await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": "speed"})
        assert not _is_error(result)
        text = _text(result)
        assert "speed" in text.lower()

    @pytest.mark.asyncio
    async def test_set_quality_mode(self):
        """UAT: Setting quality priority mode succeeds."""
        result = await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": "quality"})
        assert not _is_error(result)
        text = _text(result)
        assert "quality" in text.lower()

    @pytest.mark.asyncio
    async def test_set_balanced_mode(self):
        """UAT: Setting balanced priority mode succeeds."""
        result = await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": "balanced"})
        assert not _is_error(result)
        text = _text(result)
        assert "balanced" in text.lower()

    @pytest.mark.asyncio
    async def test_set_invalid_mode_rejected(self):
        """UAT: Setting an invalid priority mode is rejected."""
        result = await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": "turbo"})
        assert _is_error(result)

    @pytest.mark.asyncio
    async def test_priority_mode_persists_in_status(self):
        """UAT: Priority mode change is reflected in router status."""
        await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": "quality"})
        result = await ROUTER_HANDLERS["omega_router_status"]({})
        text = _text(result)
        assert "quality" in text.lower()

    @pytest.mark.asyncio
    async def test_priority_affects_routing(self):
        """UAT: Different priority modes may produce different routing."""
        prompt = {"prompt": "Write a complex distributed systems algorithm"}

        # Route in cost mode
        await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": "cost"})
        cost_result = await ROUTER_HANDLERS["omega_route_prompt"](prompt)
        cost_text = _text(cost_result)

        # Route in quality mode
        await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": "quality"})
        quality_result = await ROUTER_HANDLERS["omega_route_prompt"](prompt)
        quality_text = _text(quality_result)

        # Both should succeed (content may or may not differ)
        assert not _is_error(cost_result)
        assert not _is_error(quality_result)
        assert "Model:" in cost_text
        assert "Model:" in quality_text

    @pytest.mark.asyncio
    async def test_set_empty_mode_rejected(self):
        """UAT: Empty priority mode is rejected."""
        result = await ROUTER_HANDLERS["omega_set_priority_mode"]({"mode": ""})
        assert _is_error(result)


# ============================================================================
# SECTION 3: Context Override
# ============================================================================


class TestUATRouterContextOverride:
    """Large context override through handlers."""

    @pytest.mark.asyncio
    async def test_large_context_overrides(self):
        """UAT: Routing with >100K tokens triggers context override."""
        result = await ROUTER_HANDLERS["omega_route_prompt"]({
            "prompt": "Analyze this very large codebase",
            "estimated_tokens": 150000,
        })
        assert not _is_error(result)
        text = _text(result)
        assert "Context Override" in text or "gemini" in text.lower() or "google" in text.lower()

    @pytest.mark.asyncio
    async def test_normal_context_no_override(self):
        """UAT: Routing with normal token count does not trigger override."""
        result = await ROUTER_HANDLERS["omega_route_prompt"]({
            "prompt": "Fix a small bug in the login handler",
            "estimated_tokens": 5000,
        })
        assert not _is_error(result)
        text = _text(result)
        # Should not have context override
        assert "Context Override" not in text

    @pytest.mark.asyncio
    async def test_boundary_context_no_override(self):
        """UAT: Routing at exactly 100K tokens does not trigger override."""
        result = await ROUTER_HANDLERS["omega_route_prompt"]({
            "prompt": "Review this medium-sized project",
            "estimated_tokens": 100000,
        })
        assert not _is_error(result)
        text = _text(result)
        assert "Context Override" not in text

    @pytest.mark.asyncio
    async def test_massive_context_override(self):
        """UAT: Very large context (500K+) also triggers override."""
        result = await ROUTER_HANDLERS["omega_route_prompt"]({
            "prompt": "Process this entire repository",
            "estimated_tokens": 500000,
        })
        assert not _is_error(result)
        text = _text(result)
        assert "Context Override" in text or "gemini" in text.lower() or "google" in text.lower()


# ============================================================================
# SECTION 4: Session Context
# ============================================================================


class TestUATRouterSessionContext:
    """Session context and model switching through handlers."""

    @pytest.mark.asyncio
    async def test_get_current_model_no_context(self):
        """UAT: Getting current model with no session context returns appropriate message."""
        result = await ROUTER_HANDLERS["omega_get_current_model"]({
            "session_id": "no-context-session",
        })
        assert not _is_error(result)
        text = _text(result)
        assert "No model context" in text or "no-context" in text

    @pytest.mark.asyncio
    async def test_get_current_model_requires_session(self):
        """UAT: Getting current model requires session_id."""
        result = await ROUTER_HANDLERS["omega_get_current_model"]({"session_id": ""})
        assert _is_error(result)

    @pytest.mark.asyncio
    async def test_router_context_no_session(self):
        """UAT: Getting router context with no session returns no context."""
        result = await ROUTER_HANDLERS["omega_router_context"]({
            "session_id": "nonexistent-session",
        })
        assert not _is_error(result)
        text = _text(result)
        assert "No context" in text

    @pytest.mark.asyncio
    async def test_router_context_requires_session(self):
        """UAT: Router context requires session_id."""
        result = await ROUTER_HANDLERS["omega_router_context"]({"session_id": ""})
        assert _is_error(result)

    @pytest.mark.asyncio
    async def test_switch_model_requires_fields(self):
        """UAT: Switch model requires session_id, target_provider, target_model."""
        result = await ROUTER_HANDLERS["omega_switch_model"]({
            "session_id": "",
            "target_provider": "anthropic",
            "target_model": "claude-sonnet-4-5-20250929",
        })
        assert _is_error(result)

        result = await ROUTER_HANDLERS["omega_switch_model"]({
            "session_id": "test-session",
            "target_provider": "",
            "target_model": "",
        })
        assert _is_error(result)
