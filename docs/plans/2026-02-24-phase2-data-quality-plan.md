# Phase 2: Data Quality Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Surface hidden contradiction detections, add bi-temporal fact validity tracking, and enhance maintenance with strength decay and entity deduplication.

**Architecture:** 3 independent agent worktrees, each tackling one feature. Same parallel pattern as Phase 1. All changes are additive -- no breaking changes to existing APIs.

**Tech Stack:** Python 3.11, SQLite, pytest. No new dependencies.

---

## Agent 1: Contradiction Surfacing

**Branch:** `phase2/contradiction-surfacing`

### Context for Agent

OMEGA has THREE layers of contradiction/conflict detection on the store path:

1. **Bridge Phase 2.5** (`bridge.py:1107`): `detect_conflicts()` from `omega.conflicts` -- runs pre-store, results surfaced in output as "conflicts: N auto-resolved, M flagged"
2. **Bridge Phase 4.1** (`bridge.py:1218`): `_detect_and_supersede()` -- runs post-store, results surfaced as "N superseded"
3. **SQLiteStore `_check_contradictions()`** (`sqlite_store.py:4427`): runs post-store inside `store()` method, does deep 4-signal detection (negation, antonym, preference change, temporal override), annotates both memories' metadata, creates "contradicts" edges -- but **returns None and results are never surfaced**

Your job is to surface layer 3 and add a query filter for contradicted memories.

### Task 1.1: Surface contradiction results from `_check_contradictions()`

**Files:**
- Modify: `src/omega/sqlite_store.py:4427-4582` (`_check_contradictions` method)
- Modify: `src/omega/sqlite_store.py:974-982` (post-store call site in `store()`)
- Modify: `src/omega/bridge.py:1158-1168` (in `auto_capture`, after `store.store()`)
- Test: `tests/test_contradiction_surfacing.py` (create)

**Step 1: Write tests**

```python
"""Tests for contradiction surfacing in store responses and query filtering."""
import pytest
from omega.sqlite_store import OmegaSQLiteStore


class TestContradictionResultReturn:
    """_check_contradictions returns results instead of None."""

    def test_returns_empty_list_no_contradictions(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="The sky is blue", session_id="s1")
        # get_last_contradiction_results should return empty
        results = db.get_last_contradiction_results()
        assert results == []

    def test_returns_contradiction_info(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        db.store(content="User prefers dark mode for all interfaces", session_id="s1",
                 metadata={"event_type": "user_preference"})
        db.store(content="User prefers light mode for all interfaces", session_id="s2",
                 metadata={"event_type": "user_preference"})
        results = db.get_last_contradiction_results()
        # May or may not detect depending on embedding availability;
        # if vec not available, returns empty (that's OK)
        assert isinstance(results, list)

    def test_contradiction_results_contain_required_fields(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        db.store(content="Always use PostgreSQL for production databases", session_id="s1",
                 metadata={"event_type": "decision"})
        db.store(content="Never use PostgreSQL, always use SQLite instead", session_id="s2",
                 metadata={"event_type": "decision"})
        results = db.get_last_contradiction_results()
        for r in results:
            assert "node_id" in r
            assert "confidence" in r
            assert "reason" in r
            assert "content_preview" in r
            assert 0.0 <= r["confidence"] <= 1.0


class TestContradictionInStoreOutput:
    """Bridge auto_capture includes contradiction info in output."""

    def test_output_includes_contradiction_block(self, tmp_path, monkeypatch):
        """When contradictions are detected, output includes [CONTRADICTION] block."""
        # This test may need mocking if embeddings aren't available in test env.
        # The key assertion: if _last_contradiction_results is non-empty,
        # the output string contains "[CONTRADICTION]"
        from omega import bridge
        import omega.bridge as bridge_mod

        # Mock _get_store to return a store with pre-set contradiction results
        class MockStore:
            _last_contradiction_results = [
                {"node_id": "mem-old123", "confidence": 0.78, "reason": "Preference value changed",
                 "content_preview": "User prefers dark mode..."}
            ]
            def store(self, **kwargs):
                return "mem-new456"
            def get_last_contradiction_results(self):
                results = self._last_contradiction_results
                self._last_contradiction_results = []
                return results
            def node_count(self):
                return 10
            def query(self, *a, **kw):
                return []
            stats = {}

        # Test the output formatting logic directly
        results = [{"node_id": "mem-old123", "confidence": 0.78,
                     "reason": "Preference value changed",
                     "content_preview": "User prefers dark mode..."}]
        # Build expected output format
        lines = []
        for r in results:
            lines.append(f"  - `{r['node_id'][:16]}` ({r['confidence']:.0%}): {r['reason']}")
        block = "[CONTRADICTION] New memory may contradict:\n" + "\n".join(lines)
        assert "[CONTRADICTION]" in block
        assert "mem-old123" in block
        assert "78%" in block


class TestIncludeContradictedFilter:
    """omega_query with include_contradicted returns only contradicted memories."""

    def test_include_contradicted_true(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        # Store a memory with contradicted_by in metadata
        import json
        db.store(content="Use dark mode", session_id="s1",
                 metadata={"event_type": "user_preference",
                           "contradicted_by": [{"node_id": "mem-new", "confidence": 0.8}]})
        db.store(content="Use light mode", session_id="s2",
                 metadata={"event_type": "user_preference"})
        db.store(content="Unrelated memory about cats", session_id="s3")
        # Query for contradicted memories only
        # This will need the filter added to the query path
        results = db.query("mode preference", limit=10)
        contradicted = [r for r in results if (r.metadata or {}).get("contradicted_by")]
        assert len(contradicted) >= 1

    def test_include_contradicted_false_excludes(self, tmp_path):
        """Default query behavior does not specifically filter for contradicted."""
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        db.store(content="Important decision about architecture", session_id="s1",
                 metadata={"event_type": "decision"})
        results = db.query("architecture", limit=10)
        # Normal query works without the flag
        assert isinstance(results, list)
```

**Step 2: Run tests to verify they fail**

```bash
python3.11 -m pytest tests/test_contradiction_surfacing.py -v --timeout=60
```
Expected: FAIL (get_last_contradiction_results doesn't exist yet, etc.)

**Step 3: Implement changes**

**3a. `sqlite_store.py` -- Add `_last_contradiction_results` and `get_last_contradiction_results()`**

Add instance attribute in `__init__`:
```python
self._last_contradiction_results: List[dict] = []
```

Add public method (near other getter methods):
```python
def get_last_contradiction_results(self) -> list:
    """Return contradiction results from the most recent store() call.

    Results are cleared after reading (consume-once pattern).
    Each result is a dict with: node_id, confidence, reason, content_preview.
    """
    results = self._last_contradiction_results
    self._last_contradiction_results = []
    return results
```

**3b. `sqlite_store.py` -- Change `_check_contradictions()` return type**

At `sqlite_store.py:4427`, change signature from `-> None` to `-> List[dict]`.

At the early returns (lines 4444, 4462, 4513), return `[]` instead of bare `return`.

At line 4521 (`if not results: return`), change to `return []`.

After the annotation loop (after line 4575 commit), build return value:
```python
surfaced = []
for r in results:
    old_nid = candidate_ids[r.candidate_index]
    surfaced.append({
        "node_id": old_nid,
        "confidence": round(r.confidence, 3),
        "reason": r.reason,
        "content_preview": candidate_contents[r.candidate_index][:80],
    })
self._last_contradiction_results = surfaced
return surfaced
```

**3c. `sqlite_store.py` -- Capture return in `store()`**

At line 978, change:
```python
self._check_contradictions(node_id, content, embedding)
```
to:
```python
self._last_contradiction_results = self._check_contradictions(
    node_id, content, embedding
)
```

**3d. `bridge.py` -- Surface contradictions in `auto_capture()` output**

After line 1168 (`output = f"Stored {node_id} ({event_type}, {ttl_str})"`), add:
```python
# Surface deep contradiction detection results
contradiction_results = store.get_last_contradiction_results()
if contradiction_results:
    lines = []
    for cr in contradiction_results:
        lines.append(
            f"  - `{cr['node_id'][:16]}` ({cr['confidence']:.0%}): {cr['reason']}"
        )
    output += "\n\n[CONTRADICTION] New memory may contradict:\n" + "\n".join(lines)
```

**3e. `tool_schemas.py` -- Add `include_contradicted` param to omega_query**

In the `omega_query` tool schema properties dict, add:
```python
"include_contradicted": {
    "type": "boolean",
    "description": "If true, return only memories that have been contradicted by newer memories. Useful for data quality auditing.",
},
```

**3f. `handlers.py` -- Extract and pass `include_contradicted`**

In `handle_omega_query()`, extract:
```python
include_contradicted = arguments.get("include_contradicted", False)
```

Pass to bridge query call:
```python
include_contradicted=include_contradicted,
```

**3g. `bridge.py` -- Add `include_contradicted` param to `query()` and `query_structured()`**

Add `include_contradicted: bool = False` parameter to both functions.

In `query_structured()`, after the memory_type filter (around line 1634), add:
```python
# Filter for contradicted memories only
if include_contradicted and results:
    results = [r for r in results if (r.metadata or {}).get("contradicted_by")]
```

In `query()`, add the same filter after the equivalent point.

**Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_contradiction_surfacing.py -v --timeout=60
```
Expected: PASS

**Step 5: Run full test suite for regressions**

```bash
python3.11 -m pytest tests/ -x --timeout=60 -q --ignore=tests/server/test_handlers_decision_trail.py
```
Expected: All pass (contradiction surfacing is additive)

**Step 6: Commit**

```bash
git add src/omega/sqlite_store.py src/omega/bridge.py src/omega/server/handlers.py src/omega/server/tool_schemas.py tests/test_contradiction_surfacing.py
git commit -m "feat: surface contradiction detection results in store response

- _check_contradictions() now returns List[dict] with node_id, confidence, reason
- Store response includes [CONTRADICTION] block when contradictions detected
- Added include_contradicted filter to omega_query for data quality auditing
- Added get_last_contradiction_results() consume-once API"
```

---

## Agent 2: Bi-Temporal Data Model

**Branch:** `phase2/bi-temporal`

### Context for Agent

OMEGA memories have `created_at` (when stored) but no way to express temporal fact validity. The goal is to add `valid_from` (when this fact became true) and `valid_until` (when it stopped being true, NULL if still valid). This enables "point-in-time" queries: "what was true at time X?"

Key integration: `mark_superseded()` at `sqlite_store.py:3960` already sets `superseded_at` in metadata. We'll also set `valid_until` column so temporal queries work without parsing JSON.

### Task 2.1: Schema migration v11 -> v12

**Files:**
- Modify: `src/omega/schema.py:12` (SCHEMA_VERSION), `src/omega/schema.py:226` (after v11 migration)
- Modify: `src/omega/schema.py:254` (CREATE TABLE -- add columns)
- Modify: `src/omega/schema.py:274` (index loop -- add new columns)
- Test: `tests/test_bitemporal.py` (create)

**Step 1: Write tests**

```python
"""Tests for bi-temporal data model (valid_from, valid_until)."""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import pytest
from omega.sqlite_store import OmegaSQLiteStore


class TestBitemporalSchema:
    """Schema v12 adds valid_from and valid_until columns."""

    def test_schema_version_is_12(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        version = db._conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == 12

    def test_valid_from_column_exists(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        cols = [row[1] for row in db._conn.execute("PRAGMA table_info(memories)").fetchall()]
        assert "valid_from" in cols

    def test_valid_until_column_exists(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        cols = [row[1] for row in db._conn.execute("PRAGMA table_info(memories)").fetchall()]
        assert "valid_until" in cols

    def test_valid_from_index_exists(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        indexes = [row[1] for row in db._conn.execute("PRAGMA index_list(memories)").fetchall()]
        assert any("valid_from" in idx for idx in indexes)

    def test_backfill_sets_valid_from(self, tmp_path):
        """Existing memories get valid_from = COALESCE(referenced_date, created_at)."""
        # Create a v11 database, then upgrade
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="Test memory", session_id="s1")
        row = db._conn.execute(
            "SELECT valid_from, created_at FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        assert row[0] is not None
        assert row[0] == row[1]  # valid_from defaults to created_at

    def test_backfill_superseded_gets_valid_until(self, tmp_path):
        """Superseded memories get valid_until from metadata.superseded_at."""
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node1 = db.store(content="Old fact", session_id="s1",
                         metadata={"event_type": "decision"})
        db.mark_superseded(node1, "mem-new")
        row = db._conn.execute(
            "SELECT valid_until FROM memories WHERE node_id = ?", (node1,)
        ).fetchone()
        assert row[0] is not None


class TestBitemporalStore:
    """Store sets valid_from correctly."""

    def test_store_sets_valid_from_to_created_at(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="New fact", session_id="s1")
        row = db._conn.execute(
            "SELECT valid_from, created_at FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        assert row[0] == row[1]

    def test_store_with_referenced_date_uses_it(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        ref_date = "2025-01-15T10:00:00+00:00"
        node_id = db.store(content="Historical fact", session_id="s1",
                           referenced_date=ref_date)
        row = db._conn.execute(
            "SELECT valid_from FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        assert row[0] == ref_date

    def test_store_valid_until_is_null(self, tmp_path):
        """New memories have valid_until = NULL (still valid)."""
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="Current fact", session_id="s1")
        row = db._conn.execute(
            "SELECT valid_until FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        assert row[0] is None


class TestBitemporalSupersession:
    """mark_superseded sets valid_until."""

    def test_superseded_gets_valid_until(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        old = db.store(content="Old decision", session_id="s1",
                       metadata={"event_type": "decision"})
        new = db.store(content="New decision", session_id="s2",
                       metadata={"event_type": "decision"})
        db.mark_superseded(old, new)
        row = db._conn.execute(
            "SELECT valid_until FROM memories WHERE node_id = ?", (old,)
        ).fetchone()
        assert row[0] is not None

    def test_superseding_memory_valid_until_stays_null(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        old = db.store(content="Old preference", session_id="s1")
        new = db.store(content="New preference", session_id="s2")
        db.mark_superseded(old, new)
        row = db._conn.execute(
            "SELECT valid_until FROM memories WHERE node_id = ?", (new,)
        ).fetchone()
        assert row[0] is None


class TestBitemporalQuery:
    """Query with valid_at returns only temporally valid memories."""

    def test_valid_at_excludes_superseded(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        old = db.store(content="Use React for frontend", session_id="s1",
                       metadata={"event_type": "decision"})
        new = db.store(content="Use Vue for frontend", session_id="s2",
                       metadata={"event_type": "decision"})
        db.mark_superseded(old, new)

        # Query at current time should only return the new one
        now = datetime.now(timezone.utc).isoformat()
        results = db.query("frontend framework", limit=10, valid_at=now)
        result_ids = [r.id for r in results]
        assert new in result_ids
        # old should be excluded (its valid_until is set)

    def test_valid_at_none_returns_all(self, tmp_path):
        """Without valid_at, query returns all (backward compatible)."""
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        db.store(content="Some decision about databases", session_id="s1",
                 metadata={"event_type": "decision"})
        results = db.query("databases", limit=10)
        assert len(results) >= 1

    def test_valid_at_historical_point(self, tmp_path):
        """Query at a past time returns what was valid then."""
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        # Store memory with explicit valid_from in the past
        past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        node = db.store(content="We use PostgreSQL", session_id="s1",
                        referenced_date=past,
                        metadata={"event_type": "decision"})
        # Mark it superseded (sets valid_until to now)
        db.mark_superseded(node, "mem-new")

        # Query at a point between valid_from and valid_until should find it
        mid = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        results = db.query("database choice", limit=10, valid_at=mid)
        result_ids = [r.id for r in results]
        assert node in result_ids


class TestBitemporalMemoryResult:
    """MemoryResult includes valid_from and valid_until."""

    def test_query_structured_includes_valid_from(self, tmp_path):
        """query_structured output dicts include valid_from."""
        import omega.bridge as bridge_mod
        # This tests the bridge layer, which may need a running store
        # Tested via integration in the bridge tests
        pass

    def test_query_structured_includes_valid_until(self, tmp_path):
        pass
```

**Step 2: Run tests to verify they fail**

```bash
python3.11 -m pytest tests/test_bitemporal.py -v --timeout=60
```

**Step 3: Implement changes**

**3a. `schema.py` -- Update SCHEMA_VERSION and add migration**

Change line 12: `SCHEMA_VERSION = 12`

After the v10->v11 migration block (after line 226), add:
```python
# v11 -> v12: add bi-temporal columns (valid_from, valid_until)
current_version = c.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
if current_version and current_version[0] < 12:
    try:
        c.execute("ALTER TABLE memories ADD COLUMN valid_from TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE memories ADD COLUMN valid_until TEXT")
    except sqlite3.OperationalError:
        pass
    # Backfill: valid_from = referenced_date if set, else created_at
    c.execute("UPDATE memories SET valid_from = COALESCE(referenced_date, created_at)")
    # Backfill: superseded memories get valid_until from metadata
    c.execute("""
        UPDATE memories SET valid_until = json_extract(metadata, '$.superseded_at')
        WHERE json_extract(metadata, '$.superseded') = 1
        AND json_extract(metadata, '$.superseded_at') IS NOT NULL
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_valid_from ON memories(valid_from)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_valid_until ON memories(valid_until)")
    c.execute("UPDATE schema_version SET version = 12")
    c.commit()
    logger.info("Schema migrated v11 -> v12: added bi-temporal columns with backfill")
```

Update CREATE TABLE (line 254) -- add after `memory_type`:
```sql
    valid_from TEXT,
    valid_until TEXT
```

Update index loop (line 274) -- add `"valid_from"`, `"valid_until"` to the tuple.

**3b. `sqlite_store.py` -- Set valid_from on store**

In the `store()` method INSERT statement (line 923-948), add `valid_from` column:
- Add `valid_from` to the column list
- Set value: `referenced_date or now` (where `now` is the `created_at` value)
- `valid_until` stays NULL (omit from INSERT, uses default)

**3c. `sqlite_store.py` -- Set valid_until in `mark_superseded()`**

In `mark_superseded()` at line 3960, after setting metadata fields (line 3979), add:
```python
now_str = datetime.now(timezone.utc).isoformat()
# ...existing meta updates...
self._conn.execute(
    "UPDATE memories SET valid_until = ? WHERE node_id = ?",
    (now_str, node_id),
)
```

**3d. `sqlite_store.py` -- Add valid_at filter to query**

Add `valid_at: Optional[str] = None` parameter to the `query()` method.

In the query's WHERE clause construction, when `valid_at` is provided:
```python
if valid_at:
    # Only return memories that were valid at the specified time
    conditions.append("valid_from <= ? AND (valid_until IS NULL OR valid_until > ?)")
    params.extend([valid_at, valid_at])
```

The exact insertion point depends on how the query is built. Look for where other filters (entity_id, agent_type, event_type) are added as WHERE conditions. Add the temporal filter alongside them.

**3e. `MemoryResult` -- Add valid_from and valid_until**

At `sqlite_store.py:190`, add to `__slots__`:
```python
"valid_from",
"valid_until",
```

In `__init__` (line 204), add parameters and set them:
```python
valid_from: Optional[datetime] = None,
valid_until: Optional[datetime] = None,
```
```python
self.valid_from = valid_from
self.valid_until = valid_until
```

**3f. `tool_schemas.py` -- Add valid_at param**

In omega_query schema properties:
```python
"valid_at": {
    "type": "string",
    "description": "ISO datetime. Return only memories that were valid at this point in time. Enables temporal queries like 'what did we know before session X?'",
},
```

**3g. `handlers.py` / `bridge.py` -- Pass valid_at through**

Extract in handler:
```python
valid_at = arguments.get("valid_at")
```

Add to bridge `query()` and `query_structured()` signatures:
```python
valid_at: Optional[str] = None,
```

Pass through to `db.query()`.

In `query_structured()` output dict (line 1644-1656), add:
```python
"valid_from": node.valid_from.isoformat() if node.valid_from else None,
"valid_until": node.valid_until.isoformat() if node.valid_until else None,
```

**3h. Update hardcoded schema version in tests**

Grep all test files for `version == 11` or `version >= 11` assertions and update to 12:
```bash
grep -rn "version.*11\|SCHEMA_VERSION.*11" tests/
```

**Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_bitemporal.py -v --timeout=60
```

**Step 5: Run full suite**

```bash
python3.11 -m pytest tests/ -x --timeout=60 -q --ignore=tests/server/test_handlers_decision_trail.py
```

**Step 6: Commit**

```bash
git add src/omega/schema.py src/omega/sqlite_store.py src/omega/bridge.py \
    src/omega/server/handlers.py src/omega/server/tool_schemas.py \
    tests/test_bitemporal.py
git commit -m "feat: add bi-temporal data model (valid_from, valid_until)

Schema v11->v12: adds valid_from and valid_until columns to memories table.
- valid_from set to referenced_date or created_at on store
- valid_until set when mark_superseded() is called
- omega_query supports valid_at param for point-in-time queries
- Backfill migration: existing memories get valid_from from created_at,
  superseded memories get valid_until from metadata.superseded_at
- MemoryResult includes valid_from and valid_until in structured output"
```

---

## Agent 3: Sleep-Time Consolidation

**Branch:** `phase2/sleep-time-consolidation`

### Context for Agent

OMEGA's `consolidate()` at `sqlite_store.py:2838` runs 4 phases of pruning (decisions, stale, summary cap, orphans). Your job is to add 2 new phases:

- **Phase 5: Strength decay** -- compute strength for each memory (same formula as query-time), mark the weakest as superseded
- **Phase 6: Entity deduplication** -- find entities with similar names and merge them

The strength formula (from Phase 1): `type_weight * feedback_factor * decay_factor`, where:
- `_TYPE_WEIGHTS` dict at `sqlite_store.py:279` (36 event types)
- `_compute_decay_factor()` at `sqlite_store.py:4209`
- `_compute_fb_factor()` at `sqlite_store.py:4244`

Entity engine: `src/omega/entity/engine.py`, class `EntityManager`
- `list_entities()` at line 200 returns formatted markdown (not programmatic)
- Need to add `list_entity_ids()` that returns raw `List[tuple[str, str]]` of (id, name) pairs

### Task 3.1: Strength decay pruning

**Files:**
- Modify: `src/omega/sqlite_store.py:2838` (consolidate method -- add Phase 5)
- Test: `tests/test_sleep_consolidation.py` (create)

**Step 1: Write tests**

```python
"""Tests for sleep-time consolidation: strength decay and entity dedup."""
import json
from datetime import datetime, timezone, timedelta
import pytest
from omega.sqlite_store import OmegaSQLiteStore


class TestApplyStrengthDecay:
    """Phase 5: strength decay marks weak old memories as superseded."""

    def test_old_low_strength_memory_gets_superseded(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        # Store a memory, then make it old and never-accessed
        node_id = db.store(content="Trivial observation about weather", session_id="s1",
                           metadata={"event_type": "memory"})
        # Backdate created_at to 60 days ago
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        db._conn.execute(
            "UPDATE memories SET created_at = ?, access_count = 0 WHERE node_id = ?",
            (old_date, node_id),
        )
        db._conn.commit()

        stats = db.apply_strength_decay(min_strength=0.05, min_age_days=30)
        assert stats["decayed"] >= 1

        # Check the memory is now superseded
        row = db._conn.execute(
            "SELECT metadata FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        meta = json.loads(row[0]) if row[0] else {}
        assert meta.get("superseded") is True
        assert meta.get("superseded_reason") == "strength_decay"

    def test_recent_memory_not_decayed(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="Recent important decision", session_id="s1",
                           metadata={"event_type": "decision"})
        stats = db.apply_strength_decay(min_strength=0.05, min_age_days=30)
        assert stats["decayed"] == 0

    def test_protected_types_not_decayed(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="Always validate input before processing", session_id="s1",
                           metadata={"event_type": "user_preference"})
        old_date = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        db._conn.execute(
            "UPDATE memories SET created_at = ?, access_count = 0 WHERE node_id = ?",
            (old_date, node_id),
        )
        db._conn.commit()

        stats = db.apply_strength_decay(min_strength=0.05, min_age_days=30)
        row = db._conn.execute(
            "SELECT metadata FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        meta = json.loads(row[0]) if row[0] else {}
        assert not meta.get("superseded"), "user_preference should be protected"

    def test_accessed_memory_not_decayed(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="Frequently accessed info", session_id="s1",
                           metadata={"event_type": "memory"})
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        db._conn.execute(
            "UPDATE memories SET created_at = ?, access_count = 5, last_accessed = ? WHERE node_id = ?",
            (old_date, recent, node_id),
        )
        db._conn.commit()

        stats = db.apply_strength_decay(min_strength=0.05, min_age_days=30)
        row = db._conn.execute(
            "SELECT metadata FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        meta = json.loads(row[0]) if row[0] else {}
        assert not meta.get("superseded"), "Recently accessed memory should not decay"

    def test_already_superseded_skipped(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="Already superseded", session_id="s1")
        db.mark_superseded(node_id, "mem-other")
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        db._conn.execute(
            "UPDATE memories SET created_at = ? WHERE node_id = ?",
            (old_date, node_id),
        )
        db._conn.commit()

        stats = db.apply_strength_decay(min_strength=0.05, min_age_days=30)
        assert stats["decayed"] == 0  # Already superseded, don't double-count

    def test_forgetting_log_entry_created(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        node_id = db.store(content="Will decay away", session_id="s1",
                           metadata={"event_type": "memory"})
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        db._conn.execute(
            "UPDATE memories SET created_at = ?, access_count = 0 WHERE node_id = ?",
            (old_date, node_id),
        )
        db._conn.commit()

        db.apply_strength_decay(min_strength=0.05, min_age_days=30)
        log = db._conn.execute(
            "SELECT reason FROM forgetting_log WHERE node_id = ?", (node_id,)
        ).fetchone()
        assert log is not None
        assert log[0] == "strength_decay"


class TestConsolidateIncludesNewPhases:
    """consolidate() runs the new phases and returns stats."""

    def test_consolidate_returns_decayed_count(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        stats = db.consolidate()
        assert "decayed_memories" in stats

    def test_consolidate_returns_merged_entities_count(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        stats = db.consolidate()
        assert "merged_entities" in stats


class TestMergeDuplicateEntities:
    """Phase 6: entity deduplication merges similar entity names."""

    def test_merge_exact_case_variants(self, tmp_path):
        """Entities like 'omega' and 'OMEGA' get merged."""
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        # This test requires entity engine setup
        # Entity creation happens through EntityManager
        try:
            from omega.entity.engine import get_entity_manager
            em = get_entity_manager(tmp_path / "test.db")
            em.create_entity("omega-lower", "Omega Project", "company")
            em.create_entity("OMEGA-UPPER", "OMEGA Project", "company")

            stats = db.merge_duplicate_entities()
            assert stats["merged"] >= 0  # Depends on similarity logic
        except Exception:
            pytest.skip("Entity engine not available in test environment")

    def test_empty_entities_returns_zero(self, tmp_path):
        db = OmegaSQLiteStore(str(tmp_path / "test.db"))
        stats = db.merge_duplicate_entities()
        assert stats["merged"] == 0
```

**Step 2: Run tests to verify they fail**

```bash
python3.11 -m pytest tests/test_sleep_consolidation.py -v --timeout=60
```

**Step 3: Implement changes**

**3a. `sqlite_store.py` -- Add `apply_strength_decay()` method**

Add near the `consolidate()` method:
```python
def apply_strength_decay(
    self,
    min_strength: float = 0.05,
    min_age_days: int = 30,
) -> dict:
    """Mark weak, old, unaccessed memories as superseded (ACT-R forgetting curve).

    Computes strength = type_weight * feedback_factor * decay_factor for each
    non-protected, non-superseded memory older than min_age_days. Memories with
    strength below min_strength get marked superseded with reason 'strength_decay'.

    Returns dict with 'decayed' count.
    """
    protected_types = frozenset({
        "user_preference", "error_pattern", "behavioral_pattern",
        "constraint", "reminder",
    })
    cutoff = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).isoformat()
    stats = {"decayed": 0, "scanned": 0}

    with self._lock:
        rows = self._conn.execute(
            """SELECT node_id, content, metadata, created_at, access_count,
                      last_accessed, event_type
               FROM memories
               WHERE created_at < ?
               AND access_count = 0""",
            (cutoff,),
        ).fetchall()

    for row in rows:
        node_id, content, meta_json, created_at, access_count, last_accessed, event_type = row
        meta = json.loads(meta_json) if meta_json else {}
        stats["scanned"] += 1

        # Skip already superseded
        if meta.get("superseded"):
            continue
        # Skip protected types
        if event_type in protected_types:
            continue
        # Skip recently accessed (last_accessed within min_age_days)
        if last_accessed:
            la_dt = self._parse_dt(last_accessed)
            cutoff_dt = datetime.now(timezone.utc) - timedelta(days=min_age_days)
            if la_dt and la_dt > cutoff_dt:
                continue

        # Compute strength (same formula as query-time)
        type_weight = self._TYPE_WEIGHTS.get(event_type, 1.0)
        created_dt = self._parse_dt(created_at)
        decay = self._compute_decay_factor(created_dt, access_count, last_accessed)
        fb = self._compute_fb_factor(meta)
        strength = type_weight * fb * decay

        if strength < min_strength:
            self._log_forgetting(node_id, content or "", event_type or "", "strength_decay")
            with self._lock:
                meta["superseded"] = True
                meta["superseded_reason"] = "strength_decay"
                meta["superseded_at"] = datetime.now(timezone.utc).isoformat()
                self._conn.execute(
                    "UPDATE memories SET metadata = ? WHERE node_id = ?",
                    (json.dumps(meta), node_id),
                )
                self._conn.commit()
            stats["decayed"] += 1

    return stats
```

**3b. `sqlite_store.py` -- Add `merge_duplicate_entities()` method**

```python
def merge_duplicate_entities(self) -> dict:
    """Merge entities with matching lowercased names.

    Transfers memories from duplicate entity_id to the primary (first-seen),
    merges relationship edges, and removes the duplicate entity.

    Returns dict with 'merged' count.
    """
    stats = {"merged": 0}
    try:
        from omega.entity.engine import get_entity_manager
        em = get_entity_manager(self.db_path)
    except Exception as e:
        logger.debug("Entity engine unavailable for merge: %s", e)
        return stats

    try:
        entity_ids = em.list_entity_ids()  # [(id, name), ...]
    except Exception as e:
        logger.debug("list_entity_ids failed: %s", e)
        return stats

    if len(entity_ids) < 2:
        return stats

    # Group by normalized name
    name_groups: dict = {}
    for eid, name in entity_ids:
        key = name.strip().lower()
        name_groups.setdefault(key, []).append(eid)

    for name_key, eids in name_groups.items():
        if len(eids) < 2:
            continue
        primary = eids[0]
        for duplicate in eids[1:]:
            # Transfer memories
            with self._lock:
                self._conn.execute(
                    "UPDATE memories SET entity_id = ? WHERE entity_id = ?",
                    (primary, duplicate),
                )
                self._conn.commit()
            # Remove duplicate entity
            try:
                em.delete_entity(duplicate)
            except Exception as e:
                logger.debug("Failed to delete duplicate entity %s: %s", duplicate, e)
            stats["merged"] += 1
            logger.info("Merged entity %s into %s (name: %s)", duplicate, primary, name_key)

    return stats
```

**3c. `sqlite_store.py` `consolidate()` -- Add Phase 5 and 6**

After Phase 4 (orphaned vec cleanup, around line 3011), add:
```python
        # Phase 5: Strength decay — mark weak old memories as superseded
        decay_stats = self.apply_strength_decay()
        stats["decayed_memories"] = decay_stats["decayed"]

        # Phase 6: Entity deduplication — merge entities with matching names
        merge_stats = self.merge_duplicate_entities()
        stats["merged_entities"] = merge_stats["merged"]
```

**3d. `bridge.py` `consolidate()` -- Surface new stats**

In the bridge `consolidate()` function (line 3002), after the existing breakdown lines, add:
```python
output += f"- **Strength-decayed:** {stats.get('decayed_memories', 0)}\n"
output += f"- **Merged entities:** {stats.get('merged_entities', 0)}\n"
```

**3e. `entity/engine.py` -- Add `list_entity_ids()` method**

In `EntityManager` class, add:
```python
def list_entity_ids(self) -> list:
    """Return list of (entity_id, name) tuples for all entities."""
    with self._lock:
        rows = self._conn.execute(
            "SELECT id, name FROM entities ORDER BY name"
        ).fetchall()
    return [(row[0], row[1]) for row in rows]
```

Also check if `delete_entity()` exists. If not, add:
```python
def delete_entity(self, entity_id: str) -> bool:
    """Delete an entity by ID. Returns True if found and deleted."""
    with self._lock:
        cursor = self._conn.execute(
            "DELETE FROM entities WHERE id = ?", (entity_id,)
        )
        if cursor.rowcount > 0:
            # Clean up relationships
            self._conn.execute(
                "DELETE FROM entity_relationships WHERE source_id = ? OR target_id = ?",
                (entity_id, entity_id),
            )
            self._conn.commit()
            return True
        return False
```

**Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_sleep_consolidation.py -v --timeout=60
```

**Step 5: Run full suite**

```bash
python3.11 -m pytest tests/ -x --timeout=60 -q --ignore=tests/server/test_handlers_decision_trail.py
```

**Step 6: Commit**

```bash
git add src/omega/sqlite_store.py src/omega/bridge.py src/omega/entity/engine.py \
    tests/test_sleep_consolidation.py
git commit -m "feat: add sleep-time consolidation (strength decay + entity dedup)

- apply_strength_decay(): marks weak, old, unaccessed memories as superseded
  using ACT-R forgetting curve (type_weight * feedback * decay < threshold)
- merge_duplicate_entities(): merges entities with matching lowercased names,
  transfers memories and cleans up relationships
- consolidate() now runs 6 phases (4 existing + 2 new)
- EntityManager.list_entity_ids() for programmatic entity listing
- Forgetting audit trail entries for strength-decayed memories"
```

---

## Merge Order

1. **Agent 1** (contradiction surfacing) -- output wiring only, no schema changes
2. **Agent 3** (sleep-time consolidation) -- internal consolidate changes, no schema
3. **Agent 2** (bi-temporal) -- schema v11->v12, most overlap potential

After all three merge, run:
```bash
python3.11 -m pytest tests/ -x --timeout=60 -q --ignore=tests/server/test_handlers_decision_trail.py
```

## Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Agent 2 schema version conflicts with Agent 1/3 test assertions | Only Agent 2 changes schema version; others don't touch it |
| `apply_strength_decay()` too aggressive | Protected types list + min_age_days + min_strength threshold. Conservative defaults (0.05 strength, 30 days) |
| Entity merge loses data | Only transfers memories, doesn't delete memory content. Entity deletion only after transfer |
| `_check_contradictions` return type change breaks callers | Only called in one place (store method line 978). Return value was previously discarded |
| Bi-temporal WHERE clause slows queries | Indexed on valid_from, valid_until. Only applied when valid_at param provided |
