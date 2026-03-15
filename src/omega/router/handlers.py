"""
OMEGA Router MCP Handlers -- Maps router tool names to async handlers.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("omega.router.handlers")

# Current priority mode (persisted to ~/.omega/router_priority.txt)
_PRIORITY_FILE = __import__("pathlib").Path.home() / ".omega" / "router_priority.txt"


def _load_priority_mode() -> str:
    """Load persisted priority mode, default to balanced."""
    try:
        if _PRIORITY_FILE.exists():
            mode = _PRIORITY_FILE.read_text().strip()
            if mode in ("cost", "speed", "quality", "balanced"):
                return mode
    except Exception as e:
        logger.debug("Failed to load priority mode: %s", e)
    return "balanced"


def _save_priority_mode(mode: str):
    """Persist priority mode to disk (atomic write)."""
    import os
    import tempfile

    try:
        _PRIORITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(_PRIORITY_FILE.parent), suffix=".tmp")
        closed = False
        try:
            os.write(fd, mode.encode())
            os.close(fd)
            closed = True
            os.replace(tmp, str(_PRIORITY_FILE))
        except BaseException:
            if not closed:
                os.close(fd)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.warning("Failed to persist priority mode: %s", e)


_current_priority_mode = _load_priority_mode()


from omega.server.responses import mcp_response, mcp_error


def _check_router():
    """Get router, return None if unavailable."""
    try:
        from omega.router.engine import get_router

        return get_router()
    except Exception as e:
        logger.error(f"Router unavailable: {e}")
        return None


# ============================================================================
# Handler: omega_route_prompt
# ============================================================================


async def handle_route_prompt(arguments: dict) -> dict:
    """Route a prompt to the optimal LLM."""
    prompt = arguments.get("prompt", "").strip()
    if not prompt:
        return mcp_error("prompt is required")

    router = _check_router()
    if not router:
        return mcp_error("Router not available. Install with: pip install omega-memory[router]")

    priority = arguments.get("priority", _current_priority_mode)
    estimated_tokens = arguments.get("estimated_tokens", 0)
    force_intent = arguments.get("force_intent")
    session_id = arguments.get("session_id")

    try:
        result = router.route(
            prompt=prompt,
            priority=priority,
            estimated_tokens=estimated_tokens,
            force_intent=force_intent,
            session_id=session_id,
        )

        # Format scores as visual bars
        score_lines = []
        for intent, score in sorted(result.all_scores.items(), key=lambda x: x[1], reverse=True):
            bar = "\u2588" * int(score * 20)
            marker = " \u25c0" if intent == result.intent else ""
            score_lines.append(f"  {intent:15s} {bar} {score:.3f}{marker}")

        lines = [
            "## Routing Result",
            f"**Model:** {result.provider}/{result.model}",
            f"**Intent:** {result.intent} (confidence: {result.confidence:.3f})",
            f"**Priority:** {result.priority_mode}",
            f"**Reason:** {result.reason}",
        ]

        if result.fallback_model:
            lines.append(f"**Fallback:** {result.fallback_provider}/{result.fallback_model}")
        if result.context_override:
            lines.append("**Context Override:** Yes (large context detected)")

        lines.append(f"**Latency:** {result.latency_ms:.2f}ms")
        lines.append("\n### Intent Scores")
        lines.extend(score_lines)

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error(f"route_prompt failed: {e}")
        return mcp_error(f"Routing failed: {e}")


# ============================================================================
# Handler: omega_classify_intent
# ============================================================================


async def handle_classify_intent(arguments: dict) -> dict:
    """Classify a prompt's intent."""
    prompt = arguments.get("prompt", "").strip()
    if not prompt:
        return mcp_error("prompt is required")

    try:
        from omega.router.classifier import classify_intent_detailed

        result = classify_intent_detailed(prompt)

        lines = [
            f"**Intent:** {result['intent']}",
            f"**Confidence:** {result['confidence']:.3f}",
            f"**Latency:** {result['latency_ms']:.2f}ms",
        ]

        if arguments.get("detailed", True):
            lines.append("\n### All Scores")
            for intent, score in sorted(result["all_scores"].items(), key=lambda x: x[1], reverse=True):
                bar = "\u2588" * int(score * 20)
                lines.append(f"  {intent:15s} {bar} {score:.3f}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error(f"classify_intent failed: {e}")
        return mcp_error(f"Classification failed: {e}")


# ============================================================================
# Handler: omega_router_status
# ============================================================================


async def handle_router_status(arguments: dict) -> dict:
    """Show router status and provider availability."""
    router = _check_router()
    if not router:
        return mcp_error("Router not available")

    try:
        status = router.get_provider_status()
        stats = router.get_routing_stats()

        lines = [
            "## Router Status",
            f"**Priority Mode:** {_current_priority_mode}",
            f"**Intents:** {', '.join(stats['intents_configured'])}",
            f"**Context Override:** >{stats['context_override_threshold']:,} tokens",
            "",
            "### Providers",
        ]

        for provider, pstatus in sorted(status.items()):
            icon = "\u2705" if pstatus == "available" else "\u274c"
            lines.append(f"  {icon} **{provider}**: {pstatus}")

        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error(f"router_status failed: {e}")
        return mcp_error(f"Status failed: {e}")


# ============================================================================
# Handler: omega_set_priority_mode
# ============================================================================


async def handle_set_priority_mode(arguments: dict) -> dict:
    """Set the routing priority mode."""
    global _current_priority_mode
    mode = arguments.get("mode", "").strip()
    if mode not in ("cost", "speed", "quality", "balanced"):
        return mcp_error("mode must be one of: cost, speed, quality, balanced")

    _current_priority_mode = mode
    _save_priority_mode(mode)
    return mcp_response(f"Priority mode set to **{mode}**")


# ============================================================================
# Handler: omega_get_model_config
# ============================================================================


async def handle_get_model_config(arguments: dict) -> dict:
    """View routing configuration."""
    router = _check_router()
    if not router:
        return mcp_error("Router not available")

    try:
        router._load_config()
        intent = arguments.get("intent")

        if intent:
            config = router.config.get("intent_routing", {}).get(intent)
            if not config:
                return mcp_error(f"Unknown intent: {intent}")
            lines = [
                f"## Routing Config: {intent}",
                f"**Primary:** {config['primary']['provider']}/{config['primary']['model']}",
                f"  Reason: {config['primary'].get('reason', '')}",
            ]
            if config.get("fallback"):
                lines.append(f"**Fallback:** {config['fallback']['provider']}/{config['fallback']['model']}")
                lines.append(f"  Reason: {config['fallback'].get('reason', '')}")
            return mcp_response("\n".join(lines))
        else:
            lines = ["## All Routing Configs\n"]
            for intent_name, config in router.config.get("intent_routing", {}).items():
                primary = config.get("primary", {})
                fallback = config.get("fallback", {})
                lines.append(
                    f"**{intent_name}**: {primary.get('provider')}/{primary.get('model')}"
                    f" (fallback: {fallback.get('provider', '?')}/{fallback.get('model', '?')})"
                )
            return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error(f"get_model_config failed: {e}")
        return mcp_error(f"Config failed: {e}")


# ============================================================================
# Handler: omega_switch_model
# ============================================================================


async def handle_switch_model(arguments: dict) -> dict:
    """Switch to a different model with context preservation."""
    session_id = arguments.get("session_id", "").strip()
    target_provider = arguments.get("target_provider", "").strip()
    target_model = arguments.get("target_model", "").strip()
    if not session_id:
        return mcp_error("session_id is required")
    if not target_provider or not target_model:
        return mcp_error("target_provider and target_model are required")

    router = _check_router()
    if not router:
        return mcp_error("Router not available")

    try:
        result = router.switch_model(
            session_id=session_id,
            target_provider=target_provider,
            target_model=target_model,
            retrieve_context=arguments.get("retrieve_context", True),
        )

        if result["success"]:
            lines = [
                "## Model Switch Complete",
                f"**From:** {result.get('previous_provider')}/{result.get('previous_model')}",
                f"**To:** {target_provider}/{target_model}",
            ]
            if result.get("context_retrieved"):
                lines.append("**Context:** Retrieved")
            return mcp_response("\n".join(lines))
        else:
            return mcp_error(result.get("error", "Switch failed"))
    except Exception as e:
        logger.error(f"switch_model failed: {e}")
        return mcp_error(f"Switch failed: {e}")


# ============================================================================
# Handler: omega_get_current_model
# ============================================================================


async def handle_get_current_model(arguments: dict) -> dict:
    """Get current model for a session."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")

    router = _check_router()
    if not router:
        return mcp_error("Router not available")

    model = router.get_current_model(session_id)
    if model:
        return mcp_response(
            f"**Current Model:** {model['provider']}/{model['model']}\n**Since:** {model.get('switched_at', 'unknown')}"
        )
    return mcp_response(f"No model context found for session {session_id[:20]}")


# ============================================================================
# Handler: omega_router_context
# ============================================================================


async def handle_router_context(arguments: dict) -> dict:
    """Get router session context."""
    session_id = arguments.get("session_id", "").strip()
    if not session_id:
        return mcp_error("session_id is required")

    router = _check_router()
    if not router:
        return mcp_error("Router not available")

    ctx = router.get_session_context(session_id)
    if ctx:
        return mcp_response(
            f"## Session Context: {session_id[:20]}\n"
            f"**Model:** {ctx.current_provider}/{ctx.current_model}\n"
            f"**Tokens:** {ctx.context_tokens:,}\n"
            f"**Depth:** {ctx.conversation_depth}\n"
            f"**Updated:** {ctx.last_updated}"
        )
    return mcp_response(f"No context found for session {session_id[:20]}")


# ============================================================================
# Handler: omega_warm_router
# ============================================================================


async def handle_warm_router(arguments: dict) -> dict:
    """Pre-load classifier prototypes and config."""
    import time

    start = time.perf_counter()
    try:
        from omega.router.classifier import warm_up

        warm_up()

        router = _check_router()
        if router:
            router._load_config()

        elapsed = (time.perf_counter() - start) * 1000
        return mcp_response(f"Router warmed up in {elapsed:.1f}ms")
    except Exception as e:
        logger.error(f"warm_router failed: {e}")
        return mcp_error(f"Warmup failed: {e}")


# ============================================================================
# Handler: omega_router_benchmark
# ============================================================================


async def handle_router_benchmark(arguments: dict) -> dict:
    """Run accuracy benchmark on 6 sample prompts."""
    router = _check_router()
    if not router:
        return mcp_error("Router not available")

    test_prompts = [
        ("write a python function to sort a list", "coding"),
        ("fix the bug in the login handler", "coding"),
        ("draft an email to the team", "creative"),
        ("analyze the architecture of this system", "logic"),
        ("find where the config is defined", "exploration"),
        ("fix the typo in the comment", "simple_edit"),
    ]

    try:
        results = []
        total_ms = 0
        correct = 0

        for prompt, expected in test_prompts:
            result = router.route(prompt)
            total_ms += result.latency_ms
            is_correct = result.intent == expected
            if is_correct:
                correct += 1
            icon = "  \u2705" if is_correct else "  \u274c"
            short_prompt = prompt[:40]
            results.append(
                f'{icon} "{short_prompt}" \u2192 {result.intent} (expected: {expected}, {result.latency_ms:.1f}ms)'
            )

        lines = [
            "## Router Benchmark",
            f"**Accuracy:** {correct}/{len(test_prompts)} ({100 * correct / len(test_prompts):.0f}%)",
            f"**Avg Latency:** {total_ms / len(test_prompts):.2f}ms",
            "",
        ]
        lines.extend(results)
        return mcp_response("\n".join(lines))
    except Exception as e:
        logger.error(f"benchmark failed: {e}")
        return mcp_error(f"Benchmark failed: {e}")


# ============================================================================
# Handler Registry
# ============================================================================

ROUTER_HANDLERS: Dict[str, Any] = {
    "omega_route_prompt": handle_route_prompt,
    "omega_classify_intent": handle_classify_intent,
    "omega_router_status": handle_router_status,
    "omega_set_priority_mode": handle_set_priority_mode,
    "omega_get_model_config": handle_get_model_config,
    "omega_switch_model": handle_switch_model,
    "omega_get_current_model": handle_get_current_model,
    "omega_router_context": handle_router_context,
    "omega_warm_router": handle_warm_router,
    "omega_router_benchmark": handle_router_benchmark,
}
