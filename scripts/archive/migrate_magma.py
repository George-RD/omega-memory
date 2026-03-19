#!/usr/bin/env python3
"""
OMEGA Migration: Import high-value MAGMA entries into OMEGA.

Reads ~/.magma/store.jsonl, filters to decisions/lessons/errors/preferences,
deduplicates against existing OMEGA entries via SQLiteStore.store() (which has
both exact-hash and embedding-based dedup built in).

This script bypasses bridge.auto_capture() intentionally:
  - The blocklist would reject ~50% of MAGMA entries that contain system noise
    markers in their content but are legitimately tagged as decisions/lessons
  - Direct SQLiteStore.store() is faster and handles its own dedup

Usage:
    python scripts/migrate_magma.py                    # Dry run (default)
    python scripts/migrate_magma.py --execute          # Actually migrate
    python scripts/migrate_magma.py --execute --batch 50  # Custom batch size
"""

import argparse
import hashlib
import logging
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

# Add src to path for editable install compatibility
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega import json_compat as json
from omega.types import TTLCategory

logger = logging.getLogger("omega.migrate_magma")

MAGMA_STORE = Path.home() / ".magma" / "store.jsonl"

# Only migrate these event types — everything else is noise
HIGH_VALUE_TYPES = {"decision", "lesson_learned", "error_pattern", "user_preference"}

# Skip entries shorter than this
MIN_CONTENT_LENGTH = 30

# Max retries per entry on database lock
MAX_RETRIES = 3
RETRY_DELAY = 0.5  # seconds


def load_magma_entries() -> list[dict]:
    """Load and filter MAGMA entries to high-value types."""
    if not MAGMA_STORE.exists():
        print(f"MAGMA store not found: {MAGMA_STORE}")
        sys.exit(1)

    entries = []
    skipped_type = 0
    skipped_short = 0
    skipped_parse = 0

    with open(MAGMA_STORE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.encode() if isinstance(line, str) else line)
            except Exception:
                skipped_parse += 1
                continue

            content = obj.get("content", "").strip()
            metadata = obj.get("metadata") or {}
            event_type = metadata.get("event_type", "")

            if event_type not in HIGH_VALUE_TYPES:
                skipped_type += 1
                continue

            if len(content) < MIN_CONTENT_LENGTH:
                skipped_short += 1
                continue

            entries.append(obj)

    print(f"MAGMA store: {MAGMA_STORE}")
    print(f"  High-value entries: {len(entries)}")
    print(f"  Skipped (wrong type): {skipped_type}")
    print(f"  Skipped (too short): {skipped_short}")
    print(f"  Skipped (parse error): {skipped_parse}")

    return entries


def _pre_dedup_entries(entries: list[dict]) -> list[dict]:
    """Remove exact-duplicate content within MAGMA entries before migration."""
    seen_hashes = set()
    unique = []
    for entry in entries:
        content = entry.get("content", "").strip()
        h = hashlib.sha256(content.encode()).hexdigest()
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(entry)
    removed = len(entries) - len(unique)
    if removed:
        print(f"  Pre-dedup: removed {removed} exact duplicates within MAGMA")
    return unique


def migrate(entries: list[dict], dry_run: bool = True, batch_size: int = 25):
    """Migrate MAGMA entries into OMEGA via SQLiteStore.store() directly."""
    stats = {
        "total": len(entries),
        "stored": 0,
        "deduped": 0,
        "errors": 0,
    }

    if dry_run:
        print(f"\n[DRY RUN] Would migrate {len(entries)} entries. Use --execute to run.")
        type_counts = Counter()
        for e in entries:
            et = (e.get("metadata") or {}).get("event_type", "unknown")
            type_counts[et] += 1
        for et, c in type_counts.most_common():
            print(f"  {et}: {c}")
        return stats

    # Pre-dedup within MAGMA entries
    entries = _pre_dedup_entries(entries)
    stats["total"] = len(entries)

    # Get a SQLiteStore instance with extended busy_timeout
    from omega.sqlite_store import SQLiteStore
    db_path = Path.home() / ".omega" / "omega.db"
    store = SQLiteStore(str(db_path))
    # Increase busy_timeout for migration (30 seconds instead of 5)
    store._conn.execute("PRAGMA busy_timeout=30000")

    # Pre-load existing content hashes to skip already-migrated entries
    print("\nBuilding existing content hash index...")
    existing_hashes = set()
    rows = store._conn.execute("SELECT content_hash FROM memories WHERE content_hash IS NOT NULL").fetchall()
    for row in rows:
        existing_hashes.add(row[0])
    print(f"  {len(existing_hashes)} existing memories indexed")

    # Filter out entries already in OMEGA
    pre_filter_count = len(entries)
    filtered = []
    for entry in entries:
        content = unicodedata.normalize("NFC", entry.get("content", "").strip())
        h = hashlib.sha256(content.encode()).hexdigest()
        if h not in existing_hashes:
            filtered.append(entry)
    already_present = pre_filter_count - len(filtered)
    if already_present:
        print(f"  {already_present} entries already in OMEGA (hash match)")
    entries = filtered
    stats["deduped"] = already_present

    print(f"\nMigrating {len(entries)} new entries...")
    start = time.time()

    for i, entry in enumerate(entries):
        content = unicodedata.normalize("NFC", entry.get("content", "").strip())
        metadata = entry.get("metadata") or {}
        event_type = metadata.get("event_type", "memory")

        # Build metadata
        meta = {
            "event_type": event_type,
            "source": "magma_migration",
            "magma_id": entry.get("id", ""),
            "capture_confidence": "medium",
        }
        if metadata.get("session_id"):
            meta["original_session_id"] = metadata["session_id"]
        if metadata.get("project"):
            meta["project"] = metadata["project"]
        if entry.get("created_at"):
            meta["original_created_at"] = entry["created_at"]

        # Extract tags
        try:
            from omega.bridge import _extract_tags
            auto_tags = _extract_tags(content, meta.get("project"))
            if auto_tags:
                meta["tags"] = sorted(set(auto_tags))[:15]
        except Exception:
            pass

        ttl = TTLCategory.for_event_type(event_type)

        # Store with retry on lock
        for attempt in range(MAX_RETRIES):
            try:
                node_id = store.store(
                    content=content,
                    session_id="magma-migration",
                    metadata=meta,
                    ttl_seconds=ttl,
                )
                # Check if it was deduped (store returns existing node_id)
                if store.stats.get("dedup_exact", 0) > stats.get("_last_exact_dedup", 0):
                    stats["deduped"] += 1
                    stats["_last_exact_dedup"] = store.stats.get("dedup_exact", 0)
                elif store.stats.get("dedup_skips", 0) > stats.get("_last_embed_dedup", 0):
                    stats["deduped"] += 1
                    stats["_last_embed_dedup"] = store.stats.get("dedup_skips", 0)
                else:
                    stats["stored"] += 1
                break
            except Exception as e:
                if "locked" in str(e).lower() and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                stats["errors"] += 1
                if stats["errors"] <= 10:
                    logger.warning(f"Error on entry {i}: {e}")
                break

        # Progress reporting
        if (i + 1) % batch_size == 0 or (i + 1) == len(entries):
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(
                f"  [{i+1}/{len(entries)}] "
                f"stored={stats['stored']} deduped={stats['deduped']} "
                f"errors={stats['errors']} "
                f"({rate:.1f} entries/sec)"
            )

    elapsed = time.time() - start

    # Cleanup internal tracking keys
    stats.pop("_last_exact_dedup", None)
    stats.pop("_last_embed_dedup", None)

    print(f"\nMigration complete in {elapsed:.1f}s")
    print(f"  New entries stored: {stats['stored']}")
    print(f"  Deduped (already existed): {stats['deduped']}")
    print(f"  Errors: {stats['errors']}")

    # Close our connection
    store.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate MAGMA entries to OMEGA")
    parser.add_argument("--execute", action="store_true", help="Actually perform migration (default: dry run)")
    parser.add_argument("--batch", type=int, default=50, help="Progress report interval (default: 50)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    entries = load_magma_entries()
    if not entries:
        print("No entries to migrate.")
        return

    stats = migrate(entries, dry_run=not args.execute, batch_size=args.batch)

    if args.execute and stats["stored"] > 0:
        print("\nTo rebuild auto-relate edges for better connectivity:")
        print("  python scripts/clean_store.py")


if __name__ == "__main__":
    main()
