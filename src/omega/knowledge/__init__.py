"""OMEGA Knowledge -- Document vectorization and RAG-style retrieval."""

from omega.knowledge.engine import (
    KnowledgeBase,
    get_knowledge_base,
    ingest_document,
    search_documents,
    list_documents,
    remove_document,
    scan_directory,
)

__all__ = [
    "KnowledgeBase",
    "get_knowledge_base",
    "ingest_document",
    "search_documents",
    "list_documents",
    "remove_document",
    "scan_directory",
]
