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


def _setup_entity_manager(store):
    """Create an EntityManager using the store's db_path."""
    from omega.entity.engine import EntityManager
    return EntityManager(db_path=store.db_path)


class TestGetRelatedEntityIds:

    def test_returns_related_ids(self, entity_store):
        mgr = _setup_entity_manager(entity_store)
        mgr.create_entity("acme", "Acme Corp", "company")
        mgr.create_entity("acme-uk", "Acme UK", "company")
        mgr.add_relationship("acme", "acme-uk", "parent_of")
        related = mgr.get_related_entity_ids("acme")
        assert "acme-uk" in related

    def test_returns_both_directions(self, entity_store):
        mgr = _setup_entity_manager(entity_store)
        mgr.create_entity("parent", "Parent Co", "company")
        mgr.create_entity("child", "Child Co", "company")
        mgr.add_relationship("parent", "child", "parent_of")
        related = mgr.get_related_entity_ids("child")
        assert "parent" in related

    def test_empty_for_no_relationships(self, entity_store):
        mgr = _setup_entity_manager(entity_store)
        mgr.create_entity("solo", "Solo Entity", "company")
        related = mgr.get_related_entity_ids("solo")
        assert related == set()

    def test_nonexistent_entity_returns_empty(self, entity_store):
        mgr = _setup_entity_manager(entity_store)
        related = mgr.get_related_entity_ids("nonexistent")
        assert related == set()

    def test_max_hops_limits_depth(self, entity_store):
        mgr = _setup_entity_manager(entity_store)
        mgr.create_entity("a", "A", "company")
        mgr.create_entity("b", "B", "company")
        mgr.create_entity("c", "C", "company")
        mgr.add_relationship("a", "b", "parent_of")
        mgr.add_relationship("b", "c", "parent_of")
        related_1 = mgr.get_related_entity_ids("a", max_hops=1)
        assert "b" in related_1
        assert "c" not in related_1
        related_2 = mgr.get_related_entity_ids("a", max_hops=2)
        assert "b" in related_2
        assert "c" in related_2


class TestEntityGraphRetrieval:

    def test_related_entity_memories_appear_in_results(self, entity_store):
        mgr = _setup_entity_manager(entity_store)
        mgr.create_entity("omega", "OMEGA", "company")
        mgr.create_entity("omega-public", "OMEGA Public", "company")
        mgr.add_relationship("omega", "omega-public", "parent_of")

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

        results = entity_store.query("memory tools", entity_id="omega")
        result_contents = [r.content for r in results]
        has_related = any("public" in c.lower() for c in result_contents)
        assert has_related, f"Expected related entity memories. Got: {result_contents}"

    def test_no_entity_relationship_no_boost(self, entity_store):
        mgr = _setup_entity_manager(entity_store)
        mgr.create_entity("proj-a", "Project A", "company")
        mgr.create_entity("proj-b", "Project B", "company")

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

        results = entity_store.query("Redis caching", entity_id="proj-a")
        for r in results:
            meta = r.metadata or {}
            eid = meta.get("entity_id")
            if eid:
                assert eid == "proj-a", f"Unexpected entity_id {eid} in results"

    def test_entity_graph_with_no_entities_is_noop(self, entity_store):
        entity_store.store(
            content="A memory with no entity scope",
            metadata={"event_type": "decision"},
        )
        results = entity_store.query("memory")
        assert len(results) > 0
