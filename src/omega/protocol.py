"""OMEGA Protocol — Operating rules and behavioral guidelines for agents.

Provides context-sensitive instructions covering memory usage, coordination,
reminders, and workflow patterns.
"""

from typing import Optional


def get_protocol(
    section: Optional[str] = None,
    project: Optional[str] = None,
    include_lessons: bool = True,
    peer_count: int = 0,
) -> str:
    """Retrieve operating rules and behavioral guidelines.

    Args:
        section: Specific section or group name. Sections: 'memory', 'coordination',
            'coordination_gate', 'teamwork', 'context', 'reminders', 'diagnostics',
            'entity', 'heuristics', 'git', 'what_next'. Groups: 'solo', 'multi_agent',
            'full', 'minimal'. If None, auto-detects based on peer_count.
        project: Project path for context-sensitive rules (currently unused).
        include_lessons: Whether to include learned lessons (currently unused).
        peer_count: Number of peer agents. Used for auto-detection when section is None.

    Returns:
        Markdown-formatted protocol text with operating rules.
    """
    # Auto-detect mode if no section specified
    if section is None:
        if peer_count > 0:
            section = "multi_agent"
        else:
            section = "solo"

    # Handle section groups
    if section == "solo":
        sections = ["memory", "context", "git"]
    elif section == "multi_agent":
        sections = ["memory", "coordination", "context", "git"]
    elif section == "full":
        sections = [
            "memory",
            "coordination",
            "teamwork",
            "context",
            "reminders",
            "diagnostics",
            "heuristics",
            "git",
            "what_next",
        ]
    elif section == "minimal":
        sections = ["memory", "context", "git"]
    else:
        # Single section or unknown (fallback to solo)
        if section in [
            "memory",
            "coordination",
            "coordination_gate",
            "teamwork",
            "context",
            "reminders",
            "diagnostics",
            "entity",
            "heuristics",
            "git",
            "what_next",
        ]:
            sections = [section]
        else:
            # Unknown section, fallback to solo
            sections = ["memory", "context", "git"]

    # Build protocol text
    lines = ["# OMEGA Protocol", ""]

    # Pro-only sections
    pro_sections = {"coordination", "coordination_gate", "teamwork", "entity"}

    for sec in sections:
        if sec in pro_sections:
            lines.append("## " + sec.replace("_", " ").title())
            lines.append("")
            lines.append(
                "This section is available in OMEGA Pro. Upgrade at https://omegamax.co for multi-agent coordination features."
            )
            lines.append("")
        else:
            lines.extend(_get_section_content(sec))

    return "\n".join(lines)


def _get_section_content(section: str) -> list[str]:
    """Get content for a specific protocol section."""
    sections = {
        "memory": [
            "## Memory Usage",
            "",
            "### Core Principles",
            "- Use `omega_query()` before non-trivial tasks to check for prior context",
            "- Store key outcomes with `omega_store(content, \"decision\")` after completing tasks",
            "- When user says \"remember\": use `omega_store(text, \"user_preference\")`",
            "- Use `omega_checkpoint()` when context is getting full",
            "",
            "### Memory Types",
            "- **decisions**: Architectural choices and important decisions",
            "- **lesson_learned**: Insights from debugging, errors, or discoveries",
            "- **error_pattern**: Error patterns to avoid repeating",
            "- **user_preference**: User preferences and coding style",
            "- **session_summary**: Session summaries (auto-generated)",
            "",
            "### Best Practices",
            "- Query before starting work: `omega_query(\"relevant topic\")`",
            "- Store decisions immediately after making them",
            "- Use checkpoints for long-running tasks",
            "",
        ],
        "context": [
            "## Context Management",
            "",
            "### Context Loading",
            "- Call `omega_welcome()` at session start for recent context",
            "- Use `omega_profile()` to load user preferences and profile",
            "- Query for project-specific context: `omega_query(\"project name\")`",
            "",
            "### Context Surfacing",
            "- Hooks automatically surface relevant memories during file edits",
            "- `[MEMORY]` blocks from hooks are ground truth — trust them",
            "- Use `omega_query()` with `context_file` parameter for file-specific context",
            "",
        ],
        "git": [
            "## Git Rules",
            "",
            "### Before Making Changes",
            "- Check `git log` to see recent activity",
            "- Query OMEGA for prior decisions: `omega_query(\"git workflow\")`",
            "- Ask before deploying or making breaking changes",
            "",
            "### After Making Changes",
            "- Store important decisions: `omega_store(\"decision text\", \"decision\")`",
            "- Commit messages should be clear and reference stored decisions when relevant",
            "",
        ],
        "reminders": [
            "## Reminders",
            "",
            "### Using Reminders",
            "- Set reminders with `omega_remind()` for time-based tasks",
            "- Check due reminders at session start",
            "- Dismiss reminders when completed",
            "",
        ],
        "diagnostics": [
            "## Diagnostics",
            "",
            "### Health Checks",
            "- Use `omega_maintain(action=\"health\")` to check system health",
            "- Monitor memory stats with `omega_stats()`",
            "- Check for contradictions with `omega_memory(action=\"check_contradictions\")`",
            "",
        ],
        "heuristics": [
            "## Heuristics",
            "",
            "### Decision Making",
            "- Query for similar past decisions before making new ones",
            "- Check for contradictions when storing new decisions",
            "- Prefer consistency with past decisions unless explicitly overridden",
            "",
        ],
        "what_next": [
            "## What Next",
            "",
            "### Session Flow",
            "1. Call `omega_welcome()` for context",
            "2. Call `omega_protocol()` for operating rules",
            "3. Query for relevant context before starting work",
            "4. Store decisions and lessons as you work",
            "5. Use checkpoints for long tasks",
            "",
        ],
    }

    return sections.get(section, [])
