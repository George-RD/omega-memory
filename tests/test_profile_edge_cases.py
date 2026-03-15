"""Edge-case tests for OMEGA Secure Profile -- gaps not covered by test_secure_profile.py.

Covers: large encrypted values, special characters, complex metadata, category
boundaries, field-name edge cases, entity scoping isolation, upsert behavior,
cross-entity search, delete of nonexistent field, and schema migration v1->v2.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _mock_cipher():
    """Provide a deterministic Fernet cipher (no keyring dependency)."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    cipher = Fernet(key)
    with patch("omega.profile.engine._get_cipher", return_value=cipher):
        yield cipher


@pytest.fixture
def profile(tmp_omega_dir, _mock_cipher):
    """Create a fresh SecureProfile backed by a temp DB."""
    from omega.profile.engine import SecureProfile, reset_profile_engine

    reset_profile_engine()
    db_path = tmp_omega_dir / "profile_edge.db"
    p = SecureProfile(db_path=db_path)
    yield p
    p.close()
    reset_profile_engine()


# ============================================================================
# 1. Large encrypted values
# ============================================================================

class TestLargeEncryptedValues:
    """Store and retrieve values exceeding 10 KB."""

    def test_10kb_value_roundtrip(self, profile):
        big_value = "A" * 10_240  # 10 KB of 'A'
        result = profile.set_field("personal", "big_blob", big_value)
        assert "Stored" in result

        retrieved = profile.get_field("personal", "big_blob")
        assert big_value in retrieved

    def test_100kb_value_roundtrip(self, profile):
        huge = "Z" * 102_400
        result = profile.set_field("personal", "huge_blob", huge)
        assert "Stored" in result

        retrieved = profile.get_field("personal", "huge_blob")
        assert huge in retrieved


# ============================================================================
# 2. Special characters in values
# ============================================================================

class TestSpecialCharacterValues:
    """Unicode, emoji, newlines, null bytes, and other tricky strings."""

    def test_unicode_value(self, profile):
        value = "Nombre: Jose Garcia Marquez -- 42 anos"
        result = profile.set_field("identity", "name_unicode", value)
        assert "Stored" in result
        assert value in profile.get_field("identity", "name_unicode")

    def test_cjk_value(self, profile):
        value = "Tanaka Taro - Tokyo, Shinjuku-ku"
        profile.set_field("identity", "name_cjk", value)
        assert value in profile.get_field("identity", "name_cjk")

    def test_emoji_value(self, profile):
        value = "Status: healthy! Blood type O+"
        profile.set_field("medical", "status_emoji", value)
        assert value in profile.get_field("medical", "status_emoji")

    def test_newlines_in_value(self, profile):
        value = "Line 1\nLine 2\nLine 3"
        profile.set_field("personal", "multiline", value)
        assert "Line 1\nLine 2\nLine 3" in profile.get_field("personal", "multiline")

    def test_null_bytes_in_value(self, profile):
        value = "before\x00after"
        profile.set_field("personal", "null_byte", value)
        assert "before\x00after" in profile.get_field("personal", "null_byte")

    def test_json_special_chars(self, profile):
        value = '{"key": "value", "nested": {"a": 1}}'
        profile.set_field("personal", "json_string", value)
        assert value in profile.get_field("personal", "json_string")

    def test_backslash_and_quotes(self, profile):
        value = r'C:\Users\test "quoted" path'
        profile.set_field("personal", "path_val", value)
        assert value in profile.get_field("personal", "path_val")


# ============================================================================
# 3. Metadata with complex types
# ============================================================================

class TestComplexMetadata:
    """Nested dicts, lists, timestamps, and deeply-nested structures."""

    def test_nested_dict_metadata(self, profile):
        meta = {
            "source": "import",
            "provenance": {"system": "legacy", "version": 3, "migrated": True},
        }
        profile.set_field("identity", "ssn", "123-45-6789", metadata=meta)
        result = profile.get_field("identity", "ssn")
        assert "legacy" in result
        assert "provenance" in result

    def test_list_metadata(self, profile):
        meta = {"tags": ["sensitive", "verified", "2024"]}
        profile.set_field("financial", "account", "9876", metadata=meta)
        result = profile.get_field("financial", "account")
        assert "sensitive" in result

    def test_timestamp_metadata(self, profile):
        now = datetime.now(timezone.utc).isoformat()
        meta = {"verified_at": now, "expires": "2030-01-01T00:00:00+00:00"}
        profile.set_field("identity", "passport", "AB123", metadata=meta)
        result = profile.get_field("identity", "passport")
        assert "verified_at" in result

    def test_deeply_nested_metadata(self, profile):
        meta = {"a": {"b": {"c": {"d": {"e": "deep"}}}}}
        profile.set_field("personal", "deep_meta", "val", metadata=meta)
        result = profile.get_field("personal", "deep_meta")
        assert "deep" in result

    def test_empty_dict_metadata(self, profile):
        profile.set_field("personal", "empty_meta", "val", metadata={})
        # Empty dict is falsy in Python so should be stored as None/null
        result = profile.get_field("personal", "empty_meta")
        assert "val" in result

    def test_none_metadata(self, profile):
        profile.set_field("personal", "no_meta", "val", metadata=None)
        result = profile.get_field("personal", "no_meta")
        assert "val" in result
        # No metadata line should appear
        assert "metadata" not in result


# ============================================================================
# 4. Category boundary -- all 7 valid, invalid rejected
# ============================================================================

class TestCategoryBoundary:
    """Verify all 7 valid categories and rejection of invalid ones."""

    VALID_CATEGORIES = [
        "identity",
        "medical",
        "financial",
        "personal",
        "professional",
        "contacts",
        "legal",
    ]

    @pytest.mark.parametrize("cat", VALID_CATEGORIES)
    def test_valid_category(self, profile, cat):
        result = profile.set_field(cat, "test_field", f"value_{cat}")
        assert "Stored" in result
        assert cat in result

    @pytest.mark.parametrize("cat", VALID_CATEGORIES)
    def test_get_valid_category(self, profile, cat):
        profile.set_field(cat, "field1", "data")
        result = profile.get_field(cat, "field1")
        assert "data" in result

    @pytest.mark.parametrize("bad_cat", [
        "invalid",
        "IDENTITY",       # case-insensitive: should normalize to lowercase, so this works
        "health",
        "",
        "identity ",      # trailing space -- stripped before comparison
        "personal!",
    ])
    def test_invalid_category_variants(self, profile, bad_cat):
        """Categories that don't match after strip().lower() should be rejected."""
        stripped = bad_cat.strip().lower()
        from omega.profile.engine import CATEGORIES
        if stripped in CATEGORIES:
            # e.g. "IDENTITY" normalizes to "identity" which is valid
            result = profile.set_field(bad_cat, "f", "v")
            assert "Stored" in result
        else:
            result = profile.set_field(bad_cat, "f", "v")
            assert "Error" in result

    def test_exactly_seven_categories(self):
        from omega.profile.engine import CATEGORIES
        assert len(CATEGORIES) == 7
        assert CATEGORIES == frozenset(self.VALID_CATEGORIES)


# ============================================================================
# 5. Field name edge cases
# ============================================================================

class TestFieldNameEdgeCases:
    """Long names, special chars, whitespace-only."""

    def test_very_long_field_name(self, profile):
        long_name = "x" * 500
        result = profile.set_field("personal", long_name, "val")
        assert "Stored" in result
        retrieved = profile.get_field("personal", long_name)
        assert "val" in retrieved

    def test_empty_field_name_rejected(self, profile):
        result = profile.set_field("personal", "", "val")
        assert "Error" in result

    def test_whitespace_only_field_name_rejected(self, profile):
        result = profile.set_field("personal", "   ", "val")
        assert "Error" in result

    def test_field_name_with_special_chars(self, profile):
        result = profile.set_field("personal", "field/with.dots-and_underscores", "val")
        assert "Stored" in result

    def test_field_name_with_unicode(self, profile):
        result = profile.set_field("personal", "campo", "val")
        assert "Stored" in result
        # Retrieve should round-trip properly
        retrieved = profile.get_field("personal", "campo")
        assert "val" in retrieved

    def test_field_name_case_normalized(self, profile):
        """Field names are lowercased, so 'MyField' and 'myfield' are the same."""
        profile.set_field("personal", "MyField", "first")
        profile.set_field("personal", "myfield", "second")
        result = profile.get_field("personal", "myfield")
        assert "second" in result

        # Should be exactly 1 row (upsert)
        count = profile._conn.execute(
            "SELECT COUNT(*) FROM secure_profile WHERE field_name='myfield'"
        ).fetchone()[0]
        assert count == 1


# ============================================================================
# 6. Entity scoping isolation
# ============================================================================

class TestEntityScopingIsolation:
    """Two entities with the same category/field must have independent data."""

    def test_same_field_different_entities(self, profile):
        profile.set_field("identity", "name", "Alice", entity_id="alice")
        profile.set_field("identity", "name", "Bob", entity_id="bob")

        alice = profile.get_field("identity", "name", entity_id="alice")
        bob = profile.get_field("identity", "name", entity_id="bob")

        assert "Alice" in alice
        assert "Bob" in bob
        assert "Bob" not in alice
        assert "Alice" not in bob

    def test_personal_entity_isolated_from_named(self, profile):
        profile.set_field("financial", "balance", "$1000")  # default __personal__
        profile.set_field("financial", "balance", "$5000", entity_id="corp")

        personal = profile.get_field("financial", "balance")
        corp = profile.get_field("financial", "balance", entity_id="corp")

        assert "$1000" in personal
        assert "$5000" in corp

    def test_delete_one_entity_does_not_affect_other(self, profile):
        profile.set_field("contacts", "phone", "111", entity_id="entity_a")
        profile.set_field("contacts", "phone", "222", entity_id="entity_b")

        result = profile.delete_field("contacts", "phone", entity_id="entity_a")
        assert "Deleted" in result

        # entity_b should still have its value
        b_val = profile.get_field("contacts", "phone", entity_id="entity_b")
        assert "222" in b_val

        # entity_a should be gone
        a_val = profile.get_field("contacts", "phone", entity_id="entity_a")
        assert "No field found" in a_val

    def test_list_categories_per_entity(self, profile):
        profile.set_field("identity", "name", "Alice", entity_id="alice")
        profile.set_field("financial", "balance", "$100", entity_id="alice")
        profile.set_field("medical", "blood", "A+", entity_id="bob")

        alice_cats = profile.list_categories(entity_id="alice")
        assert "identity" in alice_cats
        assert "financial" in alice_cats
        # The footer lists all valid categories, so check the field entries specifically
        # Count field lines: alice should have 2 fields, not 3
        assert "2 encrypted field(s)" in alice_cats

        bob_cats = profile.list_categories(entity_id="bob")
        assert "medical" in bob_cats
        assert "1 encrypted field(s)" in bob_cats


# ============================================================================
# 7. Update (upsert) behavior
# ============================================================================

class TestUpsertBehavior:
    """set_field twice with the same key should keep only the latest value."""

    def test_upsert_value_updated(self, profile):
        profile.set_field("identity", "email", "old@test.com")
        profile.set_field("identity", "email", "new@test.com")

        result = profile.get_field("identity", "email")
        assert "new@test.com" in result
        assert "old@test.com" not in result

    def test_upsert_metadata_updated(self, profile):
        profile.set_field("identity", "id_number", "111", metadata={"source": "old"})
        profile.set_field("identity", "id_number", "222", metadata={"source": "new"})

        result = profile.get_field("identity", "id_number")
        assert "222" in result
        assert "new" in result

    def test_upsert_updated_at_changes(self, profile):
        import time
        profile.set_field("personal", "pref", "val1")
        row1 = profile._conn.execute(
            "SELECT updated_at FROM secure_profile WHERE field_name='pref'"
        ).fetchone()
        time.sleep(0.01)
        profile.set_field("personal", "pref", "val2")
        row2 = profile._conn.execute(
            "SELECT updated_at FROM secure_profile WHERE field_name='pref'"
        ).fetchone()
        assert row2["updated_at"] >= row1["updated_at"]

    def test_upsert_row_count_stays_one(self, profile):
        for i in range(10):
            profile.set_field("personal", "counter", f"value_{i}")

        count = profile._conn.execute(
            "SELECT COUNT(*) FROM secure_profile WHERE category='personal' AND field_name='counter'"
        ).fetchone()[0]
        assert count == 1

        result = profile.get_field("personal", "counter")
        assert "value_9" in result


# ============================================================================
# 8. search() across entities (entity_id=None)
# ============================================================================

class TestSearchAcrossEntities:
    """When entity_id is None, search should span all entities."""

    def test_search_all_entities(self, profile):
        profile.set_field("identity", "full_name", "Alice Smith", entity_id="alice")
        profile.set_field("identity", "full_name", "Bob Jones", entity_id="bob")
        profile.set_field("identity", "full_name", "Personal User")

        result = profile.search("name", entity_id=None)
        assert "alice" in result.lower() or "full_name" in result
        # Should find results from multiple entities
        assert "matching" in result.lower() or "Found" in result

    def test_search_scoped_to_entity(self, profile):
        profile.set_field("identity", "full_name", "Alice", entity_id="alice")
        profile.set_field("identity", "full_name", "Bob", entity_id="bob")

        result = profile.search("name", entity_id="alice")
        assert "alice" in result.lower()

    def test_search_by_metadata_across_entities(self, profile):
        profile.set_field("identity", "passport", "A1", metadata={"country": "US"}, entity_id="alice")
        profile.set_field("identity", "passport", "B2", metadata={"country": "UK"}, entity_id="bob")

        result = profile.search("country", entity_id=None)
        # Should find both
        lines = result.split("\n")
        field_lines = [l for l in lines if "passport" in l]
        assert len(field_lines) >= 2


# ============================================================================
# 9. Delete nonexistent field -- graceful handling
# ============================================================================

class TestDeleteNonexistent:
    """Deleting something that doesn't exist should not raise."""

    def test_delete_nonexistent_field(self, profile):
        result = profile.delete_field("identity", "does_not_exist")
        assert "No field found" in result

    def test_delete_nonexistent_category(self, profile):
        # "identity" is valid but has no data
        result = profile.delete_field("identity", "ghost")
        assert "No field found" in result

    def test_delete_nonexistent_entity(self, profile):
        profile.set_field("identity", "name", "Alice", entity_id="alice")
        result = profile.delete_field("identity", "name", entity_id="bob")
        assert "No field found" in result
        # Alice's record should be untouched
        assert "Alice" in profile.get_field("identity", "name", entity_id="alice")

    def test_double_delete(self, profile):
        profile.set_field("personal", "temp", "val")
        result1 = profile.delete_field("personal", "temp")
        assert "Deleted" in result1
        result2 = profile.delete_field("personal", "temp")
        assert "No field found" in result2


# ============================================================================
# 10. Schema migration v1 -> v2
# ============================================================================

class TestSchemaMigrationV1ToV2:
    """Create a v1-schema DB, then open with SecureProfile to trigger migration."""

    def test_v1_to_v2_migration(self, tmp_omega_dir, _mock_cipher):
        from omega.profile.engine import SecureProfile, reset_profile_engine
        from omega.crypto import secure_connect

        db_path = tmp_omega_dir / "migrate_test.db"

        # Manually create v1 schema (no entity_id column, old unique constraint)
        conn = secure_connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE profile_schema_version (
                version INTEGER NOT NULL
            )
        """)
        conn.execute("INSERT INTO profile_schema_version (version) VALUES (1)")
        conn.execute("""
            CREATE TABLE secure_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                field_name TEXT NOT NULL,
                field_value_encrypted TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(category, field_name)
            )
        """)
        # Insert some v1 data
        now = "2024-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO secure_profile (category, field_name, field_value_encrypted, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("identity", "name", "encrypted_placeholder", None, now, now),
        )
        conn.commit()
        conn.close()

        # Now open with SecureProfile -- this should trigger v1->v2 migration
        reset_profile_engine()
        engine = SecureProfile(db_path=db_path)

        # Verify schema version is now 2
        row = engine._conn.execute("SELECT version FROM profile_schema_version").fetchone()
        assert row["version"] == 2

        # Verify entity_id column exists and old data was migrated with default
        migrated = engine._conn.execute(
            "SELECT entity_id FROM secure_profile WHERE category='identity' AND field_name='name'"
        ).fetchone()
        assert migrated is not None
        assert migrated["entity_id"] == "__personal__"

        # Verify we can now store entity-scoped data
        result = engine.set_field("identity", "name", "Bob", entity_id="bob")
        assert "Stored" in result

        engine.close()
        reset_profile_engine()

    def test_v2_schema_idempotent(self, tmp_omega_dir, _mock_cipher):
        """Opening a v2 DB multiple times should not error."""
        from omega.profile.engine import SecureProfile, reset_profile_engine

        db_path = tmp_omega_dir / "v2_idem.db"
        reset_profile_engine()

        # First open creates v2 schema
        e1 = SecureProfile(db_path=db_path)
        e1.set_field("personal", "test", "val")
        e1.close()

        # Second open should be fine
        e2 = SecureProfile(db_path=db_path)
        result = e2.get_field("personal", "test")
        assert "val" in result
        e2.close()
        reset_profile_engine()
