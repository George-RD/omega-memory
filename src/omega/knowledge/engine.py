"""OMEGA Knowledge Engine -- Document ingestion, chunking, embedding, and retrieval.

Supports PDF files (via Docling or fallback text extraction), web pages
(via markdownify), and plain text/markdown files. Chunks are embedded using
OMEGA's existing bge-small-en-v1.5 backend and stored in sqlite-vec for
fast vector similarity search.

Ingestion pipeline:
  Input → Extract text → Semantic chunking → Embed → Store in sqlite-vec
"""

import hashlib
import logging
import os
import re
import sqlite3
import struct
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("omega.knowledge")

# Chunking defaults
DEFAULT_CHUNK_SIZE = 300  # tokens (approximate)
MIN_CHUNK_SIZE = 50
MAX_CHUNK_SIZE = 800
CHUNK_OVERLAP = 30  # tokens overlap between chunks

# Singleton
_instance: Optional["KnowledgeBase"] = None
_lock = threading.Lock()


def _omega_home() -> Path:
    return Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega")))


def _documents_dir() -> Path:
    return _omega_home() / "documents"


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate (~4 chars per token for English)."""
    return max(1, len(text) // 4)


def _compute_checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _serialize_embedding(embedding: list[float]) -> bytes:
    """Serialize embedding to bytes for sqlite-vec."""
    return struct.pack(f"{len(embedding)}f", *embedding)


class KnowledgeBase:
    """Document vectorization and retrieval backed by SQLite + sqlite-vec."""

    SCHEMA_VERSION = 2

    # Input size limits (configurable via env vars)
    MAX_DOCUMENT_SIZE_MB = int(os.environ.get("OMEGA_MAX_DOCUMENT_SIZE_MB", "50"))
    MAX_CHUNKS_PER_DOCUMENT = int(os.environ.get("OMEGA_MAX_CHUNKS_PER_DOCUMENT", "10000"))

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
        self._vec_available = self._check_vec()
        self._init_schema()

    def _check_vec(self) -> bool:
        try:
            import sqlite_vec

            self._conn.enable_load_extension(True)
            try:
                sqlite_vec.load(self._conn)
            finally:
                self._conn.enable_load_extension(False)
            return True
        except Exception:
            return False

    def _init_schema(self) -> None:
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_schema_version (
                version INTEGER NOT NULL
            )
        """)
        row = c.execute("SELECT version FROM knowledge_schema_version").fetchone()
        if not row:
            c.execute("INSERT INTO knowledge_schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))

        # Schema migration v1 → v2: add entity_id column
        if row and row[0] < 2:
            try:
                c.execute("ALTER TABLE documents ADD COLUMN entity_id TEXT")
            except Exception:
                pass  # Column already exists
            c.execute("CREATE INDEX IF NOT EXISTS idx_documents_entity_id ON documents(entity_id)")
            c.execute("UPDATE knowledge_schema_version SET version = 2")
            c.commit()
            logger.info("Knowledge schema migrated v1 → v2: added entity_id column")

        c.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,
                title TEXT,
                checksum TEXT,
                chunk_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                entity_id TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_documents_checksum ON documents(checksum)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_documents_entity_id ON documents(entity_id)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                chunk_type TEXT,
                page_number INTEGER,
                token_count INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id)")

        # Vector table for chunk embeddings
        if self._vec_available:
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_vec
                USING vec0(embedding float[384] distance_metric=cosine)
            """)

        # FTS5 for text search fallback
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts
            USING fts5(content, content='document_chunks', content_rowid='id')
        """)

        c.commit()

    def _extract_text(self, path_or_url: str, source_type: str) -> tuple[str, str]:
        """Extract text content from a source. Returns (text, title)."""
        if source_type == "pdf":
            return self._extract_pdf(path_or_url)
        elif source_type == "webpage":
            return self._extract_webpage(path_or_url)
        elif source_type in ("markdown", "text"):
            return self._extract_file(path_or_url)
        else:
            return self._extract_file(path_or_url)

    def _extract_pdf(self, path: str) -> tuple[str, str]:
        """Extract text from PDF using Docling or fallback."""
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        # Try Docling first (best quality — native markdown output)
        try:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
            result = converter.convert(str(p))
            text = result.document.export_to_markdown()
            title = result.document.name or p.stem
            return text, title
        except ImportError:
            logger.debug("Docling not available, trying pdfplumber")
        except Exception as e:
            logger.warning("Docling extraction failed: %s", e)

        # Fallback: pdfplumber (lightweight, good quality)
        try:
            import pdfplumber

            with pdfplumber.open(str(p)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                return "\n\n".join(pages), p.stem
        except ImportError:
            pass

        raise ImportError(
            "No PDF extraction library available. Install: "
            "pip install 'omega-memory[knowledge-pdf]' (docling + pdfplumber) "
            "or pip install 'omega-memory[knowledge-pdf-lite]' (pdfplumber only)"
        )

    def _extract_webpage(self, url: str) -> tuple[str, str]:
        """Extract text from a webpage."""
        import urllib.request

        # W2: Validate URL scheme to prevent SSRF (file://, ftp://, internal IPs)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme '{parsed.scheme}' — only http/https allowed")

        try:
            from markdownify import markdownify as md
        except ImportError:
            raise ImportError("markdownify package required for webpage ingestion. Install: pip install markdownify")

        req = urllib.request.Request(url, headers={
            "User-Agent": "OMEGA-Knowledge/1.0",
            "Accept": "text/markdown, text/html;q=0.9, */*;q=0.8",
        })
        max_bytes = self.MAX_DOCUMENT_SIZE_MB * 1024 * 1024
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            # W3: Limit response size to prevent OOM
            body_bytes = resp.read(max_bytes + 1)
            if len(body_bytes) > max_bytes:
                raise ValueError(
                    f"Webpage response exceeds {self.MAX_DOCUMENT_SIZE_MB} MB limit. "
                    f"Override with OMEGA_MAX_DOCUMENT_SIZE_MB env var."
                )
            body = body_bytes.decode("utf-8", errors="replace")

            # Log CF markdown-for-agents token header if present
            md_tokens = resp.headers.get("x-markdown-tokens")
            if md_tokens:
                logger.debug("x-markdown-tokens: %s for %s", md_tokens, url)

        if "text/markdown" in content_type:
            # Server returned markdown directly (e.g. Cloudflare edge)
            text = body
            # Try to extract title from first heading
            heading_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            title = heading_match.group(1).strip() if heading_match else urlparse(url).netloc
        else:
            # HTML fallback — convert via markdownify
            html = body
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else urlparse(url).netloc
            text = md(html, strip=["script", "style", "nav", "footer", "header"])

        # Clean up excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        return text, title

    def _extract_file(self, path: str) -> tuple[str, str]:
        """Extract text from a plain text or markdown file."""
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        return text, p.stem

    def _semantic_chunk(self, text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[dict]:
        """Split text into semantic chunks based on headings and paragraphs."""
        chunks = []

        # Split by headings first
        sections = re.split(r"(?m)^(#{1,4}\s+.+)$", text)

        current_heading = None
        current_text = ""

        for i, section in enumerate(sections):
            if re.match(r"^#{1,4}\s+", section):
                # This is a heading
                if current_text.strip():
                    chunks.extend(self._split_by_paragraphs(current_text, current_heading, chunk_size))
                current_heading = section.strip()
                current_text = ""
            else:
                current_text += section

        # Process remaining text
        if current_text.strip():
            chunks.extend(self._split_by_paragraphs(current_text, current_heading, chunk_size))

        # If no chunks produced (no headings), fall back to paragraph splitting
        if not chunks:
            chunks = self._split_by_paragraphs(text, None, chunk_size)

        # If still no chunks but text exists, create a single chunk
        if not chunks and text.strip():
            chunks = [{
                "content": text.strip(),
                "chunk_type": "full_document",
                "token_count": _estimate_tokens(text.strip()),
            }]

        # Number the chunks
        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i

        return chunks

    def _split_by_paragraphs(
        self, text: str, heading: Optional[str], chunk_size: int
    ) -> list[dict]:
        """Split text by paragraphs, merging small ones and splitting large ones."""
        paragraphs = re.split(r"\n\s*\n", text.strip())
        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            combined = f"{current}\n\n{para}" if current else para
            tokens = _estimate_tokens(combined)

            if tokens > chunk_size and current:
                # Emit current chunk
                chunk_text = current.strip()
                if _estimate_tokens(chunk_text) >= MIN_CHUNK_SIZE:
                    chunks.append({
                        "content": f"{heading}\n\n{chunk_text}" if heading else chunk_text,
                        "chunk_type": "section" if heading else "paragraph",
                        "token_count": _estimate_tokens(chunk_text),
                    })
                current = para
            elif tokens > MAX_CHUNK_SIZE:
                # Split oversized paragraph by sentences
                if current.strip():
                    chunk_text = current.strip()
                    if _estimate_tokens(chunk_text) >= MIN_CHUNK_SIZE:
                        chunks.append({
                            "content": f"{heading}\n\n{chunk_text}" if heading else chunk_text,
                            "chunk_type": "section" if heading else "paragraph",
                            "token_count": _estimate_tokens(chunk_text),
                        })
                sentences = re.split(r"(?<=[.!?])\s+", para)
                # If no sentence boundaries found, split by word count
                if len(sentences) <= 1:
                    words = para.split()
                    words_per_chunk = chunk_size * 4 // max(1, len(words[0]) + 1) if words else chunk_size
                    words_per_chunk = max(20, min(words_per_chunk, len(words)))
                    for wi in range(0, len(words), words_per_chunk):
                        chunk_text = " ".join(words[wi : wi + words_per_chunk])
                        if _estimate_tokens(chunk_text) >= MIN_CHUNK_SIZE:
                            chunks.append({
                                "content": f"{heading}\n\n{chunk_text}" if heading else chunk_text,
                                "chunk_type": "word_group",
                                "token_count": _estimate_tokens(chunk_text),
                            })
                    current = ""
                    continue
                current = ""
                for sent in sentences:
                    if _estimate_tokens(current + " " + sent) > chunk_size and current:
                        chunk_text = current.strip()
                        if _estimate_tokens(chunk_text) >= MIN_CHUNK_SIZE:
                            chunks.append({
                                "content": f"{heading}\n\n{chunk_text}" if heading else chunk_text,
                                "chunk_type": "sentence_group",
                                "token_count": _estimate_tokens(chunk_text),
                            })
                        current = sent
                    else:
                        current = f"{current} {sent}" if current else sent
            else:
                current = combined

        # Emit remaining
        if current.strip():
            chunk_text = current.strip()
            tokens = _estimate_tokens(chunk_text)
            if tokens >= MIN_CHUNK_SIZE:
                chunks.append({
                    "content": f"{heading}\n\n{chunk_text}" if heading else chunk_text,
                    "chunk_type": "section" if heading else "paragraph",
                    "token_count": tokens,
                })
            elif chunks:
                # Append undersized tail to previous chunk instead of dropping
                chunks[-1]["content"] += "\n\n" + chunk_text
                chunks[-1]["token_count"] += tokens
            else:
                # Only chunk — keep it even if small
                chunks.append({
                    "content": f"{heading}\n\n{chunk_text}" if heading else chunk_text,
                    "chunk_type": "section" if heading else "paragraph",
                    "token_count": tokens,
                })

        return chunks

    def ingest(
        self,
        path_or_url: str,
        source_type: Optional[str] = None,
        title: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> str:
        """Ingest a document: extract text, chunk, embed, and store."""
        # Auto-detect source type
        if source_type is None:
            source_type = self._detect_source_type(path_or_url)

        # Extract text
        try:
            text, auto_title = self._extract_text(path_or_url, source_type)
        except FileNotFoundError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error extracting text: {e}"

        if not text.strip():
            return f"Error: no text content extracted from {path_or_url}"

        # Enforce document size limit
        text_size_mb = len(text.encode("utf-8")) / (1024 * 1024)
        if text_size_mb > self.MAX_DOCUMENT_SIZE_MB:
            return (
                f"Error: document size ({text_size_mb:.1f} MB) exceeds limit "
                f"({self.MAX_DOCUMENT_SIZE_MB} MB). Override with OMEGA_MAX_DOCUMENT_SIZE_MB env var."
            )

        title = title or auto_title
        checksum = _compute_checksum(text)

        # First lock section: read existing doc and check if unchanged.
        # Do NOT delete old chunks here — if embedding later fails, we must not
        # leave the document in an orphaned state.
        with self._lock:
            existing = self._conn.execute(
                "SELECT id, checksum FROM documents WHERE source_path = ?",
                (path_or_url,),
            ).fetchone()

            if existing and existing["checksum"] == checksum:
                return f"Document already ingested (unchanged): {title}"

            if existing:
                doc_id = existing["id"]
            else:
                now = datetime.now(timezone.utc).isoformat()
                try:
                    cursor = self._conn.execute(
                        "INSERT INTO documents (source_path, source_type, title, checksum, created_at, updated_at, entity_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (path_or_url, source_type, title, checksum, now, now, entity_id),
                    )
                    doc_id = cursor.lastrowid
                    self._conn.commit()
                except sqlite3.IntegrityError:
                    # W4: Concurrent thread already inserted this source_path —
                    # re-read and treat as existing document
                    existing = self._conn.execute(
                        "SELECT id, checksum FROM documents WHERE source_path = ?",
                        (path_or_url,),
                    ).fetchone()
                    if existing and existing["checksum"] == checksum:
                        return f"Document already ingested (unchanged): {title}"
                    doc_id = existing["id"] if existing else None
                    if doc_id is None:
                        return f"Error: failed to ingest {path_or_url} (concurrent conflict)"

        # Chunk the text (outside lock — pure CPU work)
        chunks = self._semantic_chunk(text)
        if not chunks:
            return f"Error: text extracted but no chunks produced from {path_or_url}"

        if len(chunks) > self.MAX_CHUNKS_PER_DOCUMENT:
            return (
                f"Error: document produced {len(chunks):,} chunks, exceeding limit "
                f"({self.MAX_CHUNKS_PER_DOCUMENT:,}). Override with OMEGA_MAX_CHUNKS_PER_DOCUMENT env var."
            )

        # Generate embeddings in batch (outside lock — expensive I/O)
        from omega.embedding import generate_embeddings_batch

        chunk_texts = [c["content"] for c in chunks]
        embeddings = generate_embeddings_batch(chunk_texts)

        # Second lock section: now that embeddings succeeded, atomically replace
        # old chunks and insert new ones. Deleting AFTER embedding ensures we never
        # leave the document orphaned if embedding raises.
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if existing:
                # Delete old chunks now that new embeddings are ready
                self._delete_document_chunks(existing["id"])
                self._conn.execute(
                    "UPDATE documents SET checksum = ?, title = ?, entity_id = ?, updated_at = ? WHERE id = ?",
                    (checksum, title, entity_id, now, doc_id),
                )

            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                cursor = self._conn.execute(
                    """
                    INSERT INTO document_chunks
                        (document_id, chunk_index, content, chunk_type, token_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (doc_id, chunk.get("chunk_index", i), chunk["content"],
                     chunk.get("chunk_type"), chunk.get("token_count"), now),
                )
                chunk_id = cursor.lastrowid

                # Store embedding in vec table
                if self._vec_available and embedding:
                    emb_bytes = _serialize_embedding(embedding)
                    self._conn.execute(
                        "INSERT INTO document_chunks_vec (rowid, embedding) VALUES (?, ?)",
                        (chunk_id, emb_bytes),
                    )

                # Update FTS index
                self._conn.execute(
                    "INSERT INTO document_chunks_fts (rowid, content) VALUES (?, ?)",
                    (chunk_id, chunk["content"]),
                )

            # Update chunk count
            self._conn.execute(
                "UPDATE documents SET chunk_count = ?, updated_at = ? WHERE id = ?",
                (len(chunks), now, doc_id),
            )
            self._conn.commit()

        action = "Re-ingested" if existing else "Ingested"
        return f"{action} **{title}** ({source_type}): {len(chunks)} chunks, {sum(c.get('token_count', 0) for c in chunks)} tokens"

    def search(
        self,
        query: str,
        limit: int = 5,
        source_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> str:
        """Vector similarity search across all ingested documents."""
        if not query.strip():
            return "Error: search query is required"

        limit = max(1, min(limit, 50))

        # Generate query embedding
        from omega.embedding import generate_embedding

        query_embedding = generate_embedding(query)

        results = []

        if self._vec_available and query_embedding:
            emb_bytes = _serialize_embedding(query_embedding)

            with self._lock:
                # Build filter conditions for the vec search
                conditions = ["v.embedding MATCH ?", "k = ?"]
                params: list = [emb_bytes, limit * 2]

                if source_type:
                    conditions.append("d.source_type = ?")
                    params.append(source_type)
                if entity_id:
                    conditions.append("d.entity_id = ?")
                    params.append(entity_id)

                where_clause = " AND ".join(conditions)
                rows = self._conn.execute(
                    f"""
                    SELECT dc.id, dc.content, dc.chunk_type, dc.token_count,
                           d.title, d.source_path, d.source_type,
                           v.distance
                    FROM document_chunks_vec v
                    JOIN document_chunks dc ON dc.id = v.rowid
                    JOIN documents d ON d.id = dc.document_id
                    WHERE {where_clause}
                    ORDER BY v.distance ASC
                    """,
                    params,
                ).fetchall()

            for row in rows[:limit]:
                similarity = 1.0 - (row["distance"] or 0)
                results.append({
                    "content": row["content"],
                    "title": row["title"],
                    "source": row["source_path"],
                    "source_type": row["source_type"],
                    "similarity": round(similarity, 3),
                    "chunk_type": row["chunk_type"],
                })
        else:
            # FTS5 fallback
            with self._lock:
                # W2: Strip FTS5 special characters to prevent OperationalError
                _fts_special = re.compile(r'["\'\(\)\[\]\{\}\^\*\+\?\|\\]')
                sanitized_terms = [
                    _fts_special.sub("", tok)
                    for tok in query.split()[:10]
                    if _fts_special.sub("", tok)
                ]
                fts_query = " ".join(sanitized_terms) if sanitized_terms else query.split()[0] if query.split() else ""

                # W1: Collect document_ids for entity_id filter (if needed)
                entity_doc_ids: Optional[set] = None
                if entity_id:
                    id_rows = self._conn.execute(
                        "SELECT id FROM documents WHERE entity_id = ?", (entity_id,)
                    ).fetchall()
                    entity_doc_ids = {r[0] for r in id_rows}

                try:
                    rows = self._conn.execute(
                        """
                        SELECT dc.id, dc.document_id, dc.content, dc.chunk_type, dc.token_count,
                               d.title, d.source_path, d.source_type,
                               rank
                        FROM document_chunks_fts fts
                        JOIN document_chunks dc ON dc.id = fts.rowid
                        JOIN documents d ON d.id = dc.document_id
                        WHERE document_chunks_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (fts_query, limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    logger.debug("FTS5 query failed for query %r, returning empty results", query)
                    rows = []

                # W1: Apply entity_id filter to FTS results
                if entity_doc_ids is not None:
                    rows = [r for r in rows if r["document_id"] in entity_doc_ids]

            for row in rows:
                results.append({
                    "content": row["content"],
                    "title": row["title"],
                    "source": row["source_path"],
                    "source_type": row["source_type"],
                    "similarity": None,
                    "chunk_type": row["chunk_type"],
                })

        if not results:
            return f"No document matches for: {query}"

        lines = [f"Found {len(results)} relevant chunk(s):\n"]
        for i, r in enumerate(results, 1):
            sim = f" (similarity: {r['similarity']})" if r["similarity"] is not None else ""
            lines.append(f"### {i}. {r['title']} [{r['source_type']}]{sim}")
            # Truncate long content for display
            content = r["content"]
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(content)
            lines.append(f"_Source: {r['source']}_\n")

        return "\n".join(lines)

    def list_documents(self) -> str:
        """List all ingested documents with metadata."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, source_path, source_type, title, checksum, chunk_count, created_at, updated_at, entity_id FROM documents ORDER BY updated_at DESC"
            ).fetchall()

        if not rows:
            return "No documents ingested yet."

        lines = [f"## Knowledge Base ({len(rows)} documents)\n"]
        total_chunks = 0
        for r in rows:
            entity_badge = f" [entity: {r['entity_id']}]" if r["entity_id"] else ""
            lines.append(
                f"- **{r['title']}** ({r['source_type']}) — {r['chunk_count']} chunks{entity_badge}"
            )
            lines.append(f"  Source: `{r['source_path']}`")
            lines.append(f"  Ingested: {r['created_at'][:10]}, Updated: {r['updated_at'][:10]}")
            total_chunks += r["chunk_count"] or 0

        lines.append(f"\n**Total**: {len(rows)} documents, {total_chunks} chunks")
        return "\n".join(lines)

    def remove(self, source_path: str) -> str:
        """Remove a document and all its chunks/embeddings."""
        source_path = source_path.strip()
        if not source_path:
            return "Error: source_path is required"

        with self._lock:
            doc = self._conn.execute(
                "SELECT id, title FROM documents WHERE source_path = ?",
                (source_path,),
            ).fetchone()

            if not doc:
                return f"Document not found: {source_path}"

            self._delete_document_chunks(doc["id"])
            self._conn.execute("DELETE FROM documents WHERE id = ?", (doc["id"],))
            self._conn.commit()

        return f"Removed document: {doc['title']} ({source_path})"

    def _delete_document_chunks(self, doc_id: int) -> None:
        """Delete all chunks and their embeddings for a document (caller holds lock)."""
        chunk_ids = [
            r[0]
            for r in self._conn.execute(
                "SELECT id FROM document_chunks WHERE document_id = ?", (doc_id,)
            ).fetchall()
        ]

        if chunk_ids:
            placeholders = ",".join("?" * len(chunk_ids))
            # Delete from vec table
            if self._vec_available:
                self._conn.execute(
                    f"DELETE FROM document_chunks_vec WHERE rowid IN ({placeholders})",
                    chunk_ids,
                )
            # Delete from FTS
            for cid in chunk_ids:
                self._conn.execute(
                    "DELETE FROM document_chunks_fts WHERE rowid = ?", (cid,)
                )

        # Delete chunks (CASCADE would handle this, but explicit is safer)
        self._conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))

    def _detect_source_type(self, path_or_url: str) -> str:
        """Auto-detect source type from path or URL."""
        if path_or_url.startswith(("http://", "https://")):
            return "webpage"

        p = Path(path_or_url)
        ext = p.suffix.lower()
        if ext == ".pdf":
            return "pdf"
        elif ext in (".md", ".markdown"):
            return "markdown"
        else:
            return "text"

    # Supported file extensions for auto-scan
    SCAN_EXTENSIONS = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "text",
        ".text": "text",
        ".json": "text",
        ".csv": "text",
        ".rtf": "text",
        ".html": "text",
        ".htm": "text",
    }

    def scan_directory(self, directory: Optional[Path] = None) -> str:
        """Scan a directory for new/changed documents and auto-ingest them.

        Default directory: ~/.omega/documents/
        Tracks ingested files by checksum — only re-ingests if content changed.
        """
        if directory is None:
            directory = _documents_dir()
        else:
            directory = Path(directory)

        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            return f"Created documents folder: {directory}\nDrop PDF, markdown, or text files here for auto-ingestion."

        files = []
        for ext, source_type in self.SCAN_EXTENSIONS.items():
            files.extend(directory.rglob(f"*{ext}"))

        if not files:
            return f"No supported files found in {directory}"

        ingested = 0
        skipped = 0
        errors = 0
        details = []

        for filepath in sorted(files):
            try:
                result = self.ingest(str(filepath))
                if "unchanged" in result.lower():
                    skipped += 1
                elif "Error" in result:
                    errors += 1
                    details.append(f"  error: {filepath.name}: {result}")
                else:
                    ingested += 1
                    details.append(f"  new: {result}")
            except Exception as e:
                errors += 1
                details.append(f"  error: {filepath.name}: {e}")

        lines = [f"Scanned {len(files)} file(s) in {directory}"]
        if ingested:
            lines.append(f"  {ingested} ingested")
        if skipped:
            lines.append(f"  {skipped} unchanged (skipped)")
        if errors:
            lines.append(f"  {errors} error(s)")
        lines.extend(details)

        return "\n".join(lines)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def get_knowledge_base(db_path: Optional[Path] = None) -> KnowledgeBase:
    """Get or create the KnowledgeBase singleton."""
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        _instance = KnowledgeBase(db_path=db_path)
    return _instance


def reset_knowledge_base() -> None:
    """Reset singleton for testing."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
        _instance = None


# Convenience functions
def ingest_document(
    path_or_url: str,
    source_type: Optional[str] = None,
    title: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> str:
    return get_knowledge_base().ingest(path_or_url, source_type, title, entity_id)


def search_documents(
    query: str,
    limit: int = 5,
    source_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> str:
    return get_knowledge_base().search(query, limit, source_type, entity_id)


def list_documents() -> str:
    return get_knowledge_base().list_documents()


def remove_document(source_path: str) -> str:
    return get_knowledge_base().remove(source_path)


def scan_directory(directory: Optional[str] = None) -> str:
    d = Path(directory) if directory else None
    return get_knowledge_base().scan_directory(d)
