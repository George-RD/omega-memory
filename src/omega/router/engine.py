"""
OMEGA Router Engine -- Intelligent multi-LLM model selection.

Routes prompts to optimal LLM based on intent classification, priority mode,
context affinity, and provider availability.

Extracted from Gnosis gnosis_router.py, adapted for OMEGA:
  - gnosis_state.paths → module constants
  - gnosis_json → standard json
  - gnosis_magma → omega.bridge for memory operations
  - coordination.json → omega.db (via coordination manager)
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default config bundled with package
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "defaults.json"

# User override config
OMEGA_DIR = Path.home() / ".omega"
_USER_CONFIG_PATH = OMEGA_DIR / "router_config.json"

# Secrets file for API keys
_SECRETS_PATH = Path.home() / ".omega" / "secrets.json"

# Default fallback model (used when config is missing/malformed)
_DEFAULT_FALLBACK_MODEL = "claude-sonnet-4-5-20250929"

# Context window defaults (tokens)
_DEFAULT_CONTEXT_WINDOW = 200_000
_LARGE_CONTEXT_THRESHOLD = 100_000
_LARGE_CONTEXT_WINDOW = 1_000_000


class PriorityMode(Enum):
    """Priority modes for model selection."""

    COST = "cost"
    SPEED = "speed"
    QUALITY = "quality"
    BALANCED = "balanced"


@dataclass
class ModelConfig:
    """Configuration for a single model."""

    provider: str
    model: str
    reason: str
    context_window: int = _DEFAULT_CONTEXT_WINDOW
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0


@dataclass
class SessionContext:
    """Tracks context for a session to enable context affinity."""

    session_id: str
    current_model: str
    current_provider: str
    context_tokens: int = 0
    conversation_depth: int = 0
    last_updated: str = ""

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "current_model": self.current_model,
            "current_provider": self.current_provider,
            "context_tokens": self.context_tokens,
            "conversation_depth": self.conversation_depth,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SessionContext":
        return cls(
            session_id=data.get("session_id", ""),
            current_model=data.get("current_model", ""),
            current_provider=data.get("current_provider", ""),
            context_tokens=data.get("context_tokens", 0),
            conversation_depth=data.get("conversation_depth", 0),
            last_updated=data.get("last_updated", ""),
        )


@dataclass
class RoutingResult:
    """Result of routing a prompt."""

    model: str
    provider: str
    intent: str
    confidence: float
    reason: str
    fallback_model: Optional[str] = None
    fallback_provider: Optional[str] = None
    priority_mode: str = "balanced"
    context_override: bool = False
    latency_ms: float = 0.0
    all_scores: Dict[str, float] = field(default_factory=dict)


# ============================================================================
# Router Implementation
# ============================================================================


class OmegaRouter:
    """
    Intelligent LLM router. Selects optimal model based on:
    1. Intent classification (coding, creative, logic, exploration, simple_edit)
    2. Priority mode (cost, speed, quality, balanced)
    3. Context size (large context override)
    4. Provider availability
    5. Context affinity (prefer models with existing context)
    6. Provider-aware routing (prefer same-provider downgrades)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the router.

        Args:
            config_path: Path to config JSON. Falls back to user override then defaults.
        """
        if config_path:
            self.config_path = config_path
        elif _USER_CONFIG_PATH.exists():
            self.config_path = str(_USER_CONFIG_PATH)
        else:
            self.config_path = str(_DEFAULT_CONFIG_PATH)

        self.config: Dict = {}
        self._classifier = None
        self._loaded = False
        self._config_mtime: float = 0.0
        self._session_contexts: Dict[str, SessionContext] = {}
        self._max_session_contexts = 1000

    def _load_config(self):
        """Load model configuration from JSON file (with mtime-based hot-reload)."""
        try:
            mtime = os.path.getmtime(self.config_path)
        except OSError:
            if self._loaded:
                return
            raise FileNotFoundError(
                f"Router config not found at {self.config_path}. "
                f"Copy defaults.json to {_USER_CONFIG_PATH} to customize."
            )
        if self._loaded and mtime == self._config_mtime:
            return
        with open(self.config_path, "r") as f:
            self.config = json.load(f)
        self._config_mtime = mtime
        self._loaded = True

    def _get_classifier(self):
        """Lazy-load the intent classifier."""
        if self._classifier is None:
            try:
                from omega.router.classifier import get_classifier

                self._classifier = get_classifier()
            except Exception as e:
                logger.debug("Intent classifier initialization failed: %s", e)
                self._classifier = None
        return self._classifier

    def _classify_intent(self, prompt: str) -> Tuple[str, float, Dict[str, float]]:
        """Classify the intent of a prompt."""
        classifier = self._get_classifier()
        if classifier is not None:
            result = classifier.classify(prompt)
            return result.intent, result.confidence, result.all_scores
        else:
            from omega.router.classifier import classify_intent_keywords

            intent, confidence = classify_intent_keywords(prompt)
            return intent, confidence, {intent: confidence}

    def _get_model_for_intent(self, intent: str) -> Tuple[ModelConfig, Optional[ModelConfig]]:
        """Get primary and fallback models for an intent."""
        self._load_config()
        intent_config = self.config.get("intent_routing", {}).get(intent)
        if not intent_config:
            intent_config = self.config.get("intent_routing", {}).get("coding", {})

        primary = intent_config.get("primary", {})
        fallback = intent_config.get("fallback")

        primary_config = ModelConfig(
            provider=primary.get("provider", "anthropic"),
            model=primary.get("model", _DEFAULT_FALLBACK_MODEL),
            reason=primary.get("reason", "Default model"),
            context_window=primary.get("context_window", _DEFAULT_CONTEXT_WINDOW),
            cost_per_1m_input=primary.get("cost_per_1m_input", 0.0),
            cost_per_1m_output=primary.get("cost_per_1m_output", 0.0),
        )

        fallback_config = None
        if fallback:
            fallback_config = ModelConfig(
                provider=fallback.get("provider", "anthropic"),
                model=fallback.get("model", _DEFAULT_FALLBACK_MODEL),
                reason=fallback.get("reason", "Fallback model"),
            )

        return primary_config, fallback_config

    def _apply_priority_mode(
        self,
        primary: ModelConfig,
        fallback: Optional[ModelConfig],
        priority: PriorityMode,
    ) -> Tuple[ModelConfig, Optional[ModelConfig]]:
        """Apply priority mode preferences to model selection."""
        self._load_config()
        priority_config = self.config.get("priority_modes", {}).get(priority.value, {})
        preferred_models = priority_config.get("prefer_models", [])

        if not preferred_models:
            return primary, fallback
        if primary.model in preferred_models:
            return primary, fallback
        if fallback and fallback.model in preferred_models:
            return fallback, primary
        return primary, fallback

    def _check_context_override(self, estimated_tokens: int) -> Optional[ModelConfig]:
        """Check if context size requires a special model."""
        self._load_config()
        context_overrides = self.config.get("context_overrides", {})
        large_context = context_overrides.get("large_context", {})
        threshold = large_context.get("threshold_tokens", _LARGE_CONTEXT_THRESHOLD)

        if estimated_tokens > threshold:
            model_config = large_context.get("model", {})
            return ModelConfig(
                provider=model_config.get("provider", "google"),
                model=model_config.get("model", "gemini-2.5-pro"),
                reason=model_config.get("reason", "Large context window needed"),
                context_window=model_config.get("context_window", _LARGE_CONTEXT_WINDOW),
            )
        return None

    # =========================================================================
    # Context Affinity
    # =========================================================================

    def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        """Get the context for a session."""
        return self._session_contexts.get(session_id)

    def update_session_context(
        self,
        session_id: str,
        model: str,
        provider: str,
        context_tokens: int = 0,
        conversation_depth: int = 0,
    ) -> SessionContext:
        """Update the context for a session after routing."""
        # Evict oldest entries when at capacity
        if (
            session_id not in self._session_contexts
            and len(self._session_contexts) >= self._max_session_contexts
        ):
            oldest_id = min(
                self._session_contexts,
                key=lambda k: self._session_contexts[k].last_updated,
            )
            del self._session_contexts[oldest_id]

        context = SessionContext(
            session_id=session_id,
            current_model=model,
            current_provider=provider,
            context_tokens=context_tokens,
            conversation_depth=conversation_depth,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
        self._session_contexts[session_id] = context
        return context

    def _calculate_switch_penalty(
        self,
        current_context: Optional[SessionContext],
        target_model: str,
        target_provider: str,
    ) -> float:
        """Calculate penalty for switching models based on context affinity."""
        if current_context is None:
            return 0.0

        self._load_config()
        affinity_config = self.config.get("context_affinity", {})
        if not affinity_config.get("enabled", True):
            return 0.0

        min_context = affinity_config.get("min_context_for_affinity", 1000)
        if current_context.context_tokens < min_context:
            return 0.0

        penalties = affinity_config.get("switch_penalties", {})
        context_factor = affinity_config.get("context_size_factor", 0.001)
        max_penalty = affinity_config.get("max_penalty", 0.5)

        if current_context.current_model == target_model:
            return penalties.get("same_model", 0.0)

        if current_context.current_provider == target_provider:
            base_penalty = penalties.get("same_provider_different_tier", 0.1)
        else:
            base_penalty = penalties.get("different_provider", 0.3)

        context_penalty = current_context.context_tokens * context_factor
        return min(base_penalty + context_penalty, max_penalty)

    # =========================================================================
    # Provider-Aware Routing
    # =========================================================================

    def _get_provider_tiers(self, provider: str) -> List[Dict]:
        """Get tier configuration for a provider."""
        self._load_config()
        return self.config.get("provider_tiers", {}).get(provider, {}).get("tiers", [])

    def _find_same_provider_alternative(
        self,
        target_model: str,
        target_provider: str,
        current_provider: str,
        priority_mode: PriorityMode,
    ) -> Optional[Tuple[str, str]]:
        """Find an alternative model on the same provider as current context."""
        if current_provider == target_provider:
            return None

        current_tiers = self._get_provider_tiers(current_provider)
        if not current_tiers:
            return None

        target_tiers = self._get_provider_tiers(target_provider)
        target_cost_rank = None
        for tier in target_tiers:
            if tier.get("model") == target_model:
                target_cost_rank = tier.get("cost_rank", 3)
                break
        if target_cost_rank is None:
            return None

        best_match = None
        best_score = float("inf") if priority_mode == PriorityMode.COST else 0

        for tier in current_tiers:
            model = tier.get("model")
            cost_rank = tier.get("cost_rank", 3)

            if priority_mode == PriorityMode.COST:
                if cost_rank <= target_cost_rank and cost_rank < best_score:
                    best_match = (model, current_provider)
                    best_score = cost_rank
            elif priority_mode == PriorityMode.QUALITY:
                tier_level = tier.get("tier", 3)
                if tier_level < best_score:
                    best_match = (model, current_provider)
                    best_score = tier_level
            else:
                if abs(cost_rank - target_cost_rank) <= 1:
                    return (model, current_provider)

        return best_match

    def _apply_context_affinity(
        self,
        recommended: ModelConfig,
        fallback: Optional[ModelConfig],
        session_id: Optional[str],
        priority_mode: PriorityMode,
    ) -> Tuple[ModelConfig, Optional[ModelConfig], float]:
        """Apply context affinity to model selection."""
        if session_id is None:
            return recommended, fallback, 0.0

        current_context = self.get_session_context(session_id)
        if current_context is None:
            return recommended, fallback, 0.0

        switch_penalty = self._calculate_switch_penalty(current_context, recommended.model, recommended.provider)

        if switch_penalty > 0.15 and priority_mode != PriorityMode.QUALITY:
            alternative = self._find_same_provider_alternative(
                recommended.model,
                recommended.provider,
                current_context.current_provider,
                priority_mode,
            )
            if alternative:
                alt_model, alt_provider = alternative
                alt_penalty = self._calculate_switch_penalty(current_context, alt_model, alt_provider)
                if alt_penalty < switch_penalty:
                    alt_config = ModelConfig(
                        provider=alt_provider,
                        model=alt_model,
                        reason=f"Same-provider alternative (affinity: {switch_penalty:.2f} → {alt_penalty:.2f})",
                    )
                    return alt_config, recommended, alt_penalty

        return recommended, fallback, switch_penalty

    # =========================================================================
    # Main Routing
    # =========================================================================

    def route(
        self,
        prompt: str,
        priority: str = "balanced",
        estimated_tokens: int = 0,
        force_intent: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> RoutingResult:
        """Route a prompt to the optimal model."""
        start = time.perf_counter()

        if force_intent:
            intent = force_intent
            confidence = 1.0
            all_scores = {force_intent: 1.0}
        else:
            intent, confidence, all_scores = self._classify_intent(prompt)

        context_override = self._check_context_override(estimated_tokens)
        if context_override:
            if session_id:
                self.update_session_context(
                    session_id,
                    context_override.model,
                    context_override.provider,
                    estimated_tokens,
                    0,
                )
            latency_ms = (time.perf_counter() - start) * 1000
            return RoutingResult(
                model=context_override.model,
                provider=context_override.provider,
                intent=intent,
                confidence=confidence,
                reason=context_override.reason,
                priority_mode=priority,
                context_override=True,
                latency_ms=latency_ms,
                all_scores=all_scores,
            )

        primary, fallback = self._get_model_for_intent(intent)

        priority_mode = PriorityMode(priority) if priority in [p.value for p in PriorityMode] else PriorityMode.BALANCED
        primary, fallback = self._apply_priority_mode(primary, fallback, priority_mode)
        primary, fallback, switch_penalty = self._apply_context_affinity(primary, fallback, session_id, priority_mode)

        if session_id:
            current_ctx = self.get_session_context(session_id)
            depth = (current_ctx.conversation_depth + 1) if current_ctx else 1
            self.update_session_context(
                session_id,
                primary.model,
                primary.provider,
                estimated_tokens,
                depth,
            )

        latency_ms = (time.perf_counter() - start) * 1000
        reason = primary.reason
        if switch_penalty > 0:
            reason = f"{reason} (switch penalty: {switch_penalty:.2f})"

        return RoutingResult(
            model=primary.model,
            provider=primary.provider,
            intent=intent,
            confidence=confidence,
            reason=reason,
            fallback_model=fallback.model if fallback else None,
            fallback_provider=fallback.provider if fallback else None,
            priority_mode=priority,
            context_override=False,
            latency_ms=latency_ms,
            all_scores=all_scores,
        )

    # =========================================================================
    # Model Switching with OMEGA Memory
    # =========================================================================

    def switch_model(
        self,
        session_id: str,
        target_provider: str,
        target_model: str,
        retrieve_context: bool = True,
        max_memories: int = 10,
    ) -> Dict[str, Any]:
        """
        Switch to a different model with OMEGA memory preservation.

        Retrieves relevant OMEGA memories and formats them for the target model.
        """
        result = {
            "success": False,
            "session_id": session_id,
            "target_provider": target_provider,
            "target_model": target_model,
            "previous_model": None,
            "previous_provider": None,
            "context_retrieved": False,
            "memories_count": 0,
            "switched_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            current_ctx = self.get_session_context(session_id)
            if current_ctx:
                result["previous_model"] = current_ctx.current_model
                result["previous_provider"] = current_ctx.current_provider

            if retrieve_context:
                try:
                    from omega.bridge import query

                    context_query = f"context for model switch from {result['previous_model']} to {target_model}"
                    memories = query(
                        query_text=context_query,
                        limit=max_memories,
                        session_id=session_id,
                    )
                    result["context_retrieved"] = True
                    result["context_summary"] = memories[:500] if isinstance(memories, str) else str(memories)[:500]
                except Exception as e:
                    logger.warning(f"Context retrieval failed: {e}")
                    result["context_error"] = str(e)

            self.update_session_context(
                session_id=session_id,
                model=target_model,
                provider=target_provider,
                conversation_depth=(current_ctx.conversation_depth + 1 if current_ctx else 1),
            )

            # Capture the switch event to OMEGA memory
            try:
                from omega.bridge import store

                store(
                    content=(
                        f"Switched from {result['previous_provider']}/{result['previous_model']} "
                        f"to {target_provider}/{target_model}"
                    ),
                    event_type="decision",
                    metadata={
                        "source": "router_model_switch",
                        "target_provider": target_provider,
                        "target_model": target_model,
                        "previous_provider": result["previous_provider"],
                        "previous_model": result["previous_model"],
                    },
                    session_id=session_id,
                )
            except Exception as e:
                logger.debug("Failed to store model switch event: %s", e)

            result["success"] = True
            return result

        except Exception as e:
            logger.error(f"Model switch failed: {e}")
            result["error"] = str(e)
            return result

    # =========================================================================
    # Provider Status & API Keys
    # =========================================================================

    def get_provider_status(self) -> Dict[str, str]:
        """Get status of all configured providers."""
        self._load_config()
        secrets = self._load_secrets()
        providers = self.config.get("providers", {})
        status = {}
        for name, config in providers.items():
            env_key = config.get("env_key", "")
            has_key = bool(os.environ.get(env_key)) or bool(secrets.get(env_key))
            status[name] = "available" if has_key else "no_api_key"
        return status

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider from env or secrets."""
        self._load_config()
        secrets = self._load_secrets()
        provider_config = self.config.get("providers", {}).get(provider, {})
        env_key = provider_config.get("env_key", "")
        return os.environ.get(env_key) or secrets.get(env_key)

    def _load_secrets(self) -> Dict[str, str]:
        """Load API keys from secrets file."""
        secrets = {}
        # Try OMEGA secrets first, fall back to ~/.claude/secrets.json
        for path in [_SECRETS_PATH, Path.home() / ".claude" / "secrets.json"]:
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    for k, v in data.items():
                        if not k.startswith("_") and isinstance(v, str):
                            secrets[k] = v
                    break
                except Exception:
                    pass
        return secrets

    def get_routing_stats(self) -> Dict:
        """Get routing configuration statistics."""
        self._load_config()
        intent_routing = self.config.get("intent_routing", {})
        return {
            "intents_configured": list(intent_routing.keys()),
            "priority_modes": list(self.config.get("priority_modes", {}).keys()),
            "providers": list(self.config.get("providers", {}).keys()),
            "context_override_threshold": self.config.get("context_overrides", {})
            .get("large_context", {})
            .get("threshold_tokens", _LARGE_CONTEXT_THRESHOLD),
        }

    def get_current_model(self, session_id: str) -> Optional[Dict]:
        """Get current model for a session."""
        ctx = self.get_session_context(session_id)
        if ctx:
            return {
                "provider": ctx.current_provider,
                "model": ctx.current_model,
                "switched_at": ctx.last_updated,
            }
        return None


# ============================================================================
# Singleton & Convenience Functions
# ============================================================================

_router: Optional[OmegaRouter] = None


def get_router() -> OmegaRouter:
    """Get the singleton router instance."""
    global _router
    if _router is None:
        _router = OmegaRouter()
    return _router


def route_prompt(
    prompt: str,
    priority: str = "balanced",
    estimated_tokens: int = 0,
    force_intent: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict:
    """Convenience: route a prompt, return dict."""
    result = get_router().route(prompt, priority, estimated_tokens, force_intent, session_id)
    return {
        "model": result.model,
        "provider": result.provider,
        "intent": result.intent,
        "confidence": result.confidence,
        "reason": result.reason,
        "fallback_model": result.fallback_model,
        "fallback_provider": result.fallback_provider,
        "priority_mode": result.priority_mode,
        "context_override": result.context_override,
        "latency_ms": result.latency_ms,
        "all_scores": result.all_scores,
    }


def switch_model(
    session_id: str,
    target_provider: str,
    target_model: str,
    retrieve_context: bool = True,
) -> Dict:
    """Convenience: switch models with context preservation."""
    return get_router().switch_model(
        session_id=session_id,
        target_provider=target_provider,
        target_model=target_model,
        retrieve_context=retrieve_context,
    )


def get_litellm_model_string(result: RoutingResult) -> str:
    """Convert routing result to LiteLLM model string (provider/model)."""
    provider_prefixes = {
        "anthropic": "anthropic",
        "openai": "openai",
        "google": "gemini",
    }
    prefix = provider_prefixes.get(result.provider, result.provider)
    return f"{prefix}/{result.model}"
