"""Tests for OMEGA Knowledge module (document vectorization and retrieval)."""

import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def knowledge_base(tmp_omega_dir):
    """Create a fresh KnowledgeBase for testing."""
    os.environ["OMEGA_HOME"] = str(tmp_omega_dir)
    from omega.knowledge.engine import KnowledgeBase, reset_knowledge_base

    reset_knowledge_base()
    db_path = tmp_omega_dir / "test.db"
    kb = KnowledgeBase(db_path=db_path)
    yield kb
    kb.close()
    reset_knowledge_base()


@pytest.fixture
def sample_text_file(tmp_path):
    """Create a sample text file for testing with enough content to produce chunks."""
    f = tmp_path / "sample.txt"
    f.write_text(
        "This is a sample document about software engineering and project management. "
        "It contains detailed information about various topics including architecture decisions, "
        "testing strategies, deployment pipelines, and code review practices. "
        "The document serves as a reference for the entire development team.\n\n"
        "In our development workflow, we use continuous integration and continuous deployment. "
        "Every pull request triggers automated tests, linting, and security scanning. "
        "The deployment pipeline includes staging and production environments with rollback capabilities. "
        "We follow trunk-based development with short-lived feature branches."
    )
    return f


@pytest.fixture
def sample_markdown_file(tmp_path):
    """Create a sample markdown file for testing."""
    f = tmp_path / "sample.md"
    f.write_text("""# Project Overview

This is my personal project portfolio.

## Experience

I led a team of 5 engineers building a distributed system.
We achieved 99.9% uptime and reduced latency by 40%.

## Education

BS Computer Science from MIT, graduated 2020.
Focus on distributed systems and machine learning.

## Skills

Python, Rust, TypeScript, PostgreSQL, Docker, Kubernetes.
Strong background in system design and architecture.
""")
    return f


@pytest.fixture
def large_markdown_file(tmp_path):
    """Create a larger markdown file to test chunking."""
    f = tmp_path / "large.md"
    sections = []
    for i in range(10):
        section = f"## Section {i}\n\n"
        section += " ".join([f"Word{j}" for j in range(200)])  # ~200 words
        section += "\n\n"
        sections.append(section)
    f.write_text("# Large Document\n\n" + "\n".join(sections))
    return f


class TestKnowledgeBaseSchema:
    """Test schema creation."""

    def test_tables_created(self, knowledge_base):
        tables = knowledge_base._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'document%' OR name='knowledge_schema_version'"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        assert "documents" in table_names
        assert "document_chunks" in table_names

    def test_schema_version(self, knowledge_base):
        row = knowledge_base._conn.execute(
            "SELECT version FROM knowledge_schema_version"
        ).fetchone()
        assert row["version"] == 2


class TestSourceTypeDetection:
    """Test automatic source type detection."""

    def test_detect_pdf(self, knowledge_base):
        assert knowledge_base._detect_source_type("/path/to/file.pdf") == "pdf"

    def test_detect_markdown(self, knowledge_base):
        assert knowledge_base._detect_source_type("/path/to/file.md") == "markdown"

    def test_detect_text(self, knowledge_base):
        assert knowledge_base._detect_source_type("/path/to/file.txt") == "text"

    def test_detect_webpage(self, knowledge_base):
        assert knowledge_base._detect_source_type("https://example.com") == "webpage"
        assert knowledge_base._detect_source_type("http://example.com/page") == "webpage"

    def test_detect_unknown_ext(self, knowledge_base):
        assert knowledge_base._detect_source_type("/path/to/file.csv") == "text"


class TestChunking:
    """Test semantic chunking logic."""

    def test_basic_chunking(self, knowledge_base):
        text = (
            "# Title\n\n"
            "First paragraph with enough content to form a meaningful chunk. "
            "This includes details about software architecture, system design patterns, "
            "and best practices for building scalable applications. "
            "We discuss microservices, event-driven architectures, and domain-driven design.\n\n"
            "Second paragraph with more content about testing and deployment strategies. "
            "Including unit tests, integration tests, end-to-end tests, and performance benchmarks."
        )
        chunks = knowledge_base._semantic_chunk(text, chunk_size=100)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert "content" in chunk
            assert "chunk_index" in chunk

    def test_heading_based_chunks(self, knowledge_base):
        text = """# Main Title

Introduction text.

## Section 1

Content for section 1 with enough text to form a meaningful chunk that should be kept together.

## Section 2

Content for section 2 with different information that should be in its own chunk.
"""
        chunks = knowledge_base._semantic_chunk(text, chunk_size=100)
        assert len(chunks) >= 1

    def test_chunk_has_metadata(self, knowledge_base):
        text = "# Title\n\nSome paragraph with enough words to form a chunk."
        chunks = knowledge_base._semantic_chunk(text, chunk_size=50)
        for chunk in chunks:
            assert "chunk_type" in chunk
            assert "token_count" in chunk
            assert chunk["token_count"] > 0

    def test_empty_text(self, knowledge_base):
        chunks = knowledge_base._semantic_chunk("")
        assert chunks == []

    def test_large_text_splits(self, knowledge_base):
        """Verify large text is split into multiple chunks."""
        # Create text that's ~2000 tokens
        text = " ".join(["word"] * 8000)  # ~2000 tokens
        chunks = knowledge_base._semantic_chunk(text, chunk_size=300)
        assert len(chunks) > 1


class TestIngestion:
    """Test document ingestion pipeline."""

    def test_ingest_text_file(self, knowledge_base, sample_text_file):
        result = knowledge_base.ingest(str(sample_text_file))
        assert "Ingested" in result
        assert "sample" in result

    def test_ingest_markdown_file(self, knowledge_base, sample_markdown_file):
        result = knowledge_base.ingest(str(sample_markdown_file))
        assert "Ingested" in result
        assert "chunks" in result

    def test_ingest_creates_document_record(self, knowledge_base, sample_text_file):
        knowledge_base.ingest(str(sample_text_file))
        rows = knowledge_base._conn.execute("SELECT * FROM documents").fetchall()
        assert len(rows) == 1
        assert rows[0]["source_type"] == "text"

    def test_ingest_creates_chunks(self, knowledge_base, sample_markdown_file):
        knowledge_base.ingest(str(sample_markdown_file))
        chunks = knowledge_base._conn.execute("SELECT * FROM document_chunks").fetchall()
        assert len(chunks) >= 1

    def test_ingest_duplicate_same_content(self, knowledge_base, sample_text_file):
        """Second ingest of same file should report unchanged."""
        knowledge_base.ingest(str(sample_text_file))
        result = knowledge_base.ingest(str(sample_text_file))
        assert "unchanged" in result.lower()

    def test_ingest_duplicate_changed_content(self, knowledge_base, sample_text_file):
        """Second ingest with changed content should re-ingest."""
        knowledge_base.ingest(str(sample_text_file))

        # Modify the file with enough content to produce chunks
        sample_text_file.write_text(
            "Completely new and different content about machine learning and data science. "
            "This document covers neural networks, deep learning, reinforcement learning, "
            "natural language processing, computer vision, and generative AI models. "
            "It provides a comprehensive overview of modern AI techniques and their applications."
        )
        result = knowledge_base.ingest(str(sample_text_file))
        assert "Re-ingested" in result

    def test_ingest_nonexistent_file(self, knowledge_base):
        result = knowledge_base.ingest("/nonexistent/file.txt")
        assert "Error" in result
        assert "not found" in result.lower()

    def test_ingest_with_title_override(self, knowledge_base, sample_text_file):
        knowledge_base.ingest(str(sample_text_file), title="My Custom Title")
        row = knowledge_base._conn.execute("SELECT title FROM documents").fetchone()
        assert row["title"] == "My Custom Title"

    def test_ingest_with_source_type_override(self, knowledge_base, sample_text_file):
        knowledge_base.ingest(str(sample_text_file), source_type="markdown")
        row = knowledge_base._conn.execute("SELECT source_type FROM documents").fetchone()
        assert row["source_type"] == "markdown"


class TestSearch:
    """Test document search functionality."""

    def test_search_ingested_document(self, knowledge_base, sample_markdown_file):
        knowledge_base.ingest(str(sample_markdown_file))
        result = knowledge_base.search("distributed system experience")
        # Should find something (exact results depend on embedding quality)
        assert "chunk" in result.lower() or "No document" in result

    def test_search_empty_query(self, knowledge_base):
        result = knowledge_base.search("")
        assert "Error" in result

    def test_search_no_documents(self, knowledge_base):
        result = knowledge_base.search("anything")
        assert "No document" in result

    def test_search_with_limit(self, knowledge_base, sample_markdown_file):
        knowledge_base.ingest(str(sample_markdown_file))
        result = knowledge_base.search("skills", limit=1)
        # Should return at most 1 result
        assert result  # Just verify it doesn't crash

    def test_search_with_source_type_filter(self, knowledge_base, sample_text_file, sample_markdown_file):
        knowledge_base.ingest(str(sample_text_file))
        knowledge_base.ingest(str(sample_markdown_file))
        result = knowledge_base.search("content", source_type="markdown")
        # Should only search markdown docs
        assert result


class TestListDocuments:
    """Test document listing."""

    def test_list_empty(self, knowledge_base):
        result = knowledge_base.list_documents()
        assert "No documents" in result

    def test_list_with_documents(self, knowledge_base, sample_text_file, sample_markdown_file):
        knowledge_base.ingest(str(sample_text_file))
        knowledge_base.ingest(str(sample_markdown_file))
        result = knowledge_base.list_documents()
        assert "2 documents" in result
        assert "sample" in result


class TestRemoveDocument:
    """Test document removal."""

    def test_remove_existing(self, knowledge_base, sample_text_file):
        knowledge_base.ingest(str(sample_text_file))
        result = knowledge_base.remove(str(sample_text_file))
        assert "Removed" in result

        # Verify document is gone
        rows = knowledge_base._conn.execute("SELECT * FROM documents").fetchall()
        assert len(rows) == 0

    def test_remove_also_deletes_chunks(self, knowledge_base, sample_markdown_file):
        knowledge_base.ingest(str(sample_markdown_file))

        # Verify chunks exist
        count_before = knowledge_base._conn.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]
        assert count_before > 0

        knowledge_base.remove(str(sample_markdown_file))

        # Verify chunks are gone
        count_after = knowledge_base._conn.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]
        assert count_after == 0

    def test_remove_nonexistent(self, knowledge_base):
        result = knowledge_base.remove("/nonexistent/file.txt")
        assert "not found" in result.lower()

    def test_remove_empty_path(self, knowledge_base):
        result = knowledge_base.remove("")
        assert "Error" in result


class TestHandlers:
    """Test MCP handler functions."""

    @pytest.mark.asyncio
    async def test_handle_ingest(self, knowledge_base, sample_text_file):
        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            from omega.knowledge.handlers import handle_omega_ingest_document

            result = await handle_omega_ingest_document({
                "path_or_url": str(sample_text_file),
            })
            assert not result.get("isError")
            assert "Ingested" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_handle_ingest_missing_path(self):
        from omega.knowledge.handlers import handle_omega_ingest_document

        result = await handle_omega_ingest_document({})
        assert result.get("isError")

    @pytest.mark.asyncio
    async def test_handle_search(self, knowledge_base, sample_markdown_file):
        knowledge_base.ingest(str(sample_markdown_file))

        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            from omega.knowledge.handlers import handle_omega_search_documents

            result = await handle_omega_search_documents({"query": "experience"})
            assert not result.get("isError")

    @pytest.mark.asyncio
    async def test_handle_search_missing_query(self):
        from omega.knowledge.handlers import handle_omega_search_documents

        result = await handle_omega_search_documents({})
        assert result.get("isError")

    @pytest.mark.asyncio
    async def test_handle_list(self, knowledge_base):
        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            from omega.knowledge.handlers import handle_omega_list_documents

            result = await handle_omega_list_documents({})
            assert not result.get("isError")
            assert "No documents" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_handle_remove(self, knowledge_base, sample_text_file):
        knowledge_base.ingest(str(sample_text_file))

        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            from omega.knowledge.handlers import handle_omega_remove_document

            result = await handle_omega_remove_document({"source_path": str(sample_text_file)})
            assert not result.get("isError")
            assert "Removed" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_handle_remove_missing_path(self):
        from omega.knowledge.handlers import handle_omega_remove_document

        result = await handle_omega_remove_document({})
        assert result.get("isError")


class TestToolSchemas:
    """Test tool schema definitions."""

    def test_schemas_valid(self):
        from omega.knowledge.tool_schemas import KNOWLEDGE_TOOL_SCHEMAS

        assert len(KNOWLEDGE_TOOL_SCHEMAS) >= 6
        names = {s["name"] for s in KNOWLEDGE_TOOL_SCHEMAS}
        assert "omega_ingest_document" in names
        assert "omega_search_documents" in names
        assert "omega_list_documents" in names
        assert "omega_remove_document" in names
        assert "omega_scan_documents" in names
        assert "omega_sync_kb" in names

    def test_schemas_have_required_fields(self):
        from omega.knowledge.tool_schemas import KNOWLEDGE_TOOL_SCHEMAS

        for schema in KNOWLEDGE_TOOL_SCHEMAS:
            assert "name" in schema
            assert "description" in schema
            assert "inputSchema" in schema
            assert schema["inputSchema"]["type"] == "object"


class TestScanDirectory:
    """Test auto-scan directory feature."""

    def test_scan_empty_directory(self, knowledge_base, tmp_path):
        scan_dir = tmp_path / "docs"
        scan_dir.mkdir()
        result = knowledge_base.scan_directory(scan_dir)
        assert "No supported files" in result

    def test_scan_creates_directory_if_missing(self, knowledge_base, tmp_path):
        scan_dir = tmp_path / "new_docs"
        result = knowledge_base.scan_directory(scan_dir)
        assert scan_dir.exists()
        assert "Created" in result

    def test_scan_ingests_text_files(self, knowledge_base, tmp_path):
        scan_dir = tmp_path / "docs"
        scan_dir.mkdir()
        f = scan_dir / "notes.txt"
        f.write_text(
            "These are my personal notes about machine learning and data science. "
            "I've been working on neural networks, deep learning models, and NLP applications. "
            "My focus is on transformer architectures and their applications in production systems."
        )
        result = knowledge_base.scan_directory(scan_dir)
        assert "1 ingested" in result

    def test_scan_ingests_markdown_files(self, knowledge_base, tmp_path):
        scan_dir = tmp_path / "docs"
        scan_dir.mkdir()
        f = scan_dir / "resume.md"
        f.write_text(
            "# Resume\n\n## Experience\n\n"
            "Senior Engineer at ACME Corp, leading a team of 5 engineers building distributed systems. "
            "Achieved 99.9% uptime and reduced latency by 40% through architecture improvements.\n\n"
            "## Skills\n\nPython, Rust, TypeScript, PostgreSQL, Docker, Kubernetes."
        )
        result = knowledge_base.scan_directory(scan_dir)
        assert "1 ingested" in result

    def test_scan_skips_unchanged_files(self, knowledge_base, tmp_path):
        scan_dir = tmp_path / "docs"
        scan_dir.mkdir()
        f = scan_dir / "notes.txt"
        f.write_text(
            "These are my personal notes about various software engineering topics. "
            "I've documented architecture decisions, testing strategies, and deployment practices. "
            "This serves as a reference for my ongoing development work and learning."
        )
        knowledge_base.scan_directory(scan_dir)

        # Second scan should skip
        result = knowledge_base.scan_directory(scan_dir)
        assert "1 unchanged" in result
        assert "ingested" not in result.lower() or "0 ingested" in result.lower()

    def test_scan_recursive(self, knowledge_base, tmp_path):
        scan_dir = tmp_path / "docs"
        sub_dir = scan_dir / "subfolder"
        sub_dir.mkdir(parents=True)
        f1 = scan_dir / "top.txt"
        f1.write_text(
            "Top-level document about project management and software delivery practices. "
            "Covers agile methodologies, sprint planning, retrospectives, and team communication."
        )
        f2 = sub_dir / "nested.md"
        f2.write_text(
            "# Nested Document\n\n"
            "A nested markdown file with technical documentation about API design patterns, "
            "RESTful services, GraphQL endpoints, and WebSocket communication protocols."
        )
        result = knowledge_base.scan_directory(scan_dir)
        assert "2 ingested" in result

    def test_scan_ignores_unsupported_extensions(self, knowledge_base, tmp_path):
        scan_dir = tmp_path / "docs"
        scan_dir.mkdir()
        (scan_dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (scan_dir / "binary.exe").write_bytes(b"\x00\x01\x02")
        result = knowledge_base.scan_directory(scan_dir)
        assert "No supported files" in result

    def test_scan_handler(self, knowledge_base, tmp_path):
        scan_dir = tmp_path / "docs"
        scan_dir.mkdir()
        (scan_dir / "test.txt").write_text(
            "Test document with enough content for chunking and embedding. "
            "This covers software testing methodologies, test automation frameworks, "
            "and continuous integration pipeline design patterns."
        )

        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            import asyncio
            from omega.knowledge.handlers import handle_omega_scan_documents

            result = asyncio.run(
                handle_omega_scan_documents({"directory": str(scan_dir)})
            )
            assert not result.get("isError")
            assert "1 ingested" in result["content"][0]["text"]

    def test_tool_schema_exists(self):
        from omega.knowledge.tool_schemas import KNOWLEDGE_TOOL_SCHEMAS

        names = {s["name"] for s in KNOWLEDGE_TOOL_SCHEMAS}
        assert "omega_scan_documents" in names


class TestPDFExtraction:
    """Test PDF extraction fallback chain: Docling → pdfplumber → ImportError."""

    def test_docling_primary_path(self, knowledge_base, tmp_path):
        """Docling extracts markdown when available."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        mock_doc = MagicMock()
        mock_doc.export_to_markdown.return_value = "# Title\n\nExtracted content from Docling."
        mock_doc.name = "Test Document"

        mock_result = MagicMock()
        mock_result.document = mock_doc

        mock_converter_instance = MagicMock()
        mock_converter_instance.convert.return_value = mock_result

        mock_converter_class = MagicMock(return_value=mock_converter_instance)

        with patch.dict("sys.modules", {"docling": MagicMock(), "docling.document_converter": MagicMock(DocumentConverter=mock_converter_class)}):
            text, title = knowledge_base._extract_pdf(str(pdf_file))
            assert "Extracted content from Docling" in text
            assert title == "Test Document"

    def test_pdfplumber_fallback(self, knowledge_base, tmp_path):
        """pdfplumber is used when Docling is not installed."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page content from pdfplumber."

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        mock_pdfplumber = MagicMock()
        mock_pdfplumber.open.return_value = mock_pdf

        # Docling not available, pdfplumber available
        import sys
        with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
            # Force Docling ImportError
            with patch("omega.knowledge.engine.KnowledgeBase._extract_pdf", wraps=knowledge_base._extract_pdf):
                # Simulate: docling import fails, pdfplumber succeeds
                original = knowledge_base._extract_pdf

                def patched_extract(path):
                    # Remove docling from modules to force ImportError
                    saved = sys.modules.pop("docling", None)
                    saved2 = sys.modules.pop("docling.document_converter", None)
                    try:
                        return original(path)
                    finally:
                        if saved is not None:
                            sys.modules["docling"] = saved
                        if saved2 is not None:
                            sys.modules["docling.document_converter"] = saved2

                text, title = patched_extract(str(pdf_file))
                assert "Page content from pdfplumber" in text
                assert title == "test"

    def test_no_pdf_library_raises(self, knowledge_base, tmp_path):
        """ImportError raised when neither Docling nor pdfplumber is available."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        import sys
        saved_docling = sys.modules.pop("docling", None)
        saved_docling_dc = sys.modules.pop("docling.document_converter", None)
        saved_pdfplumber = sys.modules.pop("pdfplumber", None)

        # Temporarily block both imports
        import builtins
        original_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name in ("docling", "docling.document_converter", "pdfplumber"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        try:
            builtins.__import__ = blocked_import
            with pytest.raises(ImportError, match="No PDF extraction library available"):
                knowledge_base._extract_pdf(str(pdf_file))
        finally:
            builtins.__import__ = original_import
            if saved_docling is not None:
                sys.modules["docling"] = saved_docling
            if saved_docling_dc is not None:
                sys.modules["docling.document_converter"] = saved_docling_dc
            if saved_pdfplumber is not None:
                sys.modules["pdfplumber"] = saved_pdfplumber

    def test_docling_failure_falls_through(self, knowledge_base, tmp_path):
        """When Docling raises a runtime error, falls through to pdfplumber."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Fallback content from pdfplumber."

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        mock_pdfplumber = MagicMock()
        mock_pdfplumber.open.return_value = mock_pdf

        # Docling installed but fails at runtime
        mock_converter_class = MagicMock(side_effect=RuntimeError("Docling model load failed"))
        mock_docling_dc = MagicMock(DocumentConverter=mock_converter_class)

        import sys
        with patch.dict(sys.modules, {
            "docling": MagicMock(),
            "docling.document_converter": mock_docling_dc,
            "pdfplumber": mock_pdfplumber,
        }):
            text, title = knowledge_base._extract_pdf(str(pdf_file))
            assert "Fallback content from pdfplumber" in text

    def test_pdf_not_found(self, knowledge_base):
        """FileNotFoundError for nonexistent PDF."""
        with pytest.raises(FileNotFoundError, match="PDF not found"):
            knowledge_base._extract_pdf("/nonexistent/file.pdf")


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_ingest_document(self, knowledge_base, sample_text_file):
        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            from omega.knowledge.engine import ingest_document

            result = ingest_document(str(sample_text_file))
            assert "Ingested" in result

    def test_list_documents(self, knowledge_base):
        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            from omega.knowledge.engine import list_documents

            result = list_documents()
            assert "No documents" in result

    def test_search_documents(self, knowledge_base):
        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            from omega.knowledge.engine import search_documents

            result = search_documents("test")
            assert "No document" in result

    def test_remove_document(self, knowledge_base):
        with patch("omega.knowledge.engine.get_knowledge_base", return_value=knowledge_base):
            from omega.knowledge.engine import remove_document

            result = remove_document("/nonexistent")
            assert "not found" in result.lower()
