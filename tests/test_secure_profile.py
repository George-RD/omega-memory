"""Tests for OMEGA Secure Profile module."""

import os
import pytest
from unittest.mock import patch


@pytest.fixture
def profile_engine(tmp_omega_dir):
    """Create a fresh SecureProfile for testing."""
    os.environ["OMEGA_HOME"] = str(tmp_omega_dir)
    from omega.profile.engine import SecureProfile, reset_profile_engine

    reset_profile_engine()
    db_path = tmp_omega_dir / "test.db"
    engine = SecureProfile(db_path=db_path)
    yield engine
    engine.close()
    reset_profile_engine()


@pytest.fixture
def _mock_cipher():
    """Mock the cipher to avoid keyring/cryptography dependency in tests."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    cipher = Fernet(key)

    with patch("omega.profile.engine._get_cipher", return_value=cipher):
        yield cipher


class TestSecureProfileSchema:
    """Test schema creation and table structure."""

    def test_tables_created(self, profile_engine):
        """Verify secure_profile table exists."""
        tables = profile_engine._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='secure_profile'"
        ).fetchall()
        assert len(tables) == 1

    def test_schema_version(self, profile_engine):
        """Verify schema version table."""
        row = profile_engine._conn.execute(
            "SELECT version FROM profile_schema_version"
        ).fetchone()
        assert row["version"] == 2

    def test_unique_constraint(self, profile_engine, _mock_cipher):
        """Verify category+field_name uniqueness."""
        profile_engine.set_field("identity", "name", "Test User")
        result = profile_engine.set_field("identity", "name", "Updated User")
        assert "Stored" in result

        # Should have exactly 1 row
        count = profile_engine._conn.execute(
            "SELECT COUNT(*) FROM secure_profile WHERE category='identity' AND field_name='name'"
        ).fetchone()[0]
        assert count == 1


class TestSetField:
    """Test field storage and encryption."""

    def test_set_basic_field(self, profile_engine, _mock_cipher):
        result = profile_engine.set_field("identity", "full_name", "John Doe")
        assert "Stored" in result
        assert "identity/full_name" in result

    def test_set_with_metadata(self, profile_engine, _mock_cipher):
        result = profile_engine.set_field(
            "identity", "passport", "AB1234567",
            metadata={"country": "US", "expires": "2030-01"}
        )
        assert "Stored" in result

    def test_set_invalid_category(self, profile_engine, _mock_cipher):
        result = profile_engine.set_field("invalid_cat", "name", "Test")
        assert "Error" in result
        assert "invalid category" in result

    def test_set_empty_field_name(self, profile_engine, _mock_cipher):
        result = profile_engine.set_field("identity", "", "Test")
        assert "Error" in result

    def test_set_empty_value(self, profile_engine, _mock_cipher):
        result = profile_engine.set_field("identity", "name", "  ")
        assert "Error" in result

    def test_value_is_encrypted_in_db(self, profile_engine, _mock_cipher):
        """Verify plaintext is not stored in the database."""
        secret = "SSN-123-45-6789"
        profile_engine.set_field("identity", "ssn", secret)

        row = profile_engine._conn.execute(
            "SELECT field_value_encrypted FROM secure_profile WHERE field_name='ssn'"
        ).fetchone()
        assert row is not None
        # The stored value should NOT be the plaintext
        assert row["field_value_encrypted"] != secret

    def test_upsert_updates_value(self, profile_engine, _mock_cipher):
        """Verify that setting the same field updates the value."""
        profile_engine.set_field("identity", "name", "Old Name")
        profile_engine.set_field("identity", "name", "New Name")

        result = profile_engine.get_field("identity", "name")
        assert "New Name" in result

    def test_all_valid_categories(self, profile_engine, _mock_cipher):
        """Verify all valid categories work."""
        from omega.profile.engine import CATEGORIES

        for cat in CATEGORIES:
            result = profile_engine.set_field(cat, "test_field", f"value_{cat}")
            assert "Stored" in result, f"Category {cat} should be valid"


class TestGetField:
    """Test field retrieval and decryption."""

    def test_get_single_field(self, profile_engine, _mock_cipher):
        profile_engine.set_field("medical", "blood_type", "O+")
        result = profile_engine.get_field("medical", "blood_type")
        assert "O+" in result

    def test_get_all_fields_in_category(self, profile_engine, _mock_cipher):
        profile_engine.set_field("medical", "blood_type", "O+")
        profile_engine.set_field("medical", "allergies", "Penicillin")
        profile_engine.set_field("medical", "conditions", "None")

        result = profile_engine.get_field("medical")
        assert "3 fields" in result
        assert "blood_type" in result
        assert "allergies" in result

    def test_get_nonexistent_field(self, profile_engine, _mock_cipher):
        result = profile_engine.get_field("identity", "nonexistent")
        assert "No field found" in result

    def test_get_nonexistent_category(self, profile_engine, _mock_cipher):
        result = profile_engine.get_field("identity")
        assert "No fields found" in result

    def test_get_invalid_category(self, profile_engine, _mock_cipher):
        result = profile_engine.get_field("bogus")
        assert "Error" in result

    def test_roundtrip_encryption(self, profile_engine, _mock_cipher):
        """Verify encrypt → store → retrieve → decrypt roundtrip."""
        secrets = {
            "ssn": "123-45-6789",
            "bank_account": "9876543210",
            "passport": "AB1234567",
        }
        for field, value in secrets.items():
            profile_engine.set_field("identity", field, value)

        for field, value in secrets.items():
            result = profile_engine.get_field("identity", field)
            assert value in result


class TestSearch:
    """Test profile search functionality."""

    def test_search_by_field_name(self, profile_engine, _mock_cipher):
        profile_engine.set_field("identity", "full_name", "John Doe")
        profile_engine.set_field("medical", "blood_type", "O+")

        result = profile_engine.search("name")
        assert "full_name" in result

    def test_search_by_category(self, profile_engine, _mock_cipher):
        profile_engine.set_field("medical", "blood_type", "O+")
        result = profile_engine.search("medical")
        assert "medical" in result

    def test_search_by_metadata(self, profile_engine, _mock_cipher):
        profile_engine.set_field(
            "identity", "passport", "AB123",
            metadata={"country": "US"}
        )
        result = profile_engine.search("country")
        assert "passport" in result

    def test_search_no_results(self, profile_engine, _mock_cipher):
        result = profile_engine.search("xyznonexistent")
        assert "No profile fields" in result

    def test_search_empty_query(self, profile_engine, _mock_cipher):
        result = profile_engine.search("")
        assert "Error" in result


class TestDeleteField:
    """Test field deletion."""

    def test_delete_existing(self, profile_engine, _mock_cipher):
        profile_engine.set_field("identity", "name", "John Doe")
        result = profile_engine.delete_field("identity", "name")
        assert "Deleted" in result

        # Verify it's gone
        result = profile_engine.get_field("identity", "name")
        assert "No field found" in result

    def test_delete_nonexistent(self, profile_engine, _mock_cipher):
        result = profile_engine.delete_field("identity", "nonexistent")
        assert "No field found" in result


class TestListCategories:
    """Test category listing."""

    def test_empty_list(self, profile_engine, _mock_cipher):
        result = profile_engine.list_categories()
        assert "No profile data" in result
        assert "Valid categories" in result

    def test_with_data(self, profile_engine, _mock_cipher):
        profile_engine.set_field("identity", "name", "John")
        profile_engine.set_field("identity", "email", "john@test.com")
        profile_engine.set_field("medical", "blood_type", "O+")

        result = profile_engine.list_categories()
        assert "identity" in result
        assert "2 field(s)" in result
        assert "medical" in result
        assert "1 field(s)" in result
        assert "3 encrypted field(s)" in result


class TestHandlers:
    """Test MCP handler functions."""

    @pytest.mark.asyncio
    async def test_handle_profile_set(self, profile_engine, _mock_cipher):
        with patch("omega.profile.engine.get_profile_engine", return_value=profile_engine):
            from omega.profile.handlers import handle_omega_profile_set

            result = await handle_omega_profile_set({
                "category": "identity",
                "field_name": "name",
                "value": "Test User",
            })
            assert not result.get("isError")
            assert "Stored" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_handle_profile_set_missing_args(self):
        from omega.profile.handlers import handle_omega_profile_set

        result = await handle_omega_profile_set({})
        assert result.get("isError")

    @pytest.mark.asyncio
    async def test_handle_profile_get(self, profile_engine, _mock_cipher):
        profile_engine.set_field("identity", "name", "Test User")

        with patch("omega.profile.engine.get_profile_engine", return_value=profile_engine):
            from omega.profile.handlers import handle_omega_profile_get

            result = await handle_omega_profile_get({
                "category": "identity",
                "field_name": "name",
            })
            assert not result.get("isError")
            assert "Test User" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_handle_profile_search(self, profile_engine, _mock_cipher):
        profile_engine.set_field("identity", "name", "Test User")

        with patch("omega.profile.engine.get_profile_engine", return_value=profile_engine):
            from omega.profile.handlers import handle_omega_profile_search

            result = await handle_omega_profile_search({"query": "name"})
            assert not result.get("isError")

    @pytest.mark.asyncio
    async def test_handler_missing_query(self):
        from omega.profile.handlers import handle_omega_profile_search

        result = await handle_omega_profile_search({})
        assert result.get("isError")


class TestToolSchemas:
    """Test tool schema definitions."""

    def test_schemas_valid(self):
        from omega.profile.tool_schemas import PROFILE_TOOL_SCHEMAS

        assert len(PROFILE_TOOL_SCHEMAS) >= 4
        names = {s["name"] for s in PROFILE_TOOL_SCHEMAS}
        assert "omega_profile_set" in names
        assert "omega_profile_get" in names
        assert "omega_profile_search" in names
        assert "omega_profile_list" in names

    def test_schemas_have_required_fields(self):
        from omega.profile.tool_schemas import PROFILE_TOOL_SCHEMAS

        for schema in PROFILE_TOOL_SCHEMAS:
            assert "name" in schema
            assert "description" in schema
            assert "inputSchema" in schema
            assert schema["inputSchema"]["type"] == "object"


class TestListCategoriesEntityFilter:
    """Test entity_id filtering in list_categories."""

    def test_list_categories_entity_filter(self, profile_engine, _mock_cipher):
        """Entity-scoped fields only returned when filtered."""
        profile_engine.set_field("identity", "name", "John", entity_id="__personal__")
        profile_engine.set_field("identity", "ein", "12-345", entity_id="acme")
        profile_engine.set_field("financial", "revenue", "1M", entity_id="acme")

        result = profile_engine.list_categories(entity_id="acme")
        assert "acme" in result
        assert "2 encrypted field(s)" in result

        # Personal fields should not appear in acme-scoped list
        result_personal = profile_engine.list_categories(entity_id="__personal__")
        assert "1 encrypted field(s)" in result_personal


class TestProfileHandlersList:
    """Test omega_profile_list handler."""

    def test_profile_handlers_has_list(self):
        from omega.profile.handlers import PROFILE_HANDLERS

        assert "omega_profile_list" in PROFILE_HANDLERS

    @pytest.mark.asyncio
    async def test_handle_profile_list(self, profile_engine, _mock_cipher):
        profile_engine.set_field("identity", "name", "John")
        profile_engine.set_field("medical", "blood_type", "O+")

        with patch("omega.profile.engine.get_profile_engine", return_value=profile_engine):
            from omega.profile.handlers import handle_omega_profile_list

            result = await handle_omega_profile_list({})
            assert not result.get("isError")
            text = result["content"][0]["text"]
            assert "identity" in text
            assert "medical" in text

    @pytest.mark.asyncio
    async def test_handle_profile_list_with_entity(self, profile_engine, _mock_cipher):
        profile_engine.set_field("identity", "ein", "12-345", entity_id="acme")

        with patch("omega.profile.engine.get_profile_engine", return_value=profile_engine):
            from omega.profile.handlers import handle_omega_profile_list

            result = await handle_omega_profile_list({"entity_id": "acme"})
            assert not result.get("isError")
            text = result["content"][0]["text"]
            assert "acme" in text
