"""Tests for omega.cloud.sync — push, pull, auto-sync on session stop, auto-pull on start."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_supabase_table(data=None):
    """Return a mock table builder that chains .select/.eq/.order/.range/.execute."""
    mock = MagicMock()
    response = MagicMock()
    response.data = data or []
    # Every chained method returns the same mock, execute returns the response
    for method in ("select", "eq", "order", "range", "upsert", "insert"):
        getattr(mock, method).return_value = mock
    mock.execute.return_value = response
    return mock


def _mock_client(table_map=None):
    """Return a mock Supabase client with per-table mock builders."""
    client = MagicMock()
    table_map = table_map or {}

    def table_fn(name):
        if name in table_map:
            return table_map[name]
        return _mock_supabase_table()

    client.table.side_effect = table_fn
    return client


# ============================================================================
# TestCloudSyncPull
# ============================================================================

class TestCloudSyncPull:
    """Tests for pull_memories, pull_documents, pull_all."""

    def test_pull_memories_skips_existing(self, tmp_path):
        """Pull should skip memories whose content_hash already exists locally."""
        from omega.cloud.sync import CloudSync

        # Set up a local DB with one existing memory
        import hashlib
        import sqlite3

        db_path = tmp_path / "omega.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                last_accessed TEXT,
                access_count INTEGER DEFAULT 0,
                ttl_seconds INTEGER,
                session_id TEXT,
                event_type TEXT,
                project TEXT,
                content_hash TEXT,
                priority INTEGER DEFAULT 3,
                referenced_date TEXT,
                entity_id TEXT
            )
        """)
        existing_content = "I already exist"
        existing_hash = hashlib.sha256(existing_content.encode()).hexdigest()
        conn.execute(
            "INSERT INTO memories (node_id, content, content_hash, created_at) VALUES (?, ?, ?, ?)",
            ("mem-existing123", existing_content, existing_hash, "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        # Cloud returns two memories: one matching existing hash, one new
        cloud_memories = [
            {
                "content": existing_content,  # same content → same hash → skip
                "event_type": "lesson_learned",
                "session_id": "s1",
                "project": "/test",
                "tags": [],
                "metadata": None,
                "created_at": "2026-01-01T00:00:00Z",
                "priority": 3,
            },
            {
                "content": "I am new from cloud",
                "event_type": "decision",
                "session_id": "s2",
                "project": "/test",
                "tags": ["cloud"],
                "metadata": {"source": "mobile"},
                "created_at": "2026-01-02T00:00:00Z",
                "priority": 4,
            },
        ]

        memories_table = _mock_supabase_table(cloud_memories)
        client = _mock_client({"memories": memories_table})

        sync = CloudSync(local_db_path=db_path)
        with patch.object(sync, "_get_client", return_value=client):
            result = sync.pull_memories()

        assert result["pulled"] == 1
        assert result["skipped"] == 1
        assert result["status"] == "ok"

        # Verify the new memory was inserted
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT content FROM memories ORDER BY id").fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[1][0] == "I am new from cloud"

    def test_pull_memories_empty_cloud(self, tmp_path):
        """Pull with no cloud data returns zero pulled."""
        from omega.cloud.sync import CloudSync
        import sqlite3

        db_path = tmp_path / "omega.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                last_accessed TEXT,
                access_count INTEGER DEFAULT 0,
                ttl_seconds INTEGER,
                session_id TEXT,
                event_type TEXT,
                project TEXT,
                content_hash TEXT,
                priority INTEGER DEFAULT 3,
                referenced_date TEXT,
                entity_id TEXT
            )
        """)
        conn.commit()
        conn.close()

        client = _mock_client()
        sync = CloudSync(local_db_path=db_path)
        with patch.object(sync, "_get_client", return_value=client):
            result = sync.pull_memories()

        assert result["pulled"] == 0
        assert result["skipped"] == 0

    def test_pull_all_excludes_profile(self, tmp_path):
        """pull_all should exclude profile (sensitive)."""
        from omega.cloud.sync import CloudSync

        sync = CloudSync(local_db_path=tmp_path / "omega.db")
        with patch.object(sync, "pull_memories", return_value={"pulled": 5, "skipped": 1, "status": "ok"}), \
             patch.object(sync, "pull_documents", return_value={"pulled": 2, "skipped": 0, "chunks": 10, "status": "ok"}):
            result = sync.pull_all()

        assert result["profile"]["status"] == "excluded"
        assert result["profile"]["reason"] == "sensitive"
        assert result["memories"]["pulled"] == 5
        assert result["documents"]["pulled"] == 2

    def test_pull_all_fail_open(self, tmp_path):
        """pull_all should not raise even if individual pulls fail."""
        from omega.cloud.sync import CloudSync

        sync = CloudSync(local_db_path=tmp_path / "omega.db")
        with patch.object(sync, "pull_memories", side_effect=RuntimeError("connection lost")), \
             patch.object(sync, "pull_documents", return_value={"pulled": 0, "skipped": 0, "chunks": 0, "status": "ok"}):
            result = sync.pull_all()

        assert result["memories"]["status"] == "error"
        assert "connection lost" in result["memories"]["error"]
        assert result["documents"]["status"] == "ok"

    def test_pull_documents_skips_existing(self, tmp_path):
        """Pull should skip documents whose source_path already exists locally."""
        from omega.cloud.sync import CloudSync
        import sqlite3

        db_path = tmp_path / "omega.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE documents (
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
        conn.execute("""
            CREATE TABLE document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                chunk_type TEXT,
                page_number INTEGER,
                token_count INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO documents (source_path, source_type, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("/existing/doc.pdf", "pdf", "Existing", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        cloud_docs = [
            {
                "id": "uuid-existing",
                "source_path": "/existing/doc.pdf",  # already exists → skip
                "source_type": "pdf",
                "title": "Existing",
                "checksum": "abc",
                "chunk_count": 5,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "uuid-new",
                "source_path": "/new/doc.md",
                "source_type": "markdown",
                "title": "New Doc",
                "checksum": "def",
                "chunk_count": 2,
                "created_at": "2026-01-02T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
            },
        ]

        docs_table = _mock_supabase_table(cloud_docs)
        chunks_table = _mock_supabase_table([
            {"chunk_index": 0, "content": "chunk 0", "chunk_type": "text", "page_number": None, "token_count": 10, "created_at": "2026-01-02T00:00:00Z"},
            {"chunk_index": 1, "content": "chunk 1", "chunk_type": "text", "page_number": None, "token_count": 12, "created_at": "2026-01-02T00:00:00Z"},
        ])
        client = _mock_client({"documents": docs_table, "document_chunks": chunks_table})

        sync = CloudSync(local_db_path=db_path)
        with patch.object(sync, "_get_client", return_value=client):
            result = sync.pull_documents()

        assert result["pulled"] == 1
        assert result["skipped"] == 1
        assert result["chunks"] == 2
        assert result["status"] == "ok"


# ============================================================================
# TestAutoCloudSync
# ============================================================================

class TestAutoCloudSync:
    """Tests for _auto_cloud_sync in hook_server."""

    def test_fires_on_session_stop(self, tmp_path):
        """Auto cloud sync should be called during session stop."""
        from omega.server.hook_server import _auto_cloud_sync

        fake_omega = tmp_path / ".omega"
        fake_omega.mkdir()
        (fake_omega / "secrets.json").write_text("{}")

        with patch("omega.server.hook_server.utils._omega_dir", return_value=fake_omega):
            with patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                _auto_cloud_sync("test-session-123")
                mock_thread.assert_called_once()
                mock_thread.return_value.start.assert_called_once()

    def test_skips_when_no_secrets(self, tmp_path):
        """Auto cloud sync should skip when secrets.json doesn't exist."""
        from omega.server.hook_server import _auto_cloud_sync

        fake_omega = tmp_path / ".omega"
        fake_omega.mkdir()
        # No secrets.json

        with patch("omega.server.hook_server.utils._omega_dir", return_value=fake_omega):
            with patch("threading.Thread") as mock_thread:
                _auto_cloud_sync("test-session-456")
                mock_thread.assert_not_called()

    def test_fail_open_on_error(self):
        """Auto cloud sync should never propagate exceptions."""
        from omega.server.hook_server import _auto_cloud_sync

        with patch("omega.server.hook_server.utils._omega_dir", side_effect=RuntimeError("kaboom")):
            # Should not raise
            _auto_cloud_sync("test-session-789")


# ============================================================================
# TestCloudSyncPush
# ============================================================================

class TestCloudSyncPush:
    """Tests for existing push (sync_all) behavior."""

    def test_sync_all_excludes_profile(self, tmp_path):
        """sync_all should exclude profile (sensitive)."""
        from omega.cloud.sync import CloudSync

        sync = CloudSync(local_db_path=tmp_path / "omega.db")
        with patch.object(sync, "sync_memories", return_value={"synced": 3, "status": "ok"}), \
             patch.object(sync, "sync_documents", return_value={"synced": 1, "status": "ok"}):
            result = sync.sync_all()

        assert result["profile"]["status"] == "excluded"
        assert result["profile"]["reason"] == "sensitive"
        assert result["memories"]["synced"] == 3
        assert result["documents"]["synced"] == 1


# ============================================================================
# TestAutoCloudPull
# ============================================================================

class TestAutoCloudPull:
    """Tests for auto-pull on session start in handle_session_start."""

    def test_auto_pull_fires_when_marker_stale(self, tmp_path):
        """Auto-pull should fire when last-cloud-pull marker is >1 day old."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()

        # Create a stale marker (2 days old)
        pull_marker = omega_dir / "last-cloud-pull"
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        pull_marker.write_text(stale_ts)

        # Create secrets.json so cloud is "configured"
        (omega_dir / "secrets.json").write_text("{}")

        mock_sync = MagicMock()
        mock_sync.pull_all.return_value = {
            "memories": {"pulled": 3, "skipped": 1, "status": "ok"},
            "documents": {"pulled": 0, "skipped": 0, "chunks": 0, "status": "ok"},
            "profile": {"status": "excluded", "reason": "sensitive"},
        }

        with patch.object(Path, "home", return_value=tmp_path), \
             patch("omega.cloud.sync.get_sync", return_value=mock_sync), \
             patch("omega.bridge.get_session_context", return_value={
                 "memory_count": 10, "health_status": "ok",
                 "last_capture_ago": "1h", "context_items": [],
             }), patch("subprocess.run"):
            from omega.server.hook_server import handle_session_start
            result = handle_session_start({"session_id": "s1", "project": "/test"})

        mock_sync.pull_all.assert_called_once()
        assert "[CLOUD]" in result["output"]
        assert "3 memories" in result["output"]

    def test_auto_pull_skips_when_fresh(self, tmp_path):
        """Auto-pull should skip when marker is <1 day old."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()

        # Create a fresh marker (1 hour ago)
        pull_marker = omega_dir / "last-cloud-pull"
        fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        pull_marker.write_text(fresh_ts)

        (omega_dir / "secrets.json").write_text("{}")

        with patch.object(Path, "home", return_value=tmp_path), \
             patch("omega.cloud.sync.get_sync") as mock_get_sync, \
             patch("omega.bridge.get_session_context", return_value={
                 "memory_count": 10, "health_status": "ok",
                 "last_capture_ago": "1h", "context_items": [],
             }), patch("subprocess.run"):
            from omega.server.hook_server import handle_session_start
            handle_session_start({"session_id": "s2", "project": "/test"})

        mock_get_sync.assert_not_called()

    def test_auto_pull_skips_when_no_secrets(self, tmp_path):
        """Auto-pull should skip when secrets.json doesn't exist."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()
        # No secrets.json created

        with patch.object(Path, "home", return_value=tmp_path), \
             patch("omega.cloud.sync.get_sync") as mock_get_sync, \
             patch("omega.bridge.get_session_context", return_value={
                 "memory_count": 10, "health_status": "ok",
                 "last_capture_ago": "1h", "context_items": [],
             }), patch("subprocess.run"):
            from omega.server.hook_server import handle_session_start
            handle_session_start({"session_id": "s3", "project": "/test"})

        mock_get_sync.assert_not_called()

    def test_auto_pull_fail_open(self, tmp_path):
        """Auto-pull errors should not crash session start."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()
        (omega_dir / "secrets.json").write_text("{}")
        # No marker → should_pull = True

        with patch.object(Path, "home", return_value=tmp_path), \
             patch("omega.cloud.sync.get_sync", side_effect=RuntimeError("cloud down")), \
             patch("omega.bridge.get_session_context", return_value={
                 "memory_count": 10, "health_status": "ok",
                 "last_capture_ago": "1h", "context_items": [],
             }), patch("subprocess.run"):
            from omega.server.hook_server import handle_session_start
            result = handle_session_start({"session_id": "s4", "project": "/test"})

        # Should not crash — still returns output
        assert result["output"]
        assert result["error"] is None


# ============================================================================
# TestCloudStatusFooter
# ============================================================================

class TestCloudStatusFooter:
    """Tests for cloud status in session briefing footer."""

    def test_footer_shows_cloud_ok_when_configured(self, tmp_path):
        """Footer should show 'cloud ok' when secrets exist and pull is fresh."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()
        (omega_dir / "secrets.json").write_text("{}")
        pull_marker = omega_dir / "last-cloud-pull"
        pull_marker.write_text(datetime.now(timezone.utc).isoformat())

        with patch.object(Path, "home", return_value=tmp_path), \
             patch("omega.bridge.get_session_context", return_value={
                 "memory_count": 10, "health_status": "ok",
                 "last_capture_ago": "1h", "context_items": [],
             }), patch("subprocess.run"):
            from omega.server.hook_server import handle_session_start
            result = handle_session_start({"session_id": "s5", "project": "/test"})

        assert "cloud ok" in result["output"]

    def test_footer_shows_cloud_age_when_stale(self, tmp_path):
        """Footer should show age when pull marker is old and auto-pull fails."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()
        (omega_dir / "secrets.json").write_text("{}")
        pull_marker = omega_dir / "last-cloud-pull"
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        pull_marker.write_text(stale_ts)

        # Mock get_sync to raise so auto-pull fails and marker stays stale
        with patch.object(Path, "home", return_value=tmp_path), \
             patch("omega.cloud.sync.get_sync", side_effect=RuntimeError("no network")), \
             patch("omega.bridge.get_session_context", return_value={
                 "memory_count": 10, "health_status": "ok",
                 "last_capture_ago": "1h", "context_items": [],
             }), patch("subprocess.run"):
            from omega.server.hook_server import handle_session_start
            result = handle_session_start({"session_id": "s6", "project": "/test"})

        assert "cloud" in result["output"].lower()
        assert "3d ago" in result["output"]

    def test_footer_omits_cloud_when_not_configured(self, tmp_path):
        """Footer should not mention cloud when secrets.json doesn't exist."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()
        # No secrets.json

        with patch.object(Path, "home", return_value=tmp_path), \
             patch("omega.bridge.get_session_context", return_value={
                 "memory_count": 10, "health_status": "ok",
                 "last_capture_ago": "1h", "context_items": [],
             }), patch("subprocess.run"):
            from omega.server.hook_server import handle_session_start
            result = handle_session_start({"session_id": "s7", "project": "/test"})

        # Cloud content section ([CLOUD]) should not appear; timing footer may list stage names
        assert "[cloud]" not in result["output"].lower()


# ============================================================================
# TestCmdStatusCloud
# ============================================================================

class TestCmdStatusCloud:
    """Tests for cloud section in omega status CLI."""

    def test_status_shows_cloud_configured(self, tmp_path, capsys):
        """omega status should show cloud configured when secrets exist."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()
        (omega_dir / "secrets.json").write_text("{}")
        (omega_dir / "last-cloud-pull").write_text("2026-02-10T12:00:00+00:00")
        (omega_dir / "last-cloud-push").write_text("2026-02-10T13:00:00+00:00")

        with patch("omega.cli.OMEGA_DIR", omega_dir):
            from omega.cli import cmd_status

            # Capture all print_kv calls
            kv_calls = []
            original_print_kv = None
            try:
                from omega import cli_ui
                original_print_kv = cli_ui.print_kv
                cli_ui.print_kv = lambda kv: kv_calls.append(list(kv))
            except Exception:
                pass

            try:
                with patch("omega.cli_ui.print_header"), patch("builtins.print"):
                    cmd_status(MagicMock(verbose=False, json=False))
            except Exception:
                pass  # May fail on DB access
            finally:
                if original_print_kv:
                    cli_ui.print_kv = original_print_kv

        # Flatten all kv calls and check for cloud
        all_kv = [item for call in kv_calls for item in call]
        labels = [item[0] for item in all_kv]
        assert "Cloud" in labels
        cloud_idx = labels.index("Cloud")
        assert all_kv[cloud_idx][1] == "configured"

    def test_status_shows_cloud_not_configured(self, tmp_path):
        """omega status should show 'not configured' when no secrets."""
        omega_dir = tmp_path / ".omega"
        omega_dir.mkdir()

        with patch("omega.cli.OMEGA_DIR", omega_dir):
            from omega.cli import cmd_status

            kv_calls = []
            original_print_kv = None
            try:
                from omega import cli_ui
                original_print_kv = cli_ui.print_kv
                cli_ui.print_kv = lambda kv: kv_calls.append(list(kv))
            except Exception:
                pass

            try:
                with patch("omega.cli_ui.print_header"), patch("builtins.print"):
                    cmd_status(MagicMock(verbose=False, json=False))
            except Exception:
                pass
            finally:
                if original_print_kv:
                    cli_ui.print_kv = original_print_kv

        all_kv = [item for call in kv_calls for item in call]
        labels = [item[0] for item in all_kv]
        assert "Cloud" in labels
        cloud_idx = labels.index("Cloud")
        assert all_kv[cloud_idx][1] == "not configured"
