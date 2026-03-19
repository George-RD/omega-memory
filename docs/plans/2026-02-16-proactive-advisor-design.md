# Proactive Advisor Design

**Date:** 2026-02-16
**Status:** Approved
**Scope:** Pro-only (singularityjason/omega). Do NOT sync to omega-public.

## Problem

OMEGA captures hindsight but never delivers foresight. It records "you hit a deadlock in coordination.py" but never says "you're about to edit coordination.py, watch out for deadlocks" next time. The system shows context but never suggests actions, doesn't learn patterns to anticipate, is reactive rather than preemptive, and surfaces memories with low signal-to-noise.

## Solution

A ~300-line module (`src/omega/advisor.py`) that converts stored error patterns, lessons, and decisions into forward-looking warnings at the right trigger points. Plugs into existing hooks at 3 integration points. No new MCP tools, no schema changes, no new dependencies.

## Architecture

```
Hook fires (file edit, bash error, session start)
    |
    v
surface_memories (existing) --> raw memories
    |
    v
advisor.suggest() --> queries error_patterns, lessons, decisions
    |                   for the target file/context
    v
Format as [WARNING] / [TIP] / [WATCH] / [SUGGEST] / [RECALL]
    |
    v
Appended to hook response (existing lines list)
```

**Key decisions:**
- Not a new MCP tool. Fires automatically via existing hooks.
- Inline function call within hook_server.py, not a separate daemon.
- Fail-open. If the advisor throws, the hook still returns normal memories.
- No new DB tables or schema changes. Works with existing memory types.
- Pro-only. Uses bridge and storage APIs but stays in private repo.

## Warning Types

### `[WARNING]` - Pre-error prevention

**Trigger:** Edit/read a file that has error_pattern memories associated with it.
**Data source:** `query_structured(event_type="error_pattern", context_file=file_path)`
**Logic:**
- Match error patterns where file path (or directory/module) appears in content or metadata
- Require 2+ occurrences across different sessions (not one-off flukes)
- Traverse `get_related_chain` for linked lessons to show what fixed it

**Example:**
```
[WARNING] This file has caused 3 errors across sessions:
  - threading.Lock deadlock in _ensure_manager() -- fix: use RLock or avoid nested locking
  - DB connection gone after singleton reuse -- fix: add connection health check
```

### `[TIP]` - Relevant lessons for current context

**Trigger:** Edit a file with `lesson_learned` memories linked to that file/directory/language.
**Data source:** `query_structured(event_type="lesson_learned", context_file=file_path, context_tags=language_tags)`
**Logic:**
- Semantic search with file path + directory name as query
- Filter to relevance >= 0.3
- Max 2 tips per hook fire
- Deduplicate against what was already shown in [MEMORY] block

**Example:**
```
[TIP] Lesson from Feb 14: sqlite_store.query() returns stale results if called
  during a write transaction -- use read_committed isolation
```

### `[WATCH]` - Repeat-mistake escalation

**Trigger:** Bash error matches a known error_pattern for the same file edited in the last 5 minutes.
**Data source:** Session-local edit history + error_pattern match
**Logic:**
- Track files edited in current session (via .surfaced.json)
- When Bash error captured, cross-reference against recent edits
- If pattern seen 2+ times before on this file: escalate to [WATCH]
- Include the fix that worked last time

**Example:**
```
[WATCH] You've hit this error before on this file (3rd time):
  "get_manager() returned singleton with dead DB connection"
  Last fix: added connection.ping() check in _ensure_manager()
```

### `[SUGGEST]` - Session-start action items

**Trigger:** `omega_welcome()` call at session start.
**Data source:** Pending tasks, recent errors from last session, unresolved blockers from handoff
**Logic:**
- Pull last session's handoff
- Find unresolved error_patterns (no linked lesson = unresolved)
- Find pending tasks sorted by priority
- Max 3 items, ranked: blockers > errors > tasks

**Example:**
```
[SUGGEST] Based on your last session:
  1. Fix DB connection bug in coordination.py (error hit 3x, no fix recorded)
  2. PR #1997 still awaiting review -- follow up
  3. SEO: check if Google indexed any pages yet
```

### `[RECALL]` - "You decided this already"

**Trigger:** Edit a file where a prior `decision` memory exists for that area.
**Data source:** `query_structured(event_type="decision", context_file=file_path)`
**Logic:**
- Semantic search for decisions related to the file/module
- Relevance >= 0.4
- Max 1 per hook fire
- Only show decisions from other sessions

**Example:**
```
[RECALL] Prior decision (Feb 10): "Use sqlite-vec for embeddings instead of
  Pinecone to keep data local" -- still applies to this file
```

## Aggressiveness Control

| Mechanism | Value | Purpose |
|-----------|-------|---------|
| Max warnings per hook | 3 total | Prevent wall of text |
| Priority order | WARNING > WATCH > RECALL > TIP | Errors before advice |
| Session dedup | Hash-based | Don't repeat same warning |
| Cooldown per file | 10 min | Don't warn on every save |
| Min occurrences for WARNING | 2 sessions | Filter one-off flukes |
| Min relevance for TIP | 0.3 | Higher bar than raw memories |
| Min relevance for RECALL | 0.4 | Only highly relevant decisions |

## Query Pipeline

Per file-edit hook fire:

1. **Query error_patterns:** `query_structured(query_text=filename+dirname, event_type="error_pattern", context_file=file_path, limit=10, entity_id=entity_id)`
2. **Query lessons:** `query_structured(query_text=filename+dirname, event_type="lesson_learned", context_file=file_path, context_tags=language_tags, limit=5, entity_id=entity_id)`
3. **Query decisions:** `query_structured(query_text=filename+dirname, event_type="decision", context_file=file_path, limit=3, entity_id=entity_id)`

Sequential (shared DB connection). Added latency: ~50-100ms.

### Scoring

```
score = relevance * 0.4 + recency * 0.3 + frequency * 0.3
```

- `relevance`: from query result (0.0-1.0)
- `recency`: 1.0 if < 7 days, 0.5 if < 30 days, 0.2 if older
- `frequency`: count of similar errors on same file / max count, capped at 1.0

### Linking Errors to Fixes

1. **Graph traversal:** `get_related_chain(error_id, max_hops=2, edge_types=["resolved_by", "related_to"])`
2. **Fallback (temporal):** lesson_learned created within 30 min after error, same session
3. **Fallback (content):** semantic search for lessons matching error content
4. If no fix found: message says "no recorded fix"

## Module API

```python
class Advisor:
    def __init__(self, project: str, entity_id: Optional[str] = None):
        """Lightweight, stateless per call."""

    def suggest_for_file(
        self,
        file_path: str,
        session_id: str,
        tool_name: str,
        already_surfaced: set,
    ) -> List[AdvisorLine]:
        """File-edit hooks. Returns ranked, capped warnings."""

    def suggest_for_session_start(
        self,
        session_id: str,
        handoff: Optional[dict],
        pending_tasks: List[dict],
    ) -> List[AdvisorLine]:
        """Welcome flow. Returns [SUGGEST] action items."""

    def suggest_for_error(
        self,
        error_summary: str,
        file_path: Optional[str],
        session_id: str,
    ) -> Optional[AdvisorLine]:
        """Bash error capture. Returns [WATCH] if repeat."""


@dataclass
class AdvisorLine:
    tag: str              # "WARNING", "TIP", "WATCH", "SUGGEST", "RECALL"
    message: str
    memory_ids: List[str] # Source memory IDs (for dedup + feedback tracking)
    score: float

    def format(self) -> str:
        return f"[{self.tag}] {self.message}"
```

## Integration Points

### 1. hook_server.py (file edits)

In `handle_surface_memories`, after existing memory surfacing:

```python
try:
    from omega.advisor import Advisor
    adv = Advisor(project=project, entity_id=entity_id)
    suggestions = adv.suggest_for_file(
        file_path=file_path,
        session_id=session_id,
        tool_name=tool_name,
        already_surfaced=surfaced_ids,
    )
    for s in suggestions:
        lines.append(s.format())
        surfaced_ids.update(s.memory_ids)
except Exception:
    pass
```

~10 lines added.

### 2. bridge.py (welcome)

In the welcome flow, after briefing assembled:

```python
try:
    from omega.advisor import Advisor
    adv = Advisor(project=project, entity_id=entity_id)
    suggestions = adv.suggest_for_session_start(
        session_id=session_id,
        handoff=last_handoff,
        pending_tasks=tasks,
    )
    if suggestions:
        briefing["suggestions"] = "\n".join(s.format() for s in suggestions)
except Exception:
    pass
```

~10 lines added.

### 3. hook_server.py (bash errors)

In the existing error capture block:

```python
try:
    from omega.advisor import Advisor
    adv = Advisor(project=project, entity_id=entity_id)
    watch = adv.suggest_for_error(
        error_summary=error_summary,
        file_path=last_edited_file,
        session_id=session_id,
    )
    if watch:
        lines.append(watch.format())
except Exception:
    pass
```

~10 lines added.

## File Inventory

| File | Change | Lines |
|------|--------|-------|
| `src/omega/advisor.py` | New | ~300 |
| `src/omega/server/hook_server.py` | Edit (3 blocks) | ~30 added |
| `src/omega/bridge.py` | Edit (welcome) | ~10 added |
| `tests/test_advisor.py` | New | ~200 |

Total: ~540 lines. Zero schema changes, zero new dependencies.

## What Does NOT Change

- MCP tool list (no new tools)
- Hook dispatch mechanism
- Memory storage format
- Existing surface_memories behavior (advisor appends, doesn't replace)
- Protocol instructions

## Performance Budget

| Operation | Current | With advisor | Delta |
|-----------|---------|-------------|-------|
| File edit hook | ~150ms | ~250ms | +100ms |
| Welcome | ~300ms | ~400ms | +100ms |
| Bash error hook | ~100ms | ~150ms | +50ms |

All within hook timeout (2s).

## Testing Strategy

### Unit tests (test_advisor.py)

**suggest_for_file:**
- 3 error_patterns across sessions: returns [WARNING] with count and fix
- 1 error_pattern single session: returns nothing (below threshold)
- Error + linked lesson via graph: warning includes fix text
- Error + no linked lesson: warning says "no recorded fix"
- Error + temporal proximity lesson: finds fix via 30min fallback
- Lessons but no errors: returns [TIP] only
- Prior decision: returns [RECALL]
- All three types: returns max 3, priority-ordered
- already_surfaced IDs excluded
- Cooldown: second call within 10 min returns empty
- Below-threshold relevance: filtered out

**suggest_for_session_start:**
- Handoff with blockers + errors + tasks: 3 items, blockers first
- No handoff, just tasks: task-based suggestions
- Empty state: empty list
- More than 3 candidates: capped

**suggest_for_error:**
- Known pattern on recently-edited file: returns [WATCH] with fix
- Pattern but file not recently edited: nothing
- First-time error: nothing
- Pattern from same session only: nothing (needs cross-session)

**Scoring:**
- Recent high-frequency > old low-frequency
- Relevance 0.29 filtered for TIP
- Relevance 0.39 filtered for RECALL

### Integration tests

- End-to-end file edit: seed errors + lesson, assert [WARNING] with fix
- End-to-end welcome: seed handoff with blockers, assert [SUGGEST] lists blocker first
- Dedup: two calls same session same file, second returns empty
- Fail-open: storage raises, suggest returns empty
- Performance: < 200ms with 1000 memories

## Sync Policy

**Pro-only.** Add to sync-manifest.yaml as pro-only:
- `src/omega/advisor.py`
- `tests/test_advisor.py`

Integration edits in hook_server.py and bridge.py must be guarded with try/except ImportError so they're harmless if advisor.py is absent in the public repo.
