"""OMEGA Router -- Intelligent multi-LLM routing with intent classification."""

from omega.router.engine import (
    OmegaRouter,
    RoutingResult,
    PriorityMode,
    ModelConfig,
    SessionContext,
    get_router,
    route_prompt,
    switch_model,
    get_litellm_model_string,
)
from omega.router.classifier import (
    IntentClassifier,
    ClassificationResult,
    classify_intent,
    classify_intent_keywords,
)

__all__ = [
    "OmegaRouter",
    "RoutingResult",
    "PriorityMode",
    "ModelConfig",
    "SessionContext",
    "IntentClassifier",
    "ClassificationResult",
    "get_router",
    "route_prompt",
    "switch_model",
    "classify_intent",
    "classify_intent_keywords",
    "get_litellm_model_string",
]
