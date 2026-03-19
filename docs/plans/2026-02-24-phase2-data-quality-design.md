# Phase 2: Data Quality -- Design Document

> **Date:** 2026-02-24
> **Status:** Approved
> **Scope:** Full (surface contradictions + bi-temporal + sleep-time consolidation)
> **Execution:** 3 parallel agent worktrees

## Context

OMEGA already has sophisticated data quality infrastructure: contradiction detection with 4 signal types, temporal supersession, mark_superseded(), forgetting audit trail, and a multi-phase consolidation pipeline. Phase 2 surfaces hidden contradiction results, adds bi-temporal fact validity tracking, and enhances maintenance with strength decay and entity deduplication. No new dependencies.

Based on SOTA research report (`docs/research/2026-02-24-sota-agent-memory.md`), Phase 2 items #4-6.

---

## Architecture: 3 Independent Agent Worktrees

| Agent | Branch | Primary Files | Scope |
|-------|--------|--------------|-------|
| Agent 1: Contradiction Surfacing | `phase2/contradiction-surfacing` | `sqlite_store.py`, `bridge.py`, `handlers.py`, `tool_schemas.py` | Surface contradiction results in store response, add query filter |
| Agent 2: Bi-Temporal | `phase2/bi-temporal` | `schema.py`, `sqlite_store.py`, `bridge.py`, `handlers.py`, `tool_schemas.py` | Add valid_from/valid_until columns, temporal queries |
| Agent 3: Sleep-Time Consolidation | `phase2/sleep-time-consolidation` | `sqlite_store.py`, `bridge.py`, `entity/engine.py` | Strength decay pruning, entity deduplication in maintain |

**Merge strategy:** Agent 1 first (most isolated, output wiring), Agent 3 second (internal maintain changes), Agent 2 last (schema migration + query changes).

---

## Agent 1: Contradiction Surfacing

### Problem
`_check_contradictions()` runs post-store and annotates metadata silently. The agent never sees the result. Contradictions are invisible unless someone queries a specific node ID and reads its metadata.

### Existing Code
- `contradictions.py` (368 lines): 4 signal types (negation, antonym, preference change, temporal override)
- `_check_contradictions()` at `sqlite_store.py:4427`: annotates both sides, creates edges, returns None
- `mark_superseded()` at `sqlite_store.py:3960`: temporal supersession
- Decision trail surfacing in `handlers.py:237-275`: same pattern we'll follow

### Changes

1. **`sqlite_store.py`**: Change `_check_contradictions()` return type from `-> None` to `-> List[dict]`. Return contradiction results (node_id, confidence, reason, content snippet) instead of discarding them. The method already has all the data.

2. **`sqlite_store.py`**: Change `store()` to capture the return value from `_check_contradictions()`. Return type becomes a tuple: `(node_id, contradictions)` where contradictions is a list of dicts (empty if none found). Callers that only need node_id can index `[0]`.

3. **`bridge.py`**: `store()` captures contradictions from the store call. Appends a `[CONTRADICTION]` block to the response string when contradictions are found:
   ```
   [CONTRADICTION] New memory contradicts existing:
   - mem-abc123 (confidence: 0.78): Preference value changed
   ```

4. **`tool_schemas.py`**: Add optional `include_contradicted` boolean param to `omega_query`.

5. **`handlers.py`**: Pass `include_contradicted` through to bridge query.

6. **`sqlite_store.py` query path**: When `include_contradicted=True`, filter to only return memories that have `contradicted_by` in their metadata JSON. Enables data quality auditing.

### No schema changes. Pure output wiring + query filter.

### Tests
- Unit: `_check_contradictions()` returns list of dicts with expected fields
- Integration: `omega_store` of contradicting content includes `[CONTRADICTION]` in response
- Integration: `omega_query` with `include_contradicted=True` returns only contradicted memories
- Regression: existing store/query tests still pass (contradiction info is additive)

---

## Agent 2: Bi-Temporal Data Model

### Problem
Memories have `created_at` (when stored) but no way to express "this fact was true from X to Y." Can't answer "what did we know about X before session Y?" or track how facts change over time. Zep's bi-temporal model is their strongest differentiator; no MCP system has this.

### Existing Code
- `created_at` -- immutable creation timestamp
- `referenced_date` -- user-supplied reference date (rarely used)
- `end_date` -- added in v8, optional
- `mark_superseded()` at `sqlite_store.py:3960`: sets `superseded_at` in metadata (not a column)
- Schema version: 11

### Changes

1. **`schema.py`**: v11->v12 migration. Add two columns:
   - `valid_from TEXT` -- when this fact became true (defaults to `created_at`)
   - `valid_until TEXT` -- when this fact stopped being true (NULL = still valid)
   - Backfill existing rows:
     ```sql
     UPDATE memories SET valid_from = COALESCE(referenced_date, created_at);
     UPDATE memories SET valid_until = json_extract(metadata, '$.superseded_at')
       WHERE json_extract(metadata, '$.superseded') = 1;
     ```
   - Add index on `valid_from`, `valid_until`

2. **`sqlite_store.py` store path**: On `store()`, set `valid_from` to `referenced_date` if provided, else `created_at`. `valid_until` stays NULL (fact is current).

3. **`sqlite_store.py` supersession path**: When `mark_superseded()` is called, also set `valid_until = NOW` on the superseded memory. Supersession now has a column-level signal, not just metadata.

4. **`sqlite_store.py` query path**: When `valid_at` param is provided (ISO timestamp), add WHERE clause: `valid_from <= ? AND (valid_until IS NULL OR valid_until > ?)`. Answers "what was true at time X?"

5. **`tool_schemas.py`**: Add optional `valid_at` (ISO datetime string) param to `omega_query`.

6. **`handlers.py` / `bridge.py`**: Pass `valid_at` through to query.

7. **`MemoryResult`**: Add `valid_from` and `valid_until` to `__slots__`. Include in `query_structured()` output.

### Tests
- Unit: v11->v12 migration adds columns and backfills correctly
- Unit: store with `referenced_date` sets `valid_from` to that date
- Unit: `mark_superseded()` sets `valid_until` column
- Integration: query with `valid_at` returns only temporally valid memories
- Integration: superseded memory excluded by `valid_at` filter
- Regression: existing query tests still pass (valid_at is optional)

---

## Agent 3: Sleep-Time Consolidation

### Problem
`consolidate()` prunes stale memories (hard delete) and `compact()` clusters and summarizes, but neither applies strength decay or merges duplicate entities. Maintenance removes data but doesn't create intelligence.

### Existing Code
- `consolidate()` at `sqlite_store.py:2838`: 4-phase pruning (decisions, stale, summary cap, orphans)
- `compact()` at `bridge.py:3135`: semantic clustering + summarization
- Strength score (Phase 1): computed at query time from `rrf_score * type_weight * feedback * decay`
- Entity engine with `get_related_entity_ids()` (Phase 1)
- `_compute_decay_factor()` at `sqlite_store.py:4209`
- `_compute_fb_factor()` at `sqlite_store.py:4244`
- `_TYPE_WEIGHTS` at `sqlite_store.py:279`

### Changes

1. **`sqlite_store.py`**: New method `apply_strength_decay()`:
   - Iterate all non-protected, non-superseded memories
   - Compute current strength: `type_weight * feedback_factor * decay_factor` (same formula as query-time)
   - Memories with strength below threshold (0.05) that haven't been accessed in 30+ days: mark superseded with reason `"strength_decay"`
   - Log to forgetting audit trail via `_log_forgetting()`
   - Return count of decayed memories
   - This implements the ACT-R "forgetting curve": unused, low-value memories fade

2. **`sqlite_store.py`**: New method `merge_duplicate_entities()`:
   - Query entity engine for all entities via `get_all_entities()` (add to engine if missing)
   - Compare entity names via string similarity (normalized Levenshtein or exact lowercased match)
   - If match found: transfer all memories from duplicate entity_id to primary, merge relationship edges, remove duplicate entity
   - Return count of merged entities
   - Handles entity drift (e.g., "OMEGA project" vs "omega" vs "OMEGA")

3. **`sqlite_store.py` consolidate()**: Add Phase 5: `apply_strength_decay()` and Phase 6: `merge_duplicate_entities()` after existing 4 phases. Stats dict gets `decayed_memories` and `merged_entities` keys.

4. **`bridge.py` consolidate()**: Return new stats from consolidation.

### No schema changes. No new tools. Enhances existing maintain pipeline.

### Tests
- Unit: `apply_strength_decay()` marks low-strength old memories as superseded
- Unit: `apply_strength_decay()` preserves protected types
- Unit: `apply_strength_decay()` preserves recently accessed memories
- Unit: `merge_duplicate_entities()` merges entities with similar names
- Unit: `merge_duplicate_entities()` transfers memories to primary entity
- Integration: `consolidate()` returns stats including `decayed_memories` and `merged_entities`
- Edge case: empty database returns zero counts

---

## Merge Order

1. **Agent 1** (contradiction surfacing) -- most isolated, mainly output wiring
2. **Agent 3** (sleep-time consolidation) -- internal maintain changes only
3. **Agent 2** (bi-temporal) -- schema migration + query changes, most overlap potential

After all three merge, run full test suite (`pytest -x`) to verify no regressions.

---

## Success Criteria

- [ ] `omega_store` response includes `[CONTRADICTION]` block when contradictions detected
- [ ] `omega_query` supports `include_contradicted` filter
- [ ] `omega_query` supports `valid_at` temporal filter ("what was true at time X?")
- [ ] `mark_superseded()` sets `valid_until` column
- [ ] Schema v12 with `valid_from`/`valid_until` columns, backfilled
- [ ] `consolidate()` applies strength decay (marks weakest memories as superseded)
- [ ] `consolidate()` merges duplicate entities
- [ ] All existing tests pass
- [ ] Each agent adds tests for its changes
