"""OMEGA Router MCP Tool Schemas -- 10 tools for multi-LLM routing."""

ROUTER_TOOL_SCHEMAS = [
    {
        "name": "omega_route_prompt",
        "description": "Route a prompt to the optimal LLM based on intent classification, priority mode, and context affinity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt to route"},
                "priority": {
                    "type": "string",
                    "description": "Priority mode for model selection",
                    "enum": ["cost", "speed", "quality", "balanced"],
                    "default": "balanced",
                },
                "estimated_tokens": {
                    "type": "integer",
                    "description": "Estimated total context size in tokens (triggers large-context override if >100K)",
                    "default": 0,
                },
                "force_intent": {
                    "type": "string",
                    "description": "Override intent classification",
                    "enum": ["coding", "creative", "logic", "exploration", "simple_edit"],
                },
                "session_id": {"type": "string", "description": "Session ID for context affinity tracking"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "omega_classify_intent",
        "description": "Classify a prompt's intent without routing. Returns intent, confidence, and all intent scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt to classify"},
                "detailed": {
                    "type": "boolean",
                    "description": "Return all intent scores (default true)",
                    "default": True,
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "omega_router_status",
        "description": "Show provider availability (which have API keys), routing stats, and current priority mode.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "omega_set_priority_mode",
        "description": "Set the routing priority mode. Affects which models are preferred for all subsequent routing decisions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "description": "Priority mode to set",
                    "enum": ["cost", "speed", "quality", "balanced"],
                },
            },
            "required": ["mode"],
        },
    },
    {
        "name": "omega_get_model_config",
        "description": "View the routing configuration for a specific intent or all intents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Specific intent to view (omit for all)",
                    "enum": ["coding", "creative", "logic", "exploration", "simple_edit"],
                },
            },
        },
    },
    {
        "name": "omega_switch_model",
        "description": "Switch to a different LLM with OMEGA memory preservation. Retrieves relevant context and adapts for the target model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Current session ID"},
                "target_provider": {
                    "type": "string",
                    "description": "Target provider",
                    "enum": ["anthropic", "openai", "google", "groq", "xai"],
                },
                "target_model": {"type": "string", "description": "Target model identifier"},
                "retrieve_context": {
                    "type": "boolean",
                    "description": "Whether to retrieve OMEGA context for the switch (default true)",
                    "default": True,
                },
            },
            "required": ["session_id", "target_provider", "target_model"],
        },
    },
    {
        "name": "omega_get_current_model",
        "description": "Get the current model for a session (from router's context affinity tracking).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to check"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_router_context",
        "description": "Get the router's session context (current model, provider, token count, conversation depth).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_warm_router",
        "description": "Pre-load the intent classifier prototypes and model config. Reduces first-route latency.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "omega_router_benchmark",
        "description": "Run a quick accuracy test: 6 sample prompts, verify intent classification and routing.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]
