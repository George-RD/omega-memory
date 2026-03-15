"""Tests for OMEGA Entity module -- multi-entity corporate memory."""

import json
import os
import pytest
import tempfile
from pathlib import Path

from omega.entity.engine import (
    EntityManager,
    reset_entity_manager,
    ENTITY_TYPES,
    RELATIONSHIP_TYPES,
)


@pytest.fixture
def tmp_omega_dir():
    """Create a temporary OMEGA directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def entity_mgr(tmp_omega_dir):
    """Create a fresh EntityManager for testing."""
    os.environ["OMEGA_HOME"] = str(tmp_omega_dir)
    reset_entity_manager()
    db_path = tmp_omega_dir / "test.db"
    mgr = EntityManager(db_path=db_path)
    yield mgr
    mgr.close()
    reset_entity_manager()


# ============================================================================
# Schema Tests
# ============================================================================

class TestEntitySchema:
    """Test schema creation and table structure."""

    def test_tables_created(self, entity_mgr):
        tables = entity_mgr._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('entities', 'entity_relationships')"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        assert "entities" in table_names
        assert "entity_relationships" in table_names

    def test_schema_version(self, entity_mgr):
        row = entity_mgr._conn.execute(
            "SELECT version FROM entity_schema_version"
        ).fetchone()
        assert row["version"] == 1

    def test_indexes_created(self, entity_mgr):
        indexes = entity_mgr._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_entit%'"
        ).fetchall()
        idx_names = {i["name"] for i in indexes}
        assert "idx_entities_type" in idx_names
        assert "idx_entities_status" in idx_names
        assert "idx_entity_rel_source" in idx_names
        assert "idx_entity_rel_target" in idx_names
        assert "idx_entity_rel_type" in idx_names


# ============================================================================
# Entity CRUD Tests
# ============================================================================

class TestCreateEntity:
    def test_create_basic(self, entity_mgr):
        result = entity_mgr.create_entity("acme", "Acme Corp", "company")
        assert "Created entity" in result
        assert "Acme Corp" in result
        assert "acme" in result

    def test_create_with_jurisdiction(self, entity_mgr):
        result = entity_mgr.create_entity(
            "acme-llc", "Acme LLC", "llc", jurisdiction="US-WY"
        )
        assert "Created entity" in result

    def test_create_with_metadata(self, entity_mgr):
        result = entity_mgr.create_entity(
            "test-co", "Test Co", "company", metadata={"ein": "12-3456789", "founded": "2023"}
        )
        assert "Created entity" in result

    def test_create_duplicate(self, entity_mgr):
        entity_mgr.create_entity("dup", "Dup Inc", "company")
        result = entity_mgr.create_entity("dup", "Dup Again", "company")
        assert "Error" in result
        assert "already exists" in result

    def test_create_invalid_type(self, entity_mgr):
        result = entity_mgr.create_entity("bad", "Bad Corp", "invalid_type")
        assert "Error" in result
        assert "invalid entity_type" in result

    def test_create_empty_id(self, entity_mgr):
        result = entity_mgr.create_entity("", "No ID", "company")
        assert "Error" in result

    def test_create_empty_name(self, entity_mgr):
        result = entity_mgr.create_entity("test", "", "company")
        assert "Error" in result

    def test_create_normalizes_id(self, entity_mgr):
        result = entity_mgr.create_entity("  MyEntity  ", "My Entity", "company")
        assert "myentity" in result

    def test_create_all_types(self, entity_mgr):
        for i, etype in enumerate(sorted(ENTITY_TYPES)):
            result = entity_mgr.create_entity(f"e-{i}", f"Entity {i}", etype)
            assert "Created entity" in result


class TestGetEntity:
    def test_get_existing(self, entity_mgr):
        entity_mgr.create_entity("test-co", "Test Company", "company", jurisdiction="US-DE")
        result = entity_mgr.get_entity("test-co")
        assert "Test Company" in result
        assert "company" in result
        assert "US-DE" in result
        assert "active" in result

    def test_get_nonexistent(self, entity_mgr):
        result = entity_mgr.get_entity("nope")
        assert "Error" in result
        assert "not found" in result

    def test_get_with_metadata(self, entity_mgr):
        entity_mgr.create_entity("m-co", "Meta Co", "llc", metadata={"ein": "123"})
        result = entity_mgr.get_entity("m-co")
        assert "ein" in result
        assert "123" in result


class TestListEntities:
    def test_list_empty(self, entity_mgr):
        result = entity_mgr.list_entities()
        assert "No entities found" in result

    def test_list_all(self, entity_mgr):
        entity_mgr.create_entity("a", "Alpha", "company")
        entity_mgr.create_entity("b", "Beta", "llc")
        result = entity_mgr.list_entities()
        assert "2" in result
        assert "Alpha" in result
        assert "Beta" in result

    def test_list_by_type(self, entity_mgr):
        entity_mgr.create_entity("a", "Alpha", "company")
        entity_mgr.create_entity("b", "Beta", "llc")
        result = entity_mgr.list_entities(entity_type="llc")
        assert "Beta" in result
        assert "Alpha" not in result

    def test_list_by_status(self, entity_mgr):
        entity_mgr.create_entity("a", "Alpha", "company")
        entity_mgr.create_entity("b", "Beta", "company")
        entity_mgr.delete_entity("b")
        result = entity_mgr.list_entities(status="dissolved")
        assert "Beta" in result
        assert "Alpha" not in result


class TestUpdateEntity:
    def test_update_name(self, entity_mgr):
        entity_mgr.create_entity("test", "Old Name", "company")
        result = entity_mgr.update_entity("test", name="New Name")
        assert "Updated entity" in result
        detail = entity_mgr.get_entity("test")
        assert "New Name" in detail

    def test_update_status(self, entity_mgr):
        entity_mgr.create_entity("test", "Test", "company")
        result = entity_mgr.update_entity("test", status="acquired")
        assert "Updated" in result
        detail = entity_mgr.get_entity("test")
        assert "acquired" in detail

    def test_update_invalid_status(self, entity_mgr):
        entity_mgr.create_entity("test", "Test", "company")
        result = entity_mgr.update_entity("test", status="bogus")
        assert "Error" in result
        assert "invalid status" in result

    def test_update_metadata_merge(self, entity_mgr):
        entity_mgr.create_entity("test", "Test", "company", metadata={"a": 1, "b": 2})
        entity_mgr.update_entity("test", metadata={"b": 99, "c": 3})
        detail = entity_mgr.get_entity("test")
        assert "99" in detail
        assert '"c": 3' in detail

    def test_update_metadata_delete_key(self, entity_mgr):
        entity_mgr.create_entity("test", "Test", "company", metadata={"a": 1, "b": 2})
        entity_mgr.update_entity("test", metadata={"b": None})
        row = entity_mgr._conn.execute(
            "SELECT metadata FROM entities WHERE id = 'test'"
        ).fetchone()
        meta = json.loads(row["metadata"])
        assert "b" not in meta
        assert meta["a"] == 1

    def test_update_nonexistent(self, entity_mgr):
        result = entity_mgr.update_entity("nope", name="Whatever")
        assert "Error" in result

    def test_update_no_fields(self, entity_mgr):
        entity_mgr.create_entity("test", "Test", "company")
        result = entity_mgr.update_entity("test")
        assert "No fields to update" in result


class TestDeleteEntity:
    def test_delete_soft(self, entity_mgr):
        entity_mgr.create_entity("test", "Test", "company")
        result = entity_mgr.delete_entity("test")
        assert "Dissolved" in result
        detail = entity_mgr.get_entity("test")
        assert "dissolved" in detail

    def test_delete_nonexistent(self, entity_mgr):
        result = entity_mgr.delete_entity("nope")
        assert "Error" in result


# ============================================================================
# Relationship Tests
# ============================================================================

class TestAddRelationship:
    def test_add_basic(self, entity_mgr):
        entity_mgr.create_entity("parent", "Parent Co", "company")
        entity_mgr.create_entity("child", "Child LLC", "llc")
        result = entity_mgr.add_relationship("parent", "child", "parent_of")
        assert "Added relationship" in result
        assert "parent_of" in result

    def test_add_with_metadata(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "company")
        result = entity_mgr.add_relationship(
            "a", "b", "owned_by", metadata={"ownership_pct": 100}
        )
        assert "Added relationship" in result

    def test_add_invalid_type(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "company")
        result = entity_mgr.add_relationship("a", "b", "bogus")
        assert "Error" in result
        assert "invalid relationship_type" in result

    def test_add_self_relationship(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        result = entity_mgr.add_relationship("a", "a", "parent_of")
        assert "Error" in result
        assert "different" in result

    def test_add_nonexistent_source(self, entity_mgr):
        entity_mgr.create_entity("b", "B", "company")
        result = entity_mgr.add_relationship("nope", "b", "parent_of")
        assert "Error" in result
        assert "not found" in result

    def test_add_nonexistent_target(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        result = entity_mgr.add_relationship("a", "nope", "parent_of")
        assert "Error" in result
        assert "not found" in result

    def test_add_duplicate(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "company")
        entity_mgr.add_relationship("a", "b", "parent_of")
        result = entity_mgr.add_relationship("a", "b", "parent_of")
        assert "Error" in result
        assert "already exists" in result

    def test_add_all_relationship_types(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "company")
        for rel in sorted(RELATIONSHIP_TYPES):
            # Remove previous relationships to avoid duplicate errors
            entity_mgr.remove_relationship("a", "b", rel)
            result = entity_mgr.add_relationship("a", "b", rel)
            assert "Added relationship" in result


class TestGetRelationships:
    def test_get_all(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "llc")
        entity_mgr.add_relationship("a", "b", "parent_of")
        result = entity_mgr.get_relationships("a")
        assert "parent_of" in result
        assert "Outgoing" in result

    def test_get_incoming(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "llc")
        entity_mgr.add_relationship("a", "b", "parent_of")
        result = entity_mgr.get_relationships("b")
        assert "Incoming" in result

    def test_get_filtered_by_direction(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "llc")
        entity_mgr.add_relationship("a", "b", "parent_of")
        result = entity_mgr.get_relationships("a", direction="outgoing")
        assert "Outgoing" in result
        assert "Incoming" not in result

    def test_get_filtered_by_type(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "llc")
        entity_mgr.create_entity("c", "C", "llc")
        entity_mgr.add_relationship("a", "b", "parent_of")
        entity_mgr.add_relationship("a", "c", "investor_in")
        result = entity_mgr.get_relationships("a", relationship_type="parent_of")
        assert "parent_of" in result
        assert "investor_in" not in result

    def test_get_none(self, entity_mgr):
        entity_mgr.create_entity("lonely", "Lonely", "company")
        result = entity_mgr.get_relationships("lonely")
        assert "No relationships found" in result

    def test_get_nonexistent_entity(self, entity_mgr):
        result = entity_mgr.get_relationships("nope")
        assert "Error" in result


class TestRemoveRelationship:
    def test_remove_existing(self, entity_mgr):
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "llc")
        entity_mgr.add_relationship("a", "b", "parent_of")
        result = entity_mgr.remove_relationship("a", "b", "parent_of")
        assert "Removed relationship" in result

    def test_remove_nonexistent(self, entity_mgr):
        result = entity_mgr.remove_relationship("a", "b", "parent_of")
        assert "No relationship found" in result


# ============================================================================
# Entity Tree Tests
# ============================================================================

class TestEntityTree:
    def test_simple_tree(self, entity_mgr):
        entity_mgr.create_entity("parent", "Parent Corp", "company")
        entity_mgr.create_entity("child1", "Child One", "llc")
        entity_mgr.create_entity("child2", "Child Two", "llc")
        entity_mgr.add_relationship("parent", "child1", "parent_of")
        entity_mgr.add_relationship("parent", "child2", "parent_of")
        result = entity_mgr.get_entity_tree("parent")
        assert "Parent Corp" in result
        assert "Child One" in result
        assert "Child Two" in result

    def test_nested_tree(self, entity_mgr):
        entity_mgr.create_entity("root", "Root Corp", "company")
        entity_mgr.create_entity("mid", "Mid LLC", "llc")
        entity_mgr.create_entity("leaf", "Leaf Inc", "company")
        entity_mgr.add_relationship("root", "mid", "parent_of")
        entity_mgr.add_relationship("mid", "leaf", "parent_of")
        result = entity_mgr.get_entity_tree("root")
        assert "Root Corp" in result
        assert "Mid LLC" in result
        assert "Leaf Inc" in result

    def test_tree_nonexistent(self, entity_mgr):
        result = entity_mgr.get_entity_tree("nope")
        assert "Error" in result

    def test_tree_no_children(self, entity_mgr):
        entity_mgr.create_entity("alone", "Alone Inc", "company")
        result = entity_mgr.get_entity_tree("alone")
        assert "Alone Inc" in result

    def test_tree_handles_cycles(self, entity_mgr):
        """Ensure tree doesn't infinite-loop on circular relationships."""
        entity_mgr.create_entity("a", "A", "company")
        entity_mgr.create_entity("b", "B", "company")
        entity_mgr.add_relationship("a", "b", "parent_of")
        entity_mgr.add_relationship("b", "a", "parent_of")
        result = entity_mgr.get_entity_tree("a")
        # Should complete without hanging
        assert "A" in result
        assert "B" in result


# ============================================================================
# Handler Tests
# ============================================================================

class TestEntityHandlers:
    """Test MCP handler wiring."""

    @pytest.mark.asyncio
    async def test_create_handler(self, entity_mgr, monkeypatch):
        monkeypatch.setattr("omega.entity.engine._instance", entity_mgr)
        from omega.entity.handlers import handle_omega_entity_create

        result = await handle_omega_entity_create({
            "entity_id": "test",
            "name": "Test Co",
            "entity_type": "company",
        })
        assert "Created entity" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_create_handler_missing_fields(self, entity_mgr, monkeypatch):
        monkeypatch.setattr("omega.entity.engine._instance", entity_mgr)
        from omega.entity.handlers import handle_omega_entity_create

        result = await handle_omega_entity_create({"entity_id": "test"})
        assert result.get("isError")

    @pytest.mark.asyncio
    async def test_get_handler(self, entity_mgr, monkeypatch):
        monkeypatch.setattr("omega.entity.engine._instance", entity_mgr)
        from omega.entity.handlers import handle_omega_entity_create, handle_omega_entity_get

        await handle_omega_entity_create({
            "entity_id": "test",
            "name": "Test Co",
            "entity_type": "company",
        })
        result = await handle_omega_entity_get({"entity_id": "test"})
        assert "Test Co" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_list_handler(self, entity_mgr, monkeypatch):
        monkeypatch.setattr("omega.entity.engine._instance", entity_mgr)
        from omega.entity.handlers import handle_omega_entity_create, handle_omega_entity_list

        await handle_omega_entity_create({
            "entity_id": "a",
            "name": "Alpha",
            "entity_type": "company",
        })
        result = await handle_omega_entity_list({})
        assert "Alpha" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_update_handler(self, entity_mgr, monkeypatch):
        monkeypatch.setattr("omega.entity.engine._instance", entity_mgr)
        from omega.entity.handlers import handle_omega_entity_create, handle_omega_entity_update

        await handle_omega_entity_create({
            "entity_id": "test",
            "name": "Test",
            "entity_type": "company",
        })
        result = await handle_omega_entity_update({
            "entity_id": "test",
            "status": "acquired",
        })
        assert "Updated" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_delete_handler(self, entity_mgr, monkeypatch):
        monkeypatch.setattr("omega.entity.engine._instance", entity_mgr)
        from omega.entity.handlers import handle_omega_entity_create, handle_omega_entity_delete

        await handle_omega_entity_create({
            "entity_id": "test",
            "name": "Test",
            "entity_type": "company",
        })
        result = await handle_omega_entity_delete({"entity_id": "test"})
        assert "Dissolved" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_relationship_handler(self, entity_mgr, monkeypatch):
        monkeypatch.setattr("omega.entity.engine._instance", entity_mgr)
        from omega.entity.handlers import (
            handle_omega_entity_create,
            handle_omega_entity_add_relationship,
            handle_omega_entity_relationships,
        )

        await handle_omega_entity_create({
            "entity_id": "parent",
            "name": "Parent",
            "entity_type": "company",
        })
        await handle_omega_entity_create({
            "entity_id": "child",
            "name": "Child",
            "entity_type": "llc",
        })
        result = await handle_omega_entity_add_relationship({
            "source_entity_id": "parent",
            "target_entity_id": "child",
            "relationship_type": "parent_of",
        })
        assert "Added" in result["content"][0]["text"]

        rels = await handle_omega_entity_relationships({"entity_id": "parent"})
        assert "parent_of" in rels["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_tree_handler(self, entity_mgr, monkeypatch):
        monkeypatch.setattr("omega.entity.engine._instance", entity_mgr)
        from omega.entity.handlers import (
            handle_omega_entity_create,
            handle_omega_entity_add_relationship,
            handle_omega_entity_tree,
        )

        await handle_omega_entity_create({
            "entity_id": "root",
            "name": "Root Corp",
            "entity_type": "company",
        })
        await handle_omega_entity_create({
            "entity_id": "sub",
            "name": "Sub LLC",
            "entity_type": "llc",
        })
        await handle_omega_entity_add_relationship({
            "source_entity_id": "root",
            "target_entity_id": "sub",
            "relationship_type": "parent_of",
        })
        result = await handle_omega_entity_tree({"entity_id": "root"})
        text = result["content"][0]["text"]
        assert "Root Corp" in text
        assert "Sub LLC" in text
