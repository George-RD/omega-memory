"""OMEGA Entity Engine -- Multi-entity corporate memory with relationships.

Stores structured entity profiles (companies, LLCs, foundations, etc.),
maps relationships (parent/subsidiary, ownership), and provides scoping
for memories, documents, and secure profile fields.

All entity data lives in the shared OMEGA SQLite database (omega.db).
"""

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("omega.entity")

# Valid entity types
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
    # NER-extracted types (Phase 3)
    "person",
    "project",
    "tool",
    "concept",
    "technology",
    "service",
})

# Valid relationship types
RELATIONSHIP_TYPES = frozenset({
    "parent_of",
    "subsidiary_of",
    "owned_by",
    "acquired_by",
    "partner_of",
    "investor_in",
    "operated_by",
    # NER-extracted types (Phase 3)
    "uses",
    "works_on",
    "depends_on",
    "mentions",
    "created_by",
})

# Valid entity statuses
ENTITY_STATUSES = frozenset({
    "active",
    "acquired",
    "dissolved",
    "dormant",
    "pending",
})

# Singleton
_instance: Optional["EntityManager"] = None
_lock = threading.Lock()


def _omega_home() -> Path:
    return Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega")))


class EntityManager:
    """Multi-entity corporate registry backed by SQLite."""

    SCHEMA_VERSION = 1

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
        self._init_schema()

    def _init_schema(self) -> None:
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS entity_schema_version (
                version INTEGER NOT NULL
            )
        """)
        row = c.execute("SELECT version FROM entity_schema_version").fetchone()
        if not row:
            c.execute(
                "INSERT INTO entity_schema_version (version) VALUES (?)",
                (self.SCHEMA_VERSION,),
            )

        c.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                jurisdiction TEXT,
                status TEXT DEFAULT 'active',
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS entity_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_entity_id TEXT NOT NULL REFERENCES entities(id),
                target_entity_id TEXT NOT NULL REFERENCES entities(id),
                relationship_type TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(source_entity_id, target_entity_id, relationship_type)
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_entity_rel_source ON entity_relationships(source_entity_id)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_entity_rel_target ON entity_relationships(target_entity_id)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_entity_rel_type ON entity_relationships(relationship_type)"
        )

        c.commit()

    def create_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        jurisdiction: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a new entity. Returns confirmation string."""
        entity_id = entity_id.strip().lower()
        entity_type = entity_type.strip().lower()

        if not entity_id:
            return "Error: entity_id is required"
        if not name.strip():
            return "Error: name is required"
        if entity_type not in ENTITY_TYPES:
            return f"Error: invalid entity_type '{entity_type}'. Valid: {', '.join(sorted(ENTITY_TYPES))}"

        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata) if metadata else None

        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            if existing:
                return f"Error: entity '{entity_id}' already exists"

            self._conn.execute(
                """INSERT INTO entities (id, name, entity_type, jurisdiction, status, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'active', ?, ?, ?)""",
                (entity_id, name.strip(), entity_type, jurisdiction, meta_json, now, now),
            )
            self._conn.commit()

        return f"Created entity: **{name.strip()}** (`{entity_id}`, {entity_type})"

    def get_entity(self, entity_id: str) -> str:
        """Get entity details by ID."""
        entity_id = entity_id.strip().lower()

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()

        if not row:
            return f"Error: entity '{entity_id}' not found"

        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        lines = [
            f"## {row['name']} (`{row['id']}`)",
            f"- **Type**: {row['entity_type']}",
            f"- **Status**: {row['status']}",
        ]
        if row["jurisdiction"]:
            lines.append(f"- **Jurisdiction**: {row['jurisdiction']}")
        if meta:
            lines.append(f"- **Metadata**: {json.dumps(meta)}")
        lines.append(f"- **Created**: {row['created_at']}")
        lines.append(f"- **Updated**: {row['updated_at']}")
        return "\n".join(lines)

    def list_entities(
        self,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> str:
        """List entities with optional filters."""
        conditions = []
        params = []

        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type.strip().lower())
        if status:
            conditions.append("status = ?")
            params.append(status.strip().lower())

        where = " WHERE " + " AND ".join(conditions) if conditions else ""

        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, name, entity_type, jurisdiction, status FROM entities{where} ORDER BY name",
                params,
            ).fetchall()

        if not rows:
            return "No entities found."

        lines = [f"## Entities ({len(rows)})\n"]
        for r in rows:
            jurisdiction = f" [{r['jurisdiction']}]" if r["jurisdiction"] else ""
            status_badge = f" ({r['status']})" if r["status"] != "active" else ""
            lines.append(
                f"- **{r['name']}** (`{r['id']}`) — {r['entity_type']}{jurisdiction}{status_badge}"
            )
        return "\n".join(lines)

    def update_entity(
        self,
        entity_id: str,
        name: Optional[str] = None,
        status: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Update entity fields. Only provided fields are changed."""
        entity_id = entity_id.strip().lower()

        with self._lock:
            existing = self._conn.execute(
                "SELECT * FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            if not existing:
                return f"Error: entity '{entity_id}' not found"

            updates = []
            params = []

            if name is not None:
                name_stripped = name.strip()
                if not name_stripped:
                    return "Error: name cannot be empty"
                updates.append("name = ?")
                params.append(name_stripped)
            if status is not None:
                status = status.strip().lower()
                if status not in ENTITY_STATUSES:
                    return f"Error: invalid status '{status}'. Valid: {', '.join(sorted(ENTITY_STATUSES))}"
                updates.append("status = ?")
                params.append(status)
            if jurisdiction is not None:
                updates.append("jurisdiction = ?")
                params.append(jurisdiction)
            if metadata is not None:
                # Merge with existing metadata
                existing_meta = json.loads(existing["metadata"]) if existing["metadata"] else {}
                for k, v in metadata.items():
                    if v is None:
                        existing_meta.pop(k, None)
                    else:
                        existing_meta[k] = v
                updates.append("metadata = ?")
                params.append(json.dumps(existing_meta) if existing_meta else None)

            if not updates:
                return "No fields to update."

            now = datetime.now(timezone.utc).isoformat()
            updates.append("updated_at = ?")
            params.append(now)
            params.append(entity_id)

            self._conn.execute(
                f"UPDATE entities SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            self._conn.commit()

        return f"Updated entity: `{entity_id}`"

    def delete_entity(self, entity_id: str) -> str:
        """Soft-delete entity by setting status to 'dissolved'."""
        entity_id = entity_id.strip().lower()

        with self._lock:
            existing = self._conn.execute(
                "SELECT id, name FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            if not existing:
                return f"Error: entity '{entity_id}' not found"

            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                "UPDATE entities SET status = 'dissolved', updated_at = ? WHERE id = ?",
                (now, entity_id),
            )
            self._conn.commit()

        return f"Dissolved entity: **{existing['name']}** (`{entity_id}`)"

    def add_relationship(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Add a directed relationship between two entities."""
        source_entity_id = source_entity_id.strip().lower()
        target_entity_id = target_entity_id.strip().lower()
        relationship_type = relationship_type.strip().lower()

        if relationship_type not in RELATIONSHIP_TYPES:
            return (
                f"Error: invalid relationship_type '{relationship_type}'. "
                f"Valid: {', '.join(sorted(RELATIONSHIP_TYPES))}"
            )

        if source_entity_id == target_entity_id:
            return "Error: source and target entity must be different"

        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata) if metadata else None

        with self._lock:
            # Verify both entities exist
            for eid in (source_entity_id, target_entity_id):
                row = self._conn.execute(
                    "SELECT id FROM entities WHERE id = ?", (eid,)
                ).fetchone()
                if not row:
                    return f"Error: entity '{eid}' not found"

            try:
                self._conn.execute(
                    """INSERT INTO entity_relationships
                       (source_entity_id, target_entity_id, relationship_type, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (source_entity_id, target_entity_id, relationship_type, meta_json, now),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                return (
                    f"Error: relationship already exists: "
                    f"{source_entity_id} --[{relationship_type}]--> {target_entity_id}"
                )

        return (
            f"Added relationship: `{source_entity_id}` --[{relationship_type}]--> `{target_entity_id}`"
        )

    def get_relationships(
        self,
        entity_id: str,
        direction: Optional[str] = None,
        relationship_type: Optional[str] = None,
    ) -> str:
        """Get relationships for an entity."""
        if direction is not None and direction not in ("outgoing", "incoming"):
            return f"Error: invalid direction '{direction}'. Use 'outgoing', 'incoming', or omit for both."
        entity_id = entity_id.strip().lower()

        with self._lock:
            existing = self._conn.execute(
                "SELECT id, name FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            if not existing:
                return f"Error: entity '{entity_id}' not found"

            outgoing = []
            incoming = []

            if direction is None or direction == "outgoing":
                q = "SELECT * FROM entity_relationships WHERE source_entity_id = ?"
                params = [entity_id]
                if relationship_type:
                    q += " AND relationship_type = ?"
                    params.append(relationship_type.strip().lower())
                outgoing = self._conn.execute(q, params).fetchall()

            if direction is None or direction == "incoming":
                q = "SELECT * FROM entity_relationships WHERE target_entity_id = ?"
                params = [entity_id]
                if relationship_type:
                    q += " AND relationship_type = ?"
                    params.append(relationship_type.strip().lower())
                incoming = self._conn.execute(q, params).fetchall()

        if not outgoing and not incoming:
            return f"No relationships found for entity `{entity_id}`"

        lines = [f"## Relationships for {existing['name']} (`{entity_id}`)\n"]

        if outgoing:
            lines.append("### Outgoing")
            for r in outgoing:
                meta = json.loads(r["metadata"]) if r["metadata"] else {}
                meta_str = f" ({json.dumps(meta)})" if meta else ""
                lines.append(
                    f"- `{entity_id}` --[{r['relationship_type']}]--> `{r['target_entity_id']}`{meta_str}"
                )

        if incoming:
            lines.append("### Incoming")
            for r in incoming:
                meta = json.loads(r["metadata"]) if r["metadata"] else {}
                meta_str = f" ({json.dumps(meta)})" if meta else ""
                lines.append(
                    f"- `{r['source_entity_id']}` --[{r['relationship_type']}]--> `{entity_id}`{meta_str}"
                )

        return "\n".join(lines)

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
                    for row in rows:
                        source = row["source_entity_id"]
                        target = row["target_entity_id"]
                        neighbor = target if source == eid else source
                        if neighbor != entity_id and neighbor not in visited:
                            visited.add(neighbor)
                            next_frontier.add(neighbor)
                frontier = next_frontier

        return visited

    def remove_relationship(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
    ) -> str:
        """Remove a specific relationship."""
        source_entity_id = source_entity_id.strip().lower()
        target_entity_id = target_entity_id.strip().lower()
        relationship_type = relationship_type.strip().lower()

        with self._lock:
            cursor = self._conn.execute(
                """DELETE FROM entity_relationships
                   WHERE source_entity_id = ? AND target_entity_id = ? AND relationship_type = ?""",
                (source_entity_id, target_entity_id, relationship_type),
            )
            self._conn.commit()
            deleted_count = cursor.rowcount

        if deleted_count == 0:
            return (
                f"No relationship found: "
                f"{source_entity_id} --[{relationship_type}]--> {target_entity_id}"
            )
        return (
            f"Removed relationship: "
            f"`{source_entity_id}` --[{relationship_type}]--> `{target_entity_id}`"
        )

    def get_entity_tree(self, entity_id: str) -> str:
        """Get recursive hierarchy view of an entity and its relationships."""
        entity_id = entity_id.strip().lower()

        with self._lock:
            root = self._conn.execute(
                "SELECT id, name, entity_type, status FROM entities WHERE id = ?",
                (entity_id,),
            ).fetchone()
            if not root:
                return f"Error: entity '{entity_id}' not found"

            lines = [f"## Entity Tree: {root['name']}\n"]
            visited = set()
            self._build_tree(lines, entity_id, 0, visited)

        return "\n".join(lines)

    def _build_tree(
        self, lines: list, entity_id: str, depth: int, visited: set
    ) -> None:
        """Recursively build entity tree (called within lock)."""
        if entity_id in visited or depth > 10:
            return
        visited.add(entity_id)

        row = self._conn.execute(
            "SELECT id, name, entity_type, status, jurisdiction FROM entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if not row:
            return

        indent = "  " * depth
        status_badge = f" ({row['status']})" if row["status"] != "active" else ""
        jurisdiction = f" [{row['jurisdiction']}]" if row["jurisdiction"] else ""
        lines.append(
            f"{indent}- **{row['name']}** (`{row['id']}`, {row['entity_type']}{jurisdiction}{status_badge})"
        )

        # Find children (entities this one is parent_of)
        children = self._conn.execute(
            """SELECT target_entity_id FROM entity_relationships
               WHERE source_entity_id = ? AND relationship_type = 'parent_of'""",
            (entity_id,),
        ).fetchall()

        for child in children:
            self._build_tree(lines, child["target_entity_id"], depth + 1, visited)

    def list_entity_ids(self) -> list:
        """Return list of (entity_id, name) tuples for all active entities."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name FROM entities WHERE status = 'active' ORDER BY name"
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def get_entity_manager(db_path: Optional[Path] = None) -> EntityManager:
    """Get or create the EntityManager singleton."""
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        _instance = EntityManager(db_path=db_path)
    return _instance


def reset_entity_manager() -> None:
    """Reset singleton for testing."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
        _instance = None


# ---------------------------------------------------------------------------
# Project → Entity resolution (config-file based, cached, fail-open)
# ---------------------------------------------------------------------------

_project_entity_cache: dict[str, str] = {}
_cache_ts: float = 0.0
_CACHE_TTL_S = 60.0
_cache_lock = threading.Lock()


def resolve_project_entity(project: str) -> Optional[str]:
    """Resolve a filesystem project path to an entity_id.

    Reads entity_scoping.mappings from ~/.omega/config.json.
    Non-empty mappings dict implicitly enables scoping.
    Cached for 60s. Returns None if no config/mappings/match (fail-open).
    """
    global _project_entity_cache, _cache_ts

    if not project:
        return None

    normalized = project.rstrip("/")
    now = time.monotonic()

    with _cache_lock:
        # Return from cache if fresh
        if now - _cache_ts < _CACHE_TTL_S and _project_entity_cache is not None:
            return _project_entity_cache.get(normalized)

        # Rebuild cache from config file
        try:
            omega_home = _omega_home()
            config_path = omega_home / "config.json"
            if not config_path.exists():
                _project_entity_cache = {}
                _cache_ts = now
                return None

            cfg = json.loads(config_path.read_text())
            mappings = cfg.get("entity_scoping", {}).get("mappings", {})

            # Normalize keys (strip trailing slashes)
            new_cache: dict[str, str] = {}
            for p, entity_id in mappings.items():
                new_cache[p.rstrip("/")] = entity_id

            _project_entity_cache = new_cache
            _cache_ts = now
        except Exception:
            return None

        return _project_entity_cache.get(normalized)


# Convenience functions (used by handlers)
def entity_create(
    entity_id: str,
    name: str,
    entity_type: str,
    jurisdiction: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    return get_entity_manager().create_entity(entity_id, name, entity_type, jurisdiction, metadata)


def entity_get(entity_id: str) -> str:
    return get_entity_manager().get_entity(entity_id)


def entity_list(entity_type: Optional[str] = None, status: Optional[str] = None) -> str:
    return get_entity_manager().list_entities(entity_type, status)


def entity_update(
    entity_id: str,
    name: Optional[str] = None,
    status: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    return get_entity_manager().update_entity(entity_id, name, status, jurisdiction, metadata)


def entity_delete(entity_id: str) -> str:
    return get_entity_manager().delete_entity(entity_id)


def entity_add_relationship(
    source_entity_id: str,
    target_entity_id: str,
    relationship_type: str,
    metadata: Optional[dict] = None,
) -> str:
    return get_entity_manager().add_relationship(
        source_entity_id, target_entity_id, relationship_type, metadata
    )


def entity_relationships(
    entity_id: str,
    direction: Optional[str] = None,
    relationship_type: Optional[str] = None,
) -> str:
    return get_entity_manager().get_relationships(entity_id, direction, relationship_type)


def entity_tree(entity_id: str) -> str:
    return get_entity_manager().get_entity_tree(entity_id)
