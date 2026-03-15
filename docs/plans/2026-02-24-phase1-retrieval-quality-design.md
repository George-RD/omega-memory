# Phase 1: Retrieval Quality -- Design Document

> **Date:** 2026-02-24
> **Status:** Approved
> **Scope:** Focused (surface and connect existing capabilities)
> **Execution:** 3 parallel agent worktrees

## Context

OMEGA's retrieval pipeline is already sophisticated (7-phase RRF fusion, temporal decay, spreading activation, 36 event type weights, feedback scoring, Thompson sampling). Phase 1 surfaces hidden scores, adds memory type classification, and wires the entity graph into retrieval. No new dependencies.

Based on SOTA research report (`docs/research/2026-02-24-sota-agent-memory.md`).

---

## Architecture: 3 Independent Agent Worktrees

| Agent | Branch | Primary Files | Scope |
|-------|--------|--------------|-------|
| Agent 1: Strength | `phase1/strength-surfacing` | `sqlite_store.py`, `bridge.py`, `handlers.py`, `tool_schemas.py` | Surface composite strength score in query results |
| Agent 2: Memory Types | `phase1/memory-types` | `schema.py`, `sqlite_store.py`, `bridge.py`, `handlers.py`, `tool_schemas.py` | Add memory_type enum, auto-classify, filter |
| Agent 3: Entity Graph | `phase1/entity-graph-retrieval` | `sqlite_store.py`, `entity/engine.py` | Wire entity relationships into retrieval scoring |

**Merge strategy:** Agents 1 and 2 both touch overlapping files but different code paths (query output vs. store input). Agent 3 only touches scoring internals. Sequential merge: Agent 3 first (most isolated), then Agent 1, then Agent 2.

---

## Agent 1: Strength Surfacing

### Problem
Decay factor, feedback factor, type weight, and Thompson boost are all computed during query but the composite score is discarded. Results return with a `relevance` field that only captures RRF rank position, not the full signal.

### Existing Code
- `_compute_decay_factor()` at `sqlite_store.py:4209`
- `_compute_fb_factor()` at `sqlite_store.py:4244`
- `_TYPE_WEIGHTS` at `sqlite_store.py:279`
- `_get_thompson_boost()` at `sqlite_store.py:4256`
- `MemoryResult.__slots__` at `sqlite_store.py:190` (has `relevance`, no `strength`)

### Changes

1. **MemoryResult**: Add `strength` to `__slots__` (float, 0.0-1.0)
2. **Scoring pipeline**: After RRF fusion, compute `strength = rrf_score * decay * feedback * type_weight` normalized to [0,1]. Attach to each MemoryResult.
3. **bridge.query()**: Include strength in markdown output (e.g., strength indicator after memory ID)
4. **bridge.query_structured()**: Include `strength` key in returned dicts
5. **tool_schemas.py**: Add optional `strength_min` (float, 0.0-1.0) param to `omega_query`
6. **handlers.py**: Pass `strength_min` through to bridge, filter results below threshold

### No schema changes. Pure compute + output wiring.

### Tests
- Unit: `_compute_strength()` returns expected values for known inputs
- Integration: `omega_query` with `strength_min=0.5` filters weak results
- Regression: existing query tests still pass (strength is additive, not breaking)

---

## Agent 2: Memory Type Classification

### Problem
36 event types exist but no higher-level grouping. Cognitive science taxonomy (episodic/semantic/procedural) is now standard across competitors. OMEGA's `omega_lessons` is proto-procedural but not formalized.

### Existing Code
- `_TYPE_WEIGHTS` dict at `sqlite_store.py:279` (36 event types)
- `event_type` stored in metadata JSON
- No `memory_type` column in schema

### Changes

1. **schema.py**: Add `memory_type TEXT DEFAULT 'semantic'` column to `memories` table. Migration: `ALTER TABLE memories ADD COLUMN memory_type TEXT DEFAULT 'semantic'`

2. **sqlite_store.py**: Define `_MEMORY_TYPE_MAP`:
   ```
   episodic: session_summary, task_completion, coordination_snapshot,
             session_respawn, merge_claim, merge_release, file_claimed,
             file_released, branch_claimed, branch_released, code_chunk,
             file_summary, file_conflict
   semantic: decision, constraint, user_preference, error_pattern,
             sota_research, research_report, benchmark_update,
             entity_profile_update, public_statement, outcome_resolution,
             contradiction_detected, sota_scan, preference_generated,
             advisor_action_outcome
   procedural: lesson_learned, reflexion, self_reflection,
               outcome_evaluation, reminder
   ```
   Default (unmapped types): `semantic`

3. **Store path**: On `omega_store`, auto-classify `memory_type` from `event_type` using the map. One dict lookup, zero LLM calls.

4. **tool_schemas.py**: Add optional `memory_type` enum param to `omega_query` (episodic/semantic/procedural)

5. **handlers.py/bridge.py**: Pass `memory_type` filter through to query. Add WHERE clause.

6. **Migration**: Backfill existing memories:
   ```sql
   UPDATE memories SET memory_type = 'episodic'
   WHERE json_extract(metadata, '$.event_type') IN ('session_summary', ...);
   UPDATE memories SET memory_type = 'procedural'
   WHERE json_extract(metadata, '$.event_type') IN ('lesson_learned', ...);
   -- Remaining stay 'semantic' (the default)
   ```

### Tests
- Unit: `_MEMORY_TYPE_MAP` covers all 36 event types
- Integration: store with event_type='decision' gets memory_type='semantic'
- Integration: query with memory_type='procedural' returns only procedural memories
- Migration: backfill correctly classifies existing memories

---

## Agent 3: Entity Graph Integration

### Problem
Entity relationships exist (`entity/engine.py`: 7 relationship types, `get_relationships()`) but are completely isolated from memory retrieval. The `entity_id` column on memories is used only for hard filtering, not scoring.

### Existing Code
- `entity/engine.py:get_relationships()` at line 367
- `sqlite_store.py:get_related_chain()` at line 3384 (memory-edge graph, NOT entity graph)
- `entity_id` column on memories table (used for WHERE filtering only)
- `_rrf_fuse()` at `sqlite_store.py:4037` (multi-channel fusion)

### Changes

1. **sqlite_store.py**: New method `_get_entity_related_memories()`:
   - Input: set of entity_ids from initial results
   - For each entity_id, call entity engine's `get_relationships()` to find related entities
   - Query memories with those related entity_ids
   - Return as ranked list (entity proximity as score: direct=1.0, one-hop=0.5)

2. **Scoring pipeline**: After initial RRF fusion, if any results have `entity_id`:
   - Call `_get_entity_related_memories()` to get entity-graph-related memories
   - Add as a new RRF channel with weight 0.3
   - Re-fuse with existing results

3. **entity/engine.py**: Add `get_related_entity_ids(entity_id, max_hops=1)` that returns just IDs (lightweight, no formatting). The existing `get_relationships()` returns formatted strings; we need raw IDs for programmatic use.

### No schema changes. Wiring between two existing systems.

### Tests
- Unit: `_get_entity_related_memories()` returns memories from related entities
- Unit: `get_related_entity_ids()` returns correct IDs for known relationships
- Integration: query about entity X surfaces memories from related entity Y
- Edge case: entity with no relationships returns unchanged results

---

## Merge Order

1. **Agent 3** (entity graph) -- most isolated, only touches scoring internals
2. **Agent 1** (strength) -- touches query output path
3. **Agent 2** (memory types) -- touches store input path + adds schema migration

After all three merge, run full test suite (`pytest -x`) to verify no regressions.

---

## Success Criteria

- [ ] `omega_query` results include `strength` score (0.0-1.0)
- [ ] `omega_query` supports `strength_min` filter
- [ ] `omega_query` supports `memory_type` filter (episodic/semantic/procedural)
- [ ] `omega_store` auto-classifies `memory_type` from `event_type`
- [ ] Existing memories backfilled with correct `memory_type`
- [ ] Entity relationships influence retrieval scoring
- [ ] All existing tests pass
- [ ] Each agent adds tests for its changes
