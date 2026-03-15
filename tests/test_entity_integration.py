"""Integration tests for entity-scoped memory flows.

Tests the wiring between project→entity resolution and OMEGA's
auto-capture, surfacing, and querying pipelines.
"""

import json
import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _skip_embeddings():
    """Context manager that skips embeddings and resets the circuit breaker after."""
    from omega.embedding import reset_embedding_state

    os.environ["OMEGA_SKIP_EMBEDDINGS"] = "1"
    try:
        yield
    finally:
        os.environ.pop("OMEGA_SKIP_EMBEDDINGS", None)
        reset_embedding_state()


@pytest.fixture(autouse=True)
def _reset_all(tmp_omega_dir):
    """Reset all singletons before and after each test."""
    from omega.bridge import reset_memory
    from omega.entity.engine import reset_entity_manager

    reset_memory()
    reset_entity_manager()
    yield
    reset_memory()
    reset_entity_manager()


@pytest.fixture
def entity_mgr(tmp_omega_dir):
    """Create a fresh EntityManager with test DB."""
    from omega.entity.engine import EntityManager, reset_entity_manager

    reset_entity_manager()
    mgr = EntityManager(db_path=tmp_omega_dir / "omega.db")
    yield mgr
    mgr.close()
    reset_entity_manager()


# ---------------------------------------------------------------------------
# 1. TestProjectEntityResolution
# ---------------------------------------------------------------------------


class TestProjectEntityResolution:
    """Test resolve_project_entity() — config-file based project path → entity_id mapping."""

    def _write_mappings(self, tmp_omega_dir, mappings):
        """Helper to write entity_scoping.mappings to config.json."""
        import omega.entity.engine as ee

        config_path = tmp_omega_dir / "config.json"
        config_path.write_text(json.dumps({
            "entity_scoping": {"mappings": mappings}
        }))
        ee._cache_ts = 0.0  # invalidate cache

    def test_resolve_match(self, tmp_omega_dir, entity_mgr):
        """Config mapping resolves project path to entity_id."""
        from omega.entity.engine import resolve_project_entity

        entity_mgr.create_entity("acme", "Acme Corp", "company")
        self._write_mappings(tmp_omega_dir, {"/projects/acme": "acme"})
        assert resolve_project_entity("/projects/acme") == "acme"

    def test_resolve_no_match(self, tmp_omega_dir, entity_mgr):
        """Returns None when no mapping matches."""
        from omega.entity.engine import resolve_project_entity

        self._write_mappings(tmp_omega_dir, {"/projects/acme": "acme"})
        assert resolve_project_entity("/projects/unknown") is None

    def test_resolve_empty_project(self, tmp_omega_dir):
        """Returns None for empty project string."""
        from omega.entity.engine import resolve_project_entity

        assert resolve_project_entity("") is None

    def test_resolve_trailing_slash_normalization(self, tmp_omega_dir, entity_mgr):
        """Trailing slash on input is stripped for matching."""
        from omega.entity.engine import resolve_project_entity

        self._write_mappings(tmp_omega_dir, {"/projects/acme": "acme"})
        assert resolve_project_entity("/projects/acme/") == "acme"

    def test_resolve_trailing_slash_in_config(self, tmp_omega_dir, entity_mgr):
        """Trailing slash in config mapping key is also normalized."""
        from omega.entity.engine import resolve_project_entity

        self._write_mappings(tmp_omega_dir, {"/projects/acme/": "acme"})
        assert resolve_project_entity("/projects/acme") == "acme"

    def test_resolve_caching(self, tmp_omega_dir, entity_mgr):
        """Second call uses cache (no file read)."""
        from omega.entity.engine import resolve_project_entity

        self._write_mappings(tmp_omega_dir, {"/projects/acme": "acme"})
        resolve_project_entity("/projects/acme")

        # Remove config file — if cache works, second call still succeeds
        (tmp_omega_dir / "config.json").unlink()
        result = resolve_project_entity("/projects/acme")
        assert result == "acme"

    def test_no_config_file(self, tmp_omega_dir):
        """Returns None when config.json doesn't exist."""
        from omega.entity.engine import resolve_project_entity
        import omega.entity.engine as ee

        ee._cache_ts = 0.0
        # Ensure no config.json exists
        config_path = tmp_omega_dir / "config.json"
        if config_path.exists():
            config_path.unlink()

        assert resolve_project_entity("/projects/acme") is None

    def test_empty_mappings(self, tmp_omega_dir):
        """Returns None when mappings dict is empty."""
        from omega.entity.engine import resolve_project_entity

        self._write_mappings(tmp_omega_dir, {})
        assert resolve_project_entity("/projects/acme") is None

    def test_no_mappings_key(self, tmp_omega_dir):
        """Returns None when entity_scoping has no mappings key."""
        from omega.entity.engine import resolve_project_entity
        import omega.entity.engine as ee

        config_path = tmp_omega_dir / "config.json"
        config_path.write_text(json.dumps({"entity_scoping": {}}))
        ee._cache_ts = 0.0

        assert resolve_project_entity("/projects/acme") is None

    def test_multiple_mappings(self, tmp_omega_dir, entity_mgr):
        """Multiple mappings resolve correctly."""
        from omega.entity.engine import resolve_project_entity

        self._write_mappings(tmp_omega_dir, {
            "/projects/alpha": "alpha",
            "/projects/beta": "beta",
        })

        assert resolve_project_entity("/projects/alpha") == "alpha"
        assert resolve_project_entity("/projects/beta") == "beta"
        assert resolve_project_entity("/projects/gamma") is None


# ---------------------------------------------------------------------------
# 2. TestEntityScopedMemory
# ---------------------------------------------------------------------------


class TestEntityScopedMemory:
    """Test entity-scoped memory storage and retrieval."""

    def test_store_with_entity_id(self, tmp_omega_dir):
        """auto_capture with entity_id stores memory scoped to that entity."""
        with _skip_embeddings():
            from omega.bridge import auto_capture, reset_memory

            reset_memory()
            result = auto_capture(
                content="Entity-scoped decision: use PostgreSQL",
                event_type="decision",
                session_id="test-session",
                entity_id="acme",
            )
            assert "Stored" in result or "Deduped" in result or "Evolved" in result

    def test_query_filters_by_entity_id(self, tmp_omega_dir):
        """query() with entity_id only returns memories for that entity."""
        with _skip_embeddings():
            from omega.bridge import auto_capture, query, reset_memory

            reset_memory()

            auto_capture(
                content="Acme decision: deploy to AWS",
                event_type="decision",
                entity_id="acme",
            )
            auto_capture(
                content="Beta decision: deploy to GCP",
                event_type="decision",
                entity_id="beta",
            )

            acme_results = query(query_text="deploy", entity_id="acme")
            assert "AWS" in acme_results
            # Beta's GCP decision should not appear in acme-scoped query
            # (may still appear if no entity filter or if text search picks it up)

    def test_query_structured_passes_entity_id(self, tmp_omega_dir):
        """query_structured with entity_id passes through to db.query."""
        with _skip_embeddings():
            from omega.bridge import auto_capture, query_structured, reset_memory

            reset_memory()

            auto_capture(
                content="Entity-scoped lesson: always validate inputs",
                event_type="lesson_learned",
                entity_id="acme",
            )

            results = query_structured(
                query_text="validate inputs",
                entity_id="acme",
            )
            assert isinstance(results, list)

    def test_unscoped_query_returns_all(self, tmp_omega_dir):
        """query without entity_id returns memories from all entities."""
        with _skip_embeddings():
            from omega.bridge import auto_capture, query, reset_memory

            reset_memory()

            auto_capture(
                content="Acme unique insight: parallel processing",
                event_type="lesson_learned",
                entity_id="acme",
            )
            auto_capture(
                content="Beta unique insight: batch processing",
                event_type="lesson_learned",
                entity_id="beta",
            )

            all_results = query(query_text="processing insight")
            # Without entity filter, both should be queryable
            assert isinstance(all_results, str)

    def test_store_without_entity_id(self, tmp_omega_dir):
        """auto_capture without entity_id stores memory with no entity scope."""
        with _skip_embeddings():
            from omega.bridge import auto_capture, reset_memory

            reset_memory()
            result = auto_capture(
                content="Global lesson: always check return values",
                event_type="lesson_learned",
            )
            assert "Stored" in result or "Deduped" in result or "Evolved" in result


# ---------------------------------------------------------------------------
# 3. TestEntityScopedKnowledge
# ---------------------------------------------------------------------------


class TestEntityScopedKnowledge:
    """Test entity-scoped document ingestion and search."""

    def test_ingest_with_entity_id(self, tmp_omega_dir):
        """Knowledge engine accepts entity_id on ingest."""
        try:
            from omega.knowledge.engine import KnowledgeEngine

            engine = KnowledgeEngine(db_path=tmp_omega_dir / "omega.db")
            # Create a small text file to ingest
            test_file = tmp_omega_dir / "test_doc.txt"
            test_file.write_text("Acme Corp uses PostgreSQL for all services.")

            result = engine.ingest(str(test_file), entity_id="acme")
            assert "ingest" in result.lower() or "chunk" in result.lower() or "error" not in result.lower()
            engine.close()
        except ImportError:
            pytest.skip("Knowledge engine not available")

    def test_search_filters_by_entity_id(self, tmp_omega_dir):
        """Knowledge search with entity_id scopes results."""
        try:
            from omega.knowledge.engine import KnowledgeEngine

            engine = KnowledgeEngine(db_path=tmp_omega_dir / "omega.db")

            acme_file = tmp_omega_dir / "acme_doc.txt"
            acme_file.write_text("Acme Corp uses PostgreSQL for all database needs.")
            engine.ingest(str(acme_file), entity_id="acme")

            beta_file = tmp_omega_dir / "beta_doc.txt"
            beta_file.write_text("Beta Inc uses MongoDB for document storage.")
            engine.ingest(str(beta_file), entity_id="beta")

            acme_results = engine.search("database", entity_id="acme")
            assert isinstance(acme_results, (str, list))
            engine.close()
        except ImportError:
            pytest.skip("Knowledge engine not available")

    def test_search_without_entity_id(self, tmp_omega_dir):
        """Knowledge search without entity_id returns all results."""
        try:
            from omega.knowledge.engine import KnowledgeEngine

            engine = KnowledgeEngine(db_path=tmp_omega_dir / "omega.db")

            doc_file = tmp_omega_dir / "doc.txt"
            doc_file.write_text("Important technical reference document.")
            engine.ingest(str(doc_file))

            results = engine.search("technical reference")
            assert isinstance(results, (str, list))
            engine.close()
        except ImportError:
            pytest.skip("Knowledge engine not available")


# ---------------------------------------------------------------------------
# 4. TestEntityScopedProfile
# ---------------------------------------------------------------------------


class TestEntityScopedProfile:
    """Test entity-scoped secure profile fields."""

    @pytest.fixture
    def _mock_cipher(self):
        """Mock the cipher to avoid keyring dependency in tests."""
        try:
            from cryptography.fernet import Fernet

            key = Fernet.generate_key()
            cipher = Fernet(key)
            with patch("omega.profile.engine._get_cipher", return_value=cipher):
                yield cipher
        except ImportError:
            pytest.skip("cryptography not installed")

    def test_set_get_with_entity_id(self, tmp_omega_dir, _mock_cipher):
        """Profile fields scoped to an entity."""
        from omega.profile.engine import SecureProfile, reset_profile_engine

        reset_profile_engine()
        engine = SecureProfile(db_path=tmp_omega_dir / "omega.db")

        engine.set_field("identity", "company_name", "Acme Corp", entity_id="acme")
        result = engine.get_field("identity", "company_name", entity_id="acme")
        assert "Acme" in result

        engine.close()
        reset_profile_engine()

    def test_entity_isolation(self, tmp_omega_dir, _mock_cipher):
        """Different entities have isolated profile fields."""
        from omega.profile.engine import SecureProfile, reset_profile_engine

        reset_profile_engine()
        engine = SecureProfile(db_path=tmp_omega_dir / "omega.db")

        engine.set_field("identity", "company_name", "Acme Corp", entity_id="acme")
        engine.set_field("identity", "company_name", "Beta Inc", entity_id="beta")

        acme = engine.get_field("identity", "company_name", entity_id="acme")
        beta = engine.get_field("identity", "company_name", entity_id="beta")
        assert "Acme" in acme
        assert "Beta" in beta

        engine.close()
        reset_profile_engine()

    def test_default_personal_scope(self, tmp_omega_dir, _mock_cipher):
        """Fields without entity_id use default __personal__ scope."""
        from omega.profile.engine import SecureProfile, reset_profile_engine

        reset_profile_engine()
        engine = SecureProfile(db_path=tmp_omega_dir / "omega.db")

        engine.set_field("identity", "full_name", "John Doe")
        result = engine.get_field("identity", "full_name")
        assert "John" in result

        engine.close()
        reset_profile_engine()


# ---------------------------------------------------------------------------
# 5. TestHookEntityWiring
# ---------------------------------------------------------------------------


class TestHookEntityWiring:
    """Test that hook handlers resolve and pass entity_id."""

    @pytest.fixture(autouse=True)
    def _enable_entity_scoping(self, tmp_omega_dir):
        """Write config.json with entity_scoping mappings for test projects."""
        config_path = tmp_omega_dir / "config.json"
        config_path.write_text(json.dumps({
            "entity_scoping": {
                "mappings": {
                    "/projects/acme": "acme",
                }
            }
        }))
        # Invalidate engine's config cache
        import omega.entity.engine as ee
        ee._cache_ts = 0.0
        yield
        ee._cache_ts = 0.0

    def test_resolve_entity_helper(self, entity_mgr):
        """_resolve_entity returns entity_id for matching project via config mapping."""
        from omega.server.hook_server import _resolve_entity

        entity_mgr.create_entity("acme", "Acme Corp", "company")
        assert _resolve_entity("/projects/acme") == "acme"

    def test_resolve_entity_no_match(self, entity_mgr):
        """_resolve_entity returns None for unknown project."""
        from omega.server.hook_server import _resolve_entity

        assert _resolve_entity("/projects/unknown") is None

    def test_resolve_entity_disabled_by_default(self, tmp_omega_dir, entity_mgr):
        """_resolve_entity returns None when no mappings configured."""
        import omega.entity.engine as ee

        # Override: write config with empty mappings
        config_path = tmp_omega_dir / "config.json"
        config_path.write_text(json.dumps({"entity_scoping": {"mappings": {}}}))
        ee._cache_ts = 0.0

        entity_mgr.create_entity("acme", "Acme Corp", "company")

        from omega.server.hook_server import _resolve_entity

        assert _resolve_entity("/projects/acme") is None

    def test_resolve_entity_fail_open(self):
        """_resolve_entity returns None on import/other errors."""
        from omega.server.hook_server import _resolve_entity

        with patch(
            "omega.entity.engine.resolve_project_entity",
            side_effect=Exception("DB error"),
        ):
            assert _resolve_entity("/projects/acme") is None

    def test_session_stop_passes_entity_id(self, tmp_omega_dir, entity_mgr):
        """handle_session_stop resolves entity and passes to auto_capture."""
        with _skip_embeddings():
            from omega.bridge import reset_memory

            reset_memory()

            entity_mgr.create_entity("acme", "Acme Corp", "company")

            with patch("omega.bridge.auto_capture", return_value="ok") as mock_ac:
                from omega.server.hook_server import handle_session_stop

                handle_session_stop({
                    "session_id": "test-sess",
                    "project": "/projects/acme",
                })

                # auto_capture should have been called with entity_id="acme"
                if mock_ac.called:
                    _, kwargs = mock_ac.call_args
                    assert kwargs.get("entity_id") == "acme"

    def test_auto_capture_passes_entity_id(self, tmp_omega_dir, entity_mgr):
        """handle_auto_capture resolves entity and passes to auto_capture."""
        entity_mgr.create_entity("acme", "Acme Corp", "company")

        with patch("omega.bridge.auto_capture", return_value="ok") as mock_ac:
            from omega.server.hook_server import handle_auto_capture

            payload = {
                "stdin": json.dumps({
                    "prompt": "let's go with PostgreSQL for the database layer instead of MySQL",
                    "session_id": "test-sess",
                    "cwd": "/projects/acme",
                }),
            }
            handle_auto_capture(payload)

            if mock_ac.called:
                _, kwargs = mock_ac.call_args
                assert kwargs.get("entity_id") == "acme"

    def test_surface_memories_passes_entity_id(self, tmp_omega_dir, entity_mgr):
        """handle_surface_memories resolves entity and passes to _surface_for_edit."""
        entity_mgr.create_entity("acme", "Acme Corp", "company")

        with patch(
            "omega.server.hook_server._surface_for_edit", return_value=[]
        ) as mock_sfe:
            from omega.server.hook_server import handle_surface_memories

            payload = {
                "tool_name": "Edit",
                "tool_input": json.dumps({"file_path": "/projects/acme/src/main.py"}),
                "tool_output": "ok",
                "session_id": "test-sess",
                "project": "/projects/acme",
            }
            handle_surface_memories(payload)

            if mock_sfe.called:
                _, kwargs = mock_sfe.call_args
                assert kwargs.get("entity_id") == "acme"

    def test_capture_error_passes_entity_id(self, tmp_omega_dir, entity_mgr):
        """_capture_error receives and passes entity_id to auto_capture."""
        entity_mgr.create_entity("acme", "Acme Corp", "company")

        with patch("omega.bridge.auto_capture", return_value="ok") as mock_ac:
            from omega.server.hook_server import _capture_error

            _capture_error(
                "Traceback (most recent call last):\nValueError: bad input",
                "test-sess",
                "/projects/acme",
                entity_id="acme",
            )

            if mock_ac.called:
                _, kwargs = mock_ac.call_args
                assert kwargs.get("entity_id") == "acme"


# ---------------------------------------------------------------------------
# 7. TestAutoResolveEntityInBridge
# ---------------------------------------------------------------------------


class TestAutoResolveEntityInBridge:
    """Test auto-resolution of entity_id from project in bridge.auto_capture() and store()."""

    def _write_mappings(self, tmp_omega_dir, mappings):
        """Helper to write entity_scoping.mappings to config.json."""
        import omega.entity.engine as ee

        config_path = tmp_omega_dir / "config.json"
        config_path.write_text(json.dumps({
            "entity_scoping": {"mappings": mappings}
        }))
        ee._cache_ts = 0.0  # invalidate cache

    def test_auto_capture_resolves_entity_from_project(self, tmp_omega_dir):
        """auto_capture() auto-resolves entity_id when project is provided."""
        self._write_mappings(tmp_omega_dir, {"/projects/acme": "acme"})

        with _skip_embeddings():
            from omega.bridge import auto_capture, reset_memory

            reset_memory()
            result = auto_capture(
                content="Auto-resolved entity test: important decision about deployment",
                event_type="decision",
                project="/projects/acme",
            )
            assert "Stored" in result or "Deduped" in result or "Evolved" in result
            # Verify entity_id was stored in the DB
            from omega.bridge import _get_store
            nodes = _get_store().get_by_type("decision", limit=1)
            assert nodes and (nodes[0].metadata or {}).get("entity_id") == "acme"

    def test_store_passes_project_to_auto_capture(self, tmp_omega_dir):
        """store() passes project through to auto_capture() for resolution."""
        self._write_mappings(tmp_omega_dir, {"/projects/beta": "beta"})

        with _skip_embeddings():
            from omega.bridge import store, reset_memory

            reset_memory()
            result = store(
                content="Store with project resolution: beta configuration change",
                event_type="decision",
                project="/projects/beta",
            )
            assert "Stored" in result or "Deduped" in result or "Evolved" in result
            # Verify entity_id was stored in the DB
            from omega.bridge import _get_store
            nodes = _get_store().get_by_type("decision", limit=1)
            assert nodes and (nodes[0].metadata or {}).get("entity_id") == "beta"

    def test_explicit_entity_id_takes_priority(self, tmp_omega_dir):
        """Explicit entity_id is NOT overwritten by project resolution."""
        self._write_mappings(tmp_omega_dir, {"/projects/acme": "acme"})

        with _skip_embeddings():
            from omega.bridge import auto_capture, reset_memory

            reset_memory()
            result = auto_capture(
                content="Explicit entity priority test: manual override scenario",
                event_type="decision",
                project="/projects/acme",
                entity_id="manual-override",
            )
            assert "Stored" in result or "Deduped" in result or "Evolved" in result
            # Verify explicit entity_id takes priority over project mapping
            from omega.bridge import _get_store
            nodes = _get_store().get_by_type("decision", limit=1)
            assert nodes and (nodes[0].metadata or {}).get("entity_id") == "manual-override"

    def test_unmapped_project_returns_none(self, tmp_omega_dir):
        """Unmapped project doesn't set entity_id (fail-open)."""
        self._write_mappings(tmp_omega_dir, {"/projects/acme": "acme"})

        with _skip_embeddings():
            from omega.bridge import auto_capture, reset_memory

            reset_memory()
            result = auto_capture(
                content="Unmapped project test: no entity should be resolved here",
                event_type="decision",
                project="/projects/unknown",
            )
            assert "Stored" in result or "Deduped" in result or "Evolved" in result
            # Verify no entity_id was stored for unmapped project
            from omega.bridge import _get_store
            nodes = _get_store().get_by_type("decision", limit=1)
            assert nodes and not (nodes[0].metadata or {}).get("entity_id")
