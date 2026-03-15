"""OMEGA Secure Profile Engine -- App-layer encryption with Keychain-managed keys.

Stores sensitive personal data (identity, medical, financial, etc.) with
AES-256 encryption via Fernet. The encryption key is stored in the macOS
Keychain (via the `keyring` library) and never leaves the local machine.

Data is stored in the OMEGA SQLite database in a dedicated `secure_profile`
table. Only ciphertext is persisted -- decryption happens at query time.
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("omega.profile")

# Valid profile categories
CATEGORIES = frozenset({
    "identity",
    "medical",
    "financial",
    "personal",
    "professional",
    "contacts",
    "legal",
})

# Singleton
_instance: Optional["SecureProfile"] = None
_lock = threading.Lock()


def _omega_home() -> Path:
    return Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega")))


def _get_cipher():
    """Get Fernet cipher using keyring (macOS Keychain) or file-based fallback."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise ImportError(
            "cryptography package required for secure profile. "
            "Install with: pip install 'omega-memory[encrypt]'"
        )

    # Try keyring first (macOS Keychain)
    key = None
    try:
        import keyring

        key = keyring.get_password("omega-memory", "profile_encryption_key")
    except ImportError:
        logger.debug("keyring not available, using file-based key storage")
    except Exception as e:
        logger.debug("keyring lookup failed: %s", e)

    if key is not None:
        return Fernet(key.encode())

    # File-based fallback (reuses OMEGA's existing key infrastructure)
    key_path = _omega_home() / ".profile_key"
    if key_path.exists():
        key = key_path.read_text().strip()
        return Fernet(key.encode())

    # Generate new key
    key = Fernet.generate_key().decode()

    # Try keyring first
    stored_in_keyring = False
    try:
        import keyring

        keyring.set_password("omega-memory", "profile_encryption_key", key)
        stored_in_keyring = True
        logger.info("Profile encryption key stored in system keychain")
    except Exception as e:
        logger.debug("keyring storage failed: %s", e)

    if not stored_in_keyring:
        # File fallback
        key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(key_path), os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        try:
            os.write(fd, key.encode())
        finally:
            os.close(fd)
        logger.info("Profile encryption key stored at %s", key_path)

    return Fernet(key.encode())


class SecureProfile:
    """Encrypted personal profile storage backed by SQLite."""

    SCHEMA_VERSION = 2

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = _omega_home() / "omega.db"
        self._db_path = db_path
        from omega.crypto import secure_connect

        self._conn = secure_connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()
        self._cipher = None  # Lazy-loaded
        self._init_schema()

    def _init_schema(self) -> None:
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS profile_schema_version (
                version INTEGER NOT NULL
            )
        """)
        row = c.execute("SELECT version FROM profile_schema_version").fetchone()
        if not row:
            c.execute("INSERT INTO profile_schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))

        # Schema migration v1 → v2: add entity_id column
        if row and row[0] < 2:
            # Check if secure_profile table exists before attempting migration
            table_exists = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='secure_profile'"
            ).fetchone()
            if table_exists:
                try:
                    c.execute(
                        "ALTER TABLE secure_profile ADD COLUMN entity_id TEXT NOT NULL DEFAULT '__personal__'"
                    )
                except Exception:
                    pass  # Column already exists
                # Drop old unique constraint and create new one
                # SQLite doesn't support DROP CONSTRAINT, so we recreate the table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS secure_profile_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        field_name TEXT NOT NULL,
                        field_value_encrypted TEXT NOT NULL,
                        metadata TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        entity_id TEXT NOT NULL DEFAULT '__personal__',
                        UNIQUE(category, field_name, entity_id)
                    )
                """)
                c.execute("""
                    INSERT OR IGNORE INTO secure_profile_v2
                        (id, category, field_name, field_value_encrypted, metadata, created_at, updated_at, entity_id)
                    SELECT id, category, field_name, field_value_encrypted, metadata, created_at, updated_at,
                           COALESCE(entity_id, '__personal__')
                    FROM secure_profile
                """)
                c.execute("DROP TABLE secure_profile")
                c.execute("ALTER TABLE secure_profile_v2 RENAME TO secure_profile")
                c.execute("UPDATE profile_schema_version SET version = 2")
                c.commit()
                logger.info("Profile schema migrated v1 → v2: added entity_id column")
            else:
                # Fresh install path or table was never created - just drop v2 if it exists
                c.execute("DROP TABLE IF EXISTS secure_profile_v2")

        c.execute("""
            CREATE TABLE IF NOT EXISTS secure_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                field_name TEXT NOT NULL,
                field_value_encrypted TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                entity_id TEXT NOT NULL DEFAULT '__personal__',
                UNIQUE(category, field_name, entity_id)
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_secure_profile_category
            ON secure_profile(category)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_secure_profile_field_name
            ON secure_profile(field_name)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_secure_profile_entity_id
            ON secure_profile(entity_id)
        """)
        c.commit()

    def _get_cipher(self):
        if self._cipher is None:
            self._cipher = _get_cipher()
        return self._cipher

    def _encrypt(self, value: str) -> str:
        cipher = self._get_cipher()
        return cipher.encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, token: str) -> str:
        cipher = self._get_cipher()
        return cipher.decrypt(token.encode("ascii")).decode("utf-8")

    def set_field(
        self,
        category: str,
        field_name: str,
        value: str,
        metadata: Optional[dict] = None,
        entity_id: str = "__personal__",
    ) -> str:
        """Encrypt and store a profile field. Upserts on (category, field_name, entity_id)."""
        category = category.strip().lower()
        field_name = field_name.strip().lower()
        entity_id = entity_id.strip() if entity_id else "__personal__"

        if category not in CATEGORIES:
            return f"Error: invalid category '{category}'. Valid: {', '.join(sorted(CATEGORIES))}"
        if not field_name:
            return "Error: field_name is required"
        if not value.strip():
            return "Error: value is required"

        encrypted = self._encrypt(value)
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata) if metadata else None

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO secure_profile (category, field_name, field_value_encrypted, metadata, created_at, updated_at, entity_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(category, field_name, entity_id) DO UPDATE SET
                    field_value_encrypted = excluded.field_value_encrypted,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (category, field_name, encrypted, meta_json, now, now, entity_id),
            )
            self._conn.commit()

        scope = f" [entity: {entity_id}]" if entity_id != "__personal__" else ""
        return f"Stored encrypted field: {category}/{field_name}{scope}"

    def get_field(
        self,
        category: str,
        field_name: Optional[str] = None,
        entity_id: str = "__personal__",
    ) -> str:
        """Decrypt and retrieve profile field(s). If field_name is None, returns all fields in category."""
        category = category.strip().lower()
        entity_id = entity_id.strip() if entity_id else "__personal__"

        if category not in CATEGORIES:
            return f"Error: invalid category '{category}'. Valid: {', '.join(sorted(CATEGORIES))}"

        with self._lock:
            if field_name:
                field_name = field_name.strip().lower()
                row = self._conn.execute(
                    "SELECT field_value_encrypted, metadata, updated_at FROM secure_profile WHERE category = ? AND field_name = ? AND entity_id = ?",
                    (category, field_name, entity_id),
                ).fetchone()

                if not row:
                    scope = f" [entity: {entity_id}]" if entity_id != "__personal__" else ""
                    return f"No field found: {category}/{field_name}{scope}"

                try:
                    decrypted = self._decrypt(row["field_value_encrypted"])
                except Exception as e:
                    logger.error("Decryption failed for %s/%s: %s", category, field_name, e)
                    return f"Error: decryption failed for {category}/{field_name}"

                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                result = f"**{category}/{field_name}**: {decrypted}"
                if entity_id != "__personal__":
                    result += f"\n  entity: {entity_id}"
                if meta:
                    result += f"\n  metadata: {json.dumps(meta)}"
                result += f"\n  updated: {row['updated_at']}"
                return result

            else:
                rows = self._conn.execute(
                    "SELECT field_name, field_value_encrypted, metadata, updated_at FROM secure_profile WHERE category = ? AND entity_id = ? ORDER BY field_name",
                    (category, entity_id),
                ).fetchall()

                if not rows:
                    scope = f" [entity: {entity_id}]" if entity_id != "__personal__" else ""
                    return f"No fields found in category: {category}{scope}"

                scope = f" (entity: {entity_id})" if entity_id != "__personal__" else ""
                lines = [f"## {category} ({len(rows)} fields){scope}\n"]
                for r in rows:
                    try:
                        decrypted = self._decrypt(r["field_value_encrypted"])
                    except Exception:
                        decrypted = "[decryption failed]"

                    meta = json.loads(r["metadata"]) if r["metadata"] else {}
                    lines.append(f"- **{r['field_name']}**: {decrypted}")
                    if meta:
                        lines.append(f"  metadata: {json.dumps(meta)}")

                return "\n".join(lines)

    def search(self, query: str, entity_id: Optional[str] = None) -> str:
        """Search profile by field name or category (metadata only, not encrypted values).

        Args:
            entity_id: If provided, search only within that entity. None = search all entities.
        """
        query = query.strip().lower()
        if not query:
            return "Error: search query is required"

        with self._lock:
            if entity_id:
                rows = self._conn.execute(
                    """
                    SELECT category, field_name, metadata, updated_at, entity_id
                    FROM secure_profile
                    WHERE (field_name LIKE ? OR category LIKE ? OR metadata LIKE ?)
                      AND entity_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 20
                    """,
                    (f"%{query}%", f"%{query}%", f"%{query}%", entity_id.strip()),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT category, field_name, metadata, updated_at, entity_id
                    FROM secure_profile
                    WHERE field_name LIKE ? OR category LIKE ? OR metadata LIKE ?
                    ORDER BY updated_at DESC
                    LIMIT 20
                    """,
                    (f"%{query}%", f"%{query}%", f"%{query}%"),
                ).fetchall()

        if not rows:
            return f"No profile fields matching '{query}'"

        lines = [f"Found {len(rows)} matching profile field(s):\n"]
        for r in rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            eid = r["entity_id"]
            scope = f" [entity: {eid}]" if eid != "__personal__" else ""
            lines.append(f"- **{r['category']}/{r['field_name']}**{scope} (updated: {r['updated_at']})")
            if meta:
                lines.append(f"  metadata: {json.dumps(meta)}")

        lines.append("\nUse `omega_profile_get(category, field)` to decrypt and view values.")
        return "\n".join(lines)

    def delete_field(self, category: str, field_name: str, entity_id: str = "__personal__") -> str:
        """Delete a specific profile field."""
        category = category.strip().lower()
        field_name = field_name.strip().lower()
        entity_id = entity_id.strip() if entity_id else "__personal__"

        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM secure_profile WHERE category = ? AND field_name = ? AND entity_id = ?",
                (category, field_name, entity_id),
            )
            self._conn.commit()

        if cursor.rowcount == 0:
            scope = f" [entity: {entity_id}]" if entity_id != "__personal__" else ""
            return f"No field found: {category}/{field_name}{scope}"
        scope = f" [entity: {entity_id}]" if entity_id != "__personal__" else ""
        return f"Deleted profile field: {category}/{field_name}{scope}"

    def list_categories(self, entity_id: Optional[str] = None) -> str:
        """List all categories with field counts, optionally filtered by entity_id."""
        with self._lock:
            if entity_id:
                rows = self._conn.execute(
                    "SELECT category, COUNT(*) as cnt FROM secure_profile WHERE entity_id = ? GROUP BY category ORDER BY category",
                    (entity_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT category, COUNT(*) as cnt FROM secure_profile GROUP BY category ORDER BY category"
                ).fetchall()

        scope = f" [entity: {entity_id}]" if entity_id else ""
        if not rows:
            return f"No profile data stored yet{scope}.\n\nValid categories: " + ", ".join(sorted(CATEGORIES))

        lines = [f"## Secure Profile Categories{scope}\n"]
        total = 0
        for r in rows:
            lines.append(f"- **{r['category']}**: {r['cnt']} field(s)")
            total += r["cnt"]
        lines.append(f"\n**Total**: {total} encrypted field(s)")
        lines.append(f"Valid categories: {', '.join(sorted(CATEGORIES))}")
        return "\n".join(lines)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def get_profile_engine(db_path: Optional[Path] = None) -> SecureProfile:
    """Get or create the SecureProfile singleton."""
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        _instance = SecureProfile(db_path=db_path)
    return _instance


def reset_profile_engine() -> None:
    """Reset singleton for testing."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
        _instance = None


# Convenience functions (used by handlers)
def profile_set(
    category: str,
    field_name: str,
    value: str,
    metadata: Optional[dict] = None,
    entity_id: str = "__personal__",
) -> str:
    return get_profile_engine().set_field(category, field_name, value, metadata, entity_id)


def profile_get(
    category: str,
    field_name: Optional[str] = None,
    entity_id: str = "__personal__",
) -> str:
    return get_profile_engine().get_field(category, field_name, entity_id)


def profile_search(query: str, entity_id: Optional[str] = None) -> str:
    return get_profile_engine().search(query, entity_id)


def profile_delete(category: str, field_name: str, entity_id: str = "__personal__") -> str:
    return get_profile_engine().delete_field(category, field_name, entity_id)


def profile_list_categories(entity_id: Optional[str] = None) -> str:
    return get_profile_engine().list_categories(entity_id=entity_id)
