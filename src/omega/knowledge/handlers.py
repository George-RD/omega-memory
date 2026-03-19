"""OMEGA Knowledge Handlers -- MCP handlers for document vectorization and retrieval."""

import logging
from typing import Any, Dict

logger = logging.getLogger("omega.knowledge.handlers")


from omega.server.responses import mcp_response, mcp_error


def _clamp_int(value, default: int, min_val: int = 1, max_val: int = 50) -> int:
    try:
        v = int(value)
        return max(min_val, min(v, max_val))
    except (TypeError, ValueError):
        return default


async def handle_omega_ingest_document(arguments: dict) -> dict:
    """Ingest a document into the knowledge base."""
    path_or_url = arguments.get("path_or_url", "").strip()
    if not path_or_url:
        return mcp_error("path_or_url is required")

    source_type = arguments.get("source_type")
    if source_type:
        source_type = source_type.strip().lower()
    title = arguments.get("title")
    entity_id = arguments.get("entity_id")

    try:
        from omega.knowledge.engine import ingest_document

        result = ingest_document(path_or_url, source_type, title, entity_id)
        return mcp_response(result)
    except ImportError as e:
        return mcp_error(str(e))
    except Exception as e:
        logger.error("omega_ingest_document failed: %s", e)
        return mcp_error(f"Failed to ingest document: {e}")


async def handle_omega_search_documents(arguments: dict) -> dict:
    """Search across ingested documents."""
    query = arguments.get("query", "").strip()
    if not query:
        return mcp_error("query is required")

    limit = _clamp_int(arguments.get("limit"), default=5, min_val=1, max_val=50)
    source_type = arguments.get("source_type")
    if source_type:
        source_type = source_type.strip().lower()
    entity_id = arguments.get("entity_id")

    try:
        from omega.knowledge.engine import search_documents

        result = search_documents(query, limit, source_type, entity_id)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_search_documents failed: %s", e)
        return mcp_error(f"Failed to search documents: {e}")


async def handle_omega_list_documents(arguments: dict) -> dict:
    """List all ingested documents."""
    try:
        from omega.knowledge.engine import list_documents

        result = list_documents()
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_list_documents failed: %s", e)
        return mcp_error(f"Failed to list documents: {e}")


async def handle_omega_remove_document(arguments: dict) -> dict:
    """Remove a document from the knowledge base."""
    source_path = arguments.get("source_path", "").strip()
    if not source_path:
        return mcp_error("source_path is required")

    try:
        from omega.knowledge.engine import remove_document

        result = remove_document(source_path)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_remove_document failed: %s", e)
        return mcp_error(f"Failed to remove document: {e}")


async def handle_omega_scan_documents(arguments: dict) -> dict:
    """Scan documents folder for new/changed files."""
    directory = arguments.get("directory")

    try:
        from omega.knowledge.engine import scan_directory

        result = scan_directory(directory)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_scan_documents failed: %s", e)
        return mcp_error(f"Failed to scan documents: {e}")


async def handle_omega_sync_kb(arguments: dict) -> dict:
    """Sync pending files from cloud kb_queue into local knowledge base."""
    batch_size = _clamp_int(arguments.get("batch_size"), default=10, min_val=1, max_val=50)

    try:
        from omega.knowledge.cloud_sync import sync_kb_queue

        result = sync_kb_queue(batch_size)
        return mcp_response(result)
    except ImportError as e:
        return mcp_error(str(e))
    except Exception as e:
        logger.error("omega_sync_kb failed: %s", e)
        return mcp_error(f"Failed to sync KB queue: {e}")


KNOWLEDGE_HANDLERS: Dict[str, Any] = {
    "omega_ingest_document": handle_omega_ingest_document,
    "omega_search_documents": handle_omega_search_documents,
    "omega_list_documents": handle_omega_list_documents,
    "omega_remove_document": handle_omega_remove_document,
    "omega_scan_documents": handle_omega_scan_documents,
    "omega_sync_kb": handle_omega_sync_kb,
}
