"""Tests for OMEGA Phase 3 -- Automatic Entity Extraction.

Covers:
- Extended entity types (person, project, tool, concept, technology, service)
- Extended relationship types (uses, works_on, depends_on, mentions, created_by)
- extract_entities() -- Haiku NER with graceful degradation
- resolve_and_link() -- entity dedup and memory linking
"""

import json
import os
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from omega.entity.engine import (
    EntityManager,
    reset_entity_manager,
    ENTITY_TYPES,
    RELATIONSHIP_TYPES,
)


@pytest.fixture(autouse=True)
def _reset_entity_singleton():
    reset_entity_manager()
    yield
    reset_entity_manager()


@pytest.fixture
def tmp_omega_dir():
    """Create a temporary OMEGA directory for testing."""
    with tempfile.TemporaryDirectory() as d:
        omega_dir = Path(d)
        old_home = os.environ.get("OMEGA_HOME")
        old_encrypt = os.environ.get("OMEGA_ENCRYPT")
        os.environ["OMEGA_HOME"] = str(omega_dir)
        os.environ["OMEGA_ENCRYPT"] = "0"
        yield omega_dir
        if old_home is not None:
            os.environ["OMEGA_HOME"] = old_home
        else:
            os.environ.pop("OMEGA_HOME", None)
        if old_encrypt is not None:
            os.environ["OMEGA_ENCRYPT"] = old_encrypt
        else:
            os.environ.pop("OMEGA_ENCRYPT", None)
        from omega.crypto import reset_crypto_state
        reset_crypto_state()


@pytest.fixture
def store(tmp_omega_dir):
    from omega.sqlite_store import SQLiteStore
    db_path = tmp_omega_dir / "test.db"
    s = SQLiteStore(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def em(tmp_omega_dir):
    from omega.entity.engine import get_entity_manager
    db_path = tmp_omega_dir / "omega.db"
    return get_entity_manager(db_path)


# ============================================================================
# Extended Entity Types
# ============================================================================

class TestExtendedEntityTypes:
    """Verify new entity types can be created."""

    @pytest.mark.parametrize("etype", [
        "person", "project", "tool", "concept", "technology", "service",
    ])
    def test_create_entity_with_new_type(self, em, etype):
        result = em.create_entity(f"test-{etype}", f"Test {etype}", etype)
        assert "Created entity" in result
        assert etype in result

    def test_new_types_in_frozenset(self):
        """All new types must be in the ENTITY_TYPES frozenset."""
        for etype in ("person", "project", "tool", "concept", "technology", "service"):
            assert etype in ENTITY_TYPES, f"{etype} not in ENTITY_TYPES"


# ============================================================================
# Extended Relationship Types
# ============================================================================

class TestExtendedRelationshipTypes:
    """Verify new relationship types can be used."""

    @pytest.mark.parametrize("rtype", [
        "uses", "works_on", "depends_on", "mentions", "created_by",
    ])
    def test_add_relationship_with_new_type(self, em, rtype):
        em.create_entity("src", "Source", "person")
        em.create_entity("tgt", "Target", "project")
        result = em.add_relationship("src", "tgt", rtype)
        assert "Added relationship" in result
        assert rtype in result

    def test_new_types_in_frozenset(self):
        """All new relationship types must be in RELATIONSHIP_TYPES."""
        for rtype in ("uses", "works_on", "depends_on", "mentions", "created_by"):
            assert rtype in RELATIONSHIP_TYPES, f"{rtype} not in RELATIONSHIP_TYPES"


# ============================================================================
# extract_entities()
# ============================================================================

class TestExtractEntities:
    """Test the extract_entities() function."""

    def _empty_result(self):
        return {"entities": [], "relationships": []}

    def test_returns_empty_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from omega.entity.extraction import extract_entities
        result = extract_entities("This is a long enough test content about React.", "user_message")
        assert result == self._empty_result()

    def test_returns_empty_for_short_content(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from omega.entity.extraction import extract_entities
        result = extract_entities("too short", "user_message")
        assert result == self._empty_result()

    @pytest.mark.parametrize("event_type", [
        "file_summary", "code_chunk", "branch_switch",
        "session_respawn", "session_summary",
    ])
    def test_returns_empty_for_skipped_event_types(self, event_type, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from omega.entity.extraction import extract_entities
        result = extract_entities(
            "This content is long enough to pass the length check.",
            event_type,
        )
        assert result == self._empty_result()

    def test_returns_empty_when_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("OMEGA_ENTITY_EXTRACTION", "0")
        from omega.entity.extraction import extract_entities
        result = extract_entities(
            "This content is long enough to pass the length check.",
            "user_message",
        )
        assert result == self._empty_result()

    def test_returns_parsed_entities_from_haiku(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        # Reset throttle state
        import omega.entity.extraction as ext_mod
        ext_mod._last_call_ts = 0.0

        haiku_response = json.dumps({
            "entities": [
                {"name": "React", "type": "technology"},
                {"name": "Jason", "type": "person"},
            ],
            "relationships": [
                {"source": "Jason", "target": "React", "type": "uses"},
            ],
        })

        with patch("omega.entity.extraction.llm_complete", return_value=haiku_response):
            from omega.entity.extraction import extract_entities
            result = extract_entities(
                "Jason is building a project with React and TypeScript.",
                "user_message",
            )

        assert len(result["entities"]) == 2
        assert result["entities"][0]["name"] == "React"
        assert result["entities"][0]["type"] == "technology"
        assert len(result["relationships"]) == 1
        assert result["relationships"][0]["source"] == "Jason"

    def test_returns_empty_on_api_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import omega.entity.extraction as ext_mod
        ext_mod._last_call_ts = 0.0

        with patch("omega.entity.extraction.llm_complete", return_value=""):
            from omega.entity.extraction import extract_entities
            result = extract_entities(
                "This content is long enough to pass the length check.",
                "user_message",
            )
        assert result == self._empty_result()

    def test_returns_empty_on_invalid_json(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import omega.entity.extraction as ext_mod
        ext_mod._last_call_ts = 0.0

        with patch("omega.entity.extraction.llm_complete", return_value="this is not valid json at all"):
            from omega.entity.extraction import extract_entities
            result = extract_entities(
                "This content is long enough to pass the length check.",
                "user_message",
            )
        assert result == self._empty_result()

    def test_strips_markdown_code_fences(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import omega.entity.extraction as ext_mod
        ext_mod._last_call_ts = 0.0

        raw = json.dumps({
            "entities": [{"name": "Python", "type": "technology"}],
            "relationships": [],
        })
        fenced = f"```json\n{raw}\n```"

        with patch("omega.entity.extraction.llm_complete", return_value=fenced):
            from omega.entity.extraction import extract_entities
            result = extract_entities(
                "We are using Python to build a data pipeline.",
                "user_message",
            )
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "Python"

    def test_filters_entries_missing_required_fields(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import omega.entity.extraction as ext_mod
        ext_mod._last_call_ts = 0.0

        haiku_response = json.dumps({
            "entities": [
                {"name": "React", "type": "technology"},
                {"name": "BadEntry"},  # missing "type"
                {"type": "person"},  # missing "name"
            ],
            "relationships": [
                {"source": "A", "target": "B", "type": "uses"},
                {"source": "A", "target": "B"},  # missing "type"
                {"source": "A"},  # missing target and type
            ],
        })

        with patch("omega.entity.extraction.llm_complete", return_value=haiku_response):
            from omega.entity.extraction import extract_entities
            result = extract_entities(
                "This content is long enough to pass the length check.",
                "user_message",
            )
        # Only the valid entity and relationship should survive
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "React"
        assert len(result["relationships"]) == 1
        assert result["relationships"][0]["type"] == "uses"

    def test_uses_llm_complete(self, monkeypatch):
        """extract_entities uses omega.llm.llm_complete under the hood."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import omega.entity.extraction as ext_mod
        ext_mod._last_call_ts = 0.0

        haiku_response = json.dumps({
            "entities": [{"name": "Python", "type": "technology"}],
            "relationships": [],
        })

        with patch("omega.entity.extraction.llm_complete", return_value=haiku_response) as mock_llm:
            result = ext_mod.extract_entities(
                "We are using Python to build a data pipeline.",
                "user_message",
            )

        mock_llm.assert_called_once()
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "Python"


# ============================================================================
# resolve_and_link()
# ============================================================================

class TestResolveAndLink:
    """Test resolve_and_link() -- entity dedup and memory linking."""

    def test_creates_new_entities(self, store, em):
        from omega.entity.extraction import resolve_and_link

        extraction = {
            "entities": [
                {"name": "React", "type": "technology"},
                {"name": "Jason", "type": "person"},
            ],
            "relationships": [],
        }

        # Create a memory node to link
        node_id = store.store("Test memory about React and Jason")

        result = resolve_and_link(store, em, node_id, extraction)
        assert result["entities_created"] == 2
        assert result["entities_linked"] >= 1

    def test_links_to_existing_entity_by_name(self, store, em):
        from omega.entity.extraction import resolve_and_link

        # Pre-create "React" entity
        em.create_entity("react", "React", "technology")

        extraction = {
            "entities": [
                {"name": "react", "type": "technology"},  # lowercase match
            ],
            "relationships": [],
        }

        node_id = store.store("Test memory about React")

        result = resolve_and_link(store, em, node_id, extraction)
        assert result["entities_created"] == 0  # already exists
        assert result["entities_linked"] >= 1

    def test_creates_relationships(self, store, em):
        from omega.entity.extraction import resolve_and_link

        extraction = {
            "entities": [
                {"name": "Jason", "type": "person"},
                {"name": "React", "type": "technology"},
            ],
            "relationships": [
                {"source": "Jason", "target": "React", "type": "uses"},
            ],
        }

        node_id = store.store("Jason uses React")

        result = resolve_and_link(store, em, node_id, extraction)
        assert result["relationships_created"] == 1

    def test_skips_invalid_entity_type(self, store, em):
        from omega.entity.extraction import resolve_and_link

        extraction = {
            "entities": [
                {"name": "Something", "type": "invalid_type_xyz"},
                {"name": "React", "type": "technology"},
            ],
            "relationships": [],
        }

        node_id = store.store("Test memory content for testing purposes")

        result = resolve_and_link(store, em, node_id, extraction)
        # Only React should be created; invalid type is silently skipped
        assert result["entities_created"] == 1

    def test_empty_extraction_returns_zeros(self, store, em):
        from omega.entity.extraction import resolve_and_link

        extraction = {"entities": [], "relationships": []}
        node_id = store.store("Test memory content for testing purposes")

        result = resolve_and_link(store, em, node_id, extraction)
        assert result == {
            "entities_created": 0,
            "entities_linked": 0,
            "relationships_created": 0,
        }

    def test_skips_self_relationships(self, store, em):
        from omega.entity.extraction import resolve_and_link

        extraction = {
            "entities": [
                {"name": "React", "type": "technology"},
            ],
            "relationships": [
                {"source": "React", "target": "React", "type": "depends_on"},
            ],
        }

        node_id = store.store("Test memory content for testing purposes")

        result = resolve_and_link(store, em, node_id, extraction)
        assert result["relationships_created"] == 0

    def test_does_not_overwrite_existing_entity_id(self, store, em):
        from omega.entity.extraction import resolve_and_link

        # Create a memory with an existing entity_id
        node_id = store.store("Test memory about React", entity_id="existing-entity")

        extraction = {
            "entities": [
                {"name": "React", "type": "technology"},
            ],
            "relationships": [],
        }

        result = resolve_and_link(store, em, node_id, extraction)
        # Entity created, but link should not overwrite existing entity_id
        assert result["entities_linked"] == 0


# ============================================================================
# Bridge wiring: _schedule_entity_extraction
# ============================================================================

import time
from unittest.mock import patch


class TestBridgeEntityExtraction:
    """Tests for entity extraction wired into auto_capture."""

    def test_schedule_entity_extraction_exists(self):
        """The scheduling function exists in bridge module."""
        from omega.bridge import _schedule_entity_extraction
        assert callable(_schedule_entity_extraction)

    def test_schedule_skips_without_api_key(self, tmp_omega_dir):
        """Scheduling with no API key is a no-op (no crash)."""
        from omega.bridge import _schedule_entity_extraction
        from omega.sqlite_store import SQLiteStore
        db_path = tmp_omega_dir / "test.db"
        store = SQLiteStore(db_path=db_path)
        try:
            with patch.dict(os.environ, {"OMEGA_HOME": str(tmp_omega_dir)}, clear=False):
                os.environ.pop("ANTHROPIC_API_KEY", None)
                _schedule_entity_extraction(store, "test-node-id", "Jason uses React", "decision")
        finally:
            store.close()

    def test_extraction_disabled_by_env(self, tmp_omega_dir):
        """OMEGA_ENTITY_EXTRACTION=0 disables extraction."""
        from omega.bridge import _schedule_entity_extraction
        from omega.sqlite_store import SQLiteStore
        db_path = tmp_omega_dir / "test.db"
        store = SQLiteStore(db_path=db_path)
        try:
            with patch.dict(os.environ, {"OMEGA_ENTITY_EXTRACTION": "0", "OMEGA_HOME": str(tmp_omega_dir)}):
                _schedule_entity_extraction(store, "test-node-id", "Jason uses React", "decision")
        finally:
            store.close()


# ============================================================================
# resolve_and_link() Edge Cases
# ============================================================================

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
        em.create_entity("existing-entity", "Existing", "project")
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
        assert _slugify("  spaces  ") == "spaces"


# ============================================================================
# Throttling
# ============================================================================

class TestThrottling:
    """Tests for extraction throttle."""

    def test_throttle_skips_rapid_calls(self):
        """Second call within throttle interval returns empty."""
        from omega.entity import extraction
        # Set throttle to just now so next call is within interval
        extraction._last_call_ts = time.monotonic()
        result = extraction.extract_entities("Jason deployed React to Vercel for a big project", "decision")
        assert result == {"entities": [], "relationships": []}
