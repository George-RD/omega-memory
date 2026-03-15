# OMEGA Utilization Gap Fixes — Design Spec (Expanded)

**Date**: 2026-03-14
**Status**: Draft (v2 — expanded with 3 feedback loops)
**Approach**: Hybrid — hooks for mechanical tasks, protocol for judgment calls

## Problem

OMEGA has ~25 tools but agents actively use ~40% of capabilities. The advanced intelligence layer — graph traversal, reflection, cross-model consultation, and proactive checkpointing — is nearly dormant. Additionally, there are no automated feedback loops that close the quality gap between storing and retrieving memories. Key stats (30-day window, 47 sessions):

- `omega_reflect`: 0 calls (auto-reflect at session stop partially compensates)
- `omega_checkpoint`: 0 explicit agent calls (sessions average 275 tool calls)
- `omega_memory` graph ops (traverse/link/similar): 4 calls total
- `omega_consult_gpt/claude`: 0 calls
- `omega_profile`: 0 calls
- 21 dead memories (never accessed, 14+ days old)
- 28 behavioral patterns inferred, 0 confirmed/denied
- 232 `advisor_insight` entries (30% of all memories, potential near-dupes)
- 0 automated retrieval quality signal (strength decay flies blind)
- 0 procedural learnings auto-extracted (session summaries capture "what" not "what worked")
- Context push only at welcome — agents go amnesic after 50+ tool calls

## Design

### Layer 1: Hook-Enforced (Mechanical)

These are tasks agents forget but should always happen.

#### 1.1 Enhance Auto-Checkpoint at Session Stop

**File**: `src/omega/server/hook_server/session.py` (in `handle_session_stop()`, ~line 1707)

**Status**: Trigger logic already implemented (lines 1707-1754). The `captured >= 3 OR tool_calls >= 30` trigger and skip-if-already-checkpointed logic are live.

**Remaining work**: Enrich checkpoint content with:
  - `files_touched`: Extract from `coord_audit` entries for this session where `tool_name` is Edit/Write (file paths parseable from `result_summary`)
  - `next_steps`: Pull from last handoff content if available (query `event_type='handoff'` for this session)

**Why auto, not nudge**: Checkpoints at session end capture context that's about to be lost. Nudging at 70% context relies on agent awareness of context usage, which is unreliable. Auto-save guarantees continuity.

#### 1.2 Auto-Reflect Stale — Welcome Surfacing

**File**: `src/omega/server/hook_server/session.py` (welcome briefing)

**Status**: Maintenance pipeline stage already implemented. `_do_reflect_stale()` in `maintenance.py` (lines 557-588) calls `find_stale()` directly and stores results as `advisor_insight` with `source=auto_reflect_stale`. Registered in `build_session_start_pipeline()` (lines 659-665) with 7-day interval.

**Remaining work**: Surface the stored stale memory insights in the welcome briefing. Query `advisor_insight` memories with `source=auto_reflect_stale`, show top 3 in a "Stale memories to review" heading with memory ID and content preview.

#### 1.3 Habit Confirmation Prompt

**File**: `src/omega/server/hook_server/session.py` (welcome briefing)

Currently habits are displayed as a read-only table. Add actionable prompt:

- After the habits table, append:
  ```
  **Action needed**: Confirm or deny these patterns to improve predictions:
  - Confirm: `omega_stats(action='habits_confirm', pattern_id='<id>')`
  - Deny: `omega_stats(action='habits_deny', pattern_id='<id>')`
  ```
- **Gate**: Only show if 3+ unconfirmed habits exist (avoid noise for new users)
- **Prerequisite**: The `[PATTERNS]` welcome block must surface pattern `node_id` values (currently shows only truncated content). Add memory IDs to the habits table output so the confirmation prompt is actionable.

#### 1.4 ~~Verify advisor_insight in Compact Pipeline~~

**Status**: Verified — already implemented. `advisor_insight` is already the first entry in the compact pipeline's `event_types` tuple (`maintenance.py` line 472). No change needed.

#### 1.5 Dead Memory Surfacing

**File**: `src/omega/server/hook_server/session.py` (welcome briefing)

In the welcome briefing, after "Recent Activity":

- Query memories with `access_count=0` and age > 14 days (use existing store query methods)
- If any exist, surface top 3:
  ```
  **Dead memories (never accessed, 14+ days old)** — review or delete:
  - `mem-abc123`: [first 80 chars of content]...
  - `mem-def456`: [first 80 chars of content]...
  ```
- Include count of total dead memories if > 3 shown

#### 1.6 Retrieval Quality Feedback (Session-Stop)

**File**: `src/omega/server/hook_server/session.py` (in `handle_session_stop()`, after the auto-checkpoint block ~line 1755)

Closes the biggest open loop: 800+ memories stored, no signal on which are useful when retrieved. Strength decay has no quality input.

**Mechanism**: New function `_auto_feedback_on_retrieval(session_id)`:

1. Query `coord_audit` for all tool calls in this session via `CoordinationManager.query_audit(session_id=session_id)`. **Important**: `query_audit()` returns rows `ORDER BY created_at DESC` (newest first). The implementation must re-sort results by `call_index ASC` before processing to ensure chronological order.
2. Filter to rows where `tool_name` contains `omega_query`. Extract memory IDs from their `result_summary` via regex `r"mem-[a-f0-9]{12}"`. IDs are 16 chars each. Due to 200-char `result_summary` truncation, typically only 1-3 IDs are visible per query (formatted markdown with headers/content consumes most of the 200 chars). This is acceptable: top-ranked results appear first and are most valuable to track.
3. For each retrieved memory ID, scan subsequent entries (higher `call_index`) for references to that ID in `result_summary` only. **Note**: The `arguments` column is always NULL in trace captures (`trace.py` line 63 passes `arguments=None`), so it cannot be used as a signal source.
4. Score using `record_feedback(memory_id, rating, reason)` where `rating` is a string enum:
   - **Used after retrieval** (ID appears in later `result_summary`) → `record_feedback(memory_id, "helpful", "retrieval_used")`
   - **Retrieved but never referenced** → No negative feedback recorded. The absence-of-use signal is too unreliable given the `result_summary` truncation — a memory could be used without its ID reappearing in trace output. Positive-only feedback avoids penalizing useful memories. Over time, memories that are never marked "helpful" will decay naturally via ACT-R.

**Feedback API**: `record_feedback()` in `bridge.py` accepts `rating: str` — one of `"helpful"` (+1 score delta), `"unhelpful"` (-1), or `"outdated"` (-2). Numeric values are not accepted and will silently no-op via the `.get(rating, 0)` fallback.

**Data source**: `coord_audit` table via `CoordinationManager.query_audit(session_id=session_id)`. Already indexed on `session_id`.

**Relationship to existing `_auto_feedback_on_surfaced`**: No overlap. `_auto_feedback_on_surfaced` covers *edit-time hook surfaced* memories (file → memory correlation via `surfaced.json`). This covers *agent-initiated queries* — a different signal path.

#### 1.7 Cross-Session Learning Extraction (Session-Stop)

**File**: `src/omega/server/hook_server/session.py` (in `handle_session_stop()`, after `_auto_feedback_on_retrieval()`, both placed after the auto-checkpoint block ~line 1755)

Session summaries capture *what* happened but not *what worked*. No procedural memories accumulate automatically.

**Mechanism**: New function `_extract_procedural_learnings(session_id)`:

1. Query `coord_audit` for this session's tool calls via `CoordinationManager.query_audit(session_id=session_id)`. **Important**: `query_audit()` returns rows `ORDER BY created_at DESC`. Re-sort by `call_index ASC` before pattern detection.
2. Detect **recovery patterns**: `result_status = 'error'` followed within 10 calls by `result_status = 'ok'` **on the same tool_name**. **Note**: `coord_audit` stores `tool_name` reliably but does not store tool input content (only `input_size`). "Same file" detection is not feasible from `coord_audit` alone. Instead, match on `tool_name` — e.g., repeated `Bash` errors followed by `Bash` success, or `Edit` errors followed by `Edit` success. This is coarser than file-level matching but still captures meaningful patterns like "pytest kept failing until approach changed" or "edit kept erroring until correct syntax found."
3. Detect **stuck patterns**: Same `tool_name` called 5+ times consecutively with `result_status = 'error'`
4. Store via `auto_capture()`:
   - Recovery: `"Approach that worked: [tool_name] error resolved after [N] attempts. Error context: [first error result_summary[:100]]. Success context: [success result_summary[:100]]"` → `event_type="lesson_learned"`, `metadata={"source": "auto_procedural", "polarity": "positive", "memory_type": "procedural"}`
   - Stuck: `"Anti-pattern: [tool_name] failed [N] consecutive times. Error: [last error result_summary[:100]]"` → `event_type="lesson_learned"`, `metadata={"source": "auto_procedural", "polarity": "negative", "memory_type": "procedural"}`

**Gates**:
- Only runs if session has 20+ tool calls (short sessions lack meaningful patterns)
- Max 3 learnings per session (avoid noise)
- Dedup via existing `auto_capture` Jaccard threshold (0.85 for `lesson_learned`)

**Quality control**: These are heuristic extractions — coarser than ideal since we match on `tool_name` not file path. ~50% accuracy expected. Good ones get accessed and strengthened via ACT-R decay; bad ones decay naturally. Loop 1.6 (retrieval feedback) provides additional quality signal when these learnings are later retrieved.

#### 1.8 Proactive Mid-Session Context Push (Pre-Tool Hook)

**File**: `src/omega/server/hook_server/insights.py` (extend `handle_pre_insight_surface()`)

Agents get context at welcome only. By tool call 200, the agent has forgotten relevant memories. The existing `pre_insight_surface` surfaces *system insights* during edits but not *general memories* relevant to the file being edited.

**Mechanism**: Add memory context push as a **separate code path** in `handle_pre_insight_surface()`. Insert **after the `_is_plan_file` guard (line 68-69), before the `tags = _tags_for_file(file_path)` call (line 72)**. This ensures:
- The `tool_name` check (Edit/Write only) and `file_path` extraction still gate the memory push (no false fires on Bash/Read)
- The memory push fires for ALL files, not just OMEGA-internal files with tag mappings
- The existing insight surfacing continues independently after the tags gate
- The function builds a combined response: memory context stored in a local variable; tags gate proceeds normally; both outputs concatenated at return

New import: `from omega.server.hook_server.trace import _call_counters` (new dependency — `insights.py` does not currently import from `trace.py`).

1. **Trigger**: Fires on `Edit`/`Write` tool calls (same tool_name check as existing, reused)
2. **Gate**: Only fires when `_call_counters.get(session_id, 0) >= 50` (early session has fresh welcome context) AND file hasn't been memory-pushed this session (tracked via `_session_memory_pushed: dict[str, set[str]]` — session_id → set of file paths, module-level dict)
3. **Query**: Semantic search via `query_structured(query_text=file_path, limit=9)` with `event_type=None` (no filter). **Note**: `query_structured` accepts only a single `event_type: Optional[str]`, not a list. To get results across three types, call without `event_type` and post-filter the returned list to `event_type IN ('lesson_learned', 'decision', 'error_pattern')`. Take top 3 after filtering. `query_structured` exists in `bridge.py` and accepts `query_text`, `limit`, `event_type`, `entity_id` params.
4. **Output**: Append `[MEMORY_CONTEXT]` block to hook response output:
   ```
   [MEMORY_CONTEXT] Relevant memories for this file:
   - mem-abc123: [first 100 chars]
   - mem-def456: [first 100 chars]
   ```
   If the existing insight surfacing also produces output, both blocks are concatenated (memory context first, then insights).
5. **Track surfaced IDs**: Append to existing `session-{id}.surfaced.json` so they flow into `_auto_feedback_on_surfaced` (existing) and `_auto_feedback_on_retrieval` (Loop 1.6).
6. **Cleanup**: `_session_memory_pushed` entries cleaned up via existing `cleanup_session()` pattern or size-bounded (max 50 sessions tracked).

**Performance**: Query adds ~50-100ms but fires once per file after 50+ calls. For a 275-call session editing 10 files: 10 extra queries total. Negligible.

**Difference from existing `pre_insight_surface`**:

| Dimension | Existing insights | New memory push |
|-----------|------------------|-----------------|
| What | `advisor_insight` type, tag-matched | `lesson_learned`/`decision`/`error_pattern`, file-path semantic search |
| When | Every 5 min per file | Once per file per session, after call 50 |
| Purpose | Warn about known gotchas | Remind of relevant context |
| Debounce | Time-based (300s) | Session-scoped (once per file) |

### Layer 2: Protocol-Enforced (Judgment Calls)

These require agent reasoning and context-dependent decisions.

#### 2.1 Graph Linking After Stores

**File**: `src/omega/protocol.py` (memory section)

Add after the "Always tag stores" bullet:

```
- **Build the graph**: After `omega_store` returns a memory ID, call
  `omega_memory(action="similar", memory_id=<id>)`. If similar memories exist
  (score > 0.7), call `omega_memory(action="link", memory_id=<id>,
  target_id=<similar_id>)` with appropriate edge_type:
  - `evolves`: Same topic, updated understanding
  - `related`: Cross-topic connection
  - `supersedes`: Replacement for outdated memory
  Skip for `session_summary` and `checkpoint` types (high volume, low link value).
```

**Why protocol, not hook**: Choosing edge types requires semantic understanding of the relationship. A hook can't determine if a memory "evolves" vs "supersedes" another.

#### 2.2 Enhance Existing Consultation Section

**File**: `src/omega/protocol.py` (existing `consultation` section, line 389)

**Status**: A `consultation` section already exists with DO/DON'T consult heuristics and usage tips. It already covers: stuck 10+ min, 3+ approaches, architecture decisions, debugging dead ends, domain gaps. The existing `_provider_consultation()` function dynamically adapts the section for different providers (GPT vs Claude).

**Do NOT add a separate `cross_model` section** — this would duplicate the existing `consultation` section and confuse agents with redundant guidance.

**Remaining work**: Add one bullet to the existing section's "Usage tips":
```
- Store the consultation result as a `decision` memory with
  metadata={"source": "cross_model_consult"} — this ensures the second opinion
  is retrievable in future sessions facing similar problems.
```

This is the only gap: the current section tells agents *when* to consult but not to *store* the result.

#### 2.3 Reflect Before Architecture Decisions

**File**: `src/omega/protocol.py` (coordination_gate section, HIGH-risk steps)

Add to HIGH-risk gate:

```
- For architecture/design decisions: also run
  `omega_reflect(action="evolution", topic=<domain>)` to see how understanding
  has changed. This prevents repeating abandoned approaches.
```

#### 2.4 Profile Read at Session Start

**File**: `src/omega/protocol.py` (memory section, first bullet)

Add as first bullet:

```
- **Load user profile**: Call `omega_profile()` at session start (after
  welcome/protocol) to load working style preferences. Update it when you learn
  new preferences: `omega_profile(action="update", update={"key": "value"})`.
```

### Layer 3: CLAUDE.md Reinforcement

**File**: `~/.claude/CLAUDE.md` (Core Rules section)

Add one bullet (checkpoint is already in protocol, so CLAUDE.md only reinforces graph linking):

```
- **Graph linking**: After `omega_store`, check `omega_memory(similar)` and link
  related memories. This turns flat storage into a knowledge graph.
```

Note: Checkpoint discipline at 30+ tool calls is already in protocol.py's `context` section. CLAUDE.md reinforcement is redundant — the auto-checkpoint enhancement (1.1) is the real fix.

## Scope

| Layer | File | Changes |
|-------|------|---------|
| Hook | `src/omega/server/hook_server/session.py` | Enrich auto-checkpoint content (1.1), stale memory welcome surfacing (1.2), habit confirmation prompt with IDs (1.3), dead memory surfacing (1.5), retrieval quality feedback (1.6), procedural learning extraction (1.7) (~200 lines) |
| Hook | `src/omega/server/hook_server/insights.py` | Mid-session memory context push (1.8) (~60 lines) |
| Protocol | `src/omega/protocol.py` | Enhance existing consultation section (2.2), graph linking (2.1), reflect before arch (2.3), profile loading (2.4) (~20 lines) |
| Config | `~/.claude/CLAUDE.md` | +1 bullet (graph linking) |

**Total**: 3 source files modified, 1 config file updated, ~280 lines of new code, 0 new files created.

## Testing

- **Auto-checkpoint**: Run a session with 30+ tool calls but <3 stores, verify checkpoint fires (new trigger). Run session with <30 tool calls and <3 stores, verify no auto-checkpoint. Run session where agent calls checkpoint manually, verify no duplicate auto-checkpoint.
- **Reflect stale**: Set marker to force trigger, verify stale memories surfaced in next welcome. Verify 7-day gate respects marker.
- **Habit confirmation**: Create 3+ unconfirmed habits, verify prompt appears in welcome with memory IDs. Verify prompt absent with <3 unconfirmed.
- **Dead memory surfacing**: Create memories, never access them, wait 14 days (or mock age), verify surfaced in welcome.
- **Protocol changes**: Verify `consultation` section includes "Store the consultation result" bullet. Run protocol with `section="memory"` and verify graph linking and profile instructions present. Verify `coordination_gate` section includes `omega_reflect(action="evolution")` instruction.
- **Retrieval feedback**: Seed `coord_audit` with `omega_query` entries containing known memory IDs in `result_summary`. Seed subsequent entries that reference those IDs. Run `_auto_feedback_on_retrieval()`. Verify `"helpful"` feedback recorded for referenced IDs. Verify no feedback recorded for unreferenced IDs (positive-only). Verify no feedback recorded for sessions with 0 `omega_query` calls.
- **Procedural learning**: Seed `coord_audit` with error→recovery sequence (same `tool_name` with `result_status='error'` followed by `result_status='ok'` within 10 calls). Run `_extract_procedural_learnings()`. Verify `lesson_learned` memory stored with `source=auto_procedural`. Verify no learnings extracted for sessions with <20 tool calls. Verify max 3 learnings per session. Verify stuck pattern detected when same `tool_name` has 5+ consecutive errors.
- **Mid-session context push**: Mock `_call_counters[session_id] = 60`. Call `handle_pre_insight_surface()` with an Edit payload for a file that has relevant memories. Verify `[MEMORY_CONTEXT]` block in output. Call again for same file, verify no duplicate push. Call with `_call_counters[session_id] = 10`, verify no push (below threshold).

## Risks

- **Auto-checkpoint quality**: Session-end checkpoints may have lower quality than agent-authored ones (less context about "why"). Mitigated by treating auto-checkpoints as fallback, not replacement.
- **Welcome briefing bloat**: Adding dead memories + habit prompts + stale memories could make welcome too long. Mitigated by gating (3+ habits, any dead memories) and limiting to top 3. **Ordering**: Stale memories appear in "Stale memories to review" section (after Recent Activity), dead memories in a separate "Dead memories" section, habit prompts inline after the existing `[PATTERNS]` block. No overlap — stale = low-access memories surfaced by `reflect_stale`, dead = zero-access memories surfaced by direct query.
- **Graph link noise**: Agents may over-link if threshold is too low. Starting at 0.7 similarity; can tune up if graph becomes noisy.
- **Maintenance pipeline latency**: Adding `reflect_stale` as a weekly stage adds DB scan time to session start. Expected <2s for 793 memories. The existing pipeline already tracks per-stage `elapsed_s` — monitor and gate if latency exceeds 5s.
- **Retrieval feedback is positive-only**: We only record `"helpful"` when a memory ID reappears after retrieval. No negative signal is recorded because `result_summary` truncation (200 chars) makes absence-of-reappearance unreliable — a memory could be useful without its ID showing up in subsequent trace. This means the loop is conservative: it strengthens good memories but doesn't actively weaken bad ones. Bad memories still decay via ACT-R (no access = strength drops over time).
- **Procedural learning noise**: ~50% accuracy expected from tool_name-level matching (coarser than file-level). Mitigated by: (a) max 3 per session cap, (b) Jaccard dedup prevents duplicates, (c) bad learnings decay naturally via ACT-R (never accessed → strength drops), (d) retrieval feedback (1.6) provides additional quality signal.
- **Mid-session query latency**: Adds ~50-100ms to Edit/Write hook calls. Mitigated by: fires once per file per session (not per edit), only after 50+ tool calls. For typical 275-call session editing 10 files: 10 extra queries total.

## Non-Goals

- Automating `consult_gpt` calls (requires agent judgment)
- Auto-confirming behavioral patterns (requires user input)
- Retyping the 13 generic `memory` type entries (one-time cleanup, not a system change)
- Memory ROI dashboard (diagnostic, not an operational loop — defer to later)
- Embedding freshness detection (model changes are infrequent — defer to later)
