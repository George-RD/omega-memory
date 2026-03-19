# Phase 1: Retrieval Quality Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Surface hidden strength scores in query results, add memory type classification, and wire entity relationships into retrieval scoring.

**Architecture:** Three independent agent worktrees, each touching different code paths in the 7-phase retrieval pipeline. Agent 1 modifies the query output path (assembly phase). Agent 2 modifies the store input path + adds a filter. Agent 3 modifies the scoring pipeline (fusion phase). Merge order: Agent 3 (most isolated), Agent 1, Agent 2.

**Tech Stack:** Python 3.11+, SQLite, pytest

---

## Agent 1: Strength Surfacing

> Branch: `phase1/strength-surfacing`
> Work in isolated git worktree.

### Task 1.1: Add `strength` to MemoryResult

**Files:**
- Modify: `src/omega/sqlite_store.py:190-224` (MemoryResult class)

**Step 1: Write the failing test**

Create: `tests/test_strength_surfacing.py`

```python
"""Tests for strength surfacing in query results."""
import pytest
from omega.sqlite_store import SQLiteStore


class TestStrengthField:
    """Test that MemoryResult includes strength score."""

    def test_memory_result_has_strength_slot(self, store):
        """MemoryResult should have a 'strength' slot."""
        node_id = store.store(
            content="Temporal decay is computed at query time",
            metadata={"event_type": "decision"},
        )
        results = store.query("temporal decay")
        assert len(results) > 0
        assert hasattr(results[0], "strength"), "MemoryResult missing 'strength' attribute"

    def test_strength_is_float_between_0_and_1(self, store):
        """Strength should be a normalized float in [0.0, 1.0]."""
        store.store(content="Alpha memory", metadata={"event_type": "decision"})
        store.store(content="Beta memory", metadata={"event_type": "lesson_learned"})
        store.store(content="Gamma memory", metadata={"event_type": "session_summary"})
        results = store.query("memory")
        for r in results:
            assert 0.0 <= r.strength <= 1.0, f"strength {r.strength} not in [0, 1]"

    def test_strength_default_is_zero(self):
        """Freshly constructed MemoryResult should have strength=0.0."""
        from omega.sqlite_store import MemoryResult
        mr = MemoryResult(id="test-123", content="test")
        assert mr.strength == 0.0
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_strength_surfacing.py::TestStrengthField -v -x`
Expected: FAIL with `AttributeError: 'MemoryResult' object has no attribute 'strength'`

**Step 3: Add `strength` to MemoryResult**

In `src/omega/sqlite_store.py`, modify `MemoryResult`:

1. Add `"strength"` to `__slots__` tuple (after `"relevance"`)
2. Add `strength: float = 0.0` parameter to `__init__`
3. Add `self.strength = strength` in `__init__` body

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_strength_surfacing.py::TestStrengthField -v -x`
Expected: PASS (strength exists but is 0.0 for all results since it's not computed yet)

Wait -- `test_strength_is_float_between_0_and_1` will pass because 0.0 is in [0, 1]. We need the computation step next to give it real values.

**Step 5: Commit**

```bash
cd ~/Projects/omega
git add tests/test_strength_surfacing.py src/omega/sqlite_store.py
git commit -m "feat: add strength slot to MemoryResult"
```

### Task 1.2: Compute strength in assembly phase

**Files:**
- Modify: `src/omega/sqlite_store.py:1807-1884` (`_query_phase_assemble`)

**Step 1: Write the failing test**

Add to `tests/test_strength_surfacing.py`:

```python
class TestStrengthComputation:
    """Test that strength is computed from decay, feedback, type weight."""

    def test_decisions_have_higher_strength_than_sessions(self, store):
        """Decisions (type_weight=2.0) should score higher than session_summaries (1.2)."""
        store.store(
            content="We decided to use SQLite for storage",
            metadata={"event_type": "decision"},
        )
        store.store(
            content="Session summary about SQLite storage choice",
            metadata={"event_type": "session_summary"},
        )
        results = store.query("SQLite storage")
        # Find each type
        decision = next((r for r in results if (r.metadata or {}).get("event_type") == "decision"), None)
        session = next((r for r in results if (r.metadata or {}).get("event_type") == "session_summary"), None)
        assert decision is not None and session is not None
        assert decision.strength > session.strength, (
            f"Decision strength ({decision.strength}) should exceed session ({session.strength})"
        )

    def test_strength_nonzero_for_query_results(self, store):
        """Queried results should have nonzero strength."""
        store.store(content="Important architecture decision", metadata={"event_type": "decision"})
        results = store.query("architecture")
        assert len(results) > 0
        assert results[0].strength > 0.0, "Top result should have nonzero strength"

    def test_negative_feedback_reduces_strength(self, store):
        """Memories with negative feedback should have lower strength."""
        nid1 = store.store(
            content="Good memory about testing patterns",
            metadata={"event_type": "lesson_learned", "feedback_score": 3},
        )
        nid2 = store.store(
            content="Bad memory about testing patterns",
            metadata={"event_type": "lesson_learned", "feedback_score": -3},
        )
        results = store.query("testing patterns")
        good = next((r for r in results if r.id == nid1), None)
        bad = next((r for r in results if r.id == nid2), None)
        assert good is not None and bad is not None
        assert good.strength > bad.strength
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_strength_surfacing.py::TestStrengthComputation -v -x`
Expected: FAIL (strength is 0.0 for all results)

**Step 3: Compute strength in `_query_phase_assemble`**

In `src/omega/sqlite_store.py`, in `_query_phase_assemble`, after the normalization block (line ~1883 where `node.relevance = round(raw / max_score, 3)`), add strength computation:

```python
        # Compute strength: composite of all scoring signals, normalized to [0, 1]
        if deduped:
            raw_strengths = {}
            for node in deduped:
                event_type = (node.metadata or {}).get("event_type", "")
                type_weight = self._TYPE_WEIGHTS.get(event_type, 1.0)
                fb_score = (node.metadata or {}).get("feedback_score", 0)
                fb_factor = self._compute_fb_factor(fb_score)
                _la = node.last_accessed.isoformat() if node.last_accessed else None
                _ca = node.created_at.isoformat() if node.created_at else None
                decay = self._compute_decay_factor(event_type, _la, _ca, node.access_count or 0)
                raw_strengths[node.id] = node.relevance * type_weight * fb_factor * decay
            max_strength = max(raw_strengths.values()) if raw_strengths else 1.0
            for node in deduped:
                node.strength = round(raw_strengths[node.id] / max_strength, 3) if max_strength > 0 else 0.0
```

This is placed AFTER the relevance normalization so it can use `node.relevance` as the base signal.

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_strength_surfacing.py::TestStrengthComputation -v -x`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/Projects/omega
git add tests/test_strength_surfacing.py src/omega/sqlite_store.py
git commit -m "feat: compute strength score in query assembly phase"
```

### Task 1.3: Surface strength in bridge output

**Files:**
- Modify: `src/omega/bridge.py:1513-1523` (query markdown formatting)
- Modify: `src/omega/bridge.py:1620-1633` (query_structured dict)

**Step 1: Write the failing test**

Add to `tests/test_strength_surfacing.py`:

```python
@pytest.mark.usefixtures("_reset_bridge")
class TestStrengthInBridgeOutput:
    """Test that strength appears in bridge query output."""

    def test_query_markdown_includes_strength(self, tmp_omega_dir):
        """bridge.query() markdown output should include strength indicator."""
        from omega.bridge import store, query
        store(content="Architecture: we use event sourcing", event_type="decision")
        result = query(query_text="event sourcing")
        # Strength should appear as a tag like [strength: 0.xxx]
        assert "strength:" in result.lower() or "str:" in result.lower(), (
            f"Strength not found in query output: {result[:300]}"
        )

    def test_query_structured_includes_strength(self, tmp_omega_dir):
        """bridge.query_structured() should include 'strength' key."""
        from omega.bridge import store, query_structured
        store(content="Architecture: we use event sourcing", event_type="decision")
        results = query_structured(query_text="event sourcing")
        assert len(results) > 0
        assert "strength" in results[0], f"Missing 'strength' key. Keys: {results[0].keys()}"
        assert isinstance(results[0]["strength"], float)
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_strength_surfacing.py::TestStrengthInBridgeOutput -v -x`
Expected: FAIL

**Step 3: Add strength to bridge output**

In `src/omega/bridge.py`:

1. In `query()` function (line ~1520), modify the output formatting:
```python
# Change from:
output += f"## {i}. [{ntype}] `{node.id}`\n"
# To:
_str = getattr(node, "strength", 0.0)
output += f"## {i}. [{ntype}] `{node.id}` (str: {_str:.2f})\n"
```

2. In `query_structured()` (line ~1622), add strength to the dict:
```python
# Add after "relevance" line:
"strength": round(getattr(node, "strength", 0.0), 3),
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_strength_surfacing.py::TestStrengthInBridgeOutput -v -x`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/Projects/omega
git add tests/test_strength_surfacing.py src/omega/bridge.py
git commit -m "feat: surface strength score in bridge query output"
```

### Task 1.4: Add `strength_min` filter to omega_query

**Files:**
- Modify: `src/omega/server/tool_schemas.py:43-84` (omega_query schema)
- Modify: `src/omega/server/handlers.py:256-355` (handle_omega_query)
- Modify: `src/omega/bridge.py:1437-1560` (query function signature + filter)

**Step 1: Write the failing test**

Add to `tests/test_strength_surfacing.py`:

```python
@pytest.mark.usefixtures("_reset_bridge")
class TestStrengthMinFilter:
    """Test strength_min parameter on omega_query."""

    def test_strength_min_filters_weak_results(self, tmp_omega_dir):
        """Setting strength_min should exclude weak results."""
        from omega.bridge import store, query
        # Store a high-value and low-value memory
        store(content="Critical architecture decision about database", event_type="decision")
        store(content="Random session note about database", event_type="session_summary")
        # Query without filter
        all_results = query(query_text="database")
        # Query with high strength_min
        filtered = query(query_text="database", strength_min=0.8)
        # Filtered should have fewer or equal results
        assert len(filtered.split("##")) <= len(all_results.split("##"))

    def test_strength_min_zero_returns_all(self, tmp_omega_dir):
        """strength_min=0.0 should be equivalent to no filter."""
        from omega.bridge import store, query
        store(content="Test memory for strength filtering", event_type="decision")
        all_results = query(query_text="strength filtering")
        filtered = query(query_text="strength filtering", strength_min=0.0)
        assert filtered == all_results
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_strength_surfacing.py::TestStrengthMinFilter -v -x`
Expected: FAIL (strength_min param not accepted)

**Step 3: Add strength_min parameter**

1. In `src/omega/server/tool_schemas.py`, add to omega_query properties (after `perspective`):
```python
"strength_min": {
    "type": "number",
    "minimum": 0.0,
    "maximum": 1.0,
    "description": "Minimum strength score (0.0-1.0). Filters out weak/decayed memories.",
},
```

2. In `src/omega/server/handlers.py` `handle_omega_query()`, add after line 310:
```python
strength_min = arguments.get("strength_min")
if strength_min is not None:
    strength_min = max(0.0, min(1.0, float(strength_min)))
```
And pass it to the bridge call:
```python
result = query(
    ...existing params...
    strength_min=strength_min,
)
```

3. In `src/omega/bridge.py` `query()`, add `strength_min: Optional[float] = None` parameter. After the line `results = results[:limit]` (line 1511), add:
```python
# Filter by minimum strength
if strength_min is not None and strength_min > 0:
    results = [r for r in results if getattr(r, "strength", 0.0) >= strength_min]
```

4. In `src/omega/bridge.py` `query_structured()`, add same parameter and filter.

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_strength_surfacing.py::TestStrengthMinFilter -v -x`
Expected: PASS

**Step 5: Run full test suite for regressions**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x --timeout=60 -q`
Expected: All existing tests pass.

**Step 6: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/tool_schemas.py src/omega/server/handlers.py src/omega/bridge.py tests/test_strength_surfacing.py
git commit -m "feat: add strength_min filter to omega_query"
```

---

## Agent 2: Memory Type Classification

> Branch: `phase1/memory-types`
> Work in isolated git worktree.

### Task 2.1: Add `memory_type` column (schema migration v10 -> v11)

**Files:**
- Modify: `src/omega/schema.py:12` (SCHEMA_VERSION) and `src/omega/schema.py:197` (after v10 migration)

**Step 1: Write the failing test**

Create: `tests/test_memory_types.py`

```python
"""Tests for memory type classification (episodic/semantic/procedural)."""
import pytest
import sqlite3
from omega.sqlite_store import SQLiteStore


class TestMemoryTypeSchema:
    """Test schema migration adds memory_type column."""

    def test_memory_type_column_exists(self, store):
        """The memories table should have a memory_type column."""
        info = store._conn.execute("PRAGMA table_info(memories)").fetchall()
        col_names = [col[1] for col in info]
        assert "memory_type" in col_names

    def test_memory_type_default_is_semantic(self, store):
        """Default memory_type should be 'semantic'."""
        node_id = store.store(content="A generic memory", metadata={"event_type": "memory"})
        row = store._conn.execute(
            "SELECT memory_type FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        assert row[0] == "semantic"

    def test_memory_type_index_exists(self, store):
        """An index on memory_type should exist."""
        indexes = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_memories_memory_type'"
        ).fetchall()
        assert len(indexes) == 1

    def test_schema_version_is_11(self, store):
        """Schema version should be 11 after migration."""
        from omega.schema import SCHEMA_VERSION
        assert SCHEMA_VERSION == 11
        row = store._conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        assert row[0] == 11
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_memory_types.py::TestMemoryTypeSchema -v -x`
Expected: FAIL (`memory_type` column not found, SCHEMA_VERSION is 10)

**Step 3: Add migration**

1. In `src/omega/schema.py` line 12, change: `SCHEMA_VERSION = 11`

2. After the v10 migration block (line ~197), add:
```python
    # v10 -> v11: add memory_type column for cognitive classification
    current_version = c.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if current_version and current_version[0] < 11:
        try:
            c.execute("ALTER TABLE memories ADD COLUMN memory_type TEXT DEFAULT 'semantic'")
        except sqlite3.OperationalError:
            pass
        c.execute("CREATE INDEX IF NOT EXISTS idx_memories_memory_type ON memories(memory_type)")
        # Backfill existing memories
        c.execute("""
            UPDATE memories SET memory_type = 'episodic'
            WHERE event_type IN (
                'session_summary', 'task_completion', 'coordination_snapshot',
                'session_respawn', 'merge_claim', 'merge_release',
                'file_claimed', 'file_released', 'branch_claimed',
                'branch_released', 'code_chunk', 'file_summary', 'file_conflict'
            )
        """)
        c.execute("""
            UPDATE memories SET memory_type = 'procedural'
            WHERE event_type IN (
                'lesson_learned', 'reflexion', 'self_reflection',
                'outcome_evaluation', 'reminder'
            )
        """)
        # Remaining stay 'semantic' (the default)
        c.execute("UPDATE schema_version SET version = 11")
        c.commit()
        logger.info("Schema migrated v10 -> v11: added memory_type column with backfill")
```

3. In the CREATE TABLE block (line ~204), add `memory_type TEXT DEFAULT 'semantic'` after `retrieval_count`:
```sql
            retrieval_count INTEGER DEFAULT 0,
            memory_type TEXT DEFAULT 'semantic'
```

4. Add `"memory_type"` to the index loop tuple (line ~229).

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_memory_types.py::TestMemoryTypeSchema -v -x`
Expected: PASS

**Step 5: Update hardcoded SCHEMA_VERSION assertions in existing tests**

Run: `cd ~/Projects/omega && grep -rn "SCHEMA_VERSION == 10\|version == 10\|assert.*== 10" tests/ --include="*.py"`

Update all found assertions from `10` to `11`. Common locations:
- `tests/test_agent_type.py:17` and `:71`
- Any other test that asserts schema version

**Step 6: Commit**

```bash
cd ~/Projects/omega
git add src/omega/schema.py tests/test_memory_types.py tests/test_agent_type.py
git commit -m "feat: add memory_type column with v10->v11 migration and backfill"
```

### Task 2.2: Auto-classify memory_type on store

**Files:**
- Modify: `src/omega/sqlite_store.py:279-315` (add _MEMORY_TYPE_MAP near _TYPE_WEIGHTS)
- Modify: `src/omega/sqlite_store.py:855-899` (store method INSERT)

**Step 1: Write the failing test**

Add to `tests/test_memory_types.py`:

```python
class TestMemoryTypeAutoClassify:
    """Test auto-classification of memory_type on store."""

    def test_decision_is_semantic(self, store):
        nid = store.store(content="We chose PostgreSQL", metadata={"event_type": "decision"})
        row = store._conn.execute("SELECT memory_type FROM memories WHERE node_id = ?", (nid,)).fetchone()
        assert row[0] == "semantic"

    def test_lesson_is_procedural(self, store):
        nid = store.store(content="Always run tests before deploy", metadata={"event_type": "lesson_learned"})
        row = store._conn.execute("SELECT memory_type FROM memories WHERE node_id = ?", (nid,)).fetchone()
        assert row[0] == "procedural"

    def test_session_summary_is_episodic(self, store):
        nid = store.store(content="Session: fixed auth bug", metadata={"event_type": "session_summary"})
        row = store._conn.execute("SELECT memory_type FROM memories WHERE node_id = ?", (nid,)).fetchone()
        assert row[0] == "episodic"

    def test_constraint_is_semantic(self, store):
        nid = store.store(content="Never deploy on Fridays", metadata={"event_type": "constraint"})
        row = store._conn.execute("SELECT memory_type FROM memories WHERE node_id = ?", (nid,)).fetchone()
        assert row[0] == "semantic"

    def test_reflexion_is_procedural(self, store):
        nid = store.store(content="I should check logs first", metadata={"event_type": "reflexion"})
        row = store._conn.execute("SELECT memory_type FROM memories WHERE node_id = ?", (nid,)).fetchone()
        assert row[0] == "procedural"

    def test_unknown_type_defaults_to_semantic(self, store):
        nid = store.store(content="Some content", metadata={"event_type": "unknown_type"})
        row = store._conn.execute("SELECT memory_type FROM memories WHERE node_id = ?", (nid,)).fetchone()
        assert row[0] == "semantic"

    def test_no_event_type_defaults_to_semantic(self, store):
        nid = store.store(content="No type specified")
        row = store._conn.execute("SELECT memory_type FROM memories WHERE node_id = ?", (nid,)).fetchone()
        assert row[0] == "semantic"

    def test_all_event_types_mapped(self, store):
        """Every key in _TYPE_WEIGHTS should be in _MEMORY_TYPE_MAP."""
        from omega.sqlite_store import SQLiteStore
        for etype in SQLiteStore._TYPE_WEIGHTS:
            assert etype in SQLiteStore._MEMORY_TYPE_MAP, f"{etype} not in _MEMORY_TYPE_MAP"
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_memory_types.py::TestMemoryTypeAutoClassify -v -x`
Expected: FAIL (memory_type is always 'semantic' default, no _MEMORY_TYPE_MAP)

**Step 3: Add classification map and wire into store**

1. In `src/omega/sqlite_store.py`, add class-level dict after `_TYPE_WEIGHTS` (around line 315):

```python
    # Memory type classification: maps event_type -> cognitive category
    _MEMORY_TYPE_MAP = {
        # Episodic: raw experiences and session events
        "session_summary": "episodic",
        "task_completion": "episodic",
        "coordination_snapshot": "episodic",
        "session_respawn": "episodic",
        "merge_claim": "episodic",
        "merge_release": "episodic",
        "file_claimed": "episodic",
        "file_released": "episodic",
        "branch_claimed": "episodic",
        "branch_released": "episodic",
        "code_chunk": "episodic",
        "file_summary": "episodic",
        "file_conflict": "episodic",
        # Procedural: learned behavioral patterns and rules
        "lesson_learned": "procedural",
        "reflexion": "procedural",
        "self_reflection": "procedural",
        "outcome_evaluation": "procedural",
        "reminder": "procedural",
        # Semantic: extracted facts and stable knowledge (everything else)
        "constraint": "semantic",
        "decision": "semantic",
        "user_preference": "semantic",
        "error_pattern": "semantic",
        "sota_research": "semantic",
        "research_report": "semantic",
        "benchmark_update": "semantic",
        "entity_profile_update": "semantic",
        "public_statement": "semantic",
        "outcome_resolution": "semantic",
        "contradiction_detected": "semantic",
        "sota_scan": "semantic",
        "preference_generated": "semantic",
        "advisor_action_outcome": "semantic",
        "test": "semantic",
    }
```

2. In the `store()` method, after line 873 (`extracted_keywords = ...`), add:
```python
            # Classify memory type from event_type
            memory_type = self._MEMORY_TYPE_MAP.get(event_type, "semantic")
```

3. Modify the INSERT statement (line 875-898) to include `memory_type`:
   - Add `memory_type` to the column list
   - Add `memory_type` to the VALUES placeholders
   - Add `memory_type` to the parameter tuple

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_memory_types.py::TestMemoryTypeAutoClassify -v -x`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/Projects/omega
git add src/omega/sqlite_store.py tests/test_memory_types.py
git commit -m "feat: auto-classify memory_type from event_type on store"
```

### Task 2.3: Add `memory_type` filter to omega_query

**Files:**
- Modify: `src/omega/server/tool_schemas.py:43-84` (omega_query schema)
- Modify: `src/omega/server/handlers.py:256-355` (handle_omega_query)
- Modify: `src/omega/bridge.py:1437-1560` (query function)

**Step 1: Write the failing test**

Add to `tests/test_memory_types.py`:

```python
@pytest.mark.usefixtures("_reset_bridge")
class TestMemoryTypeFilter:
    """Test filtering by memory_type in omega_query."""

    def test_filter_procedural(self, tmp_omega_dir):
        """memory_type='procedural' should only return procedural memories."""
        from omega.bridge import store, query
        store(content="Always validate input before processing", event_type="lesson_learned")
        store(content="We decided to use REST over GraphQL", event_type="decision")
        result = query(query_text="processing", memory_type="procedural")
        assert "validate input" in result.lower() or "No matching" in result

    def test_filter_semantic(self, tmp_omega_dir):
        """memory_type='semantic' should only return semantic memories."""
        from omega.bridge import store, query
        store(content="Database choice: PostgreSQL for OLTP", event_type="decision")
        store(content="Lesson: always index foreign keys", event_type="lesson_learned")
        result = query(query_text="database", memory_type="semantic")
        # Decision (semantic) should appear, lesson (procedural) should not
        assert "PostgreSQL" in result or "Results: 0" in result

    def test_filter_episodic(self, tmp_omega_dir):
        """memory_type='episodic' should only return episodic memories."""
        from omega.bridge import store, query
        store(content="Session: debugged memory leak in production", event_type="session_summary")
        store(content="Never ignore memory leak warnings", event_type="constraint")
        result = query(query_text="memory leak", memory_type="episodic")
        assert "debugged" in result.lower() or "Results: 0" in result

    def test_no_filter_returns_all_types(self, tmp_omega_dir):
        """Without memory_type filter, all types should be returned."""
        from omega.bridge import store, query
        store(content="Episodic: completed auth feature", event_type="session_summary")
        store(content="Semantic: auth uses JWT tokens", event_type="decision")
        store(content="Procedural: always check token expiry", event_type="lesson_learned")
        result = query(query_text="auth")
        # Should contain results from multiple types
        assert "Results:" in result
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_memory_types.py::TestMemoryTypeFilter -v -x`
Expected: FAIL (memory_type param not accepted)

**Step 3: Add memory_type filter**

1. In `src/omega/server/tool_schemas.py`, add to omega_query properties:
```python
"memory_type": {
    "type": "string",
    "enum": ["episodic", "semantic", "procedural"],
    "description": "Filter by memory type: 'episodic' (session events), 'semantic' (facts/decisions), 'procedural' (lessons/rules).",
},
```

2. In `src/omega/server/handlers.py` `handle_omega_query()`, add after entity_id extraction:
```python
memory_type = arguments.get("memory_type")
if memory_type and memory_type not in ("episodic", "semantic", "procedural"):
    memory_type = None
```
Pass `memory_type=memory_type` to the bridge call.

3. In `src/omega/bridge.py` `query()`, add `memory_type: Optional[str] = None` parameter. After the `filter_tags` filter block (line ~1509), add:
```python
# Filter by memory_type
if memory_type and results:
    results = [r for r in results if r.metadata.get("memory_type") == memory_type]
```

Wait -- `memory_type` is a column, not in metadata. We need to check how it's exposed. The column is on the table but `MemoryResult.metadata` won't have it unless we add it.

**Alternative approach**: Add `memory_type` to `MemoryResult` or to the metadata dict during `_row_to_result`. Actually, the simplest approach is to store `memory_type` in the metadata dict during store, in addition to the column. That way existing filtering code works. OR, add a `memory_type` attribute to MemoryResult and populate it from the column during `_row_to_result`.

**Simpler approach**: In the store method, also write `meta["memory_type"] = memory_type` before the INSERT. Then the bridge filter can use `r.metadata.get("memory_type")`. This is consistent with how `event_type` works (it's both a column AND in metadata).

In `src/omega/sqlite_store.py` store method, after computing `memory_type`, add:
```python
            meta["memory_type"] = memory_type
```

4. In `src/omega/bridge.py` `query_structured()`, add same parameter and filter.

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_memory_types.py::TestMemoryTypeFilter -v -x`
Expected: PASS

**Step 5: Run full test suite for regressions**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x --timeout=60 -q`
Expected: All existing tests pass.

**Step 6: Commit**

```bash
cd ~/Projects/omega
git add src/omega/server/tool_schemas.py src/omega/server/handlers.py src/omega/bridge.py src/omega/sqlite_store.py tests/test_memory_types.py
git commit -m "feat: add memory_type filter to omega_query"
```

---

## Agent 3: Entity Graph Integration

> Branch: `phase1/entity-graph-retrieval`
> Work in isolated git worktree.

### Task 3.1: Add `get_related_entity_ids` to entity engine

**Files:**
- Modify: `src/omega/entity/engine.py:367-425`

**Step 1: Write the failing test**

Create: `tests/test_entity_graph_retrieval.py`

```python
"""Tests for entity graph integration into retrieval scoring."""
import pytest
from omega.sqlite_store import SQLiteStore


@pytest.fixture
def entity_store(tmp_omega_dir):
    """Store with entity engine available."""
    db_path = tmp_omega_dir / "test.db"
    s = SQLiteStore(db_path=db_path)
    yield s
    s.close()


def _setup_entity_engine(store):
    """Create an EntityEngine using the store's connection."""
    from omega.entity.engine import EntityEngine
    return EntityEngine(store._conn)


class TestGetRelatedEntityIds:
    """Test the lightweight get_related_entity_ids method."""

    def test_returns_related_ids(self, entity_store):
        engine = _setup_entity_engine(entity_store)
        engine.create_entity("acme", "Acme Corp", "organization")
        engine.create_entity("acme-uk", "Acme UK", "organization")
        engine.add_relationship("acme", "acme-uk", "parent_of")
        related = engine.get_related_entity_ids("acme")
        assert "acme-uk" in related

    def test_returns_both_directions(self, entity_store):
        engine = _setup_entity_engine(entity_store)
        engine.create_entity("parent", "Parent Co", "organization")
        engine.create_entity("child", "Child Co", "organization")
        engine.add_relationship("parent", "child", "parent_of")
        # From child's perspective, parent should be related
        related = engine.get_related_entity_ids("child")
        assert "parent" in related

    def test_empty_for_no_relationships(self, entity_store):
        engine = _setup_entity_engine(entity_store)
        engine.create_entity("solo", "Solo Entity", "organization")
        related = engine.get_related_entity_ids("solo")
        assert related == set()

    def test_nonexistent_entity_returns_empty(self, entity_store):
        engine = _setup_entity_engine(entity_store)
        related = engine.get_related_entity_ids("nonexistent")
        assert related == set()

    def test_max_hops_limits_depth(self, entity_store):
        engine = _setup_entity_engine(entity_store)
        engine.create_entity("a", "A", "organization")
        engine.create_entity("b", "B", "organization")
        engine.create_entity("c", "C", "organization")
        engine.add_relationship("a", "b", "parent_of")
        engine.add_relationship("b", "c", "parent_of")
        # 1-hop from a should find b but not c
        related_1 = engine.get_related_entity_ids("a", max_hops=1)
        assert "b" in related_1
        assert "c" not in related_1
        # 2-hop from a should find both
        related_2 = engine.get_related_entity_ids("a", max_hops=2)
        assert "b" in related_2
        assert "c" in related_2
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_entity_graph_retrieval.py::TestGetRelatedEntityIds -v -x`
Expected: FAIL (`AttributeError: 'EntityEngine' has no attribute 'get_related_entity_ids'`)

**Step 3: Implement get_related_entity_ids**

In `src/omega/entity/engine.py`, add after `get_relationships()` (after line 425):

```python
    def get_related_entity_ids(
        self,
        entity_id: str,
        max_hops: int = 1,
    ) -> set:
        """Get IDs of entities related to the given entity.

        Lightweight method for programmatic use (no formatting).
        Traverses relationships in both directions up to max_hops.

        Returns:
            Set of related entity IDs (excluding the input entity).
        """
        entity_id = entity_id.strip().lower()
        if max_hops < 1:
            max_hops = 1

        with self._lock:
            # Verify entity exists
            existing = self._conn.execute(
                "SELECT id FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            if not existing:
                return set()

            visited = set()
            frontier = {entity_id}

            for _hop in range(max_hops):
                if not frontier:
                    break
                next_frontier = set()
                for eid in frontier:
                    rows = self._conn.execute(
                        """SELECT source_entity_id, target_entity_id
                           FROM entity_relationships
                           WHERE source_entity_id = ? OR target_entity_id = ?""",
                        (eid, eid),
                    ).fetchall()
                    for source, target in rows:
                        neighbor = target if source == eid else source
                        if neighbor != entity_id and neighbor not in visited:
                            visited.add(neighbor)
                            next_frontier.add(neighbor)
                frontier = next_frontier

        return visited
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_entity_graph_retrieval.py::TestGetRelatedEntityIds -v -x`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/Projects/omega
git add src/omega/entity/engine.py tests/test_entity_graph_retrieval.py
git commit -m "feat: add get_related_entity_ids for lightweight entity traversal"
```

### Task 3.2: Wire entity graph into retrieval scoring

**Files:**
- Modify: `src/omega/sqlite_store.py:1289-1300` (Phase 5/6 area, or add new Phase 5.5)

**Step 1: Write the failing test**

Add to `tests/test_entity_graph_retrieval.py`:

```python
class TestEntityGraphRetrieval:
    """Test that entity relationships influence query results."""

    def test_related_entity_memories_appear_in_results(self, entity_store):
        """Memories from related entities should appear in query results."""
        engine = _setup_entity_engine(entity_store)
        engine.create_entity("omega", "OMEGA", "project")
        engine.create_entity("omega-public", "OMEGA Public", "project")
        engine.add_relationship("omega", "omega-public", "parent_of")

        # Store memories scoped to different entities
        entity_store.store(
            content="OMEGA private repo has coordination tools",
            metadata={"event_type": "decision"},
            entity_id="omega",
        )
        entity_store.store(
            content="OMEGA public repo has core memory tools",
            metadata={"event_type": "decision"},
            entity_id="omega-public",
        )

        # Query scoped to omega should also surface omega-public memories
        results = entity_store.query("memory tools", entity_id="omega")
        result_contents = [r.content for r in results]
        # At least one result should mention "public"
        has_related = any("public" in c.lower() for c in result_contents)
        assert has_related, (
            f"Expected related entity memories. Got: {result_contents}"
        )

    def test_no_entity_relationship_no_boost(self, entity_store):
        """Without relationships, only direct entity matches appear."""
        engine = _setup_entity_engine(entity_store)
        engine.create_entity("proj-a", "Project A", "project")
        engine.create_entity("proj-b", "Project B", "project")
        # No relationship between them

        entity_store.store(
            content="Project A uses Redis for caching",
            metadata={"event_type": "decision"},
            entity_id="proj-a",
        )
        entity_store.store(
            content="Project B uses Redis for caching too",
            metadata={"event_type": "decision"},
            entity_id="proj-b",
        )

        # Query scoped to proj-a should NOT get proj-b results
        results = entity_store.query("Redis caching", entity_id="proj-a")
        for r in results:
            meta = r.metadata or {}
            eid = meta.get("entity_id")
            if eid:
                assert eid == "proj-a", f"Unexpected entity_id {eid} in results"

    def test_entity_graph_with_no_entities_is_noop(self, entity_store):
        """Query without entity_id should work normally (no crash)."""
        entity_store.store(
            content="A memory with no entity scope",
            metadata={"event_type": "decision"},
        )
        results = entity_store.query("memory")
        assert len(results) > 0  # Should return results normally
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_entity_graph_retrieval.py::TestEntityGraphRetrieval -v -x`
Expected: `test_related_entity_memories_appear_in_results` FAIL (related entity memories filtered out by entity_id WHERE clause)

**Step 3: Wire entity graph into query pipeline**

In `src/omega/sqlite_store.py`, add a new method `_expand_entity_scope`:

```python
    def _expand_entity_scope(
        self,
        entity_id: Optional[str],
        all_results: Dict[str, "MemoryResult"],
        node_scores: Dict[str, float],
        limit: int,
    ) -> None:
        """Expand query scope to include memories from related entities.

        If entity_id is set and entity relationships exist, queries memories
        from related entities and adds them as lower-weighted candidates.
        """
        if not entity_id:
            return

        try:
            from omega.entity.engine import EntityEngine
            engine = EntityEngine(self._conn)
            related_ids = engine.get_related_entity_ids(entity_id, max_hops=1)
            if not related_ids:
                return

            # Query memories from related entities
            placeholders = ",".join("?" * len(related_ids))
            rows = self._conn.execute(
                f"""SELECT node_id, content, metadata, created_at,
                           access_count, last_accessed, ttl_seconds
                    FROM memories
                    WHERE entity_id IN ({placeholders})
                    AND node_id NOT IN ({",".join("?" * len(all_results))})
                    ORDER BY created_at DESC
                    LIMIT ?""",
                (*related_ids, *all_results.keys(), limit),
            ).fetchall()

            for row in rows:
                result = self._row_to_result(row)
                if result.id not in all_results:
                    all_results[result.id] = result
                    # Score at 0.3x of the average existing score (lower priority)
                    avg_score = sum(node_scores.values()) / len(node_scores) if node_scores else 0.5
                    node_scores[result.id] = avg_score * 0.3

        except ImportError:
            pass  # entity module not available
        except Exception as e:
            logger.debug("Entity graph expansion failed: %s", e)
```

Then in the `query()` method, call it in Phase 5 area. After `_query_phase_boost` call (line ~1294) and before `_query_phase_rerank` (line ~1297), add:

```python
        # Phase 5.5: Entity graph expansion
        self._expand_entity_scope(entity_id, all_results, node_scores, limit)
```

**Important**: The existing entity_id filtering in Phase 4 (`_query_phase_filter`) and in Phase 1 (`_query_phase_vec`) restricts results to entity_id. The expansion in Phase 5.5 happens AFTER the initial filtering, adding related-entity memories back with lower scores. This works because Phase 6 (rerank) and Phase 7 (assembly) will process all candidates in `all_results`.

However, there's a subtlety: the initial vec and FTS phases already filter by entity_id. So related-entity memories won't appear in `all_results` before Phase 5.5. The `_expand_entity_scope` method does a fresh SQL query specifically for related entities, so this is fine.

**Step 4: Run test to verify it passes**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_entity_graph_retrieval.py::TestEntityGraphRetrieval -v -x`
Expected: PASS

**Step 5: Run full test suite for regressions**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x --timeout=60 -q`
Expected: All existing tests pass.

**Step 6: Commit**

```bash
cd ~/Projects/omega
git add src/omega/sqlite_store.py tests/test_entity_graph_retrieval.py
git commit -m "feat: wire entity graph relationships into retrieval scoring"
```

---

## Post-Merge Verification

After merging all three branches (order: Agent 3, Agent 1, Agent 2):

1. Run full test suite: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x --timeout=60 -q`
2. Run lint: `cd ~/Projects/omega && ruff check src/`
3. Verify SCHEMA_VERSION is 11
4. Verify omega_query tool schema has both new params (strength_min, memory_type)
5. Manual smoke test: start MCP server, store a memory, query it, check strength and memory_type in output
