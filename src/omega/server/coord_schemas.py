"""OMEGA Coordination MCP Tool Schemas -- 43 schemas (44 handlers with aliases) for multi-agent coordination."""

COORD_TOOL_SCHEMAS = [
    {
        "name": "omega_session_register",
        "description": "Register this agent session for multi-agent coordination. Called automatically by session start hook.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Unique session identifier"},
                "project": {"type": "string", "description": "Project directory path"},
                "task": {"type": "string", "description": "Current task description"},
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Agent capabilities (e.g. ['code', 'test', 'review'])",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_session_heartbeat",
        "description": "Update session heartbeat to signal this agent is still active.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session to heartbeat"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_session_deregister",
        "description": "End this agent session. Releases all file/branch claims and intents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session to deregister"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_sessions_list",
        "description": "List all active agent sessions. Auto-cleans stale sessions first.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "omega_file_claim",
        "description": "Claim exclusive access to a file. Returns conflict info if another agent owns it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "task": {"type": "string", "description": "What you're doing with this file"},
                "force": {
                    "type": "boolean",
                    "description": "Force-claim: override another agent's claim (audited). Use when coordination breaks down.",
                    "default": False,
                },
            },
            "required": ["session_id", "file_path"],
        },
    },
    {
        "name": "omega_file_release",
        "description": "Release your claim on a file so other agents can access it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "file_path": {"type": "string", "description": "File path to release"},
            },
            "required": ["session_id", "file_path"],
        },
    },
    {
        "name": "omega_file_check",
        "description": "Check who owns a file (if anyone). Use before editing to avoid conflicts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File path to check"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "omega_branch_claim",
        "description": "Claim exclusive access to a git branch. Protected branches (main, master, develop, release) are blocked.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "project": {"type": "string", "description": "Project directory path"},
                "branch": {"type": "string", "description": "Branch name to claim"},
                "task": {"type": "string", "description": "What you're doing on this branch"},
            },
            "required": ["session_id", "project", "branch"],
        },
    },
    {
        "name": "omega_branch_release",
        "description": "Release your claim on a git branch.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "project": {"type": "string", "description": "Project directory path"},
                "branch": {"type": "string", "description": "Branch name to release"},
            },
            "required": ["session_id", "project", "branch"],
        },
    },
    {
        "name": "omega_intent_announce",
        "description": "Broadcast your planned work so other agents can check for overlaps before starting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "description": {"type": "string", "description": "What you plan to do"},
                "target_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files you plan to modify",
                },
                "target_branch": {"type": "string", "description": "Branch you plan to use"},
                "intent_type": {
                    "type": "string",
                    "description": "Category of intent (e.g. work, edit, refactor, test). Default: work",
                    "default": "work",
                },
                "ttl_minutes": {
                    "type": "integer",
                    "description": "How long this intent is valid (default 30 minutes)",
                    "default": 30,
                },
            },
            "required": ["session_id", "description"],
        },
    },
    {
        "name": "omega_intent_check",
        "description": "Check if your planned files/branch overlap with other agents' announced intents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_coord_status",
        "description": "Coordination dashboard: active sessions, file/branch claims, intents, and detected conflicts.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "omega_session_snapshot",
        "description": "Explicitly snapshot a session's state (claims, intents, task) before risky operations. The snapshot persists even after session deletion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session to snapshot"},
                "reason": {
                    "type": "string",
                    "description": "Why this snapshot is being taken (default: 'manual')",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_session_recover",
        "description": "Recover context from a predecessor session that crashed or was cleaned up. Returns the most recent snapshot for the given project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project directory path to recover context for"},
            },
            "required": ["project"],
        },
    },
    {
        "name": "omega_task_create",
        "description": "Create a task for agents to claim and work on. Tasks enable formal work decomposition in multi-agent workflows. Use depends_on to chain tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID (task creator)"},
                "title": {"type": "string", "description": "Brief task title"},
                "description": {"type": "string", "description": "Detailed task description"},
                "project": {"type": "string", "description": "Project this task belongs to"},
                "priority": {
                    "type": "integer",
                    "description": "Priority (higher = more urgent, default 0)",
                    "default": 0,
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Task IDs that must complete before this task can be claimed",
                },
            },
            "required": ["session_id", "title"],
        },
    },
    {
        "name": "omega_task_claim",
        "description": "Claim a pending task so you can work on it. Only unclaimed (pending) tasks can be claimed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task to claim"},
                "session_id": {"type": "string", "description": "Your session ID"},
            },
            "required": ["task_id", "session_id"],
        },
    },
    {
        "name": "omega_task_next",
        "description": "Find and auto-claim the next available task. Picks the highest-priority unblocked pending task. Use when idle or after completing a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "project": {"type": "string", "description": "Filter by project (optional)"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_task_complete",
        "description": "Mark a task as completed. Only the session that claimed the task (or unclaimed tasks) can complete it. Returns list of any tasks that were unblocked.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task to complete"},
                "session_id": {"type": "string", "description": "Your session ID"},
                "result": {"type": "string", "description": "Result summary or output from this task"},
            },
            "required": ["task_id", "session_id"],
        },
    },
    {
        "name": "omega_tasks_list",
        "description": "List coordination tasks with optional project/status filters. Shows progress, dependencies, and blocked status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Filter by project"},
                "status": {
                    "type": "string",
                    "description": "Filter by status",
                    "enum": ["pending", "in_progress", "completed", "failed", "canceled"],
                },
            },
        },
    },
    {
        "name": "omega_audit",
        "description": "Query the coordination audit log. Shows recent tool calls with session, arguments, and results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Filter by session ID"},
                "tool_name": {"type": "string", "description": "Filter by tool name"},
                "limit": {
                    "type": "integer",
                    "description": "Max entries to return (default 50)",
                    "default": 50,
                },
            },
        },
    },
    {
        "name": "omega_task_cancel",
        "description": "Cancel a task. Only the owning session (or creator for unclaimed tasks) can cancel. Does NOT unblock dependent tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task to cancel"},
                "session_id": {"type": "string", "description": "Your session ID"},
            },
            "required": ["task_id", "session_id"],
        },
    },
    # --- v2 tools: Message bus, task deps, progress, capability routing ---
    {
        "name": "omega_send_message",
        "description": "Send a message to a specific agent session or broadcast to all agents on a project. Use msg_type to indicate intent: request, inform, acknowledge, reject, or complete.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID (sender)"},
                "subject": {"type": "string", "description": "Brief message summary shown in inbox"},
                "to_session": {"type": "string", "description": "Target session ID (omit to broadcast to project)"},
                "body": {"type": "string", "description": "Detailed message content"},
                "msg_type": {
                    "type": "string",
                    "description": "Message type: request, inform, acknowledge, reject, or complete",
                    "enum": ["request", "inform", "acknowledge", "reject", "complete"],
                    "default": "inform",
                },
                "context_id": {
                    "type": "string",
                    "description": "Thread ID to group related messages (auto-generated if omitted)",
                },
                "ref_task_id": {"type": "integer", "description": "Optional reference to a coord task ID"},
                "ttl_minutes": {"type": "integer", "description": "Auto-expire after N minutes (default: no expiry)"},
                "priority": {
                    "type": "string",
                    "description": "Notification priority: critical (immediate), high (hourly batch), medium (3-hour batch)",
                    "enum": ["critical", "high", "medium"],
                    "default": "medium",
                },
            },
            "required": ["session_id", "subject"],
        },
    },
    {
        "name": "omega_inbox",
        "description": "Check your inbox for messages from other agents. Marks fetched unread messages as read.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "unread_only": {
                    "type": "boolean",
                    "description": "Only show unread messages (default true)",
                    "default": True,
                },
                "msg_type": {
                    "type": "string",
                    "description": "Filter by message type",
                    "enum": ["request", "inform", "acknowledge", "reject", "complete"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Max messages to return (default 20)",
                    "default": 20,
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_task_fail",
        "description": "Mark a task as failed. Does NOT unblock dependent tasks. Use when a task cannot be completed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task to fail"},
                "session_id": {"type": "string", "description": "Your session ID"},
                "reason": {"type": "string", "description": "Why the task failed"},
            },
            "required": ["task_id", "session_id"],
        },
    },
    {
        "name": "omega_task_progress",
        "description": "Update progress (0-100) on a claimed task. Only the claiming session can update progress.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task"},
                "session_id": {"type": "string", "description": "Your session ID"},
                "progress": {
                    "type": "integer",
                    "description": "Progress percentage (0-100)",
                    "minimum": 0,
                    "maximum": 100,
                },
                "status_note": {"type": "string", "description": "Brief status note (e.g. 'Running tests...')"},
            },
            "required": ["task_id", "session_id", "progress"],
        },
    },
    {
        "name": "omega_find_agents",
        "description": "Find active agent sessions with a matching capability. Use to route work to the right agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "capability": {
                    "type": "string",
                    "description": "Capability to search for (e.g. 'test', 'review', 'deploy')",
                },
                "project": {"type": "string", "description": "Optionally filter by project"},
            },
            "required": ["capability"],
        },
    },
    # --- v3 tools: Task deps, git events, branch check ---
    {
        "name": "omega_task_deps",
        "description": "Get dependency graph for a task. Shows what blocks this task and what it blocks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task to inspect"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "omega_git_events",
        "description": "Query recent git events tracked by coordination (pushes, divergence warnings, merges).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Filter by project path"},
                "event_type": {"type": "string", "description": "Filter by event type (e.g. push, push_divergence_warning)"},
                "limit": {
                    "type": "integer",
                    "description": "Max events to return (default 20)",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "omega_branch_check",
        "description": "Check who owns a branch (if anyone). Use before branch operations to avoid conflicts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project directory path"},
                "branch": {"type": "string", "description": "Branch name to check"},
            },
            "required": ["project", "branch"],
        },
    },
    # --- v4 tools: Coordination metrics + structured handoffs ---
    {
        "name": "omega_coord_metrics",
        "description": "View coordination metrics: conflict rates, gate check counts, handoff read rates. Use to assess coordination health.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to aggregate (default 7)",
                    "default": 7,
                },
                "project": {"type": "string", "description": "Filter by project path"},
            },
        },
    },
    {
        "name": "omega_handoff",
        "description": "Create or retrieve a structured session handoff. Structured handoffs replace free-text decision stores with typed fields: completed tasks, blocked items, decisions, next steps. Auto-enriched with git state and file claims.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "action": {
                    "type": "string",
                    "description": "Action: 'create' (default) or 'get' (retrieve latest)",
                    "enum": ["create", "get"],
                    "default": "create",
                },
                "project": {"type": "string", "description": "Project directory path"},
                "completed_tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tasks completed in this session",
                },
                "blocked_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Items that are blocked and why",
                },
                "key_context": {"type": "string", "description": "Critical context the next agent needs"},
                "next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recommended next steps for the successor",
                },
                "files_modified": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files modified (auto-populated from claims if omitted)",
                },
                "decisions_made": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key decisions made during this session",
                },
            },
        },
    },
    # --- v5 tools: External action registry ---
    {
        "name": "omega_action_check",
        "description": "Check if an external action has already been claimed or completed. Use before deploying, submitting to directories, sending emails, or tweeting to avoid duplicate execution by multiple agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "description": "Category of action (e.g. 'deploy', 'mcp_submit', 'email', 'tweet')",
                },
                "action_target": {
                    "type": "string",
                    "description": "Specific target (e.g. 'vercel:omega-website', 'smithery.ai', 'user@example.com')",
                },
            },
            "required": ["action_type", "action_target"],
        },
    },
    {
        "name": "omega_action_claim",
        "description": "Atomically claim an external action (deploy, submit, email, tweet) to prevent duplicate execution by multiple agents. Returns failure if another agent already claimed or completed it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "action_type": {
                    "type": "string",
                    "description": "Category of action (e.g. 'deploy', 'mcp_submit', 'email', 'tweet')",
                },
                "action_target": {
                    "type": "string",
                    "description": "Specific target (e.g. 'vercel:omega-website', 'smithery.ai', 'user@example.com')",
                },
                "params": {
                    "type": "object",
                    "description": "Optional parameters for the action (stored as JSON)",
                },
            },
            "required": ["session_id", "action_type", "action_target"],
        },
    },
    {
        "name": "omega_action_complete",
        "description": "Mark a claimed external action as completed or failed. Only the session that claimed the action can complete it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_id": {"type": "integer", "description": "ID of the action to complete"},
                "session_id": {"type": "string", "description": "Your session ID"},
                "result": {"type": "string", "description": "Result summary or output from the action"},
                "success": {
                    "type": "boolean",
                    "description": "Whether the action succeeded (default true)",
                    "default": True,
                },
            },
            "required": ["action_id", "session_id"],
        },
    },
    # --- v6 tools: Goal persistence + drift detection ---
    {
        "name": "omega_goal",
        "description": "Manage persistent goals that survive session restarts. Goals generate tasks, provide immutable anchors for drift detection, and support decomposition (parent-child) and evolution (intent changes).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Goal action: create, evolve, complete, list, or get",
                    "enum": ["create", "evolve", "complete", "list", "get"],
                },
                "session_id": {"type": "string", "description": "Your session ID"},
                "goal_id": {"type": "integer", "description": "Goal ID (for evolve, complete, get)"},
                "title": {"type": "string", "description": "Goal title (for create)"},
                "description": {"type": "string", "description": "Goal description (for create, evolve)"},
                "project": {"type": "string", "description": "Project path (for create, list)"},
                "target_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Expected file paths/patterns this goal touches (for create; used in drift detection)",
                },
                "target_modules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Expected module areas (for create)",
                },
                "success_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Measurable success criteria (for create)",
                },
                "parent_goal_id": {"type": "integer", "description": "Parent goal for decomposition (for create)"},
                "reason": {"type": "string", "description": "Why the goal is evolving (for evolve)"},
                "priority": {
                    "type": "integer",
                    "description": "Priority (higher = more urgent, default 0)",
                    "default": 0,
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status (for list, default 'active')",
                    "enum": ["active", "paused", "completed", "abandoned"],
                    "default": "active",
                },
                "include_children": {
                    "type": "boolean",
                    "description": "Include child goals in list results (default false)",
                    "default": False,
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "omega_goal_link",
        "description": "Link an existing coordination task to a goal. Tasks linked to goals participate in drift detection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to link"},
                "goal_id": {"type": "integer", "description": "Goal ID to link to"},
            },
            "required": ["task_id", "goal_id"],
        },
    },
    {
        "name": "omega_drift_check",
        "description": "Check drift for a specific goal or all active goals in a project. Pure SQL, no LLM calls, <50ms. Returns composite drift score (0-1) with signal breakdown and alert level.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "integer", "description": "Check drift for a specific goal"},
                "project": {"type": "string", "description": "Check drift for all active goals in a project"},
            },
        },
    },
    # --- v7 tools: Drift-aware routing + cross-agent comparison ---
    {
        "name": "omega_smart_route",
        "description": "Drift-aware task routing. Claims the best available task for this session, penalizing goals with high drift and boosting sessions with matching capabilities. Falls back to priority ordering if no goal-linked tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "project": {"type": "string", "description": "Filter by project (optional)"},
                "goal_id": {"type": "integer", "description": "Filter by goal (optional)"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "omega_decision_register",
        "description": "Register an authoritative decision for a domain. Auto-supersedes prior decisions in the same domain. Broadcasts to peers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "project": {"type": "string", "description": "Project directory path"},
                "domain": {
                    "type": "string",
                    "description": "Hierarchical domain key (e.g. 'auth', 'deploy/vercel', 'testing/e2e')",
                },
                "decision": {"type": "string", "description": "The decision text"},
                "rationale": {"type": "string", "description": "Why this decision was made"},
                "goal_id": {"type": "integer", "description": "Link to a coordination goal (optional)"},
                "metadata": {"type": "object", "description": "Additional metadata (optional)"},
            },
            "required": ["session_id", "project", "domain", "decision"],
        },
    },
    {
        "name": "omega_decision_query",
        "description": "Query active decisions for a project. Supports domain prefix matching (e.g. 'auth' matches 'auth', 'auth/jwt', 'auth/oauth').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project directory path"},
                "domain": {"type": "string", "description": "Domain prefix filter (optional)"},
                "status": {
                    "type": "string",
                    "description": "Filter by status: active (default), superseded, revoked",
                    "default": "active",
                },
                "goal_id": {"type": "integer", "description": "Filter by goal (optional)"},
                "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
            },
            "required": ["project"],
        },
    },
    {
        "name": "omega_decision_revoke",
        "description": "Revoke an active decision. Use when a decision is no longer valid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "decision_id": {"type": "integer", "description": "ID of the decision to revoke"},
                "session_id": {"type": "string", "description": "Your session ID"},
                "reason": {"type": "string", "description": "Why this decision is being revoked"},
            },
            "required": ["decision_id", "session_id"],
        },
    },
    {
        "name": "omega_update_task",
        "description": "Set or update the task description for your session. Shows on the admin dashboard.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Your session ID"},
                "task": {"type": "string", "description": "Brief description of what you are working on"},
            },
            "required": ["session_id", "task"],
        },
    },
    # --- v8 tools: Self-audit council ---
    {
        "name": "omega_council",
        "description": "Run a self-audit council analysis. Domains: platform_health (error rates, capacity, tool failures), security (credential exposure, injection risks), innovation (unused capabilities, new feature ideas).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Council domain to run",
                    "enum": ["platform_health", "security", "innovation"],
                },
                "project": {
                    "type": "string",
                    "description": "Scope to specific project (optional)",
                },
            },
            "required": ["domain"],
        },
    },
]
