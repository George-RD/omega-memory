"""OMEGA Knowledge Cloud Sync -- Process kb_queue from Supabase into local knowledge base.

Files are uploaded to Supabase Storage by the web app (via Google Drive Picker),
queued in the kb_queue table, and pulled/ingested locally by this module.
"""

import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("omega.knowledge.cloud_sync")


def _omega_home() -> Path:
    return Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega")))


def _get_supabase_client():
    """Create a Supabase client reusing the cloud sync config pattern."""
    from omega.cloud.sync import _get_supabase_client as _get_client

    return _get_client()


def sync_kb_queue(batch_size: int = 10) -> str:
    """Process pending items from Supabase kb_queue into the local knowledge base.

    For each pending item:
      1. Set status to 'processing'
      2. Download file from Supabase Storage
      3. Write to temp file and ingest via ingest_document()
      4. Update source_path to gdrive:// URI
      5. Set status to 'synced'

    Returns a summary string.
    """
    from omega.knowledge.engine import get_knowledge_base, ingest_document

    client = _get_supabase_client()

    # W3: Recover items stuck in "processing" for more than 10 minutes
    ten_minutes_ago = (
        datetime.now(timezone.utc).replace(microsecond=0)
        - timedelta(minutes=10)
    ).isoformat()
    try:
        client.table("kb_queue").update({
            "status": "pending",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("status", "processing").lt("updated_at", ten_minutes_ago).execute()
    except Exception as e:
        logger.warning("Failed to recover stale 'processing' items: %s", e)

    # Fetch pending items
    result = (
        client.table("kb_queue")
        .select("*")
        .eq("status", "pending")
        .order("created_at")
        .limit(batch_size)
        .execute()
    )
    items = result.data
    if not items:
        return "No pending items in kb_queue."

    synced = 0
    errors = 0
    error_details = []

    for item in items:
        item_id = item["id"]
        file_name = item.get("file_name", "unknown")
        storage_path = item.get("storage_path", "")
        source_type = item.get("source_type", "text")
        title = item.get("title") or file_name
        entity_id = item.get("entity_id")
        drive_file_id = item.get("drive_file_id", "")

        tmp_path: Optional[str] = None
        try:
            # Mark as processing
            client.table("kb_queue").update({
                "status": "processing",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", item_id).execute()

            # Download from Supabase Storage
            file_bytes = client.storage.from_("kb-files").download(storage_path)
            if not file_bytes:
                raise ValueError(f"Empty file downloaded from {storage_path}")

            # Determine file extension
            ext = ".txt"
            if source_type == "pdf":
                ext = ".pdf"
            elif source_type == "markdown":
                ext = ".md"

            # Write to temp file
            with tempfile.NamedTemporaryFile(
                suffix=ext, prefix="omega_kb_", delete=False
            ) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            # Ingest into local knowledge base
            ingest_result = ingest_document(
                tmp_path, source_type, title, entity_id
            )

            # C3: Treat ingest errors as failures — do not mark as "synced"
            if ingest_result.startswith("Error"):
                errors += 1
                error_msg = ingest_result[:500]
                error_details.append(f"{file_name}: {error_msg}")
                logger.error("Ingest failed for kb_queue item %s: %s", item_id, ingest_result)
                try:
                    client.table("kb_queue").update({
                        "status": "error",
                        "error_message": error_msg,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", item_id).execute()
                except Exception:
                    pass
                continue

            # Update the local document's source_path to a stable gdrive:// URI
            if not drive_file_id:
                logger.warning("No drive_file_id for kb_queue item %s, using storage_path as URI", item_id)
                gdrive_uri = f"kb-files://{storage_path}"
            else:
                gdrive_uri = f"gdrive://{drive_file_id}/{file_name}"
            kb = get_knowledge_base()
            with kb._lock:
                kb._conn.execute(
                    "UPDATE documents SET source_path = ? WHERE source_path = ?",
                    (gdrive_uri, tmp_path),
                )
                kb._conn.commit()

            # Mark as synced in Supabase
            client.table("kb_queue").update({
                "status": "synced",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", item_id).execute()

            synced += 1
            logger.info("Synced kb_queue item %s: %s", item_id, file_name)

        except Exception as e:
            errors += 1
            error_msg = str(e)[:500]
            error_details.append(f"{file_name}: {error_msg}")
            logger.error("Failed to sync kb_queue item %s: %s", item_id, e)

            # Mark as error in Supabase
            try:
                client.table("kb_queue").update({
                    "status": "error",
                    "error_message": error_msg,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", item_id).execute()
            except Exception:
                pass  # Don't fail the loop on status update errors

        finally:
            # Clean up temp file
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # Build summary
    parts = [f"KB sync complete: {synced} synced, {errors} errors (of {len(items)} pending)."]
    if error_details:
        parts.append("Errors:")
        for detail in error_details:
            parts.append(f"  - {detail}")
    return "\n".join(parts)
