# Phase 3: Automatic Entity Extraction -- Design Document

> **Date:** 2026-02-25
> **Status:** Approved
> **Scope:** Automatic entity extraction from conversations on store (#7 from research report)
> **Items #8 (feedback scoring) and #9 (procedural-as-instructions):** Already covered by Phase 1 or deferred as aspirational.

## Context

OMEGA's entity engine is 100% manual -- entities must be created explicitly via `omega_entity_create`. Every major competitor (Mem0, Zep, Cognee, A-Mem) extracts entities automatically on store. This is the single biggest practitioner-visible gap.

Phase 1 added entity graph traversal in retrieval. Phase 2 added entity deduplication in consolidation. Phase 3 closes the loop by populating the entity graph automatically.

Based on SOTA research report (`docs/research/2026-02-24-sota-agent-memory.md`), item #7.

---

## Architecture

On every `auto_capture()` call, after Phase 3 (store), fire an async background thread that:
1. Calls Claude Haiku to extract entities and relationships from memory content
2. Deduplicates against existing entities (lowercased name match)
3. Creates new entities or links the memory to existing ones
4. Creates relationship edges between co-mentioned entities

If `ANTHROPIC_API_KEY` is missing or the call fails, extraction is silently skipped. Zero impact on store reliability or latency.

---

## Components

### 1. Entity Extraction Module (`src/omega/entity/extraction.py`)

New file with two functions:

**`extract_entities(content, event_type) -> dict`**
- Calls Claude Haiku (`claude-haiku-4-5-20251001`) with a NER-tuned prompt
- Extracts: people, projects, tools, technologies, concepts, companies
- Returns `{"entities": [{"name": str, "type": str}], "relationships": [{"source": str, "target": str, "type": str}]}`
- Timeout: 3s. Returns empty dict on any failure.
- Template: `task_utils.py:summarize_task_text()` (existing Haiku + graceful fallback pattern)

**`resolve_and_link(store, em, node_id, extraction) -> dict`**
- For each extracted entity: check if lowercased name matches existing entity
- Match → link memory to existing entity_id
- No match → create new entity, link memory
- For each relationship: create edge if both entities resolve
- Returns `{"entities_created": int, "entities_linked": int, "relationships_created": int}`

### 2. Entity Type Extension (`src/omega/entity/engine.py`)

Add to `VALID_ENTITY_TYPES`: `person`, `project`, `tool`, `concept`, `technology`, `service`

No schema migration needed -- entity_type is a validated string, not a column constraint.

### 3. Relationship Type Extension (`src/omega/entity/engine.py`)

Add to `VALID_RELATIONSHIP_TYPES`: `uses`, `works_on`, `depends_on`, `mentions`, `created_by`

### 4. Async Hook in Bridge (`src/omega/bridge.py`)

New Phase 3.1 in `auto_capture()`, after Phase 3 (store), before Phase 4 (auto-relate):

```python
# Phase 3.1: Async entity extraction (non-blocking)
_schedule_entity_extraction(store, node_id, content, event_type)
```

Uses `threading.Thread(daemon=True)`. Store returns immediately. Extraction runs in background.

### 5. Rate Limiting / Cost Control

- **Skip low-value types:** `file_summary`, `code_chunk`, `branch_switch`, `session_respawn`, `session_summary`
- **Skip short content:** < 20 chars
- **Env toggle:** `OMEGA_ENTITY_EXTRACTION=0` to disable (default: enabled if `ANTHROPIC_API_KEY` present)
- **Throttle:** Max 1 extraction call per 2 seconds (prevents burst costs)

---

## Data Flow

```
auto_capture(content, event_type)
  → Phase 1-3 (existing pipeline, unchanged)
  → Phase 3.1: _schedule_entity_extraction()
      → [background thread]
      → extract_entities(content, event_type)     # Haiku call, 3s timeout
      → resolve_and_link(store, em, node_id, result)
          → find/create entities (lowercased name dedup)
          → UPDATE memories SET entity_id = ? WHERE node_id = ?
          → create relationship edges
  → Phase 4-5 (existing pipeline continues immediately, no wait)
```

---

## Error Handling

- **No API key:** Skip extraction silently, log at debug level
- **Haiku timeout/error:** Skip extraction, log at debug level
- **Rate limited:** Skip extraction for this call
- **Entity creation failure:** Skip that entity, continue with others
- **Thread crash:** Daemon thread, no impact on caller

---

## What This Does NOT Change

- No changes to `omega_query` or `omega_store` tool schemas
- No schema migration (entity tables already exist, types are string-validated)
- No LLM calls in the query path (extraction is store-side only)
- No changes to entity graph traversal (already in Phase 1)

---

## Tests

- Unit: Haiku extraction prompt returns expected format for sample content
- Unit: dedup correctly matches existing entities (case-insensitive)
- Unit: new entity/relationship types accepted by entity engine
- Unit: skip logic for low-value event types and short content
- Integration: `auto_capture()` of content mentioning entities creates them
- Integration: second store mentioning same entities links (no duplicates)
- Edge: empty content, no API key, Haiku timeout -- all degrade gracefully
- Edge: throttle skips extraction when called too frequently

---

## Success Criteria

- [ ] Storing "Jason deployed the React app to Vercel" auto-creates entities for Jason (person), React (technology), Vercel (service)
- [ ] Second store mentioning "React" links to existing entity, doesn't duplicate
- [ ] Relationships created between co-mentioned entities
- [ ] Store latency unchanged (extraction is async)
- [ ] No failures when ANTHROPIC_API_KEY is missing
- [ ] All existing tests pass
