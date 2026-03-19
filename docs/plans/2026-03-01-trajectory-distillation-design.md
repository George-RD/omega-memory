# Trajectory-to-Skill Distillation

**Date**: 2026-03-01
**Status**: Approved
**Origin**: Paper review of "Memory in the Age of AI Agents" (arxiv 2512.13564)

## Problem

OMEGA captures factual and episodic memories but does not systematically extract **experiential/procedural knowledge** from successful agent sessions. When an agent debugs a bug through a multi-step process, the individual memories (error_pattern, decision, task_completion) are stored but the *workflow pattern* is lost. Future sessions facing similar tasks start from scratch instead of leveraging proven approaches.

The research paper identifies this as the gap between "case-based" memory (raw trajectories) and "strategy-based" memory (abstracted, reusable workflows). OMEGA currently operates at the case level; this design adds the strategy level.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Resolution | Memory-event level | Zero new capture infra. Distill from existing memories + coord_audit tool names. |
| Trigger | Session stop hook | Full trajectory available. Skills ready for next session. |
| Surfacing | Protocol injection | Automatic, contextual, familiar UX via `_get_relevant_skills()`. |
| Quality gate | Outcome-based | Only distill sessions with task_completion or git commit + >= 3 memories. |
| Approach | LLM-distilled (Haiku) | Semantic extraction justifies ~$0.003/session cost. Heuristics can't capture *why*. |

## Data Model

New event type `skill_template` stored as a regular `memories` row.

```python
# Event type config
_MEMORY_TYPE_MAP["skill_template"] = "procedural"
_TYPE_WEIGHTS["skill_template"] = 2.0      # same tier as lesson_learned
_DECAY_LAMBDAS["skill_template"] = 0.01    # ~50% at 69 days
TTLCategory.SKILL_TEMPLATE = None           # permanent (decay handles pruning)
_EVOLUTION_TYPES.add("skill_template")      # Zettelkasten in-place update
```

Metadata structure:

```json
{
    "source": "trajectory_distillation",
    "session_id": "<source_session>",
    "skill_type": "debugging|feature|refactor|config|deploy",
    "steps": ["verb_phrase_1", "verb_phrase_2"],
    "tools_used": ["Grep", "Read", "Edit", "Bash"],
    "files_involved": ["src/auth.py"],
    "key_insight": "Actionable advice from this session",
    "outcome": "success|partial|failed_then_recovered",
    "session_duration_minutes": 12,
    "memory_count": 7,
    "distillation_model": "haiku"
}
```

No schema migration required.

## Distillation Pipeline

Runs inside `handle_session_stop()` after existing summary/handoff logic.

```
Session stop
  ├─ existing: session_summary, coord_snapshot, coord_handoff
  └─ NEW: distill_trajectory(session_id)
       ├─ Step 1: Quality gate (>= 3 memories + completion/commit)
       ├─ Step 2: Gather context (memories, coord_audit tools, intents, task)
       ├─ Step 3: LLM call (Haiku, 10s timeout, fail-open)
       ├─ Step 4: Dedup (cosine >= 0.85 → evolve existing; else new)
       └─ Step 5: Store as skill_template via auto_capture()
```

LLM extraction prompt requests structured JSON with skill_type, summary (imperative form), steps (3-7 abstract verb phrases), key_insight, tools_used, files_involved, and outcome. Includes a `{"skip": true}` escape for routine sessions.

Fail-open: LLM timeout, malformed JSON, or gate failure all log a warning and skip. Session stop never blocks on distillation.

## Protocol Surfacing

New `_get_relevant_skills(task_description)` in `protocol.py`:

1. Embed task description
2. Query `skill_template` memories by embedding similarity > 0.65
3. Exclude skills from current session
4. Return top 2, formatted as:

```
[SKILLS] Prior successful approaches:
- debugging/null-check (2 days ago):
  detect_error -> read_context -> identify_root_cause -> apply_fix -> verify -> commit
  Files: src/auth.py | Insight: always validate optional fields at boundaries
```

Thompson sampling applies to `skill_template` like any other type, creating a reinforcement loop: retrieved skills that lead to successful sessions get boosted.

## Evolution & Lifecycle

- **Zettelkasten**: Similar future skills (0.65 <= Jaccard < 0.85) evolve existing templates in-place
- **ACT-R decay**: lambda=0.01, unretrieved skills decay to soft-delete over ~150 days
- **Cross-project**: Skills stored with project scope, retrieved by embedding similarity across projects
- **Feedback loop**: Successful retrieval → Thompson boost → more retrieval → skill persists

## Files Changed

| File | Change |
|---|---|
| `src/omega/sqlite_store/_base.py` | Add skill_template to type maps, weights, decay, TTL |
| `src/omega/bridge.py` | Add to EVOLUTION_TYPES, add `distill_trajectory()` method |
| `src/omega/hook_server/session.py` | Call distill_trajectory() in handle_session_stop() |
| `src/omega/protocol.py` | Add `_get_relevant_skills()`, wire into protocol output |
| `tests/` | New distillation tests + update hardcoded counts |

Estimated: ~150-200 new lines across 4 files, plus tests. No new dependencies.

## Success Criteria

1. Sessions with task_completion/commit produce a skill_template memory
2. Skill templates surface in protocol when future sessions have matching tasks
3. No measurable increase in session stop latency beyond 5s (LLM timeout cap)
4. Skill templates evolve when similar sessions recur (evolution_count > 1)
5. Unused skills naturally decay and get pruned

## Future Extensions (Not In Scope)

- Phase 2: Store tool_input in coord_audit for fine-grained trajectory replay
- Phase 2: Dedicated `omega_skills(task)` MCP tool for on-demand skill search
- Phase 2: Admin dashboard tab showing skill inventory and usage stats
- Phase 3: RL-driven store/skip bandit for memory formation decisions
