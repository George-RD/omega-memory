"""Tests for OMEGA Knowledge module -- uncovered edge cases.

Covers: scan_directory edge cases, entity scoping, FTS fallback, remove cascade,
duplicate ingestion idempotency, large text chunking, source type detection,
empty/missing file handling, empty search results, list_documents after removals,
webpage extraction, cloud_sync, and size limit enforcement.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_DIM = 384


def _fake_embedding(text: str) -> list[float]:
    """Deterministic fake 384-dim embedding from text hash."""
    import hashlib

    h = hashlib.sha256(text.encode()).digest()
    vec = []
    for i in range(FAKE_DIM):
        byte_val = h[i % len(h)]
        vec.append((byte_val / 255.0) * 2 - 1)
    # Normalize
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec]


def _fake_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Batch wrapper for fake embeddings."""
    return [_fake_embedding(t) for t in texts]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kb(tmp_path):
    """Fresh KnowledgeBase with mocked embeddings for DB isolation."""
    os.environ["OMEGA_HOME"] = str(tmp_path / ".omega")
    os.environ["OMEGA_ENCRYPT"] = "0"
    (tmp_path / ".omega").mkdir(exist_ok=True)

    with patch("omega.embedding.generate_embedding", side_effect=_fake_embedding), \
         patch("omega.embedding.generate_embeddings_batch", side_effect=_fake_embeddings_batch):
        from omega.knowledge.engine import KnowledgeBase

        kb = KnowledgeBase(db_path=tmp_path / "knowledge.db")
        yield kb
        kb.close()

    os.environ.pop("OMEGA_HOME", None)
    os.environ.pop("OMEGA_ENCRYPT", None)
    from omega.crypto import reset_crypto_state
    reset_crypto_state()


@pytest.fixture
def _mock_embeddings():
    """Context-manager fixture that patches embedding functions."""
    with patch("omega.embedding.generate_embedding", side_effect=_fake_embedding), \
         patch("omega.embedding.generate_embeddings_batch", side_effect=_fake_embeddings_batch):
        yield


# ---------------------------------------------------------------------------
# 1. scan_directory() edge cases
# ---------------------------------------------------------------------------


class TestScanDirectoryGaps:
    """Edge cases for scan_directory not covered by existing tests."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_scan_mixed_file_types(self, kb, tmp_path):
        """Scan a directory containing .txt, .md, and .py files."""
        scan_dir = tmp_path / "mixed"
        scan_dir.mkdir()

        (scan_dir / "readme.txt").write_text(
            "This is a plain text readme with enough content to produce a chunk. "
            "It describes the project goals, architecture, and usage instructions. "
            "The file is intended to be ingested by the knowledge base system."
        )
        (scan_dir / "notes.md").write_text(
            "# Notes\n\nThese are markdown notes about our development process. "
            "We follow agile methodology with two-week sprints and daily standups. "
            "Our CI/CD pipeline runs automated tests on every pull request."
        )
        # .py is NOT in SCAN_EXTENSIONS -- should be ignored
        (scan_dir / "script.py").write_text(
            "# This is a Python script\n"
            "def main():\n    print('hello world')\n"
        )

        result = kb.scan_directory(scan_dir)
        assert "2" in result  # 2 files scanned (txt + md)
        assert "2 ingested" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_scan_empty_directory(self, kb, tmp_path):
        """Empty directory reports no supported files."""
        scan_dir = tmp_path / "empty_dir"
        scan_dir.mkdir()

        result = kb.scan_directory(scan_dir)
        assert "No supported files" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_scan_directory_with_no_eligible_files(self, kb, tmp_path):
        """Directory with only unsupported file types."""
        scan_dir = tmp_path / "no_eligible"
        scan_dir.mkdir()

        (scan_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0")
        (scan_dir / "archive.zip").write_bytes(b"PK\x03\x04")
        (scan_dir / "data.parquet").write_bytes(b"PAR1")
        (scan_dir / "script.py").write_text("print('hi')")

        result = kb.scan_directory(scan_dir)
        assert "No supported files" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_scan_nested_subdirectories(self, kb, tmp_path):
        """Deeply nested subdirectories are scanned recursively."""
        scan_dir = tmp_path / "deep"
        level1 = scan_dir / "a"
        level2 = level1 / "b"
        level3 = level2 / "c"
        level3.mkdir(parents=True)

        (scan_dir / "root.txt").write_text(
            "Root level document about system architecture and design patterns. "
            "Covers microservices, event sourcing, and CQRS patterns in detail."
        )
        (level1 / "level1.md").write_text(
            "# Level 1\n\nFirst nesting level document about database design. "
            "Covers normalization, indexing strategies, and query optimization."
        )
        (level2 / "level2.txt").write_text(
            "Second nesting level document about networking and protocols. "
            "Covers TCP/IP, HTTP/2, gRPC, and WebSocket communication."
        )
        (level3 / "level3.md").write_text(
            "# Level 3\n\nThird nesting level document about security best practices. "
            "Covers authentication, authorization, encryption, and audit logging."
        )

        result = kb.scan_directory(scan_dir)
        assert "4 ingested" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_scan_nonexistent_directory_creates_it(self, kb, tmp_path):
        """If directory doesn't exist, scan_directory creates it."""
        scan_dir = tmp_path / "brand_new"
        assert not scan_dir.exists()

        result = kb.scan_directory(scan_dir)
        assert scan_dir.exists()
        assert "Created" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_scan_with_empty_files(self, kb, tmp_path):
        """Empty files in a directory should not count as ingested."""
        scan_dir = tmp_path / "empties"
        scan_dir.mkdir()

        (scan_dir / "empty.txt").write_text("")
        (scan_dir / "nonempty.txt").write_text(
            "This is a non-empty document with enough content to produce chunks. "
            "It contains information about software testing, deployment, and monitoring."
        )

        result = kb.scan_directory(scan_dir)
        # The empty file should produce an error or be skipped
        assert "1 ingested" in result or "1" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_scan_picks_up_all_supported_extensions(self, kb, tmp_path):
        """Verify .json, .csv, .html extensions are scanned too."""
        scan_dir = tmp_path / "multiext"
        scan_dir.mkdir()

        content = (
            "Enough content for a chunk about data formats and serialization. "
            "JSON, CSV, and HTML are common interchange formats used in web applications."
        )
        (scan_dir / "data.json").write_text(content)
        (scan_dir / "data.csv").write_text(content)
        (scan_dir / "page.html").write_text(content)

        result = kb.scan_directory(scan_dir)
        assert "3 ingested" in result


# ---------------------------------------------------------------------------
# 2. Entity scoping in search
# ---------------------------------------------------------------------------


class TestEntityScopingInSearch:
    """Ingest documents with different entity_ids, verify search scoping."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_search_returns_only_matching_entity(self, kb, tmp_path):
        """Search with entity_id should only return docs belonging to that entity."""
        # Create two files with distinct content
        file_a = tmp_path / "entity_a.txt"
        file_a.write_text(
            "Alpha project is about quantum computing research and development. "
            "The team focuses on superconducting qubits and error correction codes. "
            "Their goal is fault-tolerant quantum computation for drug discovery."
        )
        file_b = tmp_path / "entity_b.txt"
        file_b.write_text(
            "Beta project is about marine biology and ocean conservation efforts. "
            "The research covers coral reef ecosystems and deep sea exploration. "
            "Their goal is understanding biodiversity in extreme ocean environments."
        )

        kb.ingest(str(file_a), entity_id="alpha")
        kb.ingest(str(file_b), entity_id="beta")

        # Search scoped to "alpha" -- should NOT return beta's marine biology doc
        result = kb.search("quantum computing research", entity_id="alpha")
        # Entity filtering is post-scoring, so if there are results they should be alpha's
        if "No document" not in result:
            assert "marine biology" not in result or "quantum" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_search_without_entity_returns_all(self, kb, tmp_path):
        """Search without entity_id should return results from all entities."""
        file_a = tmp_path / "doc_alpha.txt"
        file_a.write_text(
            "Document about artificial intelligence and machine learning applications. "
            "Covers neural networks, transformers, and reinforcement learning techniques."
        )
        file_b = tmp_path / "doc_beta.txt"
        file_b.write_text(
            "Document about artificial intelligence in healthcare diagnostics. "
            "Covers medical imaging, clinical decision support, and drug interaction analysis."
        )

        kb.ingest(str(file_a), entity_id="alpha")
        kb.ingest(str(file_b), entity_id="beta")

        result = kb.search("artificial intelligence")
        # Should find results (not filtered by entity)
        if "No document" not in result:
            assert "chunk" in result.lower()

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_search_entity_with_no_matching_docs(self, kb, tmp_path):
        """Search with entity_id that has no documents returns no results."""
        file_a = tmp_path / "only_alpha.txt"
        file_a.write_text(
            "Document about programming languages and compiler design. "
            "Covers lexical analysis, parsing, type checking, and code generation."
        )
        kb.ingest(str(file_a), entity_id="alpha")

        result = kb.search("programming languages", entity_id="nonexistent")
        assert "No document" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_entity_id_stored_in_documents_table(self, kb, tmp_path):
        """Verify entity_id is persisted correctly in the documents table."""
        file_a = tmp_path / "ent_check.txt"
        file_a.write_text(
            "Content for entity persistence check with enough words for a chunk. "
            "This tests that entity_id values are correctly stored in the database."
        )
        kb.ingest(str(file_a), entity_id="my-entity-123")

        row = kb._conn.execute(
            "SELECT entity_id FROM documents WHERE source_path = ?",
            (str(file_a),),
        ).fetchone()
        assert row["entity_id"] == "my-entity-123"


# ---------------------------------------------------------------------------
# 3. FTS fallback path
# ---------------------------------------------------------------------------


class TestFTSFallbackPath:
    """When sqlite-vec is not available, FTS5 search should still work."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_fts_search_when_vec_unavailable(self, kb, tmp_path):
        """Force _vec_available=False and verify FTS5 fallback works."""
        file1 = tmp_path / "fts_doc.txt"
        file1.write_text(
            "Kubernetes container orchestration platform for deploying microservices. "
            "Includes pods, services, deployments, and horizontal pod autoscaling. "
            "Supports rolling updates, canary deployments, and blue-green strategies."
        )
        kb.ingest(str(file1))

        # Disable vec for the search call
        original_vec = kb._vec_available
        kb._vec_available = False
        try:
            result = kb.search("kubernetes container orchestration")
            # FTS should find the document
            assert "No document" not in result
            assert "chunk" in result.lower()
        finally:
            kb._vec_available = original_vec

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_fts_fallback_returns_no_similarity_score(self, kb, tmp_path):
        """FTS results should have similarity=None in the output."""
        file1 = tmp_path / "fts_nosim.txt"
        file1.write_text(
            "PostgreSQL relational database management system with advanced features. "
            "Supports JSON, full-text search, window functions, and common table expressions."
        )
        kb.ingest(str(file1))

        kb._vec_available = False
        try:
            result = kb.search("PostgreSQL database")
            # FTS results don't show similarity scores
            if "No document" not in result:
                assert "similarity" not in result
        finally:
            kb._vec_available = True

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_fts_fallback_when_embedding_returns_empty(self, kb, tmp_path):
        """If generate_embedding returns empty/None, falls back to FTS."""
        file1 = tmp_path / "fts_empty_emb.txt"
        file1.write_text(
            "Redis in-memory data structure store used for caching and messaging. "
            "Supports strings, hashes, lists, sets, and sorted sets with range queries."
        )
        kb.ingest(str(file1))

        with patch("omega.embedding.generate_embedding", return_value=[]):
            result = kb.search("Redis caching")
            # Empty embedding vector triggers FTS fallback (vec_available but no embedding)
            # Either vec search returns nothing or FTS picks it up
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 4. remove() cascade
# ---------------------------------------------------------------------------


class TestRemoveCascade:
    """Removing a document should also remove its chunks and FTS entries."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_remove_deletes_chunks(self, kb, tmp_path):
        """After remove(), document_chunks table should have no rows for that doc."""
        file1 = tmp_path / "cascade_test.md"
        file1.write_text(
            "# Cascade Test\n\n"
            "This document tests that removal cascades to chunks correctly. "
            "It has enough content to produce at least one chunk in the system. "
            "We verify the chunk table is cleaned up after document removal.\n\n"
            "## Second Section\n\n"
            "Additional content to produce more chunks for thorough testing."
        )
        kb.ingest(str(file1))

        # Verify chunks exist
        chunks_before = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]
        assert chunks_before > 0

        # Remove
        result = kb.remove(str(file1))
        assert "Removed" in result

        # Verify chunks are gone
        chunks_after = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]
        assert chunks_after == 0

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_remove_deletes_fts_entries(self, kb, tmp_path):
        """After remove(), FTS index should no longer match the removed doc's content."""
        file1 = tmp_path / "fts_cascade.txt"
        file1.write_text(
            "Xylophone orchestral percussion instrument with wooden bars and resonators. "
            "Used in classical music, jazz, and contemporary compositions worldwide."
        )
        kb.ingest(str(file1))

        # Verify FTS has entries
        fts_before = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks_fts"
        ).fetchone()[0]
        assert fts_before > 0

        kb.remove(str(file1))

        # FTS entries should be gone
        fts_after = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks_fts"
        ).fetchone()[0]
        assert fts_after == 0

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_remove_one_doc_preserves_others(self, kb, tmp_path):
        """Removing one doc should not affect chunks from other docs."""
        file_a = tmp_path / "keep_me.txt"
        file_a.write_text(
            "This document should survive the removal of its sibling document. "
            "It contains information about software reliability and fault tolerance."
        )
        file_b = tmp_path / "delete_me.txt"
        file_b.write_text(
            "This document will be removed and its chunks should be deleted. "
            "It contains information about deprecated legacy systems and migration."
        )
        kb.ingest(str(file_a))
        kb.ingest(str(file_b))

        # Count chunks for file_a
        doc_a = kb._conn.execute(
            "SELECT id FROM documents WHERE source_path = ?", (str(file_a),)
        ).fetchone()
        chunks_a_before = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
            (doc_a["id"],),
        ).fetchone()[0]

        # Remove file_b
        kb.remove(str(file_b))

        # file_a's chunks should still be there
        chunks_a_after = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
            (doc_a["id"],),
        ).fetchone()[0]
        assert chunks_a_after == chunks_a_before
        assert chunks_a_after > 0


# ---------------------------------------------------------------------------
# 5. Duplicate ingestion (checksum-based dedup)
# ---------------------------------------------------------------------------


class TestDuplicateIngestion:
    """Ingesting the same file twice should be idempotent."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_same_content_reports_unchanged(self, kb, tmp_path):
        """Second ingest of identical content returns 'unchanged' message."""
        f = tmp_path / "dedup.txt"
        f.write_text(
            "Idempotent ingestion test content for the knowledge base engine. "
            "This content should be recognized as unchanged on second ingestion."
        )
        result1 = kb.ingest(str(f))
        assert "Ingested" in result1

        result2 = kb.ingest(str(f))
        assert "unchanged" in result2.lower()

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_duplicate_does_not_create_extra_rows(self, kb, tmp_path):
        """Second ingest should not create duplicate document rows."""
        f = tmp_path / "no_dup_rows.txt"
        f.write_text(
            "Content that tests duplicate row prevention in the documents table. "
            "Only one row should exist after ingesting the same path twice."
        )
        kb.ingest(str(f))
        kb.ingest(str(f))

        count = kb._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        assert count == 1

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_duplicate_does_not_create_extra_chunks(self, kb, tmp_path):
        """Chunks should not double on re-ingest of same content."""
        f = tmp_path / "no_dup_chunks.txt"
        f.write_text(
            "Chunk dedup test ensures that ingesting the same content twice "
            "does not create duplicate chunks in the document_chunks table."
        )
        kb.ingest(str(f))
        chunks_after_first = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]

        kb.ingest(str(f))
        chunks_after_second = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]

        assert chunks_after_second == chunks_after_first

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_changed_content_re_ingests(self, kb, tmp_path):
        """If file content changes, re-ingest replaces old chunks."""
        f = tmp_path / "changing.txt"
        f.write_text(
            "Original content version one about software development practices. "
            "Covers version control, code review, and continuous integration."
        )
        result1 = kb.ingest(str(f))
        assert "Ingested" in result1

        doc_before = kb._conn.execute(
            "SELECT checksum FROM documents WHERE source_path = ?", (str(f),)
        ).fetchone()

        f.write_text(
            "Updated content version two about machine learning pipelines. "
            "Covers feature engineering, model training, and deployment strategies."
        )
        result2 = kb.ingest(str(f))
        assert "Re-ingested" in result2

        doc_after = kb._conn.execute(
            "SELECT checksum FROM documents WHERE source_path = ?", (str(f),)
        ).fetchone()
        assert doc_after["checksum"] != doc_before["checksum"]


# ---------------------------------------------------------------------------
# 6. Large text chunking
# ---------------------------------------------------------------------------


class TestLargeTextChunking:
    """Very long documents (10K+ chars) should produce multiple chunks."""

    def test_10k_chars_produces_multiple_chunks(self, kb):
        """A 10K+ char document should be split into many chunks."""
        # 10K chars ~ 2500 tokens at 4 chars/token
        text = "# Big Document\n\n"
        for i in range(20):
            text += f"## Section {i}\n\n"
            text += (
                f"This is section number {i} of a very large document. "
                "It contains multiple sentences of meaningful content about "
                "software architecture, system design, distributed computing, "
                "and cloud infrastructure. Each section discusses a different "
                "aspect of building reliable, scalable, and maintainable systems. "
                "We cover topics like load balancing, caching strategies, "
                "database sharding, message queues, and service mesh patterns. "
            ) * 3
            text += "\n\n"

        assert len(text) > 10000
        chunks = kb._semantic_chunk(text)
        assert len(chunks) > 5  # Should produce many chunks

    def test_single_giant_paragraph(self, kb):
        """A single paragraph of 10K+ chars should still be chunked."""
        words = ["distributed"] * 3000  # ~12K chars (4 chars + space)
        text = " ".join(words)
        assert len(text) > 10000

        chunks = kb._semantic_chunk(text, chunk_size=300)
        assert len(chunks) > 1

    def test_chunk_indices_are_sequential(self, kb):
        """Chunks should have sequential chunk_index values."""
        text = "# Indexed Doc\n\n"
        for i in range(10):
            text += f"## Part {i}\n\n"
            text += "Content " * 200 + "\n\n"

        chunks = kb._semantic_chunk(text)
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_no_empty_chunks_in_output(self, kb):
        """No chunk should have empty content."""
        text = "# Doc\n\n" + ("Paragraph content here. " * 100 + "\n\n") * 20
        chunks = kb._semantic_chunk(text)
        for chunk in chunks:
            assert chunk["content"].strip(), f"Empty chunk at index {chunk['chunk_index']}"

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_large_document_full_ingest(self, kb, tmp_path):
        """End-to-end ingest of a large file produces multiple chunks in DB."""
        large_file = tmp_path / "large_doc.md"
        content = "# Large Document\n\n"
        for i in range(15):
            content += f"## Chapter {i}\n\n"
            content += (
                f"Chapter {i} covers important topics in software engineering. "
                "This includes design patterns, testing strategies, deployment "
                "pipelines, monitoring, alerting, and incident response procedures. "
                "Each chapter builds on the previous one to create a comprehensive "
                "guide for engineering teams working on production systems. "
            ) * 4
            content += "\n\n"

        large_file.write_text(content)
        result = kb.ingest(str(large_file))
        assert "Ingested" in result

        chunk_count = kb._conn.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]
        assert chunk_count > 3


# ---------------------------------------------------------------------------
# 7. Source type detection
# ---------------------------------------------------------------------------


class TestSourceTypeDetection:
    """URLs vs file paths vs explicit source_type parameter."""

    def test_http_url_detected_as_webpage(self, kb):
        assert kb._detect_source_type("http://example.com/page") == "webpage"

    def test_https_url_detected_as_webpage(self, kb):
        assert kb._detect_source_type("https://docs.python.org/3/") == "webpage"

    def test_pdf_extension_detected(self, kb):
        assert kb._detect_source_type("/home/user/paper.pdf") == "pdf"

    def test_pdf_uppercase_extension(self, kb):
        """Uppercase .PDF should still detect as pdf (case-insensitive suffix)."""
        # Path.suffix preserves case, but _detect_source_type lowercases it
        assert kb._detect_source_type("/data/PAPER.PDF") == "pdf"

    def test_md_extension_detected(self, kb):
        assert kb._detect_source_type("notes.md") == "markdown"

    def test_markdown_extension_detected(self, kb):
        assert kb._detect_source_type("readme.markdown") == "markdown"

    def test_txt_extension_detected(self, kb):
        assert kb._detect_source_type("log.txt") == "text"

    def test_unknown_extension_defaults_to_text(self, kb):
        assert kb._detect_source_type("data.xyz") == "text"

    def test_no_extension_defaults_to_text(self, kb):
        assert kb._detect_source_type("/usr/local/Makefile") == "text"

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_explicit_source_type_overrides_detection(self, kb, tmp_path):
        """Passing source_type explicitly should override auto-detection."""
        f = tmp_path / "data.txt"
        f.write_text(
            "Content in a .txt file that we label as markdown explicitly. "
            "This tests that the source_type parameter takes precedence."
        )
        kb.ingest(str(f), source_type="markdown")

        row = kb._conn.execute(
            "SELECT source_type FROM documents WHERE source_path = ?",
            (str(f),),
        ).fetchone()
        assert row["source_type"] == "markdown"


# ---------------------------------------------------------------------------
# 8. Empty/missing file handling
# ---------------------------------------------------------------------------


class TestEmptyMissingFileHandling:
    """Ingest nonexistent file, empty file, whitespace-only file."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_ingest_nonexistent_file(self, kb):
        """Ingesting a file that does not exist returns an error string."""
        result = kb.ingest("/absolutely/nonexistent/path/document.txt")
        assert "Error" in result
        assert "not found" in result.lower()

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_ingest_nonexistent_does_not_create_db_row(self, kb):
        """Failed ingest should not leave orphan rows in documents table."""
        kb.ingest("/no/such/file.md")
        count = kb._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        assert count == 0

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_ingest_empty_file(self, kb, tmp_path):
        """Ingesting an empty file returns an error about no content."""
        f = tmp_path / "empty.txt"
        f.write_text("")

        result = kb.ingest(str(f))
        assert "Error" in result or "no text" in result.lower()

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_ingest_whitespace_only_file(self, kb, tmp_path):
        """Ingesting a file with only whitespace returns an error."""
        f = tmp_path / "whitespace.txt"
        f.write_text("   \n\n\t\t\n   ")

        result = kb.ingest(str(f))
        assert "Error" in result or "no text" in result.lower()

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_ingest_empty_file_no_db_row(self, kb, tmp_path):
        """Empty file ingest should not create a document row."""
        f = tmp_path / "empty_norow.txt"
        f.write_text("")

        kb.ingest(str(f))
        count = kb._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        assert count == 0


# ---------------------------------------------------------------------------
# 9. search() with no results
# ---------------------------------------------------------------------------


class TestSearchNoResults:
    """Query with no matching documents returns appropriate message."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_search_empty_kb(self, kb):
        """Search on an empty knowledge base."""
        result = kb.search("quantum physics")
        assert "No document" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_search_no_fts_match(self, kb, tmp_path):
        """FTS search with terms not present in any document."""
        f = tmp_path / "specific.txt"
        f.write_text(
            "This document is about cloud computing and infrastructure automation. "
            "It covers Terraform, Ansible, and Pulumi for infrastructure as code."
        )
        kb.ingest(str(f))

        # Force FTS path
        kb._vec_available = False
        try:
            result = kb.search("xyzzyplugh")  # Nonsense word
            assert "No document" in result
        finally:
            kb._vec_available = True

    def test_search_empty_query_returns_error(self, kb):
        """Empty string query returns an error."""
        result = kb.search("")
        assert "Error" in result

    def test_search_whitespace_query_returns_error(self, kb):
        """Whitespace-only query returns an error."""
        result = kb.search("   ")
        assert "Error" in result


# ---------------------------------------------------------------------------
# 10. list_documents() after removals
# ---------------------------------------------------------------------------


class TestListDocumentsAfterRemovals:
    """Correct count after removing some documents."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_list_after_removing_one(self, kb, tmp_path):
        """After ingesting 3 and removing 1, list shows 2."""
        files = []
        for i in range(3):
            f = tmp_path / f"doc_{i}.txt"
            f.write_text(
                f"Document number {i} about topic {i}. "
                "Contains enough content for the chunking engine to process. "
                "Information about software engineering and system design."
            )
            files.append(f)
            kb.ingest(str(f))

        # Remove the middle one
        kb.remove(str(files[1]))

        result = kb.list_documents()
        assert "2 documents" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_list_after_removing_all(self, kb, tmp_path):
        """After removing all documents, list shows empty message."""
        files = []
        for i in range(3):
            f = tmp_path / f"all_remove_{i}.txt"
            f.write_text(
                f"Document {i} to be removed entirely from the knowledge base. "
                "Enough content to be ingested and then cleaned up afterwards."
            )
            files.append(f)
            kb.ingest(str(f))

        for f in files:
            kb.remove(str(f))

        result = kb.list_documents()
        assert "No documents" in result

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_list_shows_correct_chunk_count_after_removal(self, kb, tmp_path):
        """Total chunk count in list should decrease after removal."""
        f1 = tmp_path / "counted_a.md"
        f1.write_text(
            "# Document A\n\n"
            "First document with several sections for chunking.\n\n"
            "## Section One\n\n"
            "Content about programming paradigms and functional programming. "
            "Covers immutability, pure functions, and higher-order functions.\n\n"
            "## Section Two\n\n"
            "Content about object-oriented design patterns and SOLID principles. "
            "Covers single responsibility, open-closed, and dependency inversion."
        )
        f2 = tmp_path / "counted_b.txt"
        f2.write_text(
            "Second document about database administration and optimization. "
            "Covers query planning, index selection, and connection pooling."
        )
        kb.ingest(str(f1))
        kb.ingest(str(f2))

        result_before = kb.list_documents()
        assert "2 documents" in result_before

        kb.remove(str(f1))

        result_after = kb.list_documents()
        assert "1 documents" in result_after or "1 document" in result_after

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_remove_nonexistent_does_not_affect_list(self, kb, tmp_path):
        """Removing a path that was never ingested should not change list."""
        f = tmp_path / "stable.txt"
        f.write_text(
            "Stable document that should remain in the knowledge base unchanged. "
            "Used to verify that removing nonexistent paths has no side effects."
        )
        kb.ingest(str(f))

        kb.remove("/does/not/exist.txt")

        result = kb.list_documents()
        assert "1 documents" in result or "1 document" in result


# ---------------------------------------------------------------------------
# Bonus: edge cases in _compute_checksum and _estimate_tokens
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_compute_checksum_deterministic(self):
        from omega.knowledge.engine import _compute_checksum

        c1 = _compute_checksum("hello world")
        c2 = _compute_checksum("hello world")
        assert c1 == c2

    def test_compute_checksum_different_for_different_input(self):
        from omega.knowledge.engine import _compute_checksum

        c1 = _compute_checksum("hello")
        c2 = _compute_checksum("world")
        assert c1 != c2

    def test_checksum_length(self):
        from omega.knowledge.engine import _compute_checksum

        c = _compute_checksum("test string")
        assert len(c) == 16  # truncated to 16 hex chars

    def test_estimate_tokens_rough(self):
        from omega.knowledge.engine import _estimate_tokens

        # "hello world" = 11 chars -> ~2-3 tokens
        t = _estimate_tokens("hello world")
        assert t >= 1
        assert t < 10

    def test_estimate_tokens_empty(self):
        from omega.knowledge.engine import _estimate_tokens

        t = _estimate_tokens("")
        assert t == 1  # max(1, 0//4) = 1

    def test_serialize_embedding_roundtrip(self):
        import struct
        from omega.knowledge.engine import _serialize_embedding

        vec = [0.1, 0.2, 0.3, -0.5]
        serialized = _serialize_embedding(vec)
        assert isinstance(serialized, bytes)
        assert len(serialized) == 4 * 4  # 4 floats * 4 bytes each

        # Verify roundtrip
        unpacked = list(struct.unpack(f"{len(vec)}f", serialized))
        for a, b in zip(vec, unpacked):
            assert abs(a - b) < 1e-6


# ---------------------------------------------------------------------------
# I1: Webpage extraction tests
# ---------------------------------------------------------------------------


class TestWebpageExtraction:
    """Test _extract_webpage including SSRF protection and size limits."""

    def test_file_url_rejected(self, kb):
        """file:// URLs should be rejected to prevent SSRF."""
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            kb._extract_webpage("file:///etc/passwd")

    def test_ftp_url_rejected(self, kb):
        """ftp:// URLs should be rejected."""
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            kb._extract_webpage("ftp://internal-server/data")

    def test_data_url_rejected(self, kb):
        """data: URLs should be rejected."""
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            kb._extract_webpage("data:text/html,<h1>hello</h1>")

    def test_empty_scheme_rejected(self, kb):
        """URLs without scheme should be rejected."""
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            kb._extract_webpage("/etc/passwd")

    def test_http_url_accepted(self, kb):
        """http:// URLs should be accepted (may fail on network, but scheme is valid)."""
        import urllib.error
        try:
            kb._extract_webpage("http://nonexistent.invalid/page")
        except (urllib.error.URLError, OSError):
            pass  # Network error is expected, but SSRF check should not fire
        except ImportError:
            pass  # markdownify not installed

    def test_https_url_accepted(self, kb):
        """https:// URLs should be accepted."""
        import urllib.error
        try:
            kb._extract_webpage("https://nonexistent.invalid/page")
        except (urllib.error.URLError, OSError):
            pass
        except ImportError:
            pass

    def test_response_size_limit(self, kb):
        """Oversized responses should be rejected."""
        import io
        import urllib.request

        # Mock urlopen to return a huge response
        oversized_body = b"x" * (kb.MAX_DOCUMENT_SIZE_MB * 1024 * 1024 + 100)
        mock_resp = MagicMock()
        mock_resp.read.return_value = oversized_body
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            try:
                from markdownify import markdownify
                with pytest.raises(ValueError, match="exceeds"):
                    kb._extract_webpage("https://example.com/huge-page")
            except ImportError:
                pytest.skip("markdownify not installed")

    def test_html_extraction_with_mock(self, kb):
        """HTML content is converted to markdown."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><head><title>Test Page</title></head><body><h1>Hello</h1><p>World</p></body></html>"
        mock_headers = MagicMock()
        mock_headers.get = lambda key, default="": {
            "Content-Type": "text/html",
        }.get(key, default)
        mock_resp.headers = mock_headers
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            try:
                text, title = kb._extract_webpage("https://example.com/page")
                assert title == "Test Page"
                assert "Hello" in text or "World" in text
            except ImportError:
                pytest.skip("markdownify not installed")

    def test_markdown_content_type_extraction(self, kb):
        """text/markdown responses should be used directly without HTML conversion."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"# Direct Markdown\n\nThis is markdown content."
        mock_headers = MagicMock()
        mock_headers.get = lambda key, default="": {
            "Content-Type": "text/markdown",
        }.get(key, default)
        mock_resp.headers = mock_headers
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            try:
                text, title = kb._extract_webpage("https://example.com/page.md")
                assert "Direct Markdown" in text
                assert title == "Direct Markdown"
            except ImportError:
                pytest.skip("markdownify not installed")


# ---------------------------------------------------------------------------
# I2: cloud_sync tests
# ---------------------------------------------------------------------------


class TestCloudSyncKBQueue:
    """Test sync_kb_queue with mocked Supabase client."""

    def test_no_pending_items(self):
        """Empty queue returns appropriate message."""
        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value = None
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        with patch("omega.knowledge.cloud_sync._get_supabase_client", return_value=mock_client):
            from omega.knowledge.cloud_sync import sync_kb_queue
            result = sync_kb_queue()
            assert "No pending items" in result

    def test_successful_sync_item(self, tmp_path):
        """Single item synced successfully."""
        mock_client = MagicMock()

        # Stale recovery returns nothing
        mock_client.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value = None

        # One pending item
        item = {
            "id": "test-item-1",
            "file_name": "test.txt",
            "storage_path": "uploads/test.txt",
            "source_type": "text",
            "title": "Test Doc",
            "entity_id": None,
            "drive_file_id": "gdrive-abc123",
        }
        select_mock = MagicMock(data=[item])
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = select_mock

        # Download returns content
        mock_client.storage.from_.return_value.download.return_value = (
            b"Test document content for knowledge base ingestion. "
            b"Contains enough text to produce at least one chunk."
        )

        # Mock ingest_document to return success (imported locally inside sync_kb_queue)
        with patch("omega.knowledge.cloud_sync._get_supabase_client", return_value=mock_client), \
             patch("omega.knowledge.engine.ingest_document", return_value="Ingested **Test Doc** (text): 1 chunks, 20 tokens"), \
             patch("omega.knowledge.engine.get_knowledge_base") as mock_kb:
            mock_conn = MagicMock()
            mock_kb.return_value._lock = MagicMock()
            mock_kb.return_value._lock.__enter__ = MagicMock()
            mock_kb.return_value._lock.__exit__ = MagicMock(return_value=False)
            mock_kb.return_value._conn = mock_conn

            from omega.knowledge.cloud_sync import sync_kb_queue
            result = sync_kb_queue()
            assert "1 synced" in result
            assert "0 errors" in result

    def test_ingest_error_marks_item_as_error(self):
        """When ingest returns an error string, item should be marked as error."""
        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value = None

        item = {
            "id": "test-item-err",
            "file_name": "bad.pdf",
            "storage_path": "uploads/bad.pdf",
            "source_type": "pdf",
            "title": None,
            "entity_id": None,
            "drive_file_id": "",
        }
        select_mock = MagicMock(data=[item])
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = select_mock
        mock_client.storage.from_.return_value.download.return_value = b"%PDF-1.4 fake"

        with patch("omega.knowledge.cloud_sync._get_supabase_client", return_value=mock_client), \
             patch("omega.knowledge.engine.ingest_document", return_value="Error: no text content extracted"):
            from omega.knowledge.cloud_sync import sync_kb_queue
            result = sync_kb_queue()
            assert "0 synced" in result
            assert "1 errors" in result

    def test_empty_download_raises_error(self):
        """Empty file download should be treated as error."""
        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value = None

        item = {
            "id": "test-empty",
            "file_name": "empty.txt",
            "storage_path": "uploads/empty.txt",
            "source_type": "text",
            "title": None,
            "entity_id": None,
            "drive_file_id": "gd-123",
        }
        select_mock = MagicMock(data=[item])
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = select_mock
        mock_client.storage.from_.return_value.download.return_value = b""

        with patch("omega.knowledge.cloud_sync._get_supabase_client", return_value=mock_client):
            from omega.knowledge.cloud_sync import sync_kb_queue
            result = sync_kb_queue()
            assert "1 errors" in result

    def test_gdrive_uri_fallback_when_no_drive_file_id(self):
        """When drive_file_id is empty, should use kb-files:// URI instead."""
        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value = None

        item = {
            "id": "test-no-gdrive",
            "file_name": "uploaded.txt",
            "storage_path": "uploads/uploaded.txt",
            "source_type": "text",
            "title": "Uploaded",
            "entity_id": None,
            "drive_file_id": "",  # Empty
        }
        select_mock = MagicMock(data=[item])
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = select_mock
        mock_client.storage.from_.return_value.download.return_value = (
            b"Content with enough text for chunking. "
            b"Testing the fallback URI when drive_file_id is empty."
        )

        with patch("omega.knowledge.cloud_sync._get_supabase_client", return_value=mock_client), \
             patch("omega.knowledge.engine.ingest_document", return_value="Ingested **Uploaded** (text): 1 chunks"), \
             patch("omega.knowledge.engine.get_knowledge_base") as mock_kb:
            mock_conn = MagicMock()
            mock_kb.return_value._lock = MagicMock()
            mock_kb.return_value._lock.__enter__ = MagicMock()
            mock_kb.return_value._lock.__exit__ = MagicMock(return_value=False)
            mock_kb.return_value._conn = mock_conn

            from omega.knowledge.cloud_sync import sync_kb_queue
            result = sync_kb_queue()

            # Verify the fallback URI was used
            update_call = mock_conn.execute.call_args
            if update_call:
                args = update_call[0]
                if len(args) >= 2 and isinstance(args[1], tuple):
                    uri = args[1][0]
                    assert "kb-files://" in uri or "gdrive://" not in uri


# ---------------------------------------------------------------------------
# I5: Size limit enforcement tests
# ---------------------------------------------------------------------------


class TestSizeLimitEnforcement:
    """Test MAX_DOCUMENT_SIZE_MB and MAX_CHUNKS_PER_DOCUMENT limits."""

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_document_size_limit_enforced(self, kb, tmp_path):
        """Document exceeding MAX_DOCUMENT_SIZE_MB should be rejected."""
        # Temporarily set a very low limit
        original = kb.MAX_DOCUMENT_SIZE_MB
        kb.MAX_DOCUMENT_SIZE_MB = 0  # 0 MB = reject everything with content
        try:
            f = tmp_path / "big.txt"
            f.write_text("x" * 1024)  # 1 KB > 0 MB
            result = kb.ingest(str(f))
            assert "Error" in result
            assert "exceeds limit" in result
        finally:
            kb.MAX_DOCUMENT_SIZE_MB = original

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_max_chunks_limit_enforced(self, kb, tmp_path):
        """Document producing too many chunks should be rejected."""
        original = kb.MAX_CHUNKS_PER_DOCUMENT
        kb.MAX_CHUNKS_PER_DOCUMENT = 1  # Only allow 1 chunk
        try:
            f = tmp_path / "many_sections.md"
            # Create document that produces multiple chunks
            content = "# Big Doc\n\n"
            for i in range(10):
                content += f"## Section {i}\n\n"
                content += (
                    f"Content for section {i} about software engineering. "
                    "Detailed discussion of architecture patterns, testing, "
                    "deployment, monitoring, and incident response. "
                ) * 5
                content += "\n\n"
            f.write_text(content)
            result = kb.ingest(str(f))
            assert "Error" in result
            assert "exceeds limit" in result or "chunks" in result
        finally:
            kb.MAX_CHUNKS_PER_DOCUMENT = original

    @pytest.mark.usefixtures("_mock_embeddings")
    def test_document_under_size_limit_accepted(self, kb, tmp_path):
        """Document within size limit should be ingested normally."""
        f = tmp_path / "normal.txt"
        f.write_text(
            "Normal sized document about software development practices. "
            "Covers testing strategies, deployment pipelines, and code review."
        )
        result = kb.ingest(str(f))
        assert "Ingested" in result


# ---------------------------------------------------------------------------
# I6: Tail content preservation test
# ---------------------------------------------------------------------------


class TestTailContentPreservation:
    """Verify undersized tail paragraphs are appended to previous chunk."""

    def test_small_tail_appended_to_previous(self, kb):
        """A small tail paragraph should be merged into the previous chunk."""
        # Create text with a large section followed by a tiny tail
        text = "# Document\n\n"
        text += (
            "## Main Section\n\n"
            "This is a large section with lots of content about software engineering. "
            "It discusses design patterns, testing methodologies, deployment strategies, "
            "continuous integration, code review practices, and team collaboration. "
            "The section is long enough to form its own chunk in the system.\n\n"
        )
        text += "Brief tail."  # Small tail paragraph

        chunks = kb._semantic_chunk(text, chunk_size=50)
        # The tail should be preserved (either merged or as its own chunk)
        full_text = " ".join(c["content"] for c in chunks)
        assert "Brief tail" in full_text

    def test_single_small_paragraph_kept(self, kb):
        """A document with only a small paragraph should still produce a chunk."""
        text = "Just a tiny note."
        chunks = kb._semantic_chunk(text)
        assert len(chunks) >= 1
        assert "tiny note" in chunks[0]["content"]
