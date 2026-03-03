"""
OMEGA Protocol (Community Edition) — behavioral guidelines for solo agents.

Provides context-sensitive protocol sections served on-demand via the
omega_protocol() MCP tool. This is the community edition with 8 core
sections covering memory usage, context management, and workflow best
practices.

For multi-agent coordination, entity management, and advanced features,
see the Pro edition at https://omegamax.co
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger("omega.protocol")

PROTOCOL_VERSION = "1.5.0-community"

# ---------------------------------------------------------------------------
# Protocol Sections — each is a (title, content) pair
# ---------------------------------------------------------------------------

SECTIONS: Dict[str, Dict[str, str]] = {
    "memory": {
        "title": "Memory Usage",
        "content": """\
- `[OMEGA MEMORY]` blocks from hooks = ground truth, use immediately
- ALWAYS call `omega_query()` before non-trivial tasks — check for prior context, decisions, gotchas
- **After** completing tasks: `omega_store(content, "decision"|"lesson_learned")` for key outcomes
- Sessions with 0 `omega_store` calls trigger an auto-safety-net at session end — manual stores produce higher-quality captures.
- **On errors**: check OMEGA for prior solutions before debugging from scratch
- **User says "remember"**: `omega_store(text, "user_preference")`
- When asked about preferences/history: query OMEGA FIRST, don't say "I don't know"
- **Feedback loop**: After `omega_query` surfaces memories with IDs, use `omega_feedback(memory_id, "helpful"|"unhelpful"|"outdated")` to train the ranker
- **Memory editing**: Prefer `omega_edit_memory(memory_id, new_content)` over delete+recreate
- **Always tag stores**: Pass `project` (cwd path) when calling `omega_store`. Without tags, memories can't be scoped or filtered later.
- **Use event_type precisely**: decision (choices made), lesson_learned (insights), error_pattern (bugs), user_preference (user requests). Default "memory" is low-signal.""",
    },
    "context": {
        "title": "Context Management",
        "content": """\
- When context window is getting full (>70%): `omega_checkpoint` to save task state
- When starting a session for an ongoing task: `omega_resume_task` first
- When `[CHECKPOINT]` appears at session start: offer to resume with `omega_resume_task`
- Checkpoints save: plan, progress, files changed, decisions, key context, next steps""",
    },
    "reminders": {
        "title": "Reminders",
        "content": """\
- When user says "remind me" or task has a future deadline: `omega_remind(text, duration)`
- Duration examples: '1h', '30m', '2d', '1w', '1d12h'
- At session start: check `omega_remind_list` for pending/fired reminders
- After acknowledging a reminder: `omega_remind_dismiss(reminder_id)`""",
    },
    "heuristics": {
        "title": "Decision Heuristics",
        "content": """\
- **Reversibility test**: Reversible → proceed. Irreversible → ask first.
- **Friction is signal**: Harder than expected? Investigate — usually means missing context.
- **Learn, don't just complete**: On mistakes, `omega_store` the lesson before moving on.
- **Push back from care**: If user's approach will cause problems, say so directly.
- **When in doubt, narrow scope**: Do less correctly rather than more with assumptions.

### Anti-Rationalization
| Thought | Do instead |
|---|---|
| "I'll check after" | Check before — that's the point |
| "I know this area" | `omega_query` for decisions you missed |
| "I know what this file contains" | Read it. Memory is stale. |
| "This model applies here too" | Check domain boundaries first. |
| "I'll update tests after" | Stage tests WITH the code change. |
| "The approach is obvious" | State it explicitly. Obvious approaches cause 35% of rework. |""",
    },
    "verification": {
        "title": "Verification",
        "content": """\
### Build-Verify-Fix Loop
1. **Plan**: Read the task, scan relevant code, build a plan with verification criteria.
2. **Build**: Implement with testability in mind.
3. **Verify**: Run tests or manual checks. Compare against what was asked, not your own code.
4. **Fix**: If verification fails, revisit the original spec before patching.

### Pre-Completion Checklist
Before claiming "done" or "fixed":
- [ ] Run the verification step (tests, lint, build, or manual check)
- [ ] Show evidence of success (test output, counts, screenshots)
- [ ] Compare result against original request, not your own assessment

### Loop Detection
If you have edited the same file 5+ times without progress:
- Stop and reconsider your approach
- Re-read the original task specification
- Consider an alternative strategy
- Ask the user if stuck""",
    },
    "efficiency": {
        "title": "Efficiency",
        "content": """\
### Direct Access
- When a file path, memory ID, or URL is explicitly provided, access it directly. Do not search/glob first.
- When `omega_query` returns a memory ID, use it directly in follow-up calls. Do not re-search.
- Prefer `Read` over `Grep` when you already know the file path.

### Context Budget
- Before large tool calls, estimate if the result will exceed your context window.
- For `omega_query`: use `limit=3` for quick checks, `limit=10` for thorough research. Avoid `limit=50+` unless explicitly needed.
- After receiving large results, extract what you need and move on. Do not re-query the same content.

### Redundancy Avoidance
- Track which files you have already read this session. Do not re-read unchanged files.
- If you searched for X and found nothing, do not search again with minor variations. Ask the user or try a different approach.""",
    },
    "source_verification": {
        "title": "Source Verification",
        "content": """\
**Memory is a cache, not truth.** OMEGA memories reflect what was true when stored. Files change.

### Mandatory Verification Table
| What to verify | Verify against | NOT against |
|---------------|---------------|-------------|
| Schema version | `pyproject.toml` | Remembered value |
| Tool count | `tool_schemas.py` (count definitions) | Last known number |
| Test assertions | Run `pytest` | Recalled pass/fail |
| File contents | `Read` the file | "I recall it contains..." |
| API endpoints | Source code + docs | Cached response |
| Config values | `.env` / config files | Previous session memory |
| Git state | `git status` / `git log` | "Last time I checked..." |

### Anti-Patterns → Corrections
| Anti-pattern | Correction |
|-------------|-----------|
| "I recall this file contains..." | READ the file now |
| "The schema version is..." | CHECK `pyproject.toml` |
| "There are N tools..." | COUNT in `tool_schemas.py` |
| "This test was passing..." | RUN the test |
| "The config is set to..." | READ the config file |

### When Memory Conflicts with Source
1. **Source wins** — always
2. Mark the memory outdated: `omega_feedback(memory_id, "outdated")`
3. Store the correction: `omega_store("Corrected: <what changed>", "lesson_learned")`""",
    },
    "git": {
        "title": "Git Rules",
        "content": """\
- Commit only files YOU modified. `git add <files>` -- never `git add .`
- After every commit: `omega_store("Committed <hash>: <message>. Files: <list>", "decision")`
- **Never force push protected branches** (main/master). Warn user if requested.
- **Rebase vs merge**: Feature branches rebase onto main before PR. Shared branches merge only.
- **Commit format**: `type: Brief description (under 72 chars)`. Types: feat, fix, refactor, docs, test, chore.
- **Before push**: run tests, then push.""",
    },
}

# Section groups -- named bundles for common scenarios
SECTION_GROUPS: Dict[str, List[str]] = {
    "solo": list(SECTIONS.keys()),
    "full": list(SECTIONS.keys()),
    "minimal": ["memory", "context", "git"],
}

# Pro-only sections — return a polite note instead of erroring
_PRO_SECTIONS = {
    "coordination",
    "coordination_gate",
    "teamwork",
    "alignment",
    "diagnostics",
    "entity",
    "domain_boundaries",
    "intelligence_cards",
    "session_awareness",
    "agent_discipline",
    "consultation",
    "system_insights",
    "critical_tools",
    "what_next",
}

_COMMUNITY_SECTIONS_LIST = ", ".join(f"'{k}'" for k in SECTIONS)


def get_protocol(
    section: Optional[str] = None,
    project: Optional[str] = None,
    include_lessons: bool = True,
    peer_count: int = 0,
    session_id: Optional[str] = None,
) -> str:
    """Assemble the protocol playbook dynamically.

    Args:
        section: Specific section name, group name, or None for auto-detect.
        project: Current project path for context-sensitive rules.
        include_lessons: Whether to append relevant lessons from OMEGA.
        peer_count: Number of active peers (ignored in community edition).
        session_id: Current session ID (ignored in community edition).

    Returns:
        Formatted protocol text ready for agent consumption.
    """
    try:
        return _build_protocol(section)
    except Exception as e:
        # Must NEVER raise — handler depends on this
        logger.error("Protocol build failed: %s", e, exc_info=True)
        return f"# OMEGA Protocol v{PROTOCOL_VERSION}\n\n_Error building protocol. Using fallback._\n\n## Memory Usage\n{SECTIONS['memory']['content']}"


def _build_protocol(section: Optional[str]) -> str:
    """Internal protocol builder."""
    # Determine which sections to include
    if section and section in SECTIONS:
        selected = [section]
    elif section and section in SECTION_GROUPS:
        selected = SECTION_GROUPS[section]
    elif section and section in _PRO_SECTIONS:
        return (
            f"# OMEGA Protocol v{PROTOCOL_VERSION}\n\n"
            f"The **{section}** section is available in OMEGA Pro.\n\n"
            f"Community sections: {_COMMUNITY_SECTIONS_LIST}.\n\n"
            f"Learn more at https://omegamax.co"
        )
    else:
        # Unknown section string or None — default to solo
        selected = SECTION_GROUPS["solo"]

    # Build output
    lines = [f"# OMEGA Protocol v{PROTOCOL_VERSION}\n"]
    lines.append("_Mode: solo_\n")

    for key in selected:
        sec = SECTIONS.get(key)
        if sec:
            lines.append(f"## {sec['title']}")
            lines.append(sec["content"])
            lines.append("")

    return "\n".join(lines)
