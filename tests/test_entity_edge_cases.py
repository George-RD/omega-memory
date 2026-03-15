"""Tests for OMEGA Entity module -- edge cases and uncovered paths.

Covers:
- Deep relationship traversal (get_related_entity_ids with max_hops 3-5)
- Cyclic relationship graphs (no infinite loops)
- Entity tree with deep nesting (5+ levels)
- Duplicate entity creation (idempotent error)
- Update nonexistent entity (graceful error)
- Delete entity with relationships (cascade behavior)
- Relationship on nonexistent entities (error paths)
- Large entity graphs (100+ entities)
- Entity type validation (all valid types + invalid)
- Empty/null field handling
- list_entity_ids() (empty DB, after deletes)
- get_relationships() with direction filter (incoming/outgoing/None)
"""

import pytest

from omega.entity.engine import (
    EntityManager,
    ENTITY_TYPES,
    ENTITY_STATUSES,
    RELATIONSHIP_TYPES,
)


@pytest.fixture
def em(tmp_path):
    """Create a fresh EntityManager backed by a temp DB."""
    mgr = EntityManager(db_path=tmp_path / "entity.db")
    yield mgr
    mgr.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_chain(em: EntityManager, n: int, rel: str = "parent_of"):
    """Create a linear chain: node-0 -> node-1 -> ... -> node-(n-1).

    Returns list of entity IDs in order.
    """
    ids = []
    for i in range(n):
        eid = f"node-{i}"
        em.create_entity(eid, f"Node {i}", "company")
        ids.append(eid)
    for i in range(n - 1):
        em.add_relationship(ids[i], ids[i + 1], rel)
    return ids


# ============================================================================
# 1. Deep relationship traversal -- get_related_entity_ids()
# ============================================================================

class TestDeepRelationshipTraversal:
    """Verify get_related_entity_ids() works with high max_hops values."""

    def test_hop_1_only_direct_neighbors(self, em):
        ids = _create_chain(em, 5)
        related = em.get_related_entity_ids(ids[0], max_hops=1)
        assert related == {ids[1]}

    def test_hop_2_reaches_two_levels(self, em):
        ids = _create_chain(em, 5)
        related = em.get_related_entity_ids(ids[0], max_hops=2)
        assert related == {ids[1], ids[2]}

    def test_hop_3_reaches_three_levels(self, em):
        ids = _create_chain(em, 6)
        related = em.get_related_entity_ids(ids[0], max_hops=3)
        assert related == {ids[1], ids[2], ids[3]}

    def test_hop_4_reaches_four_levels(self, em):
        ids = _create_chain(em, 7)
        related = em.get_related_entity_ids(ids[0], max_hops=4)
        assert related == {ids[1], ids[2], ids[3], ids[4]}

    def test_hop_5_reaches_five_levels(self, em):
        ids = _create_chain(em, 8)
        related = em.get_related_entity_ids(ids[0], max_hops=5)
        assert related == {ids[1], ids[2], ids[3], ids[4], ids[5]}

    def test_hop_exceeds_chain_length(self, em):
        """max_hops larger than the chain should return all reachable nodes."""
        ids = _create_chain(em, 4)
        related = em.get_related_entity_ids(ids[0], max_hops=100)
        assert related == {ids[1], ids[2], ids[3]}

    def test_hop_from_middle_node(self, em):
        """Traversal from the middle should reach nodes in both directions."""
        ids = _create_chain(em, 5)
        related = em.get_related_entity_ids(ids[2], max_hops=1)
        # Relationships are bidirectional for traversal
        assert ids[1] in related
        assert ids[3] in related

    def test_hop_0_is_clamped_to_1(self, em):
        """max_hops < 1 should be clamped to 1."""
        ids = _create_chain(em, 3)
        related = em.get_related_entity_ids(ids[0], max_hops=0)
        assert related == {ids[1]}

    def test_negative_hops_clamped_to_1(self, em):
        """Negative max_hops should be clamped to 1."""
        ids = _create_chain(em, 3)
        related = em.get_related_entity_ids(ids[0], max_hops=-5)
        assert related == {ids[1]}

    def test_nonexistent_entity_returns_empty(self, em):
        related = em.get_related_entity_ids("ghost", max_hops=3)
        assert related == set()

    def test_entity_with_no_relationships(self, em):
        em.create_entity("loner", "Loner Corp", "company")
        related = em.get_related_entity_ids("loner", max_hops=5)
        assert related == set()

    def test_branching_graph(self, em):
        """Fan-out: root -> {a, b, c}, a -> {d, e}. Verify multi-hop coverage."""
        em.create_entity("root", "Root", "company")
        for name in ("a", "b", "c", "d", "e"):
            em.create_entity(name, name.upper(), "company")
        em.add_relationship("root", "a", "parent_of")
        em.add_relationship("root", "b", "parent_of")
        em.add_relationship("root", "c", "parent_of")
        em.add_relationship("a", "d", "parent_of")
        em.add_relationship("a", "e", "parent_of")

        hop1 = em.get_related_entity_ids("root", max_hops=1)
        assert hop1 == {"a", "b", "c"}

        hop2 = em.get_related_entity_ids("root", max_hops=2)
        assert hop2 == {"a", "b", "c", "d", "e"}


# ============================================================================
# 2. Cyclic relationship graphs
# ============================================================================

class TestCyclicGraphs:
    """Cycles must not cause infinite loops."""

    def test_simple_cycle_a_b_a(self, em):
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.add_relationship("a", "b", "parent_of")
        em.add_relationship("b", "a", "parent_of")
        related = em.get_related_entity_ids("a", max_hops=10)
        assert related == {"b"}

    def test_triangle_cycle(self, em):
        """A -> B -> C -> A should terminate."""
        for eid in ("a", "b", "c"):
            em.create_entity(eid, eid.upper(), "company")
        em.add_relationship("a", "b", "parent_of")
        em.add_relationship("b", "c", "parent_of")
        em.add_relationship("c", "a", "parent_of")
        related = em.get_related_entity_ids("a", max_hops=20)
        assert related == {"b", "c"}

    def test_long_cycle(self, em):
        """Chain of 10 nodes forming a ring."""
        n = 10
        ids = []
        for i in range(n):
            eid = f"ring-{i}"
            em.create_entity(eid, f"Ring {i}", "company")
            ids.append(eid)
        for i in range(n):
            em.add_relationship(ids[i], ids[(i + 1) % n], "parent_of")

        related = em.get_related_entity_ids(ids[0], max_hops=n + 5)
        # Should find all other nodes
        assert related == set(ids[1:])

    def test_tree_with_cycle_terminates(self, em):
        """get_entity_tree handles cycles via visited set."""
        em.create_entity("x", "X", "company")
        em.create_entity("y", "Y", "company")
        em.create_entity("z", "Z", "company")
        em.add_relationship("x", "y", "parent_of")
        em.add_relationship("y", "z", "parent_of")
        em.add_relationship("z", "x", "parent_of")
        result = em.get_entity_tree("x")
        # Should complete without hanging and contain all nodes
        assert "X" in result
        assert "Y" in result
        assert "Z" in result


# ============================================================================
# 3. Entity tree with deep nesting (5+ levels)
# ============================================================================

class TestDeepEntityTree:
    """Test get_entity_tree with deep hierarchies."""

    def test_five_levels_deep(self, em):
        """Root -> L1 -> L2 -> L3 -> L4 -> L5, all visible in tree."""
        prev = None
        for i in range(6):
            eid = f"level-{i}"
            em.create_entity(eid, f"Level {i}", "company")
            if prev is not None:
                em.add_relationship(prev, eid, "parent_of")
            prev = eid
        result = em.get_entity_tree("level-0")
        for i in range(6):
            assert f"Level {i}" in result

    def test_seven_levels_deep(self, em):
        prev = None
        for i in range(8):
            eid = f"deep-{i}"
            em.create_entity(eid, f"Deep {i}", "company")
            if prev is not None:
                em.add_relationship(prev, eid, "parent_of")
            prev = eid
        result = em.get_entity_tree("deep-0")
        for i in range(8):
            assert f"Deep {i}" in result

    def test_ten_levels_deep_hits_depth_limit(self, em):
        """_build_tree has depth > 10 guard. 12 levels should stop at 11."""
        prev = None
        for i in range(12):
            eid = f"ultra-{i}"
            em.create_entity(eid, f"Ultra {i}", "company")
            if prev is not None:
                em.add_relationship(prev, eid, "parent_of")
            prev = eid
        result = em.get_entity_tree("ultra-0")
        # The root is depth 0; depth > 10 stops at depth 11 (index 11).
        # So ultra-0 (depth 0) through ultra-10 (depth 10) should appear.
        for i in range(11):
            assert f"Ultra {i}" in result
        # ultra-11 is at depth 11, which is > 10, so it should NOT appear.
        assert "Ultra 11" not in result

    def test_wide_and_deep(self, em):
        """Root with 3 children, each having 2 grandchildren."""
        em.create_entity("root", "Root", "company")
        for c in range(3):
            cid = f"child-{c}"
            em.create_entity(cid, f"Child {c}", "llc")
            em.add_relationship("root", cid, "parent_of")
            for g in range(2):
                gid = f"gc-{c}-{g}"
                em.create_entity(gid, f"GC {c}-{g}", "company")
                em.add_relationship(cid, gid, "parent_of")
        result = em.get_entity_tree("root")
        assert "Root" in result
        for c in range(3):
            assert f"Child {c}" in result
            for g in range(2):
                assert f"GC {c}-{g}" in result


# ============================================================================
# 4. Duplicate entity creation
# ============================================================================

class TestDuplicateEntityCreation:
    def test_exact_duplicate_returns_error(self, em):
        em.create_entity("dup", "Dup", "company")
        result = em.create_entity("dup", "Dup", "company")
        assert "Error" in result
        assert "already exists" in result

    def test_duplicate_id_different_name(self, em):
        em.create_entity("dup", "Original", "company")
        result = em.create_entity("dup", "Different Name", "llc")
        assert "Error" in result
        assert "already exists" in result

    def test_case_insensitive_duplicate(self, em):
        """IDs are normalized to lowercase, so 'ABC' and 'abc' collide."""
        em.create_entity("ABC", "First", "company")
        result = em.create_entity("abc", "Second", "company")
        assert "Error" in result
        assert "already exists" in result

    def test_whitespace_normalized_duplicate(self, em):
        """Leading/trailing whitespace is stripped from IDs."""
        em.create_entity("  myid  ", "First", "company")
        result = em.create_entity("myid", "Second", "company")
        assert "Error" in result
        assert "already exists" in result


# ============================================================================
# 5. Update nonexistent entity
# ============================================================================

class TestUpdateNonexistent:
    def test_update_name_nonexistent(self, em):
        result = em.update_entity("ghost", name="New Name")
        assert "Error" in result
        assert "not found" in result

    def test_update_status_nonexistent(self, em):
        result = em.update_entity("ghost", status="acquired")
        assert "Error" in result
        assert "not found" in result

    def test_update_metadata_nonexistent(self, em):
        result = em.update_entity("ghost", metadata={"key": "val"})
        assert "Error" in result
        assert "not found" in result

    def test_update_jurisdiction_nonexistent(self, em):
        result = em.update_entity("ghost", jurisdiction="US-WY")
        assert "Error" in result
        assert "not found" in result


# ============================================================================
# 6. Delete entity with relationships (cascade behavior)
# ============================================================================

class TestDeleteWithRelationships:
    """delete_entity is a soft-delete (sets status=dissolved).
    Relationships should remain intact after soft delete.
    """

    def test_soft_delete_preserves_relationships(self, em):
        em.create_entity("parent", "Parent", "company")
        em.create_entity("child", "Child", "llc")
        em.add_relationship("parent", "child", "parent_of")
        em.delete_entity("parent")

        # Entity is dissolved but still queryable
        detail = em.get_entity("parent")
        assert "dissolved" in detail

        # Relationships still present
        rels = em.get_relationships("parent")
        assert "parent_of" in rels

    def test_soft_delete_entity_still_in_tree(self, em):
        em.create_entity("root", "Root", "company")
        em.create_entity("sub", "Sub", "llc")
        em.add_relationship("root", "sub", "parent_of")
        em.delete_entity("sub")
        result = em.get_entity_tree("root")
        # Dissolved entities still show in tree
        assert "Sub" in result
        assert "dissolved" in result

    def test_dissolved_entity_not_in_list_entity_ids(self, em):
        em.create_entity("alive", "Alive", "company")
        em.create_entity("dead", "Dead", "company")
        em.delete_entity("dead")
        ids = em.list_entity_ids()
        id_set = {eid for eid, _ in ids}
        assert "alive" in id_set
        assert "dead" not in id_set

    def test_can_still_add_relationship_to_dissolved(self, em):
        """Even dissolved entities are still in DB, so relationships work."""
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.delete_entity("b")
        result = em.add_relationship("a", "b", "parent_of")
        assert "Added relationship" in result

    def test_delete_both_endpoints(self, em):
        em.create_entity("x", "X", "company")
        em.create_entity("y", "Y", "company")
        em.add_relationship("x", "y", "partner_of")
        em.delete_entity("x")
        em.delete_entity("y")
        # Relationship still queryable
        rels = em.get_relationships("x")
        assert "partner_of" in rels


# ============================================================================
# 7. Relationship on nonexistent entities (error path)
# ============================================================================

class TestRelationshipNonexistent:
    def test_both_entities_missing(self, em):
        result = em.add_relationship("ghost-a", "ghost-b", "parent_of")
        assert "Error" in result
        assert "not found" in result

    def test_source_missing(self, em):
        em.create_entity("exists", "Exists", "company")
        result = em.add_relationship("ghost", "exists", "parent_of")
        assert "Error" in result
        assert "ghost" in result

    def test_target_missing(self, em):
        em.create_entity("exists", "Exists", "company")
        result = em.add_relationship("exists", "ghost", "parent_of")
        assert "Error" in result
        assert "ghost" in result

    def test_self_relationship_blocked(self, em):
        em.create_entity("self", "Self", "company")
        result = em.add_relationship("self", "self", "parent_of")
        assert "Error" in result
        assert "different" in result

    def test_get_relationships_nonexistent(self, em):
        result = em.get_relationships("nonexistent")
        assert "Error" in result
        assert "not found" in result


# ============================================================================
# 8. Large entity graphs (100+ entities)
# ============================================================================

class TestLargeGraphs:
    def test_100_entities_linear_chain(self, em):
        """Create 100 nodes in a chain, verify traversal."""
        ids = _create_chain(em, 100)
        # 1 hop from start
        related = em.get_related_entity_ids(ids[0], max_hops=1)
        assert related == {ids[1]}

        # 5 hops from start
        related_5 = em.get_related_entity_ids(ids[0], max_hops=5)
        assert related_5 == {ids[i] for i in range(1, 6)}

    def test_100_entities_star_topology(self, em):
        """Hub with 100 spokes."""
        em.create_entity("hub", "Hub", "company")
        for i in range(100):
            eid = f"spoke-{i}"
            em.create_entity(eid, f"Spoke {i}", "llc")
            em.add_relationship("hub", eid, "parent_of")

        related = em.get_related_entity_ids("hub", max_hops=1)
        assert len(related) == 100

    def test_large_list_entities(self, em):
        """list_entities should handle 150+ entities."""
        for i in range(150):
            em.create_entity(f"e-{i:04d}", f"Entity {i}", "company")
        result = em.list_entities()
        assert "150" in result

    def test_large_list_entity_ids(self, em):
        for i in range(120):
            em.create_entity(f"id-{i:04d}", f"ID Entity {i}", "company")
        ids = em.list_entity_ids()
        assert len(ids) == 120

    def test_150_entities_with_relationships(self, em):
        """Create 150 entities each connected to the next."""
        ids = _create_chain(em, 150)
        # Spot-check middle-of-chain traversal
        middle = ids[75]
        related = em.get_related_entity_ids(middle, max_hops=2)
        expected = {ids[73], ids[74], ids[76], ids[77]}
        assert related == expected


# ============================================================================
# 9. Entity type validation
# ============================================================================

class TestEntityTypeValidation:
    def test_all_valid_types_accepted(self, em):
        """Every type in ENTITY_TYPES should succeed."""
        for i, etype in enumerate(sorted(ENTITY_TYPES)):
            result = em.create_entity(f"type-{i}", f"Type {etype}", etype)
            assert "Created entity" in result, f"Failed for type: {etype}"

    def test_invalid_type_rejected(self, em):
        # Note: "COMPANY" normalizes to "company" which is valid, so exclude it.
        for bad_type in ("invalid", "corporation", "inc", "holding", ""):
            result = em.create_entity(f"bad-{bad_type}", "Bad", bad_type.strip() or "x")
            assert "Error" in result, f"Should reject type: {bad_type!r}"

    def test_type_case_normalized(self, em):
        """'Company' (uppercase C) should be normalized to 'company'."""
        result = em.create_entity("case-test", "Case Test", "Company")
        assert "Created entity" in result

    def test_type_with_whitespace(self, em):
        result = em.create_entity("ws-test", "WS Test", "  company  ")
        assert "Created entity" in result

    def test_all_relationship_types_accepted(self, em):
        """Every relationship type in RELATIONSHIP_TYPES should succeed."""
        em.create_entity("src", "Src", "company")
        em.create_entity("tgt", "Tgt", "company")
        for rel in sorted(RELATIONSHIP_TYPES):
            em.remove_relationship("src", "tgt", rel)  # clean slate
            result = em.add_relationship("src", "tgt", rel)
            assert "Added relationship" in result, f"Failed for rel: {rel}"

    def test_invalid_relationship_type_rejected(self, em):
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        result = em.add_relationship("a", "b", "made_up_rel")
        assert "Error" in result
        assert "invalid relationship_type" in result

    def test_all_statuses_accepted(self, em):
        """Every status in ENTITY_STATUSES should succeed via update."""
        em.create_entity("status-test", "Status Test", "company")
        for status in sorted(ENTITY_STATUSES):
            result = em.update_entity("status-test", status=status)
            assert "Updated" in result, f"Failed for status: {status}"

    def test_invalid_status_rejected(self, em):
        em.create_entity("s-test", "Status Test", "company")
        result = em.update_entity("s-test", status="bankrupt")
        assert "Error" in result
        assert "invalid status" in result


# ============================================================================
# 10. Empty / null field handling
# ============================================================================

class TestEmptyNullFields:
    def test_empty_entity_id(self, em):
        result = em.create_entity("", "Name", "company")
        assert "Error" in result

    def test_whitespace_only_entity_id(self, em):
        result = em.create_entity("   ", "Name", "company")
        assert "Error" in result

    def test_empty_name(self, em):
        result = em.create_entity("test", "", "company")
        assert "Error" in result

    def test_whitespace_only_name(self, em):
        result = em.create_entity("test", "   ", "company")
        assert "Error" in result

    def test_none_jurisdiction(self, em):
        result = em.create_entity("nj", "NJ Corp", "company", jurisdiction=None)
        assert "Created entity" in result
        detail = em.get_entity("nj")
        # The "**Jurisdiction**:" field line should not appear when jurisdiction is None
        assert "**Jurisdiction**" not in detail

    def test_none_metadata(self, em):
        result = em.create_entity("nm", "No Meta", "company", metadata=None)
        assert "Created entity" in result
        detail = em.get_entity("nm")
        assert "Metadata" not in detail  # field omitted if empty

    def test_empty_dict_metadata(self, em):
        result = em.create_entity("em", "Empty Meta", "company", metadata={})
        assert "Created entity" in result

    def test_metadata_with_none_values(self, em):
        """Metadata dict with None values -- should store cleanly."""
        result = em.create_entity(
            "nv", "Null Values", "company", metadata={"key": None}
        )
        assert "Created entity" in result

    def test_update_with_empty_metadata(self, em):
        em.create_entity("test", "Test", "company", metadata={"a": 1})
        result = em.update_entity("test", metadata={})
        # No keys to merge -> no change to metadata field, but updated_at changes.
        # Actually with empty dict, no keys iterate, so metadata stays same.
        # But the update still succeeds because metadata is provided (not None-gated).
        assert "Updated" in result

    def test_get_entity_without_metadata(self, em):
        """Entity with no metadata should not show Metadata line."""
        em.create_entity("plain", "Plain", "company")
        detail = em.get_entity("plain")
        assert "Metadata" not in detail

    def test_update_name_to_stripped_value(self, em):
        em.create_entity("test", "Test", "company")
        result = em.update_entity("test", name="  New Name  ")
        assert "Updated" in result
        detail = em.get_entity("test")
        assert "New Name" in detail


# ============================================================================
# 11. list_entity_ids()
# ============================================================================

class TestListEntityIds:
    def test_empty_db(self, em):
        ids = em.list_entity_ids()
        assert ids == []

    def test_single_entity(self, em):
        em.create_entity("solo", "Solo", "company")
        ids = em.list_entity_ids()
        assert len(ids) == 1
        assert ids[0] == ("solo", "Solo")

    def test_multiple_entities_sorted_by_name(self, em):
        em.create_entity("z", "Zebra", "company")
        em.create_entity("a", "Alpha", "company")
        em.create_entity("m", "Mango", "company")
        ids = em.list_entity_ids()
        names = [name for _, name in ids]
        assert names == ["Alpha", "Mango", "Zebra"]

    def test_after_delete_excludes_dissolved(self, em):
        em.create_entity("alive", "Alive", "company")
        em.create_entity("dead", "Dead", "company")
        em.delete_entity("dead")
        ids = em.list_entity_ids()
        id_set = {eid for eid, _ in ids}
        assert "alive" in id_set
        assert "dead" not in id_set

    def test_after_all_deleted(self, em):
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.delete_entity("a")
        em.delete_entity("b")
        ids = em.list_entity_ids()
        assert ids == []

    def test_non_active_statuses_excluded(self, em):
        """list_entity_ids only returns active entities."""
        em.create_entity("active", "Active", "company")
        em.create_entity("acquired", "Acquired", "company")
        em.update_entity("acquired", status="acquired")
        em.create_entity("dormant", "Dormant", "company")
        em.update_entity("dormant", status="dormant")
        ids = em.list_entity_ids()
        id_set = {eid for eid, _ in ids}
        assert id_set == {"active"}

    def test_returns_tuples(self, em):
        em.create_entity("test", "Test Corp", "company")
        ids = em.list_entity_ids()
        assert isinstance(ids, list)
        assert isinstance(ids[0], tuple)
        assert len(ids[0]) == 2


# ============================================================================
# 12. get_relationships() with direction filter
# ============================================================================

class TestRelationshipsDirectionFilter:
    """Test direction='incoming', 'outgoing', and None."""

    def _setup_triangle(self, em):
        """A -> B, B -> C, C -> A (different rel types for clarity)."""
        for eid in ("a", "b", "c"):
            em.create_entity(eid, eid.upper(), "company")
        em.add_relationship("a", "b", "parent_of")
        em.add_relationship("b", "c", "parent_of")
        em.add_relationship("c", "a", "parent_of")

    def test_outgoing_only(self, em):
        self._setup_triangle(em)
        result = em.get_relationships("a", direction="outgoing")
        assert "Outgoing" in result
        assert "Incoming" not in result
        assert "parent_of" in result
        assert "`b`" in result

    def test_incoming_only(self, em):
        self._setup_triangle(em)
        result = em.get_relationships("a", direction="incoming")
        assert "Incoming" in result
        assert "Outgoing" not in result
        assert "`c`" in result

    def test_both_directions_default(self, em):
        self._setup_triangle(em)
        result = em.get_relationships("a", direction=None)
        assert "Outgoing" in result
        assert "Incoming" in result

    def test_outgoing_with_type_filter(self, em):
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.create_entity("c", "C", "company")
        em.add_relationship("a", "b", "parent_of")
        em.add_relationship("a", "c", "investor_in")
        result = em.get_relationships(
            "a", direction="outgoing", relationship_type="parent_of"
        )
        assert "parent_of" in result
        assert "investor_in" not in result

    def test_incoming_with_type_filter(self, em):
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.create_entity("c", "C", "company")
        em.add_relationship("b", "a", "parent_of")
        em.add_relationship("c", "a", "investor_in")
        result = em.get_relationships(
            "a", direction="incoming", relationship_type="investor_in"
        )
        assert "investor_in" in result
        assert "parent_of" not in result

    def test_no_outgoing(self, em):
        """Entity with only incoming relationships, querying outgoing."""
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.add_relationship("b", "a", "parent_of")
        result = em.get_relationships("a", direction="outgoing")
        assert "No relationships found" in result

    def test_no_incoming(self, em):
        """Entity with only outgoing relationships, querying incoming."""
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.add_relationship("a", "b", "parent_of")
        result = em.get_relationships("a", direction="incoming")
        assert "No relationships found" in result

    def test_relationship_metadata_displayed(self, em):
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.add_relationship("a", "b", "owned_by", metadata={"pct": 51})
        result = em.get_relationships("a", direction="outgoing")
        assert "pct" in result
        assert "51" in result

    def test_multiple_outgoing(self, em):
        em.create_entity("hub", "Hub", "company")
        for i in range(5):
            eid = f"spoke-{i}"
            em.create_entity(eid, f"Spoke {i}", "llc")
            em.add_relationship("hub", eid, "parent_of")
        result = em.get_relationships("hub", direction="outgoing")
        assert "Outgoing" in result
        for i in range(5):
            assert f"spoke-{i}" in result

    def test_multiple_incoming(self, em):
        em.create_entity("target", "Target", "company")
        for i in range(5):
            eid = f"src-{i}"
            em.create_entity(eid, f"Source {i}", "company")
            em.add_relationship(eid, "target", "investor_in")
        result = em.get_relationships("target", direction="incoming")
        assert "Incoming" in result
        for i in range(5):
            assert f"src-{i}" in result


# ============================================================================
# Additional edge cases (bonus coverage)
# ============================================================================

class TestMiscEdgeCases:
    """Miscellaneous edge cases not covered above."""

    def test_remove_relationship_returns_not_found(self, em):
        """Removing a relationship that doesn't exist."""
        result = em.remove_relationship("a", "b", "parent_of")
        assert "No relationship found" in result

    def test_duplicate_relationship_same_type(self, em):
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        em.add_relationship("a", "b", "parent_of")
        result = em.add_relationship("a", "b", "parent_of")
        assert "Error" in result
        assert "already exists" in result

    def test_same_pair_different_relationship_types(self, em):
        """A -> B can have multiple relationship types."""
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        r1 = em.add_relationship("a", "b", "parent_of")
        r2 = em.add_relationship("a", "b", "investor_in")
        assert "Added relationship" in r1
        assert "Added relationship" in r2

    def test_bidirectional_relationship(self, em):
        """A -> B and B -> A with same type are distinct relationships."""
        em.create_entity("a", "A", "company")
        em.create_entity("b", "B", "company")
        r1 = em.add_relationship("a", "b", "partner_of")
        r2 = em.add_relationship("b", "a", "partner_of")
        assert "Added relationship" in r1
        assert "Added relationship" in r2

    def test_update_all_fields_at_once(self, em):
        em.create_entity("all", "All Fields", "company", jurisdiction="US-CA")
        result = em.update_entity(
            "all",
            name="New Name",
            status="acquired",
            jurisdiction="US-NY",
            metadata={"new": True},
        )
        assert "Updated" in result
        detail = em.get_entity("all")
        assert "New Name" in detail
        assert "acquired" in detail
        assert "US-NY" in detail
        assert "new" in detail

    def test_entity_id_normalization_in_queries(self, em):
        """All methods normalize entity_id to lowercase + stripped."""
        em.create_entity("MyEntity", "My Entity", "company")
        assert "My Entity" in em.get_entity("  MYENTITY  ")
        assert "Updated" in em.update_entity("  MyEntity  ", name="Updated")
        assert "Dissolved" in em.delete_entity("  MYENTITY  ")

    def test_get_entity_tree_nonexistent(self, em):
        result = em.get_entity_tree("does-not-exist")
        assert "Error" in result
        assert "not found" in result

    def test_metadata_merge_adds_new_keys(self, em):
        em.create_entity("m", "M", "company", metadata={"x": 1})
        em.update_entity("m", metadata={"y": 2})
        detail = em.get_entity("m")
        assert '"x": 1' in detail or '"x":1' in detail
        assert '"y": 2' in detail or '"y":2' in detail

    def test_metadata_merge_removes_key_with_none(self, em):
        em.create_entity("m", "M", "company", metadata={"x": 1, "y": 2})
        em.update_entity("m", metadata={"x": None})
        row = em._conn.execute(
            "SELECT metadata FROM entities WHERE id = 'm'"
        ).fetchone()
        import json
        meta = json.loads(row["metadata"])
        assert "x" not in meta
        assert meta["y"] == 2

    def test_list_entities_combined_filters(self, em):
        """Filter by both type and status simultaneously."""
        em.create_entity("a", "Alpha LLC", "llc")
        em.create_entity("b", "Beta LLC", "llc")
        em.create_entity("c", "Gamma Corp", "company")
        em.delete_entity("b")  # dissolved
        result = em.list_entities(entity_type="llc", status="active")
        assert "Alpha LLC" in result
        assert "Beta LLC" not in result
        assert "Gamma Corp" not in result

    def test_entity_timestamps_present(self, em):
        """Created and updated timestamps should be ISO format UTC."""
        em.create_entity("ts", "Timestamp Test", "company")
        detail = em.get_entity("ts")
        assert "Created" in detail
        assert "Updated" in detail
        # Both should contain ISO 8601 format
        assert "T" in detail  # ISO timestamp separator

    def test_close_is_idempotent(self, tmp_path):
        """Calling close() twice should not raise."""
        mgr = EntityManager(db_path=tmp_path / "close_test.db")
        mgr.close()
        mgr.close()  # should not raise
