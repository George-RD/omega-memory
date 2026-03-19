"""OMEGA Knowledge Tool Schemas -- 6 tools for document vectorization and retrieval."""

KNOWLEDGE_TOOL_SCHEMAS = [
    {
        "name": "omega_ingest_document",
        "description": (
            "Ingest a document (PDF, webpage, or text file) into the knowledge base. "
            "Extracts text, chunks semantically, generates embeddings, and stores for vector search. "
            "Supports: PDF files (via Docling/PyPDF2), web URLs, markdown, plain text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path_or_url": {
                    "type": "string",
                    "description": "File path or URL to ingest (e.g., '/path/to/resume.pdf' or 'https://example.com')",
                },
                "source_type": {
                    "type": "string",
                    "description": "Source type override: 'pdf', 'webpage', 'markdown', 'text'. Auto-detected if omitted.",
                },
                "title": {
                    "type": "string",
                    "description": "Optional title for the document (auto-extracted if omitted)",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Scope this document to an entity (e.g., 'acme'). Omit for unscoped.",
                },
            },
            "required": ["path_or_url"],
        },
    },
    {
        "name": "omega_search_documents",
        "description": (
            "Search across all ingested documents using vector similarity. "
            "Returns the most relevant chunks with source attribution. "
            "Use this for RAG-style retrieval over personal documents."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5, max 50)",
                    "default": 5,
                },
                "source_type": {
                    "type": "string",
                    "description": "Filter by source type: 'pdf', 'webpage', 'markdown', 'text'",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Filter results to a specific entity (e.g., 'acme'). Omit for all.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "omega_list_documents",
        "description": "List all documents in the knowledge base with chunk counts and metadata.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "omega_remove_document",
        "description": "Remove a document and all its chunks/embeddings from the knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {
                    "type": "string",
                    "description": "The source path or URL of the document to remove",
                },
            },
            "required": ["source_path"],
        },
    },
    {
        "name": "omega_scan_documents",
        "description": (
            "Scan the documents folder (~/.omega/documents/) for new or changed files "
            "and auto-ingest them. Supports PDF, markdown, text, HTML, CSV, JSON. "
            "Only re-ingests files whose content has changed (checksum-based)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Custom directory to scan (default: ~/.omega/documents/)",
                },
            },
        },
    },
    {
        "name": "omega_sync_kb",
        "description": (
            "Sync pending files from the cloud knowledge base queue (Supabase) into the local "
            "knowledge base. Files are uploaded via the OMEGA web app (Google Drive Picker) "
            "and queued in Supabase. This tool downloads and ingests them locally."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_size": {
                    "type": "integer",
                    "description": "Max items to process per call (default 10, max 50)",
                    "default": 10,
                },
            },
        },
    },
]
