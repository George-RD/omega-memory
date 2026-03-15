# Phase 3: Automatic Entity Extraction -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically extract entities (people, projects, tools, technologies) and relationships from memory content on every store call, populating the entity graph without manual `omega_entity_create`.

**Architecture:** Async post-store extraction using Claude Haiku. A new `extraction.py` module handles the LLM call and entity resolution. Bridge `auto_capture()` fires extraction in a background thread after store, adding zero latency to the store path. Graceful degradation when API key is missing or Haiku is unavailable.

**Tech Stack:** Python 3.11, `anthropic` SDK (already a dependency), threading, existing EntityManager API.

---

### Task 1: Extend Entity Types and Relationship Types

**Files:**
- Modify: `src/omega/entity/engine.py:23-46`
- Test: `tests/test_entity_extraction.py` (create)

**Context:** The entity engine validates types against frozen sets. Current types are business-focused (company, LLC, etc.). Auto-extraction needs broader types: person, project, tool, concept, technology, service. Similarly, relationship types need: uses, works_on, depends_on, mentions, created_by.

**Step 1: Write failing tests for new entity types**

Create `tests/test_entity_extraction.py`:

```python
"""Tests for Phase 3: automatic entity extraction."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_entity_singleton():
    """Reset entity manager singleton before and after each test."""
    from omega.entity.engine import reset_entity_manager
    reset_entity_manager()
    yield
    reset_entity_manager()


class TestExtendedEntityTypes:
    """Entity engine accepts new types for auto-extraction."""

    @pytest.mark.parametrize("etype", ["person", "project", "tool", "concept", "technology", "service"])
    def test_create_entity_with_new_type(self, tmp_omega_dir, etype):
        from omega.entity.engine import get_entity_manager
        em = get_entity_manager(tmp_omega_dir / "test.db")
        result = em.create_entity(f"test-{etype}", f"Test {etype}", etype)
        assert "Created entity" in result
        assert "Error" not in result


class TestExtendedRelationshipTypes:
    """Entity engine accepts new relationship types."""

    @pytest.mark.parametrize("rtype", ["uses", "works_on", "depends_on", "mentions", "created_by"])
    def test_add_relationship_with_new_type(self, tmp_omega_dir, rtype):
        from omega.entity.engine import get_entity_manager
        em = get_entity_manager(tmp_omega_dir / "test.db")
        em.create_entity("source-ent", "Source", "project")
        em.create_entity("target-ent", "Target", "tool")
        result = em.add_relationship("source-ent", "target-ent", rtype)
        assert "Added relationship" in result
        assert "Error" not in result
```

**Step 2: Run tests to verify they fail**

Run: `python3.11 -m pytest tests/test_entity_extraction.py -v`
Expected: FAIL -- `"person"` not in `ENTITY_TYPES`, `"uses"` not in `RELATIONSHIP_TYPES`

**Step 3: Add new types to entity engine**

In `src/omega/entity/engine.py`, replace the `ENTITY_TYPES` frozenset (line 23-35):

```python
ENTITY_TYPES = frozenset({
    "company",
    "llc",
    "s_corp",
    "c_corp",
    "foundation",
    "startup",
    "trust",
    "partnership",
    "sole_proprietorship",
    "nonprofit",
    "other",
    # Phase 3: auto-extraction types
    "person",
    "project",
    "tool",
    "concept",
    "technology",
    "service",
})
```

Replace `RELATIONSHIP_TYPES` frozenset (line 38-46):

```python
RELATIONSHIP_TYPES = frozenset({
    "parent_of",
    "subsidiary_of",
    "owned_by",
    "acquired_by",
    "partner_of",
    "investor_in",
    "operated_by",
    # Phase 3: auto-extraction relationship types
    "uses",
    "works_on",
    "depends_on",
    "mentions",
    "created_by",
})
```

**Step 4: Run tests to verify they pass**

Run: `python3.11 -m pytest tests/test_entity_extraction.py -v`
Expected: PASS (all parametrized tests)

**Step 5: Run full test suite to check for regressions**

Run: `python3.11 -m pytest tests/ --timeout=30 --ignore=tests/test_handlers_decision_trail.py --ignore=tests/test_router.py -q`
Expected: All pass (type sets are additive, no existing code breaks)

**Step 6: Commit**

```bash
git add src/omega/entity/engine.py tests/test_entity_extraction.py
git commit -m "feat(entity): extend entity and relationship types for auto-extraction"
```

---

### Task 2: Create Entity Extraction Module

**Files:**
- Create: `src/omega/entity/extraction.py`
- Modify: `tests/test_entity_extraction.py`

**Context:** New module with two functions: (1) `extract_entities()` calls Claude Haiku to extract entities and relationships from text, (2) `resolve_and_link()` deduplicates against existing entities and creates/links them. Follow the pattern in `src/omega/task_utils.py:96-136` for Haiku calls with graceful fallback.

**Step 1: Write failing tests for extract_entities**

Append to `tests/test_entity_extraction.py`:

```python
import json
from unittest.mock import patch, MagicMock


class TestExtractEntities:
    """Tests for the Haiku-powered entity extraction."""

    def test_returns_empty_when_no_api_key(self):
        from omega.entity.extraction import extract_entities
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            result = extract_entities("Jason deployed React to Vercel", "decision")
        assert result == {"entities": [], "relationships": []}

    def test_returns_empty_for_short_content(self):
        from omega.entity.extraction import extract_entities
        result = extract_entities("ok", "decision")
        assert result == {"entities": [], "relationships": []}

    def test_returns_empty_for_skipped_event_types(self):
        from omega.entity.extraction import extract_entities
        for etype in ("file_summary", "code_chunk", "branch_switch", "session_respawn"):
            result = extract_entities("Jason deployed React to Vercel", etype)
            assert result == {"entities": [], "relationships": []}, f"Should skip {etype}"

    def test_returns_parsed_entities_from_haiku(self):
        """Mock the Anthropic API to verify parsing logic."""
        from omega.entity.extraction import extract_entities

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "entities": [
                {"name": "Jason", "type": "person"},
                {"name": "React", "type": "technology"},
            ],
            "relationships": [
                {"source": "Jason", "target": "React", "type": "uses"},
            ],
        })

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("omega.entity.extraction.anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.Anthropic.return_value = mock_client
                mock_client.messages.create.return_value = mock_response

                result = extract_entities("Jason deployed React to Vercel", "decision")

        assert len(result["entities"]) == 2
        assert result["entities"][0]["name"] == "Jason"
        assert result["entities"][0]["type"] == "person"
        assert len(result["relationships"]) == 1

    def test_returns_empty_on_api_error(self):
        from omega.entity.extraction import extract_entities

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("omega.entity.extraction.anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.Anthropic.return_value = mock_client
                mock_client.messages.create.side_effect = Exception("API timeout")

                result = extract_entities("Jason deployed React to Vercel", "decision")

        assert result == {"entities": [], "relationships": []}

    def test_returns_empty_on_invalid_json(self):
        from omega.entity.extraction import extract_entities

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "not valid json {{"

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("omega.entity.extraction.anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.Anthropic.return_value = mock_client
                mock_client.messages.create.return_value = mock_response

                result = extract_entities("Jason deployed React to Vercel", "decision")

        assert result == {"entities": [], "relationships": []}
```

**Step 2: Run tests to verify they fail**

Run: `python3.11 -m pytest tests/test_entity_extraction.py::TestExtractEntities -v`
Expected: FAIL -- `omega.entity.extraction` does not exist

**Step 3: Implement extract_entities**

Create `src/omega/entity/extraction.py`:

```python
"""OMEGA Entity Extraction -- Auto-extract entities from memory content via LLM.

Calls Claude Haiku on store to extract entities (people, projects, tools, etc.)
and relationships. Gracefully degrades when API key is missing or call fails.
"""

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("omega.entity.extraction")

# Lazy import -- only loaded when extraction actually runs
anthropic: Any = None

_EMPTY_RESULT: Dict[str, list] = {"entities": [], "relationships": []}

# Event types too low-value for entity extraction (high volume, low signal)
_SKIP_EVENT_TYPES = frozenset({
    "file_summary", "code_chunk", "branch_switch", "session_respawn",
    "session_summary",
})

# Minimum content length worth extracting from
_MIN_CONTENT_LENGTH = 20

# Throttle: minimum seconds between extraction calls
_THROTTLE_INTERVAL = 2.0
_last_extraction_time = 0.0
_throttle_lock = threading.Lock()

_EXTRACTION_PROMPT = """\
Extract named entities and relationships from this memory content.

Return ONLY valid JSON with this exact structure:
{"entities": [{"name": "...", "type": "..."}], "relationships": [{"source": "...", "target": "...", "type": "..."}]}

Entity types (pick the best fit): person, project, tool, technology, service, company, concept
Relationship types (pick the best fit): uses, works_on, depends_on, mentions, created_by

Rules:
- Only extract entities that are clearly named (not generic words like "the app" or "the server")
- Names should be proper nouns or specific identifiers
- Keep entity names short (1-3 words)
- Only extract relationships between entities you extracted
- If no entities are found, return {"entities": [], "relationships": []}
- Do NOT wrap in markdown code blocks, return raw JSON only"""


def extract_entities(content: str, event_type: str) -> Dict[str, list]:
    """Extract entities and relationships from content via Claude Haiku.

    Returns {"entities": [...], "relationships": [...]} or empty result on any failure.
    """
    global anthropic

    # Skip low-value event types
    if event_type in _SKIP_EVENT_TYPES:
        return _EMPTY_RESULT

    # Skip short content
    if len(content) < _MIN_CONTENT_LENGTH:
        return _EMPTY_RESULT

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _EMPTY_RESULT

    # Check env toggle
    if os.environ.get("OMEGA_ENTITY_EXTRACTION", "").lower() in ("0", "false", "off"):
        return _EMPTY_RESULT

    # Throttle
    global _last_extraction_time
    now = time.monotonic()
    with _throttle_lock:
        if now - _last_extraction_time < _THROTTLE_INTERVAL:
            logger.debug("Entity extraction throttled")
            return _EMPTY_RESULT
        _last_extraction_time = now

    # Lazy import anthropic
    if anthropic is None:
        try:
            import anthropic as _anthropic
            anthropic = _anthropic
        except ImportError:
            logger.debug("anthropic package not installed, skipping entity extraction")
            return _EMPTY_RESULT

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=3.0)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": content[:2000]}],
            system=_EXTRACTION_PROMPT,
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)

        # Validate structure
        entities = parsed.get("entities", [])
        relationships = parsed.get("relationships", [])

        # Filter to valid entries
        valid_entities = []
        for e in entities:
            if isinstance(e, dict) and e.get("name") and e.get("type"):
                valid_entities.append({
                    "name": str(e["name"]).strip(),
                    "type": str(e["type"]).strip().lower(),
                })

        valid_relationships = []
        for r in relationships:
            if isinstance(r, dict) and r.get("source") and r.get("target") and r.get("type"):
                valid_relationships.append({
                    "source": str(r["source"]).strip(),
                    "target": str(r["target"]).strip(),
                    "type": str(r["type"]).strip().lower(),
                })

        return {"entities": valid_entities, "relationships": valid_relationships}

    except Exception as e:
        logger.debug("Entity extraction failed: %s", e)
        return _EMPTY_RESULT
```

**Step 4: Run tests to verify they pass**

Run: `python3.11 -m pytest tests/test_entity_extraction.py::TestExtractEntities -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/omega/entity/extraction.py tests/test_entity_extraction.py
git commit -m "feat(entity): add extract_entities() with Haiku LLM call"
```

---

### Task 3: Implement resolve_and_link

**Files:**
- Modify: `src/omega/entity/extraction.py`
- Modify: `tests/test_entity_extraction.py`

**Context:** After Haiku extracts entities, we need to deduplicate against existing entities (case-insensitive name match), create new ones, link the memory, and create relationship edges. Uses existing `EntityManager.create_entity()`, `add_relationship()`, and `list_entity_ids()` (added in Phase 2).

**Step 1: Write failing tests for resolve_and_link**

Append to `tests/test_entity_extraction.py`:

```python
class TestResolveAndLink:
    """Tests for entity dedup, creation, and memory linking."""

    @pytest.fixture
    def store(self, tmp_omega_dir):
        from omega.sqlite_store import SQLiteStore
        db_path = tmp_omega_dir / "test.db"
        s = SQLiteStore(db_path=db_path)
        yield s
        s.close()

    @pytest.fixture
    def em(self, store):
        from omega.entity.engine import get_entity_manager
        return get_entity_manager(Path(store.db_path))

    def test_creates_new_entities(self, store, em):
        from omega.entity.extraction import resolve_and_link
        node_id = store.store(content="Test memory", metadata={"event_type": "decision"})
        extraction = {
            "entities": [
                {"name": "Jason", "type": "person"},
                {"name": "React", "type": "technology"},
            ],
            "relationships": [],
        }
        stats = resolve_and_link(store, em, node_id, extraction)
        assert stats["entities_created"] == 2
        assert stats["entities_linked"] >= 1

    def test_links_to_existing_entity_by_name(self, store, em):
        """If entity with same lowercased name exists, link to it instead of creating."""
        from omega.entity.extraction import resolve_and_link
        em.create_entity("react-tech", "React", "technology")
        node_id = store.store(content="Test memory", metadata={"event_type": "decision"})
        extraction = {
            "entities": [{"name": "react", "type": "technology"}],
            "relationships": [],
        }
        stats = resolve_and_link(store, em, node_id, extraction)
        assert stats["entities_created"] == 0
        assert stats["entities_linked"] == 1

        # Memory should be linked to the existing entity
        row = store._conn.execute(
            "SELECT entity_id FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        assert row[0] == "react-tech"

    def test_creates_relationships(self, store, em):
        from omega.entity.extraction import resolve_and_link
        node_id = store.store(content="Test memory", metadata={"event_type": "decision"})
        extraction = {
            "entities": [
                {"name": "Jason", "type": "person"},
                {"name": "React", "type": "technology"},
            ],
            "relationships": [
                {"source": "Jason", "target": "React", "type": "uses"},
            ],
        }
        stats = resolve_and_link(store, em, node_id, extraction)
        assert stats["relationships_created"] == 1

    def test_skips_invalid_entity_type(self, store, em):
        """Invalid entity types are silently skipped."""
        from omega.entity.extraction import resolve_and_link
        node_id = store.store(content="Test memory", metadata={"event_type": "decision"})
        extraction = {
            "entities": [{"name": "Something", "type": "invalid_type_xyz"}],
            "relationships": [],
        }
        stats = resolve_and_link(store, em, node_id, extraction)
        assert stats["entities_created"] == 0

    def test_empty_extraction_returns_zeros(self, store, em):
        from omega.entity.extraction import resolve_and_link
        node_id = store.store(content="Test memory", metadata={"event_type": "decision"})
        stats = resolve_and_link(store, em, node_id, {"entities": [], "relationships": []})
        assert stats["entities_created"] == 0
        assert stats["entities_linked"] == 0
        assert stats["relationships_created"] == 0
```

**Step 2: Run tests to verify they fail**

Run: `python3.11 -m pytest tests/test_entity_extraction.py::TestResolveAndLink -v`
Expected: FAIL -- `resolve_and_link` not defined

**Step 3: Implement resolve_and_link**

Append to `src/omega/entity/extraction.py`:

```python
def _slugify(name: str) -> str:
    """Convert entity name to a URL-safe entity_id."""
    import re
    slug = name.strip().lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:64] or "unknown"


def resolve_and_link(
    store: Any,
    em: Any,
    node_id: str,
    extraction: Dict[str, list],
) -> Dict[str, int]:
    """Create/find entities from extraction results, link memory, create relationships.

    Args:
        store: SQLiteStore instance
        em: EntityManager instance
        node_id: The memory node_id to link entities to
        extraction: Output from extract_entities()

    Returns:
        {"entities_created": int, "entities_linked": int, "relationships_created": int}
    """
    from omega.entity.engine import ENTITY_TYPES, RELATIONSHIP_TYPES

    stats = {"entities_created": 0, "entities_linked": 0, "relationships_created": 0}
    entities = extraction.get("entities", [])
    relationships = extraction.get("relationships", [])

    if not entities:
        return stats

    # Build lookup of existing entities: lowercased_name -> entity_id
    try:
        existing = em.list_entity_ids()  # [(entity_id, name), ...]
    except Exception as e:
        logger.debug("Failed to list entities: %s", e)
        existing = []
    name_to_id: Dict[str, str] = {}
    for eid, ename in existing:
        name_to_id[ename.strip().lower()] = eid

    # Resolve each extracted entity: find existing or create new
    # Maps extracted name -> resolved entity_id
    resolved: Dict[str, str] = {}
    first_entity_id: Optional[str] = None

    for entity in entities:
        name = entity.get("name", "").strip()
        etype = entity.get("type", "other").strip().lower()
        if not name:
            continue
        if etype not in ENTITY_TYPES:
            logger.debug("Skipping entity with invalid type: %s (%s)", name, etype)
            continue

        name_lower = name.lower()

        if name_lower in name_to_id:
            # Existing entity found
            resolved[name] = name_to_id[name_lower]
            stats["entities_linked"] += 1
        else:
            # Create new entity
            entity_id = _slugify(name)
            # Avoid collision with existing IDs
            base_id = entity_id
            suffix = 1
            while entity_id in {eid for eid, _ in existing}:
                entity_id = f"{base_id}-{suffix}"
                suffix += 1

            result = em.create_entity(entity_id, name, etype, metadata={"source": "auto_extraction"})
            if "Error" not in result:
                resolved[name] = entity_id
                name_to_id[name_lower] = entity_id
                existing.append((entity_id, name))
                stats["entities_created"] += 1
                stats["entities_linked"] += 1
            else:
                logger.debug("Failed to create entity %s: %s", name, result)

        # Track first entity for memory linking
        if first_entity_id is None and name in resolved:
            first_entity_id = resolved[name]

    # Link memory to first extracted entity (if memory doesn't already have one)
    if first_entity_id:
        try:
            row = store._conn.execute(
                "SELECT entity_id FROM memories WHERE node_id = ?", (node_id,)
            ).fetchone()
            if row and not row[0]:
                store._conn.execute(
                    "UPDATE memories SET entity_id = ? WHERE node_id = ?",
                    (first_entity_id, node_id),
                )
                store._conn.commit()
        except Exception as e:
            logger.debug("Failed to link memory %s to entity %s: %s", node_id, first_entity_id, e)

    # Create relationships
    for rel in relationships:
        source_name = rel.get("source", "").strip()
        target_name = rel.get("target", "").strip()
        rtype = rel.get("type", "").strip().lower()

        if not source_name or not target_name or not rtype:
            continue
        if rtype not in RELATIONSHIP_TYPES:
            continue
        if source_name not in resolved or target_name not in resolved:
            continue

        source_id = resolved[source_name]
        target_id = resolved[target_name]
        if source_id == target_id:
            continue

        result = em.add_relationship(source_id, target_id, rtype)
        if "Error" not in result:
            stats["relationships_created"] += 1
        else:
            logger.debug("Failed to add relationship: %s", result)

    return stats
```

**Step 4: Run tests to verify they pass**

Run: `python3.11 -m pytest tests/test_entity_extraction.py::TestResolveAndLink -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/omega/entity/extraction.py tests/test_entity_extraction.py
git commit -m "feat(entity): add resolve_and_link() for entity dedup and memory linking"
```

---

### Task 4: Wire Async Extraction into Bridge auto_capture

**Files:**
- Modify: `src/omega/bridge.py:1207-1220` (insert Phase 3.1 after Phase 3.5, before Phase 4)
- Modify: `tests/test_entity_extraction.py`

**Context:** `auto_capture()` in `bridge.py` has 5+ phases. Entity extraction runs as Phase 3.1, after the memory is stored (Phase 3) but before auto-relate (Phase 4). It fires in a daemon background thread so store returns immediately. The key insertion point is between the milestone check (line 1206) and Phase 3.5 (line 1208).

**Step 1: Write failing test for async extraction in bridge**

Append to `tests/test_entity_extraction.py`:

```python
import time


class TestBridgeEntityExtraction:
    """Tests for entity extraction wired into auto_capture."""

    @pytest.fixture
    def store(self, tmp_omega_dir):
        from omega.sqlite_store import SQLiteStore
        db_path = tmp_omega_dir / "test.db"
        s = SQLiteStore(db_path=db_path)
        yield s
        s.close()

    def test_schedule_entity_extraction_exists(self):
        """The scheduling function exists in bridge module."""
        from omega.bridge import _schedule_entity_extraction
        assert callable(_schedule_entity_extraction)

    def test_schedule_skips_without_api_key(self, store, tmp_omega_dir):
        """Scheduling with no API key is a no-op (no crash)."""
        from omega.bridge import _schedule_entity_extraction
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ["OMEGA_HOME"] = str(tmp_omega_dir)
            # Should not raise
            _schedule_entity_extraction(store, "test-node-id", "Jason uses React", "decision")

    def test_extraction_disabled_by_env(self, store, tmp_omega_dir):
        """OMEGA_ENTITY_EXTRACTION=0 disables extraction."""
        from omega.bridge import _schedule_entity_extraction
        with patch.dict(os.environ, {"OMEGA_ENTITY_EXTRACTION": "0", "OMEGA_HOME": str(tmp_omega_dir)}):
            _schedule_entity_extraction(store, "test-node-id", "Jason uses React", "decision")
            # No crash, no extraction
```

**Step 2: Run tests to verify they fail**

Run: `python3.11 -m pytest tests/test_entity_extraction.py::TestBridgeEntityExtraction -v`
Expected: FAIL -- `_schedule_entity_extraction` not found

**Step 3: Add _schedule_entity_extraction to bridge.py**

In `src/omega/bridge.py`, add the scheduling function near the top of the file (after imports, around line 50):

```python
def _schedule_entity_extraction(
    store: Any,
    node_id: str,
    content: str,
    event_type: str,
) -> None:
    """Fire entity extraction in a background daemon thread.

    Non-blocking. Silently skipped if API key missing or extraction disabled.
    """
    import os as _os
    if _os.environ.get("OMEGA_ENTITY_EXTRACTION", "").lower() in ("0", "false", "off"):
        return
    if not _os.environ.get("ANTHROPIC_API_KEY"):
        return

    def _run():
        try:
            from omega.entity.extraction import extract_entities, resolve_and_link
            from omega.entity.engine import get_entity_manager
            from pathlib import Path as _Path

            extraction = extract_entities(content, event_type)
            if extraction["entities"]:
                em = get_entity_manager(_Path(store.db_path))
                resolve_and_link(store, em, node_id, extraction)
        except Exception as e:
            logger.debug("Async entity extraction failed: %s", e)

    t = threading.Thread(target=_run, daemon=True, name="entity-extraction")
    t.start()
```

Then insert Phase 3.1 into `auto_capture()`. Find the milestone check block ending at line ~1206 and add after it, before Phase 3.5:

```python
    # ------------------------------------------------------------------
    # Phase 3.1: Async entity extraction (non-blocking)
    # ------------------------------------------------------------------
    _schedule_entity_extraction(store, node_id, content, event_type)
```

**Step 4: Run tests to verify they pass**

Run: `python3.11 -m pytest tests/test_entity_extraction.py::TestBridgeEntityExtraction -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/omega/bridge.py tests/test_entity_extraction.py
git commit -m "feat(entity): wire async entity extraction into auto_capture Phase 3.1"
```

---

### Task 5: Integration Tests and Edge Cases

**Files:**
- Modify: `tests/test_entity_extraction.py`

**Context:** Add integration tests that verify the full flow: auto_capture → background extraction → entity created → memory linked. Also test edge cases: throttling, duplicate entity names, missing entities in relationships.

**Step 1: Write integration and edge case tests**

Append to `tests/test_entity_extraction.py`:

```python
class TestResolveAndLinkEdgeCases:
    """Edge cases for entity resolution."""

    @pytest.fixture
    def store(self, tmp_omega_dir):
        from omega.sqlite_store import SQLiteStore
        db_path = tmp_omega_dir / "test.db"
        s = SQLiteStore(db_path=db_path)
        yield s
        s.close()

    @pytest.fixture
    def em(self, store):
        from omega.entity.engine import get_entity_manager
        return get_entity_manager(Path(store.db_path))

    def test_skips_relationship_with_unknown_entity(self, store, em):
        """Relationships referencing unresolved entities are skipped."""
        from omega.entity.extraction import resolve_and_link
        node_id = store.store(content="Test memory", metadata={"event_type": "decision"})
        extraction = {
            "entities": [{"name": "Jason", "type": "person"}],
            "relationships": [{"source": "Jason", "target": "Unknown", "type": "uses"}],
        }
        stats = resolve_and_link(store, em, node_id, extraction)
        assert stats["relationships_created"] == 0

    def test_does_not_overwrite_existing_entity_id(self, store, em):
        """If memory already has entity_id, extraction doesn't overwrite it."""
        from omega.entity.extraction import resolve_and_link
        node_id = store.store(
            content="Test memory",
            metadata={"event_type": "decision"},
            entity_id="existing-entity",
        )
        extraction = {
            "entities": [{"name": "New Entity", "type": "project"}],
            "relationships": [],
        }
        stats = resolve_and_link(store, em, node_id, extraction)
        # Entity is created but memory keeps original entity_id
        row = store._conn.execute(
            "SELECT entity_id FROM memories WHERE node_id = ?", (node_id,)
        ).fetchone()
        assert row[0] == "existing-entity"

    def test_case_insensitive_dedup(self, store, em):
        """Entity matching is case-insensitive."""
        from omega.entity.extraction import resolve_and_link
        em.create_entity("react-tech", "React", "technology")
        node_id = store.store(content="Test memory", metadata={"event_type": "decision"})

        # "REACT" should match existing "React"
        extraction = {
            "entities": [{"name": "REACT", "type": "technology"}],
            "relationships": [],
        }
        stats = resolve_and_link(store, em, node_id, extraction)
        assert stats["entities_created"] == 0
        assert stats["entities_linked"] == 1

    def test_slugify_generates_valid_ids(self):
        from omega.entity.extraction import _slugify
        assert _slugify("Jason Sosa") == "jason-sosa"
        assert _slugify("React.js") == "react-js"
        assert _slugify("C++") == "c"
        assert _slugify("  spaces  ") == "spaces"


class TestThrottling:
    """Tests for extraction throttle."""

    def test_throttle_skips_rapid_calls(self):
        """Second call within throttle interval returns empty."""
        from omega.entity import extraction
        # Reset throttle state
        extraction._last_extraction_time = time.monotonic()

        result = extraction.extract_entities("Jason deployed React to Vercel", "decision")
        assert result == {"entities": [], "relationships": []}
```

**Step 2: Run tests**

Run: `python3.11 -m pytest tests/test_entity_extraction.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `python3.11 -m pytest tests/ --timeout=30 --ignore=tests/test_handlers_decision_trail.py --ignore=tests/test_router.py -q`
Expected: All pass

**Step 4: Commit**

```bash
git add tests/test_entity_extraction.py
git commit -m "test(entity): add integration and edge case tests for auto-extraction"
```

---

### Task 6: Final Verification and Commit

**Files:**
- All modified files from Tasks 1-5

**Step 1: Run full test suite one more time**

Run: `python3.11 -m pytest tests/ --timeout=30 --ignore=tests/test_handlers_decision_trail.py --ignore=tests/test_router.py -q`
Expected: All pass, no regressions

**Step 2: Verify entity extraction module exports**

Confirm `src/omega/entity/extraction.py` has these public functions:
- `extract_entities(content, event_type) -> dict`
- `resolve_and_link(store, em, node_id, extraction) -> dict`

**Step 3: Quick manual smoke test (optional)**

If `ANTHROPIC_API_KEY` is set:
```python
from omega.entity.extraction import extract_entities
result = extract_entities("Jason deployed the React frontend to Vercel using GitHub Actions", "decision")
print(result)
# Should have entities: Jason (person), React (technology), Vercel (service), GitHub Actions (tool)
```

**Step 4: Final commit if any loose changes**

```bash
git status
# If clean, done. If changes, commit:
git add -A && git commit -m "feat(entity): Phase 3 auto entity extraction complete"
```
