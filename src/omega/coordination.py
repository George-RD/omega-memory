"""
OMEGA Coordination Layer -- Multi-agent awareness via SQLite.

Provides session registry, file/branch claims (TTL-aware), intent broadcasting,
message bus, task management (deps, progress, fail/cancel), audit logging,
session snapshots/recovery, deadlock detection, capability routing,
git event tracking, and stale session cleanup. All tables live in the
shared omega.db with a `coord_` prefix.

Usage:
    mgr = CoordinationManager()
    mgr.register_session("sess-1", pid=12345, project="/Projects/foo")
    mgr.claim_file("sess-1", "/Projects/foo/bar.py")
    mgr.deregister_session("sess-1")  # Releases claims, marks session 'ended'
"""

import asyncio
import concurrent.futures
import logging
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from omega import json_compat as json
from omega.db_utils import retry_on_locked as _retry_on_locked

logger = logging.getLogger("omega.coordination")

# Audit batching constants — reduce per-call DB writes under multi-process load
_AUDIT_BATCH_SIZE = 20
_AUDIT_FLUSH_INTERVAL_S = 30


def _safe_json_loads(raw, fallback=None):
    """Parse JSON with fallback for corrupted data. Prevents one bad row from crashing the entire hook chain."""
    if not raw:
        return fallback if fallback is not None else {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback if fallback is not None else {}


COORD_SCHEMA_VERSION = 12

# Internal strings that should never become session task descriptions.
# These leak from guard hooks, system prompts, or fallback values.
_INTERNAL_TASK_STRINGS = frozenset({
    "pre-edit guard claim",
    "auto-claimed on edit",
    "session start",
    "no task",
})
_INTERNAL_TASK_STRINGS_LOWER = frozenset(s.lower() for s in _INTERNAL_TASK_STRINGS)
# Prefixes that indicate system-level text, not user task descriptions.
_INTERNAL_TASK_PREFIXES = (
    "Read the output file",
    "Read the output",
    "Use the ",
    "Launching skill:",
)


def _sanitize_task_description(task: Optional[str]) -> Optional[str]:
    """Filter out internal/system strings from session task descriptions.

    Returns the cleaned task or None if the input is not a meaningful description.
    """
    if not task:
        return None
    task = task.strip()
    if not task or task.lower() in _INTERNAL_TASK_STRINGS_LOWER:
        return None
    for prefix in _INTERNAL_TASK_PREFIXES:
        if task.startswith(prefix):
            return None
    # Truncate to reasonable length for dashboard display
    if len(task) > 200:
        task = task[:197] + "..."
    return task
MESSAGE_EXPIRY_DEFAULT_MINUTES = 60 * 24  # 24 hours default expiry
STALE_THRESHOLD_SECONDS = 900  # 15 min without heartbeat = stale (was 30min)
CLAIM_TTL_SECONDS = 1800  # 30 min without edit activity = expired file claim
BRANCH_CLAIM_TTL_SECONDS = 3600  # 1 hour without activity = expired branch claim
SNAPSHOT_RETENTION_DAYS = 14  # How long to keep session snapshots
AUDIT_RETENTION_DAYS = 14  # How long to keep audit log entries
PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "release"})


class CoordinationManager:
    """SQLite-backed multi-agent coordination.

    Shares the omega.db database but uses `coord_*` prefixed tables.
    Thread-safe via a dedicated lock (separate from SQLiteStore's lock).
    """

    def __init__(self, db_path: Optional[str] = None, cloud_sync: bool = True, task_queue: Optional[asyncio.Queue] = None):
        omega_home = Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega")))
        self.db_path = Path(db_path) if db_path else (omega_home / "omega.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        self._cloud_sync = cloud_sync
        self._lock = threading.Lock()
        self._last_stale_cleanup: float = 0.0
        self._session_count_cache: int = 0
        self._session_count_cache_time: float = 0.0
        self._pruned_session_ids: list = []
        self._heartbeat_count: int = 0
        self._audit_buffer: list[tuple] = []
        self._audit_buffer_lock = threading.Lock()
        self._audit_last_flush = time.monotonic()
        self._drift_cache: Dict[str, Any] = {}
        self._drift_cache_times: Dict[str, float] = {}
        self._file_check_cache: dict[str, tuple[float, Any]] = {}
        self._task_queue: Optional[asyncio.Queue] = task_queue
        self._conn = self._connect()
        self._init_schema()

        # WAL checkpoint: PASSIVE every N writes, TRUNCATE every M writes.
        # Matches sqlite_store.py intervals for the shared omega.db.
        self._wal_write_count = 0
        self._WAL_CHECKPOINT_INTERVAL = 10
        self._WAL_TRUNCATE_INTERVAL = 100

        # Startup PASSIVE checkpoint: non-blocking WAL cleanup under multi-process load.
        # TRUNCATE requires exclusive access which deadlocks with concurrent readers.
        try:
            result = self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            if result and result[1] > 0:
                logger.info("Coordination startup WAL checkpoint: %d/%d pages checkpointed", result[1], result[2])
        except Exception as e:
            logger.debug("Coordination startup WAL checkpoint failed (non-fatal): %s", e)

        # Bounded executor for cloud reconciliation: at most 1 thread runs at a
        # time; excess submissions queue instead of spawning unbounded threads.
        self._cloud_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="omega-cloud-recon"
        )

        # Full-state cloud reconciliation: ensure Supabase matches local SQLite.
        # Runs in a background thread so it never blocks MCP server startup.
        if self._cloud_sync:
            self._cloud_executor.submit(self._cloud_reconcile)

    def _cloud_reconcile(self) -> None:
        """Push all active local sessions to Supabase and mark orphans as stopped."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT session_id, pid, project, task, started_at, last_heartbeat "
                    "FROM coord_sessions WHERE status = 'active'"
                ).fetchall()
            active = [
                {
                    "session_id": r[0], "pid": r[1], "project": r[2],
                    "task": r[3], "started_at": r[4], "last_heartbeat": r[5],
                }
                for r in rows
            ]
            self._cloud_fire("reconcile_sessions", active)
        except Exception as e:
            logger.debug("Cloud reconcile failed (non-fatal): %s", e)

    def _cloud_fire(self, fn: str, *args) -> None:
        """Fire-and-forget cloud sync. Never blocks or raises."""
        if not self._cloud_sync:
            return
        try:
            from omega.cloud.sync import get_sync

            getattr(get_sync(), fn)(*args)
        except Exception:
            pass

    async def enqueue_task(self, task: Any) -> None:
        """Submit a task to the async queue without blocking the event loop.

        If no ``asyncio.Queue`` was provided at construction time, falls back
        to synchronous (no-op) handling so callers remain backward-compatible.

        Args:
            task: Any picklable object describing the work to be performed.

        Raises:
            RuntimeError: If called outside of a running asyncio event loop
                when an async queue is configured.
        """
        if self._task_queue is None:
            logger.debug("enqueue_task called without an async queue; task dropped: %r", task)
            return
        await self._task_queue.put(task)
        logger.debug("Task enqueued (queue size ~%d): %r", self._task_queue.qsize(), task)

    def active_session_count(self) -> int:
        """Active session count, cached 10s."""
        now = time.monotonic()
        if now - self._session_count_cache_time < 10.0:
            return self._session_count_cache
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM coord_sessions WHERE status = 'active'"
            ).fetchone()
        self._session_count_cache = row[0] if row else 0
        self._session_count_cache_time = now
        return self._session_count_cache

    @classmethod
    def get_instance(cls) -> "CoordinationManager":
        """Return the module-level singleton CoordinationManager.

        Convenience alias for ``get_manager()`` so callers can use the
        class directly without an extra import.
        """
        return get_manager()

    def get_read_connection(self) -> sqlite3.Connection:
        """Return the DB connection for read-only queries.

        Safe without locking in WAL mode (readers don't block writers).
        Do NOT use for writes; use public methods with proper locking instead.
        """
        return self._conn

    def _connect(self) -> sqlite3.Connection:
        from omega.crypto import secure_connect

        conn = secure_connect(
            self.db_path,
            timeout=30,
            check_same_thread=False,
            isolation_level="IMMEDIATE",
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")  # 30s — match SQLiteStore
        # HTTP daemon mode: smaller footprint (see sqlite_store/_base.py comment)
        _is_http = os.environ.get("OMEGA_TRANSPORT", "").lower() == "http"
        conn.execute(f"PRAGMA cache_size={-4000 if _is_http else -16000}")  # 4MB / 16MB
        conn.execute(f"PRAGMA mmap_size={0 if _is_http else 33554432}")  # 0 / 32MB
        conn.execute("PRAGMA journal_size_limit=8388608")  # 8MB — cap WAL growth under multi-process contention
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        c = self._conn

        # Fast-path: if schema is already at current version, skip all DDL.
        # This avoids ~50 write-lock-acquiring DDL statements on every init,
        # which cause severe contention under multi-process fallback mode.
        try:
            row = c.execute("SELECT version FROM coord_schema_version LIMIT 1").fetchone()
            if row and row[0] >= COORD_SCHEMA_VERSION:
                return
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet — proceed with full init

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_schema_version (
                version INTEGER NOT NULL
            )
        """)
        row = c.execute("SELECT version FROM coord_schema_version LIMIT 1").fetchone()
        if row is None:
            c.execute("INSERT INTO coord_schema_version (version) VALUES (?)", (COORD_SCHEMA_VERSION,))
        else:
            current_version = row[0]
            if current_version < COORD_SCHEMA_VERSION:
                self._migrate_schema(c, current_version)
                c.execute("UPDATE coord_schema_version SET version = ?", (COORD_SCHEMA_VERSION,))

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_sessions (
                session_id TEXT PRIMARY KEY,
                pid INTEGER,
                project TEXT,
                task TEXT,
                status TEXT DEFAULT 'active',
                capabilities TEXT,
                started_at TEXT NOT NULL,
                last_heartbeat TEXT NOT NULL,
                metadata TEXT,
                agent_type TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_file_claims (
                file_path TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES coord_sessions(session_id) ON DELETE CASCADE,
                task TEXT,
                claimed_at TEXT NOT NULL,
                last_activity TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_file_reads (
                session_id TEXT NOT NULL REFERENCES coord_sessions(session_id) ON DELETE CASCADE,
                file_path TEXT NOT NULL,
                first_read_at TEXT NOT NULL,
                read_count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (session_id, file_path)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_branch_claims (
                project TEXT NOT NULL,
                branch TEXT NOT NULL,
                session_id TEXT NOT NULL REFERENCES coord_sessions(session_id) ON DELETE CASCADE,
                task TEXT,
                claimed_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                UNIQUE(project, branch)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES coord_sessions(session_id) ON DELETE CASCADE,
                intent_type TEXT DEFAULT 'work',
                description TEXT NOT NULL,
                target_files TEXT,
                target_branch TEXT,
                findings TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                project TEXT,
                task TEXT,
                pid INTEGER,
                file_claims TEXT,
                branch_claims TEXT,
                intents TEXT,
                metadata TEXT,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_snapshots_project
            ON coord_snapshots(project)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_snapshots_created
            ON coord_snapshots(created_at)
        """)

        # v2: coord_tasks includes result + progress columns
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                project TEXT,
                session_id TEXT,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                claimed_at TEXT,
                completed_at TEXT,
                metadata TEXT,
                result TEXT,
                progress INTEGER DEFAULT 0,
                goal_id INTEGER REFERENCES coord_goals(id)
            )
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_tasks_project
            ON coord_tasks(project)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_tasks_status
            ON coord_tasks(status)
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                tool_name TEXT NOT NULL,
                arguments TEXT,
                result_summary TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Trace columns (added v1.1.0) — nullable for backward compat
        for col, typedef in [
            ("latency_ms", "INTEGER"),
            ("call_index", "INTEGER"),
            ("result_status", "TEXT DEFAULT 'ok'"),
            ("input_size", "INTEGER"),
        ]:
            try:
                c.execute(f"ALTER TABLE coord_audit ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # Column already exists

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_audit_session
            ON coord_audit(session_id)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_audit_created
            ON coord_audit(created_at)
        """)

        # Git event tracking — bridges coordination with actual git state
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_git_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                project TEXT NOT NULL,
                event_type TEXT NOT NULL,
                commit_hash TEXT,
                branch TEXT,
                message TEXT,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_git_events_project
            ON coord_git_events(project)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_git_events_hash
            ON coord_git_events(commit_hash)
        """)

        # Indexes for common lookups
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_file_claims_session
            ON coord_file_claims(session_id)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_file_reads_session
            ON coord_file_reads(session_id)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_branch_claims_session
            ON coord_branch_claims(session_id)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_intents_session
            ON coord_intents(session_id)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_sessions_project
            ON coord_sessions(project)
        """)

        # --- v2 tables: Message bus + task dependencies ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_session TEXT NOT NULL,
                to_session TEXT,
                project TEXT,
                msg_type TEXT NOT NULL,
                context_id TEXT,
                subject TEXT NOT NULL,
                body TEXT,
                ref_task_id INTEGER,
                created_at TEXT NOT NULL,
                read_at TEXT,
                expires_at TEXT,
                priority TEXT DEFAULT 'medium',
                batch_id TEXT,
                delivered_at TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_coord_messages_to ON coord_messages(to_session)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_coord_messages_project ON coord_messages(project)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_coord_messages_context ON coord_messages(context_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_coord_messages_created ON coord_messages(created_at)")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_coord_messages_pending
                     ON coord_messages(priority, delivered_at)
                     WHERE delivered_at IS NULL""")

        # v3: Per-session read tracking for broadcast messages
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_broadcast_reads (
                message_id INTEGER NOT NULL REFERENCES coord_messages(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL,
                read_at TEXT NOT NULL,
                PRIMARY KEY (message_id, session_id)
            )
        """)

        # v4: Coordination metrics — tracks gate checks, conflicts, handoff reads
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value INTEGER DEFAULT 1,
                session_id TEXT,
                project TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_metrics_name
            ON coord_metrics(metric_name)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_metrics_created
            ON coord_metrics(created_at)
        """)

        # v4: Structured handoffs — typed session-end summaries
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                project TEXT,
                completed_tasks TEXT,
                blocked_items TEXT,
                key_context TEXT,
                next_steps TEXT,
                files_modified TEXT,
                decisions_made TEXT,
                git_branch TEXT,
                git_dirty_files TEXT,
                created_at TEXT NOT NULL,
                read_by TEXT DEFAULT '[]'
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_handoffs_project
            ON coord_handoffs(project)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_handoffs_created
            ON coord_handoffs(created_at)
        """)

        # v5: External action registry — prevents duplicate deploys, submissions, etc.
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_external_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                action_target TEXT NOT NULL,
                session_id TEXT NOT NULL REFERENCES coord_sessions(session_id) ON DELETE CASCADE,
                status TEXT DEFAULT 'claimed',
                params TEXT,
                result TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_external_actions_lookup
            ON coord_external_actions(action_type, action_target, status)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_external_actions_session
            ON coord_external_actions(session_id)
        """)

        # v6: Goal persistence + drift detection
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                project TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                parent_goal_id INTEGER REFERENCES coord_goals(id),
                evolved_from_id INTEGER REFERENCES coord_goals(id),
                evolution_reason TEXT,
                original_description TEXT NOT NULL,
                target_files TEXT,
                target_modules TEXT,
                success_criteria TEXT,
                priority INTEGER DEFAULT 0,
                metadata TEXT
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_goals_project
            ON coord_goals(project, status)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_goals_parent
            ON coord_goals(parent_goal_id)
        """)

        # v7: Capability effectiveness stats for drift-aware routing
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_capability_stats (
                capability TEXT NOT NULL,
                project TEXT,
                tasks_completed INTEGER DEFAULT 0,
                total_duration_seconds REAL DEFAULT 0.0,
                avg_duration_seconds REAL DEFAULT 0.0,
                last_updated TEXT NOT NULL,
                PRIMARY KEY (capability, project)
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_capability_stats_capability
            ON coord_capability_stats(capability)
        """)

        # v8: Decision register — authoritative shared state for alignment
        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                project TEXT NOT NULL,
                decision TEXT NOT NULL,
                rationale TEXT,
                decided_by TEXT NOT NULL,
                goal_id INTEGER REFERENCES coord_goals(id),
                status TEXT DEFAULT 'active',
                superseded_by INTEGER REFERENCES coord_decisions(id),
                created_at TEXT NOT NULL,
                superseded_at TEXT,
                metadata TEXT
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_decisions_project_domain
            ON coord_decisions(project, domain, status)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_coord_decisions_goal
            ON coord_decisions(goal_id)
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS coord_task_deps (
                task_id INTEGER NOT NULL REFERENCES coord_tasks(id) ON DELETE CASCADE,
                depends_on_id INTEGER NOT NULL REFERENCES coord_tasks(id) ON DELETE CASCADE,
                PRIMARY KEY (task_id, depends_on_id),
                CHECK (task_id != depends_on_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_coord_task_deps_depends ON coord_task_deps(depends_on_id)")

        # Post-migration column verification — self-healing for migrations that
        # were skipped (e.g., version bumped past v9 before ALTER TABLE ran).
        # Idempotent: sqlite3.OperationalError if column already exists.
        for table, col, typedef in [
            ("coord_intents", "findings", "TEXT"),
        ]:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass  # Column already exists

        _retry_on_locked(c.commit)

    def _migrate_schema(self, c: sqlite3.Connection, from_version: int) -> None:
        """Migrate schema from from_version to COORD_SCHEMA_VERSION."""
        if from_version < 2:
            # v2: Add result and progress columns to coord_tasks
            for col_sql in (
                "ALTER TABLE coord_tasks ADD COLUMN result TEXT",
                "ALTER TABLE coord_tasks ADD COLUMN progress INTEGER DEFAULT 0",
            ):
                try:
                    c.execute(col_sql)
                except sqlite3.OperationalError:
                    pass  # Column already exists (idempotent)
            _retry_on_locked(c.commit)
        if from_version < 3:
            # v3: Per-session read tracking for broadcast messages
            c.execute("""
                CREATE TABLE IF NOT EXISTS coord_broadcast_reads (
                    message_id INTEGER NOT NULL REFERENCES coord_messages(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL,
                    read_at TEXT NOT NULL,
                    PRIMARY KEY (message_id, session_id)
                )
            """)
            _retry_on_locked(c.commit)
        if from_version < 4:
            # v4: Coordination metrics + structured handoffs
            c.execute("""
                CREATE TABLE IF NOT EXISTS coord_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_value INTEGER DEFAULT 1,
                    session_id TEXT,
                    project TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_coord_metrics_name ON coord_metrics(metric_name)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_coord_metrics_created ON coord_metrics(created_at)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS coord_handoffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    project TEXT,
                    completed_tasks TEXT,
                    blocked_items TEXT,
                    key_context TEXT,
                    next_steps TEXT,
                    files_modified TEXT,
                    decisions_made TEXT,
                    git_branch TEXT,
                    git_dirty_files TEXT,
                    created_at TEXT NOT NULL,
                    read_by TEXT DEFAULT '[]'
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_coord_handoffs_project ON coord_handoffs(project)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_coord_handoffs_created ON coord_handoffs(created_at)")
            _retry_on_locked(c.commit)
        if from_version < 5:
            # v5: External action registry — prevents duplicate deploys, submissions, etc.
            c.execute("""
                CREATE TABLE IF NOT EXISTS coord_external_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    action_target TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES coord_sessions(session_id) ON DELETE CASCADE,
                    status TEXT DEFAULT 'claimed',
                    params TEXT,
                    result TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_coord_external_actions_lookup
                ON coord_external_actions(action_type, action_target, status)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_coord_external_actions_session
                ON coord_external_actions(session_id)
            """)
            _retry_on_locked(c.commit)
        if from_version < 6:
            # v6: Goal persistence + drift detection
            c.execute("""
                CREATE TABLE IF NOT EXISTS coord_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    project TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    parent_goal_id INTEGER REFERENCES coord_goals(id),
                    evolved_from_id INTEGER REFERENCES coord_goals(id),
                    evolution_reason TEXT,
                    original_description TEXT NOT NULL,
                    target_files TEXT,
                    target_modules TEXT,
                    success_criteria TEXT,
                    priority INTEGER DEFAULT 0,
                    metadata TEXT
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_coord_goals_project
                ON coord_goals(project, status)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_coord_goals_parent
                ON coord_goals(parent_goal_id)
            """)
            # Add goal_id FK to coord_tasks
            try:
                c.execute("ALTER TABLE coord_tasks ADD COLUMN goal_id INTEGER REFERENCES coord_goals(id)")
            except sqlite3.OperationalError:
                pass  # Column already exists (idempotent)
            _retry_on_locked(c.commit)
        if from_version < 7:
            # v7: Capability effectiveness stats for drift-aware routing
            c.execute("""
                CREATE TABLE IF NOT EXISTS coord_capability_stats (
                    capability TEXT NOT NULL,
                    project TEXT,
                    tasks_completed INTEGER DEFAULT 0,
                    total_duration_seconds REAL DEFAULT 0.0,
                    avg_duration_seconds REAL DEFAULT 0.0,
                    last_updated TEXT NOT NULL,
                    PRIMARY KEY (capability, project)
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_coord_capability_stats_capability
                ON coord_capability_stats(capability)
            """)
            _retry_on_locked(c.commit)
        if from_version < 8:
            # v8: Decision register — authoritative shared state for alignment
            c.execute("""
                CREATE TABLE IF NOT EXISTS coord_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    project TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    rationale TEXT,
                    decided_by TEXT NOT NULL,
                    goal_id INTEGER REFERENCES coord_goals(id),
                    status TEXT DEFAULT 'active',
                    superseded_by INTEGER REFERENCES coord_decisions(id),
                    created_at TEXT NOT NULL,
                    superseded_at TEXT,
                    metadata TEXT
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_coord_decisions_project_domain
                ON coord_decisions(project, domain, status)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_coord_decisions_goal
                ON coord_decisions(goal_id)
            """)
            _retry_on_locked(c.commit)
        if from_version < 9:
            # v9: Findings column on intents — "already explored" signal
            try:
                c.execute("ALTER TABLE coord_intents ADD COLUMN findings TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists (idempotent)
            _retry_on_locked(c.commit)
        if from_version < 10:
            # v10: File read tracking — input side of the pipeline
            c.execute("""
                CREATE TABLE IF NOT EXISTS coord_file_reads (
                    session_id TEXT NOT NULL REFERENCES coord_sessions(session_id) ON DELETE CASCADE,
                    file_path TEXT NOT NULL,
                    first_read_at TEXT NOT NULL,
                    read_count INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (session_id, file_path)
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_coord_file_reads_session
                ON coord_file_reads(session_id)
            """)
            _retry_on_locked(c.commit)
        if from_version < 11:
            for col_sql in (
                "ALTER TABLE coord_messages ADD COLUMN priority TEXT DEFAULT 'medium'",
                "ALTER TABLE coord_messages ADD COLUMN batch_id TEXT",
                "ALTER TABLE coord_messages ADD COLUMN delivered_at TEXT",
            ):
                try:
                    c.execute(col_sql)
                except sqlite3.OperationalError:
                    pass
            try:
                c.execute(
                    """CREATE INDEX IF NOT EXISTS idx_coord_messages_pending
                       ON coord_messages(priority, delivered_at)
                       WHERE delivered_at IS NULL"""
                )
            except sqlite3.OperationalError:
                pass
            _retry_on_locked(c.commit)

        if from_version < 12:
            try:
                c.execute("ALTER TABLE coord_sessions ADD COLUMN agent_type TEXT")
            except sqlite3.OperationalError:
                pass
            _retry_on_locked(c.commit)

    # ------------------------------------------------------------------
    # Resilient commit — retries on multi-process lock contention
    # ------------------------------------------------------------------

    def _commit(self) -> None:
        """Commit with retry on 'database is locked'."""
        _retry_on_locked(self._conn.commit)
        self._maybe_wal_checkpoint()

    def _maybe_wal_checkpoint(self) -> None:
        """Run WAL checkpoints: PASSIVE every N writes, TRUNCATE every M writes.

        Mirrors sqlite_store.py logic. Both modules share omega.db, so both
        must participate in WAL maintenance to prevent checkpoint starvation
        from persistent reader connections.
        """
        self._wal_write_count += 1
        if self._wal_write_count >= self._WAL_TRUNCATE_INTERVAL:
            self._wal_write_count = 0
            try:
                result = self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if result:
                    busy, checkpointed, total = result
                    logger.debug("Coordination WAL TRUNCATE checkpoint: %d/%d pages (%d busy)",
                                 checkpointed, total, busy)
            except Exception as e:
                logger.debug("Coordination WAL TRUNCATE checkpoint failed (non-fatal): %s", e)
        elif self._wal_write_count % self._WAL_CHECKPOINT_INTERVAL == 0:
            try:
                result = self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                if result:
                    busy, checkpointed, total = result
                    if checkpointed > 0:
                        logger.debug("Coordination WAL PASSIVE checkpoint: %d/%d pages (%d busy)",
                                     checkpointed, total, busy)
            except Exception as e:
                logger.debug("Coordination WAL PASSIVE checkpoint failed (non-fatal): %s", e)

    # ------------------------------------------------------------------
    # Auto-registration (golden path — agents never see "not registered")
    # ------------------------------------------------------------------

    def _ensure_registered(
        self,
        session_id: str,
        project: Optional[str] = None,
    ) -> None:
        """Transparently register a session if it doesn't exist.

        Called BEFORE the lock block in claim_file/claim_branch/announce_intent/
        create_task/claim_task so agents never hit "Session not registered".

        NOT called inside self._lock — register_session acquires it internally.
        """
        # Quick read — protected by try/except because concurrent threads can
        # hit sqlite3.InterfaceError on the shared connection.  If that happens
        # we fall through; the caller's ``with self._lock:`` block re-checks.
        try:
            row = self._conn.execute(
                "SELECT session_id FROM coord_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row:
                return  # Already registered
        except sqlite3.InterfaceError:
            return  # Concurrent access; caller's lock block will validate

        # Try snapshot recovery first, then fresh registration
        try:
            snapshot = self._conn.execute(
                """SELECT project, task, pid, metadata FROM coord_snapshots
                   WHERE session_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        except sqlite3.InterfaceError:
            snapshot = None  # Fall through to fresh registration

        if snapshot:
            snap_project, snap_task, snap_pid, snap_meta_json = snapshot
            snap_meta = _safe_json_loads(snap_meta_json)
            caps = snap_meta.get("capabilities", [])
            self.register_session(
                session_id=session_id,
                pid=snap_pid or os.getpid(),
                project=snap_project or project,
                task=snap_task,
                capabilities=caps,
            )
        else:
            self.register_session(
                session_id=session_id,
                pid=os.getpid(),
                project=project,
            )

        logger.info(
            "Auto-registered session %s (recovered from %s)",
            session_id,
            "snapshot" if snapshot else "scratch",
        )

    @staticmethod
    def _project_from_path(file_path: str) -> Optional[str]:
        """Derive project root from a file path by walking up to find .git."""
        if not file_path:
            return None
        try:
            p = Path(file_path).resolve()
            for parent in [p] + list(p.parents):
                if (parent / ".git").exists():
                    return str(parent)
        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_repo_root(project: str) -> "Optional[str]":
        """Resolve canonical git repo root, following worktree links to main repo.

        In a git worktree, ``--git-common-dir`` points to the main repo's
        ``.git`` directory.  This ensures worktree agents discover peers
        working on the same logical repository.
        """
        if not project:
            return None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                capture_output=True,
                text=True,
                timeout=3,
                cwd=project,
            )
            if result.returncode != 0:
                return None
            common = result.stdout.strip()
            if os.path.isabs(common):
                # Worktree: common is /path/to/main-repo/.git
                return str(Path(common).resolve().parent)
            # Main repo: common is ".git", resolve via --show-toplevel
            result2 = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=3,
                cwd=project,
            )
            return result2.stdout.strip() if result2.returncode == 0 else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def register_session(
        self,
        session_id: str,
        pid: Optional[int] = None,
        project: Optional[str] = None,
        task: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        agent_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a new agent session."""
        self._maybe_clean_stale()
        now = datetime.now(timezone.utc).isoformat()

        # Resolve repo root BEFORE the lock (subprocess can block)
        repo_root = self._resolve_repo_root(project) if project else None

        # Inject repo_root into metadata so worktree agents share a common key.
        # Respect caller-provided repo_root if subprocess resolution fails
        # (e.g. in tests with fake paths, or non-git directories).
        # When metadata is None (not passed by caller), preserve existing
        # metadata on re-registration.  This prevents coord_handlers (MCP tool)
        # from wiping transport info set by the hook.
        caller_meta = dict(metadata) if metadata is not None else None

        with self._lock:
            # Check if session already registered (idempotent re-register)
            existing = self._conn.execute(
                "SELECT session_id, metadata FROM coord_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()

            if caller_meta is not None:
                meta = caller_meta
            elif existing and existing[1]:
                meta = _safe_json_loads(existing[1])
            else:
                meta = {}

            # Inject repo_root so worktree agents share a common key
            if repo_root:
                meta["repo_root"] = repo_root
            else:
                repo_root = meta.get("repo_root")

            meta_json = json.dumps(meta)

            if existing:
                self._conn.execute(
                    """UPDATE coord_sessions
                       SET pid = ?, project = ?, task = ?, status = 'active',
                           capabilities = ?, last_heartbeat = ?, metadata = ?,
                           agent_type = COALESCE(?, agent_type)
                       WHERE session_id = ?""",
                    (
                        pid,
                        project,
                        task,
                        json.dumps(capabilities or []),
                        now,
                        meta_json,
                        agent_type,
                        session_id,
                    ),
                )
                self._commit()
                caps_json = json.dumps(capabilities or [])
                self._cloud_fire("upsert_session", session_id, project, "active", task, now, now, pid, caps_json, meta_json, agent_type)
                return {"registered": True, "session_id": session_id, "refreshed": True}

            self._conn.execute(
                """INSERT INTO coord_sessions
                   (session_id, pid, project, task, status, capabilities,
                    started_at, last_heartbeat, metadata, agent_type)
                   VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    pid,
                    project,
                    task,
                    json.dumps(capabilities or []),
                    now,
                    now,
                    meta_json,
                    agent_type,
                ),
            )
            self._commit()
            caps_json = json.dumps(capabilities or [])
            self._cloud_fire("upsert_session", session_id, project, "active", task, now, now, pid, caps_json, meta_json, agent_type)

            # Count active peers on same project OR same repo root (worktree-aware)
            peer_count = 0
            peer_ids = []
            if project:
                if repo_root:
                    # Worktree-aware: match by project path OR shared repo_root
                    rows = self._conn.execute(
                        """SELECT session_id FROM coord_sessions
                           WHERE session_id != ? AND status = 'active'
                           AND (project = ? OR json_extract(metadata, '$.repo_root') = ?)""",
                        (session_id, project, repo_root),
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        """SELECT session_id FROM coord_sessions
                           WHERE project = ? AND session_id != ? AND status = 'active'""",
                        (project, session_id),
                    ).fetchall()
                peer_ids = [r[0] for r in rows]
                peer_count = len(peer_ids)

        # Notify existing peers about the new arrival (direct messages so they get marked read)
        if peer_count > 0 and project:
            for peer_id in peer_ids:
                try:
                    self.send_message(
                        from_session=session_id,
                        subject="New agent joined project",
                        msg_type="inform",
                        to_session=peer_id,
                        body=f"Session {session_id[:20]} joined. {peer_count + 1} agent(s) now active on {os.path.basename(project)}.",
                        ttl_minutes=60,
                    )
                except Exception:
                    pass  # Notification is best-effort

        return {
            "registered": True,
            "session_id": session_id,
            "peers_on_project": peer_count,
        }

    def _get_session_metadata(self, session_id: str) -> Dict[str, Any]:
        """Read and parse metadata JSON for a session."""
        with self._lock:
            row = self._conn.execute(
                "SELECT metadata FROM coord_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row or not row[0]:
            return {}
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return {}

    def _update_session_metadata(self, session_id: str, meta: Dict[str, Any]) -> None:
        """Write metadata JSON for a session and cloud-sync."""
        meta_json = json.dumps(meta)
        with self._lock:
            self._conn.execute(
                "UPDATE coord_sessions SET metadata = ? WHERE session_id = ?",
                (meta_json, session_id),
            )
            self._commit()
            row = self._conn.execute(
                "SELECT project, status, task, last_heartbeat, started_at, pid, capabilities FROM coord_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row:
            self._cloud_fire("upsert_session", session_id, row[0], row[1], row[2], row[3], row[4], row[5], row[6], meta_json)

    def _merge_session_metadata(self, session_id: str, updates: Dict[str, Any]) -> None:
        """Merge keys into existing session metadata without clobbering other fields.

        Reads current metadata, applies updates (shallow merge), and writes back.
        Use this instead of _update_session_metadata when you need to add keys
        without losing existing ones (e.g., repo_root set during register_session).
        """
        existing = self._get_session_metadata(session_id)
        existing.update(updates)
        self._update_session_metadata(session_id, existing)

    def heartbeat(self, session_id: str) -> Dict[str, Any]:
        """Update session heartbeat timestamp.

        If the session was cleaned as stale, auto-re-registers it by
        recovering state from the most recent snapshot (if available).
        """
        self._maybe_clean_stale()
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            cursor = self._conn.execute(
                "UPDATE coord_sessions SET last_heartbeat = ? WHERE session_id = ? AND status = 'active'",
                (now, session_id),
            )
            # Fetch project/task/started_at for cloud sync (cheap read inside WAL lock)
            row = self._conn.execute(
                "SELECT project, task, started_at FROM coord_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            self._commit()

        if cursor.rowcount == 0:
            return self._auto_reregister(session_id, now)
        project = row[0] if row else None
        task = row[1] if row else None
        started_at = row[2] if row else now
        self._cloud_fire("upsert_session", session_id, project, "active", task, now, started_at)

        # Periodic full reconcile: every 10 heartbeats, push all active sessions
        self._heartbeat_count += 1
        if self._heartbeat_count % 10 == 0:
            self._cloud_executor.submit(self._cloud_reconcile)

        return {"success": True, "timestamp": now}

    def update_session_task(self, session_id: str, task: str) -> Dict[str, Any]:
        """Update the task description for a session. Used to enrich dashboard cards."""
        task = _sanitize_task_description(task)
        if not task:
            return {"updated": False, "reason": "task rejected by sanitizer"}
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE coord_sessions SET task = ? WHERE session_id = ? AND status = 'active'",
                (task, session_id),
            )
            self._commit()
        if cursor.rowcount == 0:
            return {"updated": False, "reason": "session not found or ended"}
        self._cloud_fire("update_session_fields", session_id, None, task, now)
        return {"updated": True, "session_id": session_id, "task": task}

    def update_session_task_if_empty(self, session_id: str, task: str) -> bool:
        """Set session task only if currently empty. Returns True if updated."""
        task = _sanitize_task_description(task)
        if not task:
            return False  # Reject internal/system strings
        with self._lock:
            row = self._conn.execute(
                "SELECT task FROM coord_sessions WHERE session_id = ? AND status = 'active'",
                (session_id,),
            ).fetchone()
            if row and not row[0]:
                self._conn.execute(
                    "UPDATE coord_sessions SET task = ? WHERE session_id = ? AND status = 'active'",
                    (task, session_id),
                )
                self._commit()
                now = datetime.now(timezone.utc).isoformat()
                self._cloud_fire("update_session_fields", session_id, None, task, now)
                return True
        return False

    def _auto_reregister(self, session_id: str, now: str) -> Dict[str, Any]:
        """Re-register a session that was cleaned as stale."""
        snapshot = self._conn.execute(
            """SELECT project, task, pid, metadata FROM coord_snapshots
               WHERE session_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (session_id,),
        ).fetchone()

        project = None
        task = None
        pid = None
        capabilities: List[str] = []
        if snapshot:
            project, task, pid, snap_meta_json = snapshot
            snap_meta = _safe_json_loads(snap_meta_json)
            capabilities = snap_meta.get("capabilities", [])

        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO coord_sessions
                       (session_id, pid, project, task, status, capabilities,
                        started_at, last_heartbeat, metadata)
                       VALUES (?, ?, ?, ?, 'active', ?, ?, ?, '{}')""",
                    (session_id, pid, project, task, json.dumps(capabilities), now, now),
                )
                self._commit()
            except sqlite3.IntegrityError:
                # Race: another path registered this session between heartbeat's
                # failed UPDATE and this INSERT. Refresh heartbeat instead.
                self._conn.execute(
                    "UPDATE coord_sessions SET last_heartbeat = ?, status = 'active' WHERE session_id = ?",
                    (now, session_id),
                )
                self._commit()

        caps_json = json.dumps(capabilities) if capabilities else None
        self._cloud_fire("upsert_session", session_id, project, "active", task, now, now, pid, caps_json)
        logger.info(
            "Auto-re-registered session %s (recovered from %s)",
            session_id,
            "snapshot" if snapshot else "scratch",
        )
        result: Dict[str, Any] = {
            "success": True,
            "timestamp": now,
            "reregistered": True,
        }
        if project:
            result["recovered_project"] = project
        return result

    def deregister_session(self, session_id: str) -> Dict[str, Any]:
        """End session. Releases all claims and marks status='ended' for successor visibility."""
        self.flush_audit_buffer()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._snapshot_session(session_id, "clean_stop")

            files = self._conn.execute(
                "SELECT file_path FROM coord_file_claims WHERE session_id = ?", (session_id,)
            ).fetchall()
            branches = self._conn.execute(
                "SELECT project, branch FROM coord_branch_claims WHERE session_id = ?", (session_id,)
            ).fetchall()

            # Reassign in-progress tasks before releasing claims
            orphaned = self._conn.execute(
                "SELECT id, title, progress FROM coord_tasks "
                "WHERE session_id = ? AND status = 'in_progress'",
                (session_id,),
            ).fetchall()
            if orphaned:
                self._conn.execute(
                    "UPDATE coord_tasks SET status = 'pending', session_id = NULL, claimed_at = NULL "
                    "WHERE session_id = ? AND status = 'in_progress'",
                    (session_id,),
                )

            # Explicitly release FK-dependent rows (no CASCADE since we UPDATE, not DELETE)
            self._conn.execute("DELETE FROM coord_file_claims WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM coord_file_reads WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM coord_branch_claims WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM coord_intents WHERE session_id = ?", (session_id,))
            # Transition claimed external actions to 'abandoned' (not deleted) so
            # check_external_action won't let another agent unknowingly re-execute.
            self._conn.execute(
                """UPDATE coord_external_actions SET status = 'abandoned', completed_at = ?
                   WHERE session_id = ? AND status = 'claimed'""",
                (now, session_id),
            )
            # Delete completed/failed actions (safe — they've been recorded).
            # Keep 'abandoned' rows visible so check_external_action surfaces them.
            self._conn.execute(
                "DELETE FROM coord_external_actions WHERE session_id = ? AND status IN ('completed', 'failed')",
                (session_id,),
            )

            # Mark ended (not deleted) so _get_last_session_info can find it
            cursor = self._conn.execute(
                "UPDATE coord_sessions SET status = 'ended', last_heartbeat = ? WHERE session_id = ?",
                (now, session_id),
            )
            self._commit()

        if cursor.rowcount == 0:
            return {"deregistered": False, "error": "Session not found"}

        self._cloud_fire("delete_session_claims", session_id)
        self._cloud_fire("delete_session_file_reads", session_id)
        self._cloud_fire("update_session_status", session_id, "ended", now)

        released_files = [f[0] for f in files]
        released_branches = [(b[0], b[1]) for b in branches]
        if released_files or released_branches:
            self._notify_resource_available(session_id, released_files, released_branches)

        reassigned_tasks = [{"id": r[0], "title": r[1], "progress": r[2] or 0} for r in orphaned]
        result_dict: Dict[str, Any] = {
            "deregistered": True,
            "session_id": session_id,
            "released_files": released_files,
            "released_branches": [f"{b[0]}:{b[1]}" for b in released_branches],
        }
        if reassigned_tasks:
            result_dict["reassigned_tasks"] = reassigned_tasks
        return result_dict

    def reassign_orphaned_tasks(self, session_id: str) -> List[Dict[str, Any]]:
        """Reset in-progress tasks owned by a dead session to pending.

        Called during session stop to return incomplete work to the queue
        so the next session can pick it up.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title, progress FROM coord_tasks WHERE session_id = ? AND status = 'in_progress'",
                (session_id,),
            ).fetchall()
            if not rows:
                return []

            self._conn.execute(
                "UPDATE coord_tasks SET status = 'pending', session_id = NULL, claimed_at = NULL "
                "WHERE session_id = ? AND status = 'in_progress'",
                (session_id,),
            )
            self._commit()

        return [{"id": r[0], "title": r[1], "progress": r[2] or 0} for r in rows]

    def list_sessions(self, auto_clean: bool = True) -> List[Dict[str, Any]]:
        """List active sessions. Optionally cleans stale ones first."""
        if auto_clean:
            self._clean_stale_sessions()

        with self._lock:
            rows = self._conn.execute(
                """SELECT session_id, pid, project, task, status, capabilities,
                          started_at, last_heartbeat, metadata
                   FROM coord_sessions WHERE status = 'active'
                   ORDER BY started_at DESC"""
            ).fetchall()

        sessions = []
        for row in rows:
            sid, pid, project, task, status, caps, started, hb, meta = row
            sessions.append(
                {
                    "session_id": sid,
                    "pid": pid,
                    "project": project,
                    "task": task,
                    "status": status,
                    "capabilities": _safe_json_loads(caps, []),
                    "started_at": started,
                    "last_heartbeat": hb,
                    "metadata": _safe_json_loads(meta),
                }
            )

        return sessions

    # ------------------------------------------------------------------
    # File claims
    # ------------------------------------------------------------------

    def claim_file(
        self,
        session_id: str,
        file_path: str,
        task: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Claim exclusive access to a file.

        If force=True and there's a conflict, overrides the existing claim
        and audits the override for visibility.
        """
        # Golden path: auto-register if needed (before lock — avoids deadlock)
        self._ensure_registered(session_id, self._project_from_path(file_path))

        # Invalidate check_file cache for this path (claim is changing)
        self._file_check_cache.pop(file_path, None)

        now = datetime.now(timezone.utc).isoformat()
        force_previous_owner: Optional[str] = None  # Set inside lock, audit outside

        with self._lock:
            sess = self._conn.execute(
                "SELECT session_id FROM coord_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not sess:
                return {"success": False, "error": "Session auto-registration failed"}

            existing = self._conn.execute(
                """SELECT fc.session_id, fc.task, fc.last_activity, s.last_heartbeat
                   FROM coord_file_claims fc
                   LEFT JOIN coord_sessions s ON fc.session_id = s.session_id
                   WHERE fc.file_path = ?""",
                (file_path,),
            ).fetchone()

            if existing:
                owner_sid, owner_task, last_activity, owner_heartbeat = existing
                if owner_sid == session_id:
                    self._conn.execute(
                        "UPDATE coord_file_claims SET last_activity = ?, task = ? WHERE file_path = ?",
                        (now, task, file_path),
                    )
                    self._commit()
                    self._cloud_fire("upsert_file_claim", file_path, session_id, task, now)
                    return {"success": True, "refreshed": True}

                # Check if claim has expired (TTL) or owning session is stale/orphaned
                cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_SECONDS)).isoformat()
                stale_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS)).isoformat()
                claim_expired = last_activity < cutoff
                session_stale = owner_heartbeat is None or owner_heartbeat < stale_cutoff
                if claim_expired or session_stale:
                    # Expired or stale-session claim — take over silently
                    self.record_metric("claim_expired_replaced", session_id=session_id,
                                       metadata={"file": file_path, "previous_owner": owner_sid})
                    reason = "orphaned" if owner_heartbeat is None else (
                        "stale_session" if session_stale else "claim_ttl"
                    )
                    self._conn.execute(
                        """UPDATE coord_file_claims
                           SET session_id = ?, task = ?, claimed_at = ?, last_activity = ?
                           WHERE file_path = ?""",
                        (session_id, task, now, now, file_path),
                    )
                    self._commit()
                    # Notify previous owner their file claim was replaced (direct INSERT
                    # because send_message() re-acquires the non-reentrant lock).
                    try:
                        self._conn.execute(
                            """INSERT INTO coord_messages
                               (from_session, to_session, msg_type, subject, body,
                                created_at, priority)
                               VALUES (?, ?, 'inform', ?, ?, ?, 'medium')""",
                            (session_id, owner_sid,
                             f"File claim expired: {file_path}",
                             f"Your claim on {file_path} was replaced by {session_id} (reason: {reason})",
                             now),
                        )
                        self._commit()
                    except Exception:
                        pass  # fail-open: notification is best-effort
                    self._cloud_fire("upsert_file_claim", file_path, session_id, task, now)
                    return {"success": True, "file_path": file_path, "expired_claim_replaced": True,
                            "reason": reason}

                if force:
                    # Force-override: steal the claim (DB write inside lock)
                    self.record_metric("conflict_force_override", session_id=session_id,
                                       metadata={"file": file_path, "previous_owner": owner_sid})
                    force_previous_owner = owner_sid
                    self._conn.execute(
                        """UPDATE coord_file_claims
                           SET session_id = ?, task = ?, claimed_at = ?, last_activity = ?
                           WHERE file_path = ?""",
                        (session_id, task, now, now, file_path),
                    )
                    self._commit()
                    # Don't return here — exit lock first, audit below
                else:
                    self.record_metric("conflict_detected", session_id=session_id,
                                       metadata={"file": file_path, "claimed_by": owner_sid})
                    return {
                        "success": False,
                        "conflict": True,
                        "claimed_by": owner_sid,
                        "task": owner_task,
                    }
            else:
                try:
                    self._conn.execute(
                        """INSERT INTO coord_file_claims (file_path, session_id, task, claimed_at, last_activity)
                           VALUES (?, ?, ?, ?, ?)""",
                        (file_path, session_id, task, now, now),
                    )
                    self._commit()
                except sqlite3.IntegrityError:
                    # Cross-process race: another process claimed between check and insert
                    existing = self._conn.execute(
                        "SELECT session_id, task FROM coord_file_claims WHERE file_path = ?", (file_path,)
                    ).fetchone()
                    if existing:
                        return {
                            "success": False,
                            "conflict": True,
                            "claimed_by": existing[0],
                            "task": existing[1],
                        }

        # Cloud sync for successful claim (force or new insert)
        self._cloud_fire("upsert_file_claim", file_path, session_id, task, now)
        # Propagate claim task to session for dashboard visibility (only if session has no task)
        if task:
            with self._lock:
                row = self._conn.execute(
                    "SELECT task FROM coord_sessions WHERE session_id = ? AND status = 'active'",
                    (session_id,),
                ).fetchone()
                if row and not row[0]:
                    self._conn.execute(
                        "UPDATE coord_sessions SET task = ? WHERE session_id = ? AND status = 'active'",
                        (task, session_id),
                    )
                    self._commit()
                    self._cloud_fire("update_session_fields", session_id, None, task, now)

        # Force-claim audit + notification (outside lock to avoid deadlock)
        if force_previous_owner is not None:
            try:
                self.log_audit(
                    tool_name="file_claim_force",
                    session_id=session_id,
                    arguments={"file_path": file_path, "previous_owner": force_previous_owner},
                    result_summary=f"Force-claimed {file_path} from {force_previous_owner[:20]}",
                )
            except Exception:
                pass
            # Notify the previous owner that their claim was taken
            try:
                filename = os.path.basename(file_path)
                self.send_message(
                    from_session=session_id,
                    subject=f"Your claim on {filename} was force-taken",
                    msg_type="inform",
                    to_session=force_previous_owner,
                    body=f"File {file_path} was force-claimed by session {session_id[:20]}. "
                    f"Your edits to this file may conflict.",
                    ttl_minutes=60,
                )
            except Exception:
                pass  # Notification is best-effort
            return {
                "success": True,
                "file_path": file_path,
                "force_override": True,
                "previous_owner": force_previous_owner,
            }

        # Track successful claim
        self.record_metric("file_claimed", session_id=session_id,
                           metadata={"file": file_path})

        # Check for intent overlaps and notify (outside lock, best-effort)
        result: Dict[str, Any] = {"success": True, "file_path": file_path}
        try:
            now_str = datetime.now(timezone.utc).isoformat()
            search_pattern = f'%"{file_path}"%'
            overlapping = self._conn.execute(
                """SELECT i.session_id, i.description
                   FROM coord_intents i
                   JOIN coord_sessions s ON i.session_id = s.session_id
                   WHERE i.session_id != ? AND i.expires_at > ?
                     AND i.target_files LIKE ?""",
                (session_id, now_str, search_pattern),
            ).fetchall()
            if overlapping:
                intent_overlaps = []
                filename = os.path.basename(file_path)
                for row in overlapping:
                    intent_overlaps.append({"session_id": row[0], "description": row[1]})
                    try:
                        self.send_message(
                            from_session=session_id,
                            subject=f"{filename} claimed — conflicts with your intent",
                            msg_type="inform",
                            to_session=row[0],
                            body=f"Session {session_id[:20]} claimed {file_path}. "
                            f"This may conflict with your planned work: {row[1][:100]}",
                            ttl_minutes=30,
                        )
                    except Exception:
                        pass
                result["intent_overlaps"] = intent_overlaps
        except Exception:
            pass
        return result

    def record_file_read(self, session_id: str, file_path: str) -> Dict[str, Any]:
        """Record that a session read a file (input tracking for pipeline view).

        Unlike claim_file (exclusive ownership), multiple sessions can read the
        same file. Uses INSERT ... ON CONFLICT to increment read_count.
        """
        self._ensure_registered(session_id, self._project_from_path(file_path))

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            sess = self._conn.execute(
                "SELECT session_id FROM coord_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not sess:
                return {"success": False, "error": "Session auto-registration failed"}

            self._conn.execute(
                """INSERT INTO coord_file_reads (session_id, file_path, first_read_at, read_count)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT(session_id, file_path)
                   DO UPDATE SET read_count = read_count + 1""",
                (session_id, file_path, now),
            )
            # Fetch actual count for accurate cloud sync
            row = self._conn.execute(
                "SELECT read_count FROM coord_file_reads WHERE session_id = ? AND file_path = ?",
                (session_id, file_path),
            ).fetchone()
            read_count = row[0] if row else 1
            self._commit()

        self._cloud_fire("upsert_file_read", session_id, file_path, now, read_count)
        return {"success": True, "file_path": file_path}

    def get_peer_file_reads(
        self, session_id: str, file_paths: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get file reads by OTHER sessions for the given file paths.

        Returns a dict mapping file_path -> list of {session_id, read_count, first_read_at}.
        Only includes reads from sessions other than the given session_id.
        """
        if not file_paths:
            return {}
        result: Dict[str, List[Dict[str, Any]]] = {}
        placeholders = ",".join("?" * len(file_paths))
        rows = self._conn.execute(
            f"""SELECT session_id, file_path, read_count, first_read_at
                FROM coord_file_reads
                WHERE file_path IN ({placeholders}) AND session_id != ?""",
            (*file_paths, session_id),
        ).fetchall()
        for row in rows:
            entry = {
                "session_id": row[0],
                "read_count": row[2],
                "first_read_at": row[3],
            }
            result.setdefault(row[1], []).append(entry)
        return result

    def refresh_file_activity(self, session_id: str, file_path: str) -> bool:
        """Lightweight last_activity refresh for debounced claim paths.

        Updates the timestamp without conflict checks or intent announces.
        Returns True if the claim was refreshed, False if no matching claim.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE coord_file_claims SET last_activity = ? WHERE file_path = ? AND session_id = ?",
                (now, file_path, session_id),
            )
            self._commit()
        return cursor.rowcount > 0

    def release_file(self, session_id: str, file_path: str) -> Dict[str, Any]:
        """Release a file claim."""
        # Invalidate check_file cache for this path (claim is changing)
        self._file_check_cache.pop(file_path, None)

        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM coord_file_claims WHERE file_path = ? AND session_id = ?", (file_path, session_id)
            )
            self._commit()

        if cursor.rowcount == 0:
            return {"released": False, "error": "No matching claim found"}
        self._cloud_fire("delete_file_claim", file_path, session_id)
        self._notify_resource_available(session_id, [file_path], [])
        return {"released": True, "file_path": file_path}

    def check_file(self, file_path: str) -> Dict[str, Any]:
        """Check who owns a file (if anyone).

        TTL-aware: claims with last_activity older than CLAIM_TTL_SECONDS
        are automatically expired and deleted.  Also expires claims from
        sessions whose heartbeat is older than STALE_THRESHOLD_SECONDS
        (zombie claim detection).

        Results are cached for 5 seconds to dedupe rapid calls from guards.
        """
        now_mono = time.monotonic()
        cached = self._file_check_cache.get(file_path)
        if cached is not None:
            cache_time, cache_result = cached
            if now_mono - cache_time < 5.0:
                return cache_result

        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_SECONDS)).isoformat()
        stale_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS)).isoformat()

        with self._lock:
            row = self._conn.execute(
                """SELECT fc.session_id, fc.task, fc.claimed_at, fc.last_activity,
                          s.project, s.pid, s.last_heartbeat
                   FROM coord_file_claims fc
                   LEFT JOIN coord_sessions s ON fc.session_id = s.session_id
                   WHERE fc.file_path = ?""",
                (file_path,),
            ).fetchone()

            if not row:
                result = {"claimed": False, "file_path": file_path}
                self._file_check_cache[file_path] = (now_mono, result)
                return result

            # Expire if: claim TTL exceeded, session heartbeat stale, or orphaned (no session row)
            owner_heartbeat = row[6]
            claim_expired = row[3] < cutoff
            session_stale = owner_heartbeat is None or owner_heartbeat < stale_cutoff
            if claim_expired or session_stale:
                expired_sid = row[0]
                self._conn.execute("DELETE FROM coord_file_claims WHERE file_path = ?", (file_path,))
                self._commit()
                # Notify OUTSIDE lock (break out, then notify + return)
                break_for_expiry = True
            else:
                break_for_expiry = False

        if break_for_expiry:
            self._notify_resource_available(expired_sid, [file_path], [])
            result = {"claimed": False, "file_path": file_path, "expired_claim": True}
            self._file_check_cache[file_path] = (now_mono, result)
            return result

        result = {
            "claimed": True,
            "file_path": file_path,
            "session_id": row[0],
            "task": row[1],
            "claimed_at": row[2],
            "last_activity": row[3],
            "project": row[4],
            "pid": row[5],
        }
        self._file_check_cache[file_path] = (now_mono, result)
        return result

    def check_branch(self, project: str, branch: str) -> Dict[str, Any]:
        """Check who owns a branch claim (if anyone).

        TTL-aware: claims with last_activity older than BRANCH_CLAIM_TTL_SECONDS
        are automatically expired and deleted.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=BRANCH_CLAIM_TTL_SECONDS)).isoformat()

        with self._lock:
            row = self._conn.execute(
                """SELECT bc.session_id, bc.task, bc.claimed_at, bc.last_activity,
                          s.pid
                   FROM coord_branch_claims bc
                   JOIN coord_sessions s ON bc.session_id = s.session_id
                   WHERE bc.project = ? AND bc.branch = ?""",
                (project, branch),
            ).fetchone()

            if not row:
                return {"claimed": False, "project": project, "branch": branch}

            if row[3] < cutoff:
                expired_sid = row[0]
                self._conn.execute(
                    "DELETE FROM coord_branch_claims WHERE project = ? AND branch = ?", (project, branch)
                )
                self._commit()
                break_for_expiry = True
            else:
                break_for_expiry = False

        if break_for_expiry:
            self._notify_resource_available(expired_sid, [], [(project, branch)])
            return {"claimed": False, "project": project, "branch": branch, "expired_claim": True}

        return {
            "claimed": True,
            "project": project,
            "branch": branch,
            "session_id": row[0],
            "task": row[1],
            "claimed_at": row[2],
            "last_activity": row[3],
            "pid": row[4],
        }

    # ------------------------------------------------------------------
    # Session claims query
    # ------------------------------------------------------------------

    def get_session_claims(self, session_id: str) -> Dict[str, Any]:
        """Return all file and branch claims for a session.

        External callers should use this instead of accessing _conn directly.
        """
        with self._lock:
            file_rows = self._conn.execute(
                "SELECT file_path FROM coord_file_claims WHERE session_id = ?",
                (session_id,),
            ).fetchall()

            branch_rows = self._conn.execute(
                "SELECT branch FROM coord_branch_claims WHERE session_id = ?",
                (session_id,),
            ).fetchall()

        return {
            "session_id": session_id,
            "file_claims": [row[0] for row in file_rows],
            "branch_claims": [row[0] for row in branch_rows],
        }

    # ------------------------------------------------------------------
    # Branch claims
    # ------------------------------------------------------------------

    def claim_branch(
        self,
        session_id: str,
        project: str,
        branch: str,
        task: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Claim exclusive access to a branch."""
        if branch in PROTECTED_BRANCHES:
            return {
                "success": False,
                "error": f"Cannot claim protected branch '{branch}'. Use a feature branch instead.",
                "protected": True,
            }

        # Golden path: auto-register if needed (before lock — avoids deadlock)
        self._ensure_registered(session_id, project)

        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            sess = self._conn.execute(
                "SELECT session_id FROM coord_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not sess:
                return {"success": False, "error": "Session auto-registration failed"}

            existing = self._conn.execute(
                "SELECT session_id, task, last_activity FROM coord_branch_claims WHERE project = ? AND branch = ?",
                (project, branch),
            ).fetchone()

            if existing:
                owner_sid, owner_task, last_activity = existing
                if owner_sid == session_id:
                    self._conn.execute(
                        """UPDATE coord_branch_claims SET last_activity = ?, task = ?
                           WHERE project = ? AND branch = ?""",
                        (now, task, project, branch),
                    )
                    self._commit()
                    return {"success": True, "refreshed": True}

                # Check if claim has expired (TTL-aware)
                cutoff = (datetime.now(timezone.utc) - timedelta(seconds=BRANCH_CLAIM_TTL_SECONDS)).isoformat()
                if last_activity < cutoff:
                    self._conn.execute(
                        """UPDATE coord_branch_claims
                           SET session_id = ?, task = ?, claimed_at = ?, last_activity = ?
                           WHERE project = ? AND branch = ?""",
                        (session_id, task, now, now, project, branch),
                    )
                    self._commit()
                    # Notify previous owner their branch claim was replaced (direct INSERT
                    # because send_message() re-acquires the non-reentrant lock).
                    try:
                        self._conn.execute(
                            """INSERT INTO coord_messages
                               (from_session, to_session, msg_type, subject, body,
                                created_at, priority)
                               VALUES (?, ?, 'inform', ?, ?, ?, 'medium')""",
                            (session_id, owner_sid,
                             f"Branch claim expired: {project}/{branch}",
                             f"Your claim on branch {branch} was replaced by {session_id}",
                             now),
                        )
                        self._commit()
                    except Exception:
                        pass  # fail-open: notification is best-effort
                    return {"success": True, "project": project, "branch": branch, "expired_claim_replaced": True}

                return {
                    "success": False,
                    "conflict": True,
                    "claimed_by": owner_sid,
                    "task": owner_task,
                }

            try:
                self._conn.execute(
                    """INSERT INTO coord_branch_claims (project, branch, session_id, task, claimed_at, last_activity)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (project, branch, session_id, task, now, now),
                )
                self._commit()
            except sqlite3.IntegrityError:
                # Cross-process race: another process claimed between check and insert
                existing = self._conn.execute(
                    "SELECT session_id, task FROM coord_branch_claims WHERE project = ? AND branch = ?",
                    (project, branch),
                ).fetchone()
                if existing:
                    return {
                        "success": False,
                        "conflict": True,
                        "claimed_by": existing[0],
                        "task": existing[1],
                    }

        return {"success": True, "project": project, "branch": branch}

    def release_branch(self, session_id: str, project: str, branch: str) -> Dict[str, Any]:
        """Release a branch claim."""
        with self._lock:
            cursor = self._conn.execute(
                """DELETE FROM coord_branch_claims
                   WHERE project = ? AND branch = ? AND session_id = ?""",
                (project, branch, session_id),
            )
            self._commit()

        if cursor.rowcount == 0:
            return {"released": False, "error": "No matching claim found"}
        self._notify_resource_available(session_id, [], [(project, branch)])
        return {"released": True, "project": project, "branch": branch}

    # ------------------------------------------------------------------
    # Session Role Assignment (behavioral diversity)
    # ------------------------------------------------------------------

    def assign_session_role(self, session_id: str) -> Dict[str, Any]:
        """Assign a structural role based on overlapping concurrent sessions.

        Returns:
            Dict with 'role' ('primary', 'challenger', 'verifier'),
            optional 'peer_approaches' (list of peer intent descriptions),
            and 'role_instruction' (structural prompt for the agent).
        """
        now = datetime.now(timezone.utc).isoformat()

        # Find this session's project
        row = self._conn.execute(
            "SELECT project FROM coord_sessions WHERE session_id = ? AND status = 'active'",
            (session_id,),
        ).fetchone()
        if not row or not row[0]:
            return {"role": "primary", "role_instruction": ""}

        project = row[0]

        # Find other active sessions on the same project, ordered by start time
        peers = self._conn.execute(
            """SELECT s.session_id, s.started_at, i.description
               FROM coord_sessions s
               LEFT JOIN coord_intents i ON s.session_id = i.session_id AND i.expires_at > ?
               WHERE s.project = ? AND s.status = 'active' AND s.session_id != ?
               ORDER BY s.started_at ASC""",
            (now, project, session_id),
        ).fetchall()

        if not peers:
            return {"role": "primary", "role_instruction": ""}

        # Collect peer approaches (from their intents)
        peer_approaches = []
        for peer_sid, _started, desc in peers:
            if desc:
                peer_approaches.append({"session_id": peer_sid[:20], "approach": desc})

        # Determine this session's start order relative to peers
        my_start = self._conn.execute(
            "SELECT started_at FROM coord_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        my_start_ts = my_start[0] if my_start else now

        # Count how many peers started before this session
        earlier_peers = sum(1 for _, started, _ in peers if started < my_start_ts)

        if earlier_peers == 0:
            role = "primary"
            instruction = ""
        elif earlier_peers == 1:
            role = "challenger"
            if peer_approaches:
                approaches_text = "; ".join(
                    f"{p['session_id']}: {p['approach'][:150]}" for p in peer_approaches
                )
                instruction = (
                    f"[CHALLENGER ROLE] A peer session is already working on this domain. "
                    f"Their approach: {approaches_text}. "
                    f"Your job: evaluate weaknesses in their approach, identify what they "
                    f"might have missed, and propose at least one concrete alternative "
                    f"before proceeding with any approach."
                )
            else:
                instruction = (
                    "[CHALLENGER ROLE] A peer session is already working on this domain. "
                    "Your job: take a different angle. Consider alternative approaches, "
                    "edge cases the primary session might miss, and potential failure modes."
                )
        else:
            role = "verifier"
            if peer_approaches:
                approaches_text = "; ".join(
                    f"{p['session_id']}: {p['approach'][:150]}" for p in peer_approaches
                )
                instruction = (
                    f"[VERIFIER ROLE] Multiple sessions are working on this domain. "
                    f"Their approaches: {approaches_text}. "
                    f"Your job: verify assumptions, test edge cases, and identify which "
                    f"approach has better evidence. Focus on correctness over speed."
                )
            else:
                instruction = (
                    "[VERIFIER ROLE] Multiple sessions are working on this domain. "
                    "Your job: verify assumptions, test edge cases, and identify which "
                    "peer approach has better evidence. Focus on correctness over speed."
                )

        result: Dict[str, Any] = {
            "role": role,
            "role_instruction": instruction,
        }
        if peer_approaches:
            result["peer_approaches"] = peer_approaches
        return result

    # ------------------------------------------------------------------
    # Intent Findings (already-explored signal)
    # ------------------------------------------------------------------

    def attach_finding(self, session_id: str, finding_summary: str) -> Dict[str, Any]:
        """Attach a finding to the session's active intent.

        Called when omega_store() creates a decision or lesson_learned.
        Enables "already explored" signals: when another session checks
        intents on the same domain, they see what this session discovered.

        Args:
            session_id: Session that made the finding.
            finding_summary: Brief summary of what was found (max 300 chars).

        Returns:
            Dict with success status and intent_id if attached.
        """
        now = datetime.now(timezone.utc).isoformat()
        finding_summary = finding_summary[:300]

        with self._lock:
            # Find the most recent active intent for this session
            row = self._conn.execute(
                """SELECT id, findings FROM coord_intents
                   WHERE session_id = ? AND expires_at > ?
                   ORDER BY created_at DESC LIMIT 1""",
                (session_id, now),
            ).fetchone()

            if not row:
                return {"success": False, "reason": "no_active_intent"}

            intent_id, existing_findings_json = row
            existing_findings = _safe_json_loads(existing_findings_json, [])
            existing_findings.append(finding_summary)
            # Keep max 10 findings per intent to prevent bloat
            existing_findings = existing_findings[-10:]

            self._conn.execute(
                "UPDATE coord_intents SET findings = ? WHERE id = ?",
                (json.dumps(existing_findings), intent_id),
            )
            self._commit()

        return {"success": True, "intent_id": intent_id, "finding_count": len(existing_findings)}

    # ------------------------------------------------------------------
    # Intents
    # ------------------------------------------------------------------

    def announce_intent(
        self,
        session_id: str,
        description: str,
        intent_type: str = "work",
        target_files: Optional[List[str]] = None,
        target_branch: Optional[str] = None,
        ttl_minutes: int = 30,
    ) -> Dict[str, Any]:
        """Broadcast planned work."""
        # Golden path: auto-register if needed (before lock — avoids deadlock)
        self._ensure_registered(session_id)

        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=ttl_minutes)

        with self._lock:
            sess = self._conn.execute(
                "SELECT session_id FROM coord_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not sess:
                return {"success": False, "error": "Session auto-registration failed"}

            # Deduplicate: merge into existing intent with same session + type
            existing_intent = self._conn.execute(
                """SELECT id, target_files FROM coord_intents
                   WHERE session_id = ? AND intent_type = ? AND expires_at > ?
                   ORDER BY created_at DESC LIMIT 1""",
                (session_id, intent_type, now.isoformat()),
            ).fetchone()

            if existing_intent:
                existing_files = set(_safe_json_loads(existing_intent[1], []))
                merged = existing_files | set(target_files or [])
                self._conn.execute(
                    "UPDATE coord_intents SET target_files = ?, description = ?, expires_at = ? WHERE id = ?",
                    (json.dumps(sorted(merged)), description, expires.isoformat(), existing_intent[0]),
                )
                self._commit()
                return {
                    "success": True,
                    "refreshed_intent": True,
                    "merged_files": len(merged),
                    "description": description,
                    "expires_at": expires.isoformat(),
                }

            self._conn.execute(
                """INSERT INTO coord_intents
                   (session_id, intent_type, description, target_files, target_branch,
                    created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    intent_type,
                    description,
                    json.dumps(target_files or []),
                    target_branch,
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
            self._commit()

        self._cloud_fire(
            "insert_intent", session_id, intent_type, description,
            json.dumps(target_files or []), target_branch,
            now.isoformat(), expires.isoformat(),
        )

        # Backfill session task from first intent (for dashboard visibility)
        try:
            self.update_session_task_if_empty(session_id, description)
        except Exception:
            pass  # Best-effort, don't fail the intent

        result: Dict[str, Any] = {
            "success": True,
            "description": description,
            "expires_at": expires.isoformat(),
        }

        # Check for overlaps inline (outside lock, best-effort)
        try:
            overlap_result = self.check_intents(session_id)
            if overlap_result.get("has_overlaps"):
                result["overlaps"] = overlap_result["overlaps"]
        except Exception:
            pass

        return result

    def check_intents(self, session_id: str) -> Dict[str, Any]:
        """Check if this session's planned files/branch overlap with other agents' intents."""
        now = datetime.now(timezone.utc).isoformat()

        my_intents = self._conn.execute(
            """SELECT target_files, target_branch FROM coord_intents
               WHERE session_id = ? AND expires_at > ?""",
            (session_id, now),
        ).fetchall()

        my_files = set()
        my_branches = set()
        for row in my_intents:
            files = _safe_json_loads(row[0], [])
            my_files.update(files)
            if row[1]:
                my_branches.add(row[1])

        others = self._conn.execute(
            """SELECT i.session_id, i.description, i.target_files, i.target_branch,
                      s.project, s.task, i.findings
               FROM coord_intents i
               JOIN coord_sessions s ON i.session_id = s.session_id
               WHERE i.session_id != ? AND i.expires_at > ?""",
            (session_id, now),
        ).fetchall()

        overlaps = []
        peer_findings = []
        for row in others:
            other_sid, desc, other_files_json, other_branch, project, task, findings_json = row
            other_files = set(_safe_json_loads(other_files_json, []))
            findings = _safe_json_loads(findings_json, [])

            file_overlap = my_files & other_files
            branch_overlap = my_branches & ({other_branch} if other_branch else set())

            if file_overlap or branch_overlap:
                overlap = {
                    "session_id": other_sid,
                    "description": desc,
                    "project": project,
                    "task": task,
                }
                if file_overlap:
                    overlap["overlapping_files"] = list(file_overlap)
                if branch_overlap:
                    overlap["overlapping_branches"] = list(branch_overlap)
                if findings:
                    overlap["findings"] = findings
                overlaps.append(overlap)

            # Surface findings from all peer intents (even without file overlap)
            if findings:
                peer_findings.append({
                    "session_id": other_sid,
                    "description": desc[:100],
                    "findings": findings,
                })

        result: Dict[str, Any] = {
            "has_overlaps": len(overlaps) > 0,
            "overlaps": overlaps,
            "my_files": list(my_files),
            "my_branches": list(my_branches),
        }
        if peer_findings:
            result["peer_findings"] = peer_findings
        return result

    # ------------------------------------------------------------------
    # Message bus
    # ------------------------------------------------------------------

    def send_message(
        self,
        from_session: str,
        subject: str,
        msg_type: str = "inform",
        to_session: Optional[str] = None,
        project: Optional[str] = None,
        body: Optional[str] = None,
        context_id: Optional[str] = None,
        ref_task_id: Optional[int] = None,
        ttl_minutes: Optional[int] = None,
        priority: str = "medium",
    ) -> Dict[str, Any]:
        """Send a message to a specific session or broadcast to a project."""
        valid_types = {"request", "inform", "acknowledge", "reject", "complete"}
        if msg_type not in valid_types:
            return {
                "success": False,
                "error": f"Invalid msg_type '{msg_type}'. Must be one of: {', '.join(sorted(valid_types))}",
            }

        if to_session is None and project is None:
            row = self._conn.execute(
                "SELECT project FROM coord_sessions WHERE session_id = ?", (from_session,)
            ).fetchone()
            if row and row[0]:
                project = row[0]
            else:
                return {"success": False, "error": "Either to_session or project is required for broadcasts"}

        now = datetime.now(timezone.utc)
        expires_at = None
        if ttl_minutes:
            expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat()

        if context_id is None:
            context_id = str(uuid.uuid4())[:8]

        delivered_at = now.isoformat() if priority == "critical" else None

        with self._lock:
            cursor = self._conn.execute(
                """INSERT INTO coord_messages
                   (from_session, to_session, project, msg_type, context_id,
                    subject, body, ref_task_id, created_at, read_at, expires_at,
                    priority, delivered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                (
                    from_session,
                    to_session,
                    project,
                    msg_type,
                    context_id,
                    subject,
                    body,
                    ref_task_id,
                    now.isoformat(),
                    expires_at,
                    priority,
                    delivered_at,
                ),
            )
            self._commit()

        self._cloud_fire(
            "insert_message", from_session, to_session, project, msg_type,
            context_id, subject, body, ref_task_id, now.isoformat(), expires_at,
        )

        return {
            "success": True,
            "message_id": cursor.lastrowid,
            "context_id": context_id,
        }

    def flush_notification_batch(self) -> int:
        """Flush pending batched notifications. Returns count of messages delivered."""
        now = datetime.now(timezone.utc)
        batch_id = uuid.uuid4().hex[:8]
        total_flushed = 0

        with self._lock:
            for priority, cutoff_hours in [("high", 1), ("medium", 3)]:
                cutoff = (now - timedelta(hours=cutoff_hours)).isoformat()
                rows = self._conn.execute(
                    """SELECT id, to_session, project, from_session, subject, msg_type
                       FROM coord_messages
                       WHERE delivered_at IS NULL
                         AND priority = ?
                         AND created_at < ?
                         AND (expires_at IS NULL OR expires_at > ?)""",
                    (priority, cutoff, now.isoformat()),
                ).fetchall()

                if not rows:
                    continue

                msg_ids = [r[0] for r in rows]
                self._conn.execute(
                    f"""UPDATE coord_messages
                        SET delivered_at = ?, batch_id = ?
                        WHERE id IN ({','.join('?' * len(msg_ids))})""",
                    [now.isoformat(), batch_id] + msg_ids,
                )
                _retry_on_locked(self._conn.commit)
                total_flushed += len(rows)

        return total_flushed

    def check_inbox(
        self,
        session_id: str,
        unread_only: bool = True,
        msg_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Check inbox for messages. Marks fetched unread messages as read.

        Direct messages: read_at set on the message row.
        Broadcasts: per-session read tracking via coord_broadcast_reads.
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            sess_row = self._conn.execute(
                "SELECT project FROM coord_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            sess_project = sess_row[0] if sess_row else None

            # Build WHERE clause for direct + broadcast messages
            if sess_project:
                direct = "(to_session = ? AND read_at IS NULL)" if unread_only else "to_session = ?"
                broadcast = (
                    "(to_session IS NULL AND project = ? AND from_session != ?"
                    " AND NOT EXISTS (SELECT 1 FROM coord_broadcast_reads br"
                    " WHERE br.message_id = m.id AND br.session_id = ?))"
                ) if unread_only else (
                    "(to_session IS NULL AND project = ? AND from_session != ?)"
                )
                where = f"({direct} OR {broadcast})"
                params: list = [session_id, sess_project, session_id]
                if unread_only:
                    params.append(session_id)  # for br.session_id = ?
            else:
                where = "to_session = ?"
                params = [session_id]
                if unread_only:
                    where += " AND read_at IS NULL"

            where += " AND (expires_at IS NULL OR expires_at > ?)"
            params.append(now)

            if msg_type:
                where += " AND msg_type = ?"
                params.append(msg_type)

            query = f"""SELECT id, from_session, to_session, project, msg_type,
                               context_id, subject, body, ref_task_id,
                               created_at, read_at, expires_at
                        FROM coord_messages m
                        WHERE {where}
                        ORDER BY created_at DESC
                        LIMIT ?"""
            params.append(limit)

            rows = self._conn.execute(query, params).fetchall()

            messages = []
            unread_direct_ids = []
            unread_broadcast_ids = []
            for r in rows:
                msg = {
                    "id": r[0],
                    "from_session": r[1],
                    "to_session": r[2],
                    "project": r[3],
                    "msg_type": r[4],
                    "context_id": r[5],
                    "subject": r[6],
                    "body": r[7],
                    "ref_task_id": r[8],
                    "created_at": r[9],
                    "read_at": r[10],
                    "expires_at": r[11],
                }
                messages.append(msg)
                if r[10] is None:  # read_at is NULL
                    if r[2] is not None:  # to_session is set — direct message
                        unread_direct_ids.append(r[0])
                    else:  # broadcast
                        unread_broadcast_ids.append(r[0])

            # Mark direct messages as read
            if unread_direct_ids:
                placeholders = ",".join("?" * len(unread_direct_ids))
                self._conn.execute(
                    f"UPDATE coord_messages SET read_at = ? WHERE id IN ({placeholders}) AND to_session = ?",
                    [now] + unread_direct_ids + [session_id],
                )

            # Mark broadcasts as read for this session
            if unread_broadcast_ids:
                for mid in unread_broadcast_ids:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO coord_broadcast_reads (message_id, session_id, read_at) VALUES (?, ?, ?)",
                        (mid, session_id, now),
                    )

            if unread_direct_ids or unread_broadcast_ids:
                self._commit()

        return messages

    def get_unread_count(self, session_id: str) -> int:
        """Get count of unread messages for a session (for heartbeat surfacing)."""
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()

            sess_row = self._conn.execute(
                "SELECT project FROM coord_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            sess_project = sess_row[0] if sess_row else None

            if sess_project:
                where = """(
                    (m.to_session = ? AND (m.expires_at IS NULL OR m.expires_at > ?) AND m.read_at IS NULL)
                    OR
                    (m.to_session IS NULL AND m.project = ? AND m.from_session != ?
                     AND (m.expires_at IS NULL OR m.expires_at > ?)
                     AND NOT EXISTS (SELECT 1 FROM coord_broadcast_reads br
                                     WHERE br.message_id = m.id AND br.session_id = ?))
                )"""
                params: list = [session_id, now, sess_project, session_id, now, session_id]
            else:
                where = "m.to_session = ? AND (m.expires_at IS NULL OR m.expires_at > ?) AND m.read_at IS NULL"
                params = [session_id, now]

            row = self._conn.execute(
                f"SELECT COUNT(*) FROM coord_messages m WHERE {where}",
                params,
            ).fetchone()
            return row[0] if row else 0

    def _prune_expired_messages(self) -> int:
        """Delete expired messages. Call inside _clean_stale_sessions."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "DELETE FROM coord_messages WHERE expires_at IS NOT NULL AND expires_at < ?", (now,)
        )
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Status dashboard
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return coordination dashboard: sessions, claims, intents, conflicts."""
        self._clean_stale_sessions()
        now = datetime.now(timezone.utc).isoformat()

        sessions = self._conn.execute(
            "SELECT session_id, project, task, last_heartbeat FROM coord_sessions WHERE status = 'active'"
        ).fetchall()

        file_claims = self._conn.execute(
            """SELECT fc.file_path, fc.session_id, fc.task, fc.claimed_at
               FROM coord_file_claims fc
               JOIN coord_sessions s ON fc.session_id = s.session_id"""
        ).fetchall()

        branch_claims = self._conn.execute(
            """SELECT bc.project, bc.branch, bc.session_id, bc.task
               FROM coord_branch_claims bc
               JOIN coord_sessions s ON bc.session_id = s.session_id"""
        ).fetchall()

        active_intents = self._conn.execute(
            """SELECT i.session_id, i.description, i.target_files, i.target_branch, i.expires_at
               FROM coord_intents i
               JOIN coord_sessions s ON i.session_id = s.session_id
               WHERE i.expires_at > ?""",
            (now,),
        ).fetchall()

        conflicts = []
        claimed_files = {row[0]: row[1] for row in file_claims}
        for intent_row in active_intents:
            intent_files = _safe_json_loads(intent_row[2], [])
            for f in intent_files:
                if f in claimed_files and claimed_files[f] != intent_row[0]:
                    conflicts.append(
                        {
                            "type": "file_intent_vs_claim",
                            "file": f,
                            "claimed_by": claimed_files[f],
                            "intended_by": intent_row[0],
                        }
                    )

        deadlocks = self.detect_deadlocks()

        return {
            "active_sessions": len(sessions),
            "sessions": [{"session_id": s[0], "project": s[1], "task": s[2], "last_heartbeat": s[3]} for s in sessions],
            "file_claims": len(file_claims),
            "files": [{"path": f[0], "session_id": f[1], "task": f[2]} for f in file_claims],
            "branch_claims": len(branch_claims),
            "branches": [{"project": b[0], "branch": b[1], "session_id": b[2], "task": b[3]} for b in branch_claims],
            "active_intents": len(active_intents),
            "conflicts": conflicts,
            "deadlocks": deadlocks,
        }

    # ------------------------------------------------------------------
    # Recent events (for human-visible coordination activity)
    # ------------------------------------------------------------------

    def get_recent_events(
        self,
        project: str,
        minutes: int = 2,
        limit: int = 5,
        exclude_session: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent coordination events for a project.

        Queries file claims, task state changes, and messages from the last
        N minutes. Returns a unified list sorted by timestamp descending.
        """
        threshold = (
            datetime.now(timezone.utc) - timedelta(minutes=minutes)
        ).isoformat()

        events: List[Dict[str, Any]] = []

        # Recent file claims
        rows = self._conn.execute(
            """SELECT session_id, file_path, claimed_at
               FROM coord_file_claims
               WHERE claimed_at > ? AND EXISTS (
                   SELECT 1 FROM coord_sessions cs
                   WHERE cs.session_id = coord_file_claims.session_id
                   AND cs.project = ?
               )
               ORDER BY claimed_at DESC LIMIT ?""",
            (threshold, project, limit),
        ).fetchall()
        for sid, fpath, ts in rows:
            if exclude_session and sid == exclude_session:
                continue
            events.append({
                "type": "claim",
                "session_id": sid,
                "summary": f"claimed {os.path.basename(fpath)}",
                "timestamp": ts,
            })

        # Recent task state changes (claimed or completed)
        rows = self._conn.execute(
            """SELECT session_id, title, status, claimed_at, completed_at, id
               FROM coord_tasks
               WHERE project = ? AND (
                   (claimed_at IS NOT NULL AND claimed_at > ?)
                   OR (completed_at IS NOT NULL AND completed_at > ?)
               )
               ORDER BY COALESCE(completed_at, claimed_at) DESC LIMIT ?""",
            (project, threshold, threshold, limit),
        ).fetchall()
        for sid, title, status, claimed_at, completed_at, task_id in rows:
            if exclude_session and sid == exclude_session:
                continue
            if completed_at and completed_at > threshold:
                events.append({
                    "type": "task",
                    "session_id": sid or "",
                    "summary": f'completed Task #{task_id} "{title}"',
                    "timestamp": completed_at,
                })
            elif claimed_at and claimed_at > threshold:
                events.append({
                    "type": "task",
                    "session_id": sid or "",
                    "summary": f'claimed Task #{task_id} "{title}"',
                    "timestamp": claimed_at,
                })

        # Recent messages (broadcast or to anyone on project)
        rows = self._conn.execute(
            """SELECT from_session, subject, created_at
               FROM coord_messages
               WHERE created_at > ? AND (project = ? OR project IS NULL)
               ORDER BY created_at DESC LIMIT ?""",
            (threshold, project, limit),
        ).fetchall()
        for from_sid, subject, ts in rows:
            if exclude_session and from_sid == exclude_session:
                continue
            events.append({
                "type": "message",
                "session_id": from_sid,
                "summary": subject[:60],
                "timestamp": ts,
            })

        # Sort by timestamp descending and limit
        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def create_task(
        self,
        created_by: str,
        title: str,
        description: Optional[str] = None,
        project: Optional[str] = None,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Create a task. Use depends_on to chain tasks."""
        # Golden path: auto-register if needed (before lock — avoids deadlock)
        self._ensure_registered(created_by, project)

        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            if depends_on:
                for dep_id in depends_on:
                    dep_row = self._conn.execute("SELECT id FROM coord_tasks WHERE id = ?", (dep_id,)).fetchone()
                    if not dep_row:
                        return {"success": False, "error": f"Dependency task #{dep_id} not found"}

            cursor = self._conn.execute(
                """INSERT INTO coord_tasks
                   (title, description, project, status, priority,
                    created_by, created_at, metadata, result, progress)
                   VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, NULL, 0)""",
                (title, description, project, priority, created_by, now, json.dumps(metadata or {})),
            )
            task_id = cursor.lastrowid

            blocked_by = []
            if depends_on:
                for dep_id in depends_on:
                    self._conn.execute(
                        "INSERT INTO coord_task_deps (task_id, depends_on_id) VALUES (?, ?)",
                        (task_id, dep_id),
                    )
                    dep_status = self._conn.execute("SELECT status FROM coord_tasks WHERE id = ?", (dep_id,)).fetchone()
                    if dep_status and dep_status[0] != "completed":
                        blocked_by.append(dep_id)

            self._commit()

        self._cloud_fire(
            "upsert_task", task_id, title, project, None,
            "pending", priority, created_by, now, None, None, 0, None,
        )

        result: Dict[str, Any] = {"success": True, "task_id": task_id, "title": title}
        if blocked_by:
            result["blocked_by"] = blocked_by
        return result

    def claim_task(self, task_id: int, session_id: str) -> Dict[str, Any]:
        """Claim an unclaimed task. Only pending tasks with all deps completed can be claimed."""
        # Golden path: auto-register if needed (before lock — avoids deadlock)
        self._ensure_registered(session_id)

        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            row = self._conn.execute("SELECT status, session_id FROM coord_tasks WHERE id = ?", (task_id,)).fetchone()

            if not row:
                return {"success": False, "error": "Task not found"}

            status, current_owner = row
            if status != "pending":
                return {
                    "success": False,
                    "error": f"Task is '{status}', not 'pending'",
                    "claimed_by": current_owner,
                }

            # Check all dependencies are completed
            blocked_by = self._conn.execute(
                """SELECT d.depends_on_id FROM coord_task_deps d
                   JOIN coord_tasks t ON d.depends_on_id = t.id
                   WHERE d.task_id = ? AND t.status != 'completed'""",
                (task_id,),
            ).fetchall()
            if blocked_by:
                return {
                    "success": False,
                    "error": "Task is blocked by incomplete dependencies",
                    "blocked_by": [r[0] for r in blocked_by],
                }

            cursor = self._conn.execute(
                """UPDATE coord_tasks
                   SET session_id = ?, status = 'in_progress', claimed_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (session_id, now, task_id),
            )
            if cursor.rowcount == 0:
                # Cross-process race: another process claimed between our check and update
                current = self._conn.execute(
                    "SELECT status, session_id FROM coord_tasks WHERE id = ?", (task_id,)
                ).fetchone()
                return {
                    "success": False,
                    "error": f"Task was concurrently claimed (now '{current[0] if current else 'unknown'}')",
                    "claimed_by": current[1] if current else None,
                }
            self._commit()

            # Read task data for cloud upsert
            task_row = self._conn.execute(
                "SELECT title, project, priority, created_by, created_at FROM coord_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()

        if task_row:
            self._cloud_fire(
                "upsert_task", task_id, task_row[0], task_row[1], session_id,
                "in_progress", task_row[2], task_row[3], task_row[4], now, None, 0, None,
            )

        return {"success": True, "task_id": task_id, "session_id": session_id}

    def next_task(
        self,
        session_id: str,
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find and auto-claim the highest-priority unblocked pending task.

        Atomic find + claim in one call. Returns the task dict if claimed,
        or a message if no tasks are available.
        """
        with self._lock:
            params: list = [project, project] if project else [None, None]
            row = self._conn.execute(
                """SELECT t.id, t.title, t.priority, t.project, t.description, t.progress
                FROM coord_tasks t
                WHERE t.status = 'pending'
                  AND (? IS NULL OR t.project = ?)
                  AND NOT EXISTS (
                    SELECT 1 FROM coord_task_deps d
                    JOIN coord_tasks dep ON d.depends_on_id = dep.id
                    WHERE d.task_id = t.id AND dep.status != 'completed'
                  )
                ORDER BY t.priority DESC, t.created_at ASC
                LIMIT 1""",
                params,
            ).fetchone()

            if not row:
                return {"success": False, "message": "No claimable tasks"}

            task_id = row[0]
            now = datetime.now(timezone.utc).isoformat()
            cursor = self._conn.execute(
                """UPDATE coord_tasks
                   SET session_id = ?, status = 'in_progress', claimed_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (session_id, now, task_id),
            )
            if cursor.rowcount == 0:
                # Cross-process race: another process claimed between SELECT and UPDATE
                self._commit()
                return {"success": False, "message": "Task was concurrently claimed by another agent"}
            self._commit()

        return {
            "success": True,
            "task_id": task_id,
            "title": row[1],
            "priority": row[2],
            "project": row[3],
            "description": row[4],
            "progress": row[5] or 0,
            "session_id": session_id,
        }

    def smart_route_task(
        self,
        session_id: str,
        project: Optional[str] = None,
        goal_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Drift-aware task routing. Claims the best task for this session.

        Scoring: priority * 10 + drift_adjustment + capability_bonus
        - Goals with drift warning: -5 for drifting sessions, +5 for clean
        - Goals with drift critical: -10 for drifting, +10 for clean
        - +3 if session capabilities overlap with goal's target_modules
        - +2 if session has above-average completion speed for project
        Falls back to standard priority ordering if no goal-linked tasks.
        """
        self._ensure_registered(session_id, project=project)

        with self._lock:
            # Fetch all claimable tasks
            params: list = [project, project] if project else [None, None]
            if goal_id is not None:
                rows = self._conn.execute(
                    """SELECT t.id, t.title, t.priority, t.project, t.description,
                              t.progress, t.goal_id
                    FROM coord_tasks t
                    WHERE t.status = 'pending'
                      AND (? IS NULL OR t.project = ?)
                      AND t.goal_id = ?
                      AND NOT EXISTS (
                        SELECT 1 FROM coord_task_deps d
                        JOIN coord_tasks dep ON d.depends_on_id = dep.id
                        WHERE d.task_id = t.id AND dep.status != 'completed'
                      )
                    ORDER BY t.priority DESC, t.created_at ASC""",
                    params + [goal_id],
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT t.id, t.title, t.priority, t.project, t.description,
                              t.progress, t.goal_id
                    FROM coord_tasks t
                    WHERE t.status = 'pending'
                      AND (? IS NULL OR t.project = ?)
                      AND NOT EXISTS (
                        SELECT 1 FROM coord_task_deps d
                        JOIN coord_tasks dep ON d.depends_on_id = dep.id
                        WHERE d.task_id = t.id AND dep.status != 'completed'
                      )
                    ORDER BY t.priority DESC, t.created_at ASC""",
                    params,
                ).fetchall()

            if not rows:
                return {"success": False, "message": "No claimable tasks"}

            # Get session capabilities
            sess_row = self._conn.execute(
                "SELECT capabilities FROM coord_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            session_caps = set()
            if sess_row and sess_row[0]:
                try:
                    session_caps = set(_safe_json_loads(sess_row[0], []))
                except (json.JSONDecodeError, TypeError):
                    pass

            # Get average completion speed for project
            avg_speed_row = self._conn.execute(
                """SELECT AVG(avg_duration_seconds) FROM coord_capability_stats
                   WHERE project = ? AND tasks_completed > 0""",
                (project,),
            ).fetchone()
            project_avg_speed = avg_speed_row[0] if avg_speed_row and avg_speed_row[0] else None

            # Cache drift results per goal to avoid redundant computation
            drift_cache: Dict[int, Dict[str, Any]] = {}

            best_task = None
            best_score = float("-inf")
            best_drift_context = None

            for row in rows:
                task_id, title, priority, task_project, description, progress, task_goal_id = row
                score = (priority or 0) * 10
                drift_context = None

                if task_goal_id is not None:
                    if task_goal_id not in drift_cache:
                        try:
                            drift_cache[task_goal_id] = self.check_drift(task_goal_id)
                        except Exception:
                            drift_cache[task_goal_id] = None

                    drift = drift_cache.get(task_goal_id)
                    if drift:
                        alert = drift.get("alert_level", "none")
                        drift_type = drift.get("drift_type", "none")

                        # Check if this session is contributing to drift
                        is_drifting = self._conn.execute(
                            """SELECT 1 FROM coord_tasks
                               WHERE goal_id = ? AND session_id = ? AND status = 'in_progress'""",
                            (task_goal_id, session_id),
                        ).fetchone() is not None

                        if alert == "warning":
                            score += -5 if is_drifting else 5
                        elif alert == "critical":
                            score += -10 if is_drifting else 10

                        # Capability overlap bonus
                        if session_caps:
                            goal_row = self._conn.execute(
                                "SELECT target_modules FROM coord_goals WHERE id = ?",
                                (task_goal_id,),
                            ).fetchone()
                            if goal_row and goal_row[0]:
                                try:
                                    target_modules = set(_safe_json_loads(goal_row[0], []))
                                    if session_caps & target_modules:
                                        score += 3
                                except (json.JSONDecodeError, TypeError):
                                    pass

                        # Speed bonus: session's capabilities have above-average speed
                        if project_avg_speed and session_caps:
                            for cap in session_caps:
                                cap_row = self._conn.execute(
                                    """SELECT avg_duration_seconds FROM coord_capability_stats
                                       WHERE capability = ? AND project = ? AND tasks_completed > 0""",
                                    (cap, task_project),
                                ).fetchone()
                                if cap_row and cap_row[0] and cap_row[0] < project_avg_speed:
                                    score += 2
                                    break

                        drift_context = {
                            "goal_drift_score": drift["drift_score"],
                            "alert_level": alert,
                            "drift_type": drift_type,
                            "routed_reason": (
                                "clean_session_preferred" if not is_drifting and alert in ("warning", "critical")
                                else "standard_priority" if alert == "none"
                                else "drift_penalized" if is_drifting
                                else "standard_priority"
                            ),
                        }

                if score > best_score:
                    best_score = score
                    best_task = row
                    best_drift_context = drift_context

            if best_task is None:
                return {"success": False, "message": "No claimable tasks"}

            task_id = best_task[0]
            now = datetime.now(timezone.utc).isoformat()
            cursor = self._conn.execute(
                """UPDATE coord_tasks
                   SET session_id = ?, status = 'in_progress', claimed_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (session_id, now, task_id),
            )
            if cursor.rowcount == 0:
                # Cross-process race: another process claimed between SELECT and UPDATE
                self._commit()
                return {"success": False, "message": "Task was concurrently claimed by another agent"}
            self._commit()

        result: Dict[str, Any] = {
            "success": True,
            "task_id": task_id,
            "title": best_task[1],
            "priority": best_task[2],
            "project": best_task[3],
            "description": best_task[4],
            "progress": best_task[5] or 0,
            "session_id": session_id,
            "effective_score": best_score,
        }
        if best_drift_context:
            result["drift_context"] = best_drift_context
        return result

    def _update_capability_stats(self, session_id: str, task_id: int, duration_seconds: float) -> None:
        """Update capability stats when a task completes. Called inside complete_task."""
        now = datetime.now(timezone.utc).isoformat()
        # Get session capabilities and task project
        sess_row = self._conn.execute(
            "SELECT capabilities FROM coord_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        task_row = self._conn.execute(
            "SELECT project FROM coord_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if not sess_row or not sess_row[0] or not task_row:
            return
        try:
            caps = json.loads(sess_row[0])
        except (json.JSONDecodeError, TypeError):
            return
        project = task_row[0]
        for cap in caps:
            existing = self._conn.execute(
                "SELECT tasks_completed, total_duration_seconds FROM coord_capability_stats WHERE capability = ? AND project = ?",
                (cap, project),
            ).fetchone()
            if existing:
                new_count = existing[0] + 1
                new_total = existing[1] + duration_seconds
                new_avg = new_total / new_count
                self._conn.execute(
                    """UPDATE coord_capability_stats
                       SET tasks_completed = ?, total_duration_seconds = ?,
                           avg_duration_seconds = ?, last_updated = ?
                       WHERE capability = ? AND project = ?""",
                    (new_count, new_total, new_avg, now, cap, project),
                )
            else:
                self._conn.execute(
                    """INSERT INTO coord_capability_stats
                       (capability, project, tasks_completed, total_duration_seconds,
                        avg_duration_seconds, last_updated)
                       VALUES (?, ?, 1, ?, ?, ?)""",
                    (cap, project, duration_seconds, duration_seconds, now),
                )

    def complete_task(
        self,
        task_id: int,
        session_id: str,
        result: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mark a task as completed. Auto-notifies creators of unblocked tasks.

        Unclaimed tasks can only be completed by the task creator.
        Claimed tasks can only be completed by the owning session.
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            row = self._conn.execute(
                "SELECT status, session_id, title, created_by FROM coord_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()

            if not row:
                return {"success": False, "error": "Task not found"}

            status, owner, title, created_by = row
            if status == "completed":
                return {"success": False, "error": "Task already completed"}
            if not owner:
                if created_by != session_id:
                    return {
                        "success": False,
                        "error": "Task is unclaimed — only the creator can complete it",
                    }
            elif owner != session_id:
                return {
                    "success": False,
                    "error": "Task is claimed by another session",
                    "claimed_by": owner,
                }

            self._conn.execute(
                """UPDATE coord_tasks
                   SET status = 'completed', completed_at = ?, result = ?,
                       session_id = COALESCE(session_id, ?)
                   WHERE id = ?""",
                (now, result, session_id, task_id),
            )

            # Find tasks that are now unblocked
            unblocked_tasks = []
            dependents = self._conn.execute(
                "SELECT task_id FROM coord_task_deps WHERE depends_on_id = ?", (task_id,)
            ).fetchall()

            for (dep_task_id,) in dependents:
                still_blocked = self._conn.execute(
                    """SELECT COUNT(*) FROM coord_task_deps d
                       JOIN coord_tasks t ON d.depends_on_id = t.id
                       WHERE d.task_id = ? AND t.status != 'completed'""",
                    (dep_task_id,),
                ).fetchone()
                if still_blocked and still_blocked[0] == 0:
                    dep_info = self._conn.execute(
                        "SELECT title, created_by FROM coord_tasks WHERE id = ?", (dep_task_id,)
                    ).fetchone()
                    if dep_info:
                        unblocked_tasks.append(
                            {
                                "task_id": dep_task_id,
                                "title": dep_info[0],
                                "created_by": dep_info[1],
                            }
                        )

            # Read task data for cloud upsert before releasing lock
            ct_row = self._conn.execute(
                "SELECT title, project, priority, created_by, created_at, claimed_at FROM coord_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()

            self._commit()

        if ct_row:
            self._cloud_fire(
                "upsert_task", task_id, ct_row[0], ct_row[1], session_id,
                "completed", ct_row[2], ct_row[3], ct_row[4], ct_row[5], now, 100, result,
            )

        # Update capability stats (best-effort)
        try:
            with self._lock:
                claimed_at_row = self._conn.execute(
                    "SELECT claimed_at FROM coord_tasks WHERE id = ?", (task_id,)
                ).fetchone()
                if claimed_at_row and claimed_at_row[0]:
                    claimed_dt = datetime.fromisoformat(claimed_at_row[0].replace("Z", "+00:00"))
                    if claimed_dt.tzinfo is None:
                        claimed_dt = claimed_dt.replace(tzinfo=timezone.utc)
                    now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
                    if now_dt.tzinfo is None:
                        now_dt = now_dt.replace(tzinfo=timezone.utc)
                    duration = (now_dt - claimed_dt).total_seconds()
                    if duration > 0:
                        self._update_capability_stats(session_id, task_id, duration)
                        self._commit()
        except Exception:
            pass

        # Auto-notify creators of unblocked tasks (outside lock)
        for ut in unblocked_tasks:
            try:
                self.send_message(
                    from_session=session_id,
                    subject=f"Task #{ut['task_id']} '{ut['title']}' is now unblocked",
                    msg_type="inform",
                    to_session=ut["created_by"],
                    body=f"Dependency #{task_id} completed. Task #{ut['task_id']} is ready to claim.",
                    ref_task_id=ut["task_id"],
                )
            except Exception:
                pass

        resp: Dict[str, Any] = {"success": True, "task_id": task_id}
        if unblocked_tasks:
            resp["unblocked_tasks"] = [{"task_id": ut["task_id"], "title": ut["title"]} for ut in unblocked_tasks]
        return resp

    def _notify_blocked_dependents(
        self,
        task_id: int,
        session_id: str,
        terminal_status: str,
        reason: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Notify creators of dependent tasks that are now permanently blocked.
        Call OUTSIDE the lock.
        """
        affected = []
        try:
            dependents = self._conn.execute(
                """SELECT d.task_id, t.title, t.created_by
                   FROM coord_task_deps d
                   JOIN coord_tasks t ON d.task_id = t.id
                   WHERE d.depends_on_id = ? AND t.status = 'pending'""",
                (task_id,),
            ).fetchall()
            for dep_task_id, dep_title, dep_creator in dependents:
                affected.append({"task_id": dep_task_id, "title": dep_title})
                try:
                    reason_str = f": {reason}" if reason else ""
                    self.send_message(
                        from_session=session_id,
                        subject=f"Task #{dep_task_id} blocked: dependency #{task_id} {terminal_status}",
                        msg_type="inform",
                        to_session=dep_creator,
                        body=f"Task #{task_id} {terminal_status}{reason_str}. "
                        f"Task #{dep_task_id} '{dep_title}' depends on it and cannot proceed.",
                        ref_task_id=dep_task_id,
                    )
                except Exception:
                    pass
        except Exception:
            pass
        return affected

    def _notify_resource_available(
        self,
        releasing_session: str,
        released_files: List[str],
        released_branches: List[tuple],
    ) -> None:
        """Notify agents with intents targeting released resources.

        Call OUTSIDE the lock (after commit), matching existing notification patterns.
        All fail-open — errors are silently swallowed per notification.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        notified: set = set()  # (session_id, resource) to avoid duplicates

        # Fetch all active intents once, filter by file membership in Python
        try:
            intent_rows = self._conn.execute(
                """SELECT i.session_id, i.target_files
                   FROM coord_intents i
                   JOIN coord_sessions s ON i.session_id = s.session_id
                   WHERE i.session_id != ? AND i.expires_at > ?
                     AND i.target_files IS NOT NULL""",
                (releasing_session, now_str),
            ).fetchall()
        except Exception:
            intent_rows = []

        for file_path in released_files:
            for row in intent_rows:
                try:
                    target_files = _safe_json_loads(row[1], [])
                    if file_path not in target_files:
                        continue
                    key = (row[0], file_path)
                    if key in notified:
                        continue
                    notified.add(key)
                    filename = os.path.basename(file_path)
                    self.send_message(
                        from_session=releasing_session,
                        subject=f"[AVAILABLE] {filename} is now free",
                        msg_type="inform",
                        to_session=row[0],
                        body=f"{file_path} has been released and is available for claiming.",
                        ttl_minutes=30,
                    )
                except Exception:
                    pass

        for proj, branch in released_branches:
            try:
                waiting = self._conn.execute(
                    """SELECT i.session_id
                       FROM coord_intents i
                       JOIN coord_sessions s ON i.session_id = s.session_id
                       WHERE i.session_id != ? AND i.expires_at > ?
                         AND i.target_branch = ?""",
                    (releasing_session, now_str, branch),
                ).fetchall()
                for row in waiting:
                    key = (row[0], f"{proj}:{branch}")
                    if key in notified:
                        continue
                    notified.add(key)
                    try:
                        self.send_message(
                            from_session=releasing_session,
                            subject=f"[AVAILABLE] branch {branch} is now free",
                            msg_type="inform",
                            to_session=row[0],
                            body=f"Branch {branch} (project {proj}) has been released and is available for claiming.",
                            ttl_minutes=30,
                        )
                    except Exception:
                        pass
            except Exception:
                pass

    def _notify_expired_claims(
        self,
        expired_files: List[tuple],
        expired_branches: List[tuple],
    ) -> None:
        """Notify agents with intents targeting expired claims.

        Groups expired claims by session_id and delegates to _notify_resource_available.
        Call OUTSIDE the lock.
        """
        # Group by session_id: {sid: (files, branches)}
        by_session: Dict[str, tuple] = {}
        for sid, file_path in expired_files:
            entry = by_session.setdefault(sid, ([], []))
            entry[0].append(file_path)
        for sid, project, branch in expired_branches:
            entry = by_session.setdefault(sid, ([], []))
            entry[1].append((project, branch))

        for sid, (files, branches) in by_session.items():
            self._notify_resource_available(sid, files, branches)

    def fail_task(
        self,
        task_id: int,
        session_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mark a task as failed. Notifies creators of blocked dependent tasks."""
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            row = self._conn.execute(
                "SELECT status, session_id, created_by FROM coord_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()

            if not row:
                return {"success": False, "error": "Task not found"}

            status, owner, created_by = row
            if status in ("completed", "failed", "canceled"):
                return {"success": False, "error": f"Task is already '{status}'"}
            if not owner:
                if created_by != session_id:
                    return {
                        "success": False,
                        "error": "Task is unclaimed — only the creator can fail it",
                    }
            elif owner != session_id:
                return {"success": False, "error": "Task is claimed by another session", "claimed_by": owner}

            self._conn.execute(
                """UPDATE coord_tasks
                   SET status = 'failed', completed_at = ?, result = ?,
                       session_id = COALESCE(session_id, ?)
                   WHERE id = ?""",
                (now, reason, session_id, task_id),
            )
            self._commit()

        affected = self._notify_blocked_dependents(task_id, session_id, "failed", reason)
        resp: Dict[str, Any] = {"success": True, "task_id": task_id, "status": "failed"}
        if affected:
            resp["blocked_dependents"] = affected
        return resp

    def cancel_task(self, task_id: int, session_id: str) -> Dict[str, Any]:
        """Mark a task as canceled. Notifies creators of blocked dependent tasks."""
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            row = self._conn.execute(
                "SELECT status, session_id, created_by FROM coord_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()

            if not row:
                return {"success": False, "error": "Task not found"}

            status, owner, created_by = row
            if status in ("completed", "failed", "canceled"):
                return {"success": False, "error": f"Task is already '{status}'"}
            if not owner:
                if created_by != session_id:
                    return {
                        "success": False,
                        "error": "Task is unclaimed — only the creator can cancel it",
                    }
            elif owner != session_id:
                return {"success": False, "error": "Task is claimed by another session", "claimed_by": owner}

            self._conn.execute(
                """UPDATE coord_tasks
                   SET status = 'canceled', completed_at = ?,
                       session_id = COALESCE(session_id, ?)
                   WHERE id = ?""",
                (now, session_id, task_id),
            )
            self._commit()

        affected = self._notify_blocked_dependents(task_id, session_id, "canceled")
        resp: Dict[str, Any] = {"success": True, "task_id": task_id, "status": "canceled"}
        if affected:
            resp["blocked_dependents"] = affected
        return resp

    def get_task_deps(self, task_id: int) -> Dict[str, Any]:
        """Get dependency info for a task."""
        row = self._conn.execute("SELECT id FROM coord_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return {"error": "Task not found"}

        depends_on = self._conn.execute(
            """SELECT d.depends_on_id, t.title, t.status
               FROM coord_task_deps d JOIN coord_tasks t ON d.depends_on_id = t.id
               WHERE d.task_id = ?""",
            (task_id,),
        ).fetchall()

        depended_by = self._conn.execute(
            """SELECT d.task_id, t.title, t.status
               FROM coord_task_deps d JOIN coord_tasks t ON d.task_id = t.id
               WHERE d.depends_on_id = ?""",
            (task_id,),
        ).fetchall()

        blocked = any(r[2] != "completed" for r in depends_on)

        return {
            "task_id": task_id,
            "depends_on": [{"task_id": r[0], "title": r[1], "status": r[2]} for r in depends_on],
            "depended_by": [{"task_id": r[0], "title": r[1], "status": r[2]} for r in depended_by],
            "blocked": blocked,
        }

    def update_task_progress(
        self,
        task_id: int,
        session_id: str,
        progress: int,
        status_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update progress (0-100) for a task. Only the claiming session can update."""
        progress = max(0, min(100, progress))

        with self._lock:
            row = self._conn.execute(
                "SELECT status, session_id, metadata FROM coord_tasks WHERE id = ?", (task_id,)
            ).fetchone()

            if not row:
                return {"success": False, "error": "Task not found"}

            status, owner, meta_json = row
            if status != "in_progress":
                return {"success": False, "error": f"Task is '{status}', not 'in_progress'"}
            if owner != session_id:
                return {"success": False, "error": "Only the claiming session can update progress", "claimed_by": owner}

            if status_note:
                meta = _safe_json_loads(meta_json)
                meta["status_note"] = status_note
                self._conn.execute(
                    "UPDATE coord_tasks SET progress = ?, metadata = ? WHERE id = ?",
                    (progress, json.dumps(meta), task_id),
                )
            else:
                self._conn.execute("UPDATE coord_tasks SET progress = ? WHERE id = ?", (progress, task_id))

            # Read task data for cloud upsert
            tp_row = self._conn.execute(
                "SELECT title, project, priority, created_by, created_at, claimed_at FROM coord_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            self._commit()

        if tp_row:
            self._cloud_fire(
                "upsert_task", task_id, tp_row[0], tp_row[1], session_id,
                "in_progress", tp_row[2], tp_row[3], tp_row[4], tp_row[5], None, progress, None,
            )

        return {"success": True, "task_id": task_id, "progress": progress}

    def has_active_task(self, session_id: str) -> Dict[str, Any]:
        """Check if session has any in_progress task.

        Returns dict with 'has_task' bool and optional 'task_id'/'title'.
        Used by pre_task_guard to enforce task declaration.
        """
        row = self._conn.execute(
            """SELECT id, title FROM coord_tasks
               WHERE session_id = ? AND status = 'in_progress'
               LIMIT 1""",
            (session_id,),
        ).fetchone()
        if row:
            return {"has_task": True, "task_id": row[0], "title": row[1]}
        return {"has_task": False}

    def project_has_active_tasks(self, project: str) -> bool:
        """Check if project has any pending/in_progress tasks.

        When False, task enforcement is disabled for this project (opt-in).
        Projects that haven't started using tasks are unaffected.
        """
        row = self._conn.execute(
            """SELECT COUNT(*) FROM coord_tasks
               WHERE project = ? AND status IN ('pending', 'in_progress')""",
            (project,),
        ).fetchone()
        return (row[0] if row else 0) > 0

    def list_tasks(
        self,
        project: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional project/status filters."""
        query = "SELECT id, title, description, project, session_id, status, priority, created_by, created_at, claimed_at, completed_at, metadata, result, progress FROM coord_tasks"
        conditions = []
        params: list = []

        if project:
            conditions.append("project = ?")
            params.append(project)
        if status:
            conditions.append("status = ?")
            params.append(status)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY priority DESC, created_at ASC"

        rows = self._conn.execute(query, params).fetchall()

        # Batch-fetch all deps for the returned tasks (avoids N+1)
        task_ids = [r[0] for r in rows]
        deps_by_task: Dict[int, list] = {}
        if task_ids:
            placeholders = ",".join("?" * len(task_ids))
            dep_rows = self._conn.execute(
                f"""SELECT d.task_id, d.depends_on_id, t.status
                    FROM coord_task_deps d
                    JOIN coord_tasks t ON d.depends_on_id = t.id
                    WHERE d.task_id IN ({placeholders})""",
                task_ids,
            ).fetchall()
            for task_id, dep_id, dep_status in dep_rows:
                deps_by_task.setdefault(task_id, []).append((dep_id, dep_status))

        tasks = []
        for r in rows:
            task_dict: Dict[str, Any] = {
                "id": r[0],
                "title": r[1],
                "description": r[2],
                "project": r[3],
                "session_id": r[4],
                "status": r[5],
                "priority": r[6],
                "created_by": r[7],
                "created_at": r[8],
                "claimed_at": r[9],
                "completed_at": r[10],
                "metadata": _safe_json_loads(r[11]),
                "result": r[12],
                "progress": r[13] or 0,
            }

            deps = deps_by_task.get(r[0], [])
            if deps:
                task_dict["depends_on"] = [d[0] for d in deps]
                task_dict["blocked"] = any(d[1] != "completed" for d in deps)
            else:
                task_dict["blocked"] = False

            tasks.append(task_dict)
        return tasks

    def find_similar_tasks(
        self,
        title: str,
        project: Optional[str] = None,
        statuses: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Find pending/in_progress tasks with keyword overlap to the given title.

        Used to warn agents about potential duplicate work before creating tasks.
        Returns tasks whose titles share significant keywords with the input.
        """
        if statuses is None:
            statuses = ["pending", "in_progress"]

        # Extract meaningful keywords (3+ chars, lowercased)
        stop_words = {
            "the", "and", "for", "with", "from", "this", "that", "into",
            "task", "fix", "add", "update", "implement", "create", "make",
        }
        keywords = {
            w.lower()
            for w in title.split()
            if len(w) >= 3 and w.lower() not in stop_words
        }
        if not keywords:
            return []

        placeholders = ",".join("?" * len(statuses))
        query = f"""SELECT id, title, description, project, session_id, status,
                           created_by, priority
                    FROM coord_tasks
                    WHERE status IN ({placeholders})"""
        params: list = list(statuses)

        if project:
            query += " AND project = ?"
            params.append(project)

        rows = self._conn.execute(query, params).fetchall()

        similar = []
        for r in rows:
            existing_title = r[1] or ""
            existing_words = {
                w.lower()
                for w in existing_title.split()
                if len(w) >= 3 and w.lower() not in stop_words
            }
            overlap = keywords & existing_words
            # Require at least 1 keyword overlap and >= 30% Jaccard similarity
            if overlap:
                jaccard = len(overlap) / len(keywords | existing_words)
                if jaccard >= 0.3:
                    similar.append({
                        "id": r[0],
                        "title": r[1],
                        "description": r[2],
                        "project": r[3],
                        "session_id": r[4],
                        "status": r[5],
                        "created_by": r[6],
                        "priority": r[7],
                        "overlap_keywords": sorted(overlap),
                        "similarity": round(jaccard, 2),
                    })

        # Sort by similarity descending
        similar.sort(key=lambda x: x["similarity"], reverse=True)
        return similar

    # ------------------------------------------------------------------
    # Capability routing
    # ------------------------------------------------------------------

    def find_capable_sessions(
        self,
        capability: str,
        project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find active sessions with a matching capability (case-insensitive substring)."""
        self._maybe_clean_stale()
        capability_lower = capability.lower()

        query = (
            "SELECT session_id, project, task, capabilities, last_heartbeat FROM coord_sessions WHERE status = 'active'"
        )
        params: list = []
        if project:
            query += " AND project = ?"
            params.append(project)

        rows = self._conn.execute(query, params).fetchall()
        matches = []
        for sid, proj, task, caps_json, hb in rows:
            caps = _safe_json_loads(caps_json, [])
            if any(capability_lower in c.lower() for c in caps):
                current_task = self._conn.execute(
                    """SELECT id, title FROM coord_tasks
                       WHERE session_id = ? AND status = 'in_progress'
                       ORDER BY claimed_at DESC LIMIT 1""",
                    (sid,),
                ).fetchone()

                entry: Dict[str, Any] = {
                    "session_id": sid,
                    "project": proj,
                    "task": task,
                    "capabilities": caps,
                    "last_heartbeat": hb,
                }
                if current_task:
                    entry["current_task"] = {"id": current_task[0], "title": current_task[1]}
                matches.append(entry)

        return matches

    # ------------------------------------------------------------------
    # Auto-release committed files
    # ------------------------------------------------------------------

    def release_committed_files(
        self,
        session_id: str,
        project: str,
        committed_files: List[str],
    ) -> Dict[str, Any]:
        """Release file claims for committed files. Idempotent."""
        released = []
        with self._lock:
            for fpath in committed_files:
                cursor = self._conn.execute(
                    "DELETE FROM coord_file_claims WHERE file_path = ? AND session_id = ?", (fpath, session_id)
                )
                if cursor.rowcount > 0:
                    released.append(fpath)
            if released:
                self._commit()

        return {"released_count": len(released), "released_files": released}

    # ------------------------------------------------------------------
    # Deadlock detection
    # ------------------------------------------------------------------

    def detect_deadlocks(self) -> List[List[str]]:
        """Detect circular wait-for dependencies between sessions."""
        now = datetime.now(timezone.utc).isoformat()

        wants: Dict[str, set] = {}
        intent_rows = self._conn.execute(
            """SELECT i.session_id, i.target_files
               FROM coord_intents i
               JOIN coord_sessions s ON i.session_id = s.session_id
               WHERE i.expires_at > ?""",
            (now,),
        ).fetchall()
        for sid, target_files_json in intent_rows:
            files = _safe_json_loads(target_files_json, [])
            if files:
                wants.setdefault(sid, set()).update(files)

        held_by: Dict[str, str] = {}
        claim_rows = self._conn.execute("SELECT file_path, session_id FROM coord_file_claims").fetchall()
        for fpath, sid in claim_rows:
            held_by[fpath] = sid

        wait_for: Dict[str, set] = {}
        for sid, wanted_files in wants.items():
            for f in wanted_files:
                holder = held_by.get(f)
                if holder and holder != sid:
                    wait_for.setdefault(sid, set()).add(holder)

        cycles = []
        visited: set = set()

        def dfs(node: str, path: list, path_set: set):
            if node in path_set:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            path_set.add(node)
            for neighbor in wait_for.get(node, set()):
                dfs(neighbor, path, path_set)
            path.pop()
            path_set.discard(node)

        for node in wait_for:
            if node not in visited:
                dfs(node, [], set())

        for cycle in cycles:
            self.record_metric("deadlock_cycle", metadata={"cycle": cycle})

        return cycles

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def log_audit(
        self,
        tool_name: str,
        session_id: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
        result_summary: Optional[str] = None,
        latency_ms: Optional[int] = None,
        call_index: Optional[int] = None,
        result_status: str = "ok",
        input_size: Optional[int] = None,
    ) -> int:
        """Buffer a coordination tool call for batched insert into coord_audit."""
        now = datetime.now(timezone.utc).isoformat()
        row = (
            session_id,
            tool_name,
            json.dumps(arguments) if arguments else None,
            result_summary,
            now,
            latency_ms,
            call_index,
            result_status,
            input_size,
        )

        with self._audit_buffer_lock:
            self._audit_buffer.append(row)
            should_flush = (
                len(self._audit_buffer) >= _AUDIT_BATCH_SIZE
                or time.monotonic() - self._audit_last_flush >= _AUDIT_FLUSH_INTERVAL_S
            )

        if should_flush:
            self.flush_audit_buffer()

        if session_id:
            self._cloud_fire(
                "insert_audit", session_id, tool_name, result_summary,
                now, call_index, result_status, input_size, latency_ms,
            )

        return 0  # No real rowid until flush

    def flush_audit_buffer(self) -> int:
        """Flush buffered audit rows to DB in a single transaction."""
        with self._audit_buffer_lock:
            if not self._audit_buffer:
                return 0
            rows = self._audit_buffer[:]
            self._audit_buffer.clear()
            self._audit_last_flush = time.monotonic()

        with self._lock:
            self._conn.executemany(
                """INSERT INTO coord_audit
                   (session_id, tool_name, arguments, result_summary, created_at,
                    latency_ms, call_index, result_status, input_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            self._commit()

        return len(rows)

    def query_audit(
        self,
        session_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query the audit log with optional filters."""
        self.flush_audit_buffer()
        query = """SELECT id, session_id, tool_name, arguments, result_summary,
                          created_at, latency_ms, call_index, result_status, input_size
                   FROM coord_audit"""
        conditions = []
        params: list = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if tool_name:
            conditions.append("tool_name = ?")
            params.append(tool_name)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "tool_name": r[2],
                "arguments": _safe_json_loads(r[3]),
                "result_summary": r[4],
                "created_at": r[5],
                "latency_ms": r[6],
                "call_index": r[7],
                "result_status": r[8],
                "input_size": r[9],
            }
            for r in rows
        ]

    def _prune_audit(self) -> int:
        """Delete audit entries older than AUDIT_RETENTION_DAYS. Call inside _lock."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=AUDIT_RETENTION_DAYS)).isoformat()
        cursor = self._conn.execute("DELETE FROM coord_audit WHERE created_at < ?", (cutoff,))
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Session snapshots (session recovery)
    # ------------------------------------------------------------------

    def _capture_git_state(self, project: str) -> Dict[str, Any]:
        """Capture current git branch and dirty files for a project directory.

        """
        result: Dict[str, Any] = {}
        try:
            branch = subprocess.run(
                ["git", "-C", project, "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if branch.returncode == 0 and branch.stdout.strip():
                result["git_branch"] = branch.stdout.strip()

            status = subprocess.run(
                ["git", "-C", project, "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if status.returncode == 0 and status.stdout.strip():
                dirty = [line[3:].strip() for line in status.stdout.strip().split("\n") if line.strip()]
                result["git_dirty_files"] = dirty
        except Exception:
            pass
        return result

    def enrich_session_metadata(self, session_id: str, project: str) -> None:
        """Merge git state into session metadata before deregister snapshots it."""
        if not project:
            return
        git_state = self._capture_git_state(project)
        if not git_state:
            return
        with self._lock:
            row = self._conn.execute(
                "SELECT metadata FROM coord_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return
            meta = _safe_json_loads(row[0])
            meta.update(git_state)
            self._conn.execute(
                "UPDATE coord_sessions SET metadata = ? WHERE session_id = ?",
                (json.dumps(meta), session_id),
            )
            self._commit()

    def _snapshot_session(self, session_id: str, reason: str) -> Optional[int]:
        """Capture session state into coord_snapshots before deletion.
        Must be called while self._lock is held.
        """
        sess = self._conn.execute(
            "SELECT pid, project, task, metadata, capabilities FROM coord_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not sess:
            return None

        pid, project, task, meta, caps_json = sess
        # Merge capabilities into metadata so _auto_reregister can recover them
        meta_dict = _safe_json_loads(meta)
        caps = _safe_json_loads(caps_json, [])
        if caps:
            meta_dict["capabilities"] = caps
            meta = json.dumps(meta_dict)

        file_rows = self._conn.execute(
            "SELECT file_path, task FROM coord_file_claims WHERE session_id = ?", (session_id,)
        ).fetchall()
        file_claims = [{"file_path": r[0], "task": r[1]} for r in file_rows]

        branch_rows = self._conn.execute(
            "SELECT project, branch, task FROM coord_branch_claims WHERE session_id = ?", (session_id,)
        ).fetchall()
        branch_claims = [{"project": r[0], "branch": r[1], "task": r[2]} for r in branch_rows]

        intent_rows = self._conn.execute(
            "SELECT description, target_files, target_branch FROM coord_intents WHERE session_id = ?", (session_id,)
        ).fetchall()
        intents = [
            {"description": r[0], "target_files": _safe_json_loads(r[1], []), "target_branch": r[2]}
            for r in intent_rows
        ]

        if not file_claims and not branch_claims and not intents and not task:
            return None

        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """INSERT INTO coord_snapshots
               (session_id, project, task, pid, file_claims, branch_claims,
                intents, metadata, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                project,
                task,
                pid,
                json.dumps(file_claims),
                json.dumps(branch_claims),
                json.dumps(intents),
                meta,
                reason,
                now,
            ),
        )
        return cursor.lastrowid

    def snapshot_session(self, session_id: str, reason: str = "manual") -> Dict[str, Any]:
        """Public wrapper: snapshot a session's state."""
        with self._lock:
            snap_id = self._snapshot_session(session_id, reason)
        if snap_id is None:
            return {"success": False, "error": "Session not found or has no meaningful state"}
        return {"success": True, "snapshot_id": snap_id, "reason": reason}

    def recover_session(self, project: str, limit: int = 1) -> List[Dict[str, Any]]:
        """Retrieve recent snapshots for a project."""
        rows = self._conn.execute(
            """SELECT id, session_id, project, task, pid, file_claims, branch_claims,
                      intents, metadata, reason, created_at
               FROM coord_snapshots WHERE project = ? ORDER BY created_at DESC LIMIT ?""",
            (project, limit),
        ).fetchall()

        return [
            {
                "id": r[0],
                "session_id": r[1],
                "project": r[2],
                "task": r[3],
                "pid": r[4],
                "file_claims": _safe_json_loads(r[5], []),
                "branch_claims": _safe_json_loads(r[6], []),
                "intents": _safe_json_loads(r[7], []),
                "metadata": _safe_json_loads(r[8]),
                "reason": r[9],
                "created_at": r[10],
            }
            for r in rows
        ]

    def _prune_snapshots(self) -> int:
        """Delete snapshots older than SNAPSHOT_RETENTION_DAYS. Call inside _lock."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_RETENTION_DAYS)).isoformat()
        cursor = self._conn.execute("DELETE FROM coord_snapshots WHERE created_at < ?", (cutoff,))
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Stale cleanup
    # ------------------------------------------------------------------

    def _maybe_clean_stale(self) -> None:
        """Run stale session cleanup at most once per 5 minutes.

        Rate-limit check runs outside the lock to avoid contention.
        """
        now = time.monotonic()
        if now - self._last_stale_cleanup < 300:
            return
        self._last_stale_cleanup = now
        self._clean_stale_sessions()

    def _clean_expired_claims(self) -> List[tuple]:
        """Delete file claims with last_activity older than CLAIM_TTL_SECONDS.
        Must be called while self._lock is held.

        Returns list of (session_id, file_path) for expired claims, so callers
        can notify waiting agents outside the lock.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_SECONDS)).isoformat()
        expired = self._conn.execute(
            "SELECT session_id, file_path FROM coord_file_claims WHERE last_activity < ?", (cutoff,)
        ).fetchall()
        if expired:
            self._conn.execute("DELETE FROM coord_file_claims WHERE last_activity < ?", (cutoff,))
        return [(r[0], r[1]) for r in expired]

    def _clean_expired_branch_claims(self) -> List[tuple]:
        """Delete branch claims with last_activity older than BRANCH_CLAIM_TTL_SECONDS.
        Must be called while self._lock is held.

        Returns list of (session_id, project, branch) for expired claims, so callers
        can notify waiting agents outside the lock.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=BRANCH_CLAIM_TTL_SECONDS)).isoformat()
        expired = self._conn.execute(
            "SELECT session_id, project, branch FROM coord_branch_claims WHERE last_activity < ?", (cutoff,)
        ).fetchall()
        if expired:
            self._conn.execute("DELETE FROM coord_branch_claims WHERE last_activity < ?", (cutoff,))
        return [(r[0], r[1], r[2]) for r in expired]

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """Check if a process with the given PID is still running."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # process exists but we can't signal it
        except OSError:
            return False

    def _clean_stale_sessions(self) -> int:
        """Remove sessions with stale heartbeat or dead PIDs.

        Checks both 'active' and 'stopped' sessions — the latter covers cases
        where the stop hook partially executed but never called deregister_session.
        PID liveness is checked as a safety net for sessions already past the
        stale threshold, catching crash/kill -9 scenarios.

        Read-only queries and PID liveness checks run outside the lock (safe
        under WAL mode) to avoid blocking other operations during the scan.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS)).isoformat()

        # --- Read-only phase: no lock needed (WAL readers don't block writers) ---
        # Find stale by heartbeat — include 'stopped' sessions too
        stale = self._conn.execute(
            "SELECT session_id FROM coord_sessions "
            "WHERE last_heartbeat < ? AND status IN ('active', 'stopped')",
            (cutoff,),
        ).fetchall()

        # Also find active sessions past stale threshold with dead PIDs
        # (safety net for crash/kill -9 where stop hook never fires)
        active_stale = self._conn.execute(
            "SELECT session_id, pid FROM coord_sessions "
            "WHERE status = 'active' AND last_heartbeat < ?",
            (cutoff,),
        ).fetchall()
        stale_set = {s[0] for s in stale}
        dead_pid_ids = [
            row[0] for row in active_stale
            if row[1] and not self._pid_alive(row[1]) and row[0] not in stale_set
        ]
        if dead_pid_ids:
            stale = list(stale) + [(sid,) for sid in dead_pid_ids]

        if not stale:
            # Still clean expired claims even if no stale sessions
            with self._lock:
                expired_files = self._clean_expired_claims()
                expired_branches = self._clean_expired_branch_claims()
                self._commit()
            # Notify outside lock for expired claims
            self._notify_expired_claims(expired_files, expired_branches)
            return 0

        stale_ids = [s[0] for s in stale]
        stale_claims: list = []  # [(sid, files, branches), ...]

        with self._lock:
            # Re-validate: only process sessions still present (guards against
            # concurrent cleanup between the two lock acquisitions).
            still_present = self._conn.execute(
                f"SELECT session_id FROM coord_sessions WHERE session_id IN ({','.join('?' * len(stale_ids))})",
                stale_ids,
            ).fetchall()
            stale_ids = [r[0] for r in still_present]

            if not stale_ids:
                expired_files = self._clean_expired_claims()
                expired_branches = self._clean_expired_branch_claims()
                self._commit()

        if not stale_ids:
            self._notify_expired_claims(expired_files, expired_branches)
            return 0

        with self._lock:
            # Capture claims BEFORE CASCADE delete for notifications
            for sid in stale_ids:
                self._snapshot_session(sid, "stale_cleanup")

                # Reassign in-progress tasks before CASCADE delete
                self._conn.execute(
                    "UPDATE coord_tasks SET status = 'pending', session_id = NULL, claimed_at = NULL "
                    "WHERE session_id = ? AND status = 'in_progress'",
                    (sid,),
                )

                files = [
                    r[0]
                    for r in self._conn.execute(
                        "SELECT file_path FROM coord_file_claims WHERE session_id = ?", (sid,)
                    ).fetchall()
                ]
                branches = [
                    (r[0], r[1])
                    for r in self._conn.execute(
                        "SELECT project, branch FROM coord_branch_claims WHERE session_id = ?", (sid,)
                    ).fetchall()
                ]
                if files or branches:
                    stale_claims.append((sid, files, branches))

            placeholders = ",".join("?" * len(stale_ids))
            self._conn.execute(
                f"DELETE FROM coord_sessions WHERE session_id IN ({placeholders})",
                stale_ids,
            )

            expired_files = self._clean_expired_claims()
            expired_branches = self._clean_expired_branch_claims()

            self._commit()

        # Notify waiting agents about released resources (outside lock)
        for sid, files, branches in stale_claims:
            self._notify_resource_available(sid, files, branches)
        self._notify_expired_claims(expired_files, expired_branches)

        for sid in stale_ids:
            self.record_metric("session_stale_cleaned", metadata={"session_id": sid})
        logger.info("Cleaned %d stale sessions: %s", len(stale_ids), stale_ids)

        # Sync stale session cleanup to Supabase
        self._cloud_fire("clean_stale_cloud_sessions", stale_ids)

        # Prune old records in a separate lock cycle to reduce lock hold time
        self._prune_old_records()

        return len(stale_ids)

    def _prune_old_records(self) -> None:
        """Prune old snapshots, audit, metrics, handoffs, messages, ended sessions.

        Runs in its own lock→commit cycle, separate from stale session cleanup,
        to reduce lock hold time and prevent lock storms when multiple MCP
        processes trigger cleanup concurrently.
        """
        pruned_ids: list = []
        try:
            with self._lock:
                self._prune_snapshots()
                self._prune_audit()
                self._prune_metrics()
                self._prune_handoffs()
                self._prune_expired_messages()
                self._prune_ended_sessions()
                pruned_ids = getattr(self, "_pruned_session_ids", [])
                self._pruned_session_ids = []
                self._commit()
        except Exception as e:
            logger.debug("Prune old records failed (non-critical): %s", e)

        # Sync ended session deletions to Supabase (outside lock)
        if pruned_ids:
            for sid in pruned_ids:
                self._cloud_fire("delete_session", sid)

    # ------------------------------------------------------------------
    # Git event tracking
    # ------------------------------------------------------------------

    def log_git_event(
        self,
        project: str,
        event_type: str,
        commit_hash: Optional[str] = None,
        branch: Optional[str] = None,
        message: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> int:
        """Record a git event."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """INSERT INTO coord_git_events
                   (session_id, project, event_type, commit_hash, branch, message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, project, event_type, commit_hash, branch, message, now),
            )
            self._commit()

        self._cloud_fire(
            "insert_git_event", session_id, project, event_type,
            commit_hash, branch, message, now,
        )
        return cursor.lastrowid

    def get_tracked_commits(self, project: str, limit: int = 50) -> List[str]:
        """Get commit hashes tracked by coordination for a project."""
        rows = self._conn.execute(
            """SELECT commit_hash FROM coord_git_events
               WHERE project = ? AND commit_hash IS NOT NULL
               ORDER BY created_at DESC LIMIT ?""",
            (project, limit),
        ).fetchall()
        return [r[0] for r in rows]

    def get_recent_git_events(
        self,
        project: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Query recent git events with optional filters."""
        query = (
            "SELECT id, session_id, project, event_type, commit_hash, branch, message, created_at FROM coord_git_events"
        )
        conditions: list = []
        params: list = []
        if project:
            conditions.append("project = ?")
            params.append(project)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "project": r[2],
                "event_type": r[3],
                "commit_hash": r[4],
                "branch": r[5],
                "message": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]

    def detect_untracked_commits(
        self,
        project: str,
        recent_hashes: List[str],
    ) -> List[str]:
        """Find commits in recent_hashes that aren't tracked by any session."""
        if not recent_hashes:
            return []
        tracked = set(self.get_tracked_commits(project, limit=200))
        return [h for h in recent_hashes if h not in tracked]

    # ------------------------------------------------------------------
    # Coordination Metrics
    # ------------------------------------------------------------------

    METRICS_RETENTION_DAYS = 30

    def record_metric(
        self,
        metric_name: str,
        session_id: Optional[str] = None,
        project: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        value: int = 1,
    ) -> None:
        """Record a coordination metric. Best-effort — never raises.

        Uses self._conn to avoid opening new connections/FDs per call.
        All locked callers share the connection safely; the INSERT is a
        single atomic statement in WAL mode, safe for the one unlocked
        caller (detect_deadlocks). Metrics commit with the next _commit().
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            meta_json = json.dumps(metadata) if metadata else None
            self._conn.execute(
                """INSERT INTO coord_metrics
                   (metric_name, metric_value, session_id, project, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (metric_name, value, session_id, project, meta_json, now),
            )
            self._cloud_fire(
                "insert_metric", metric_name, value, session_id, project, meta_json, now,
            )
        except Exception:
            pass  # Metrics are best-effort

    def get_metrics(
        self,
        days: int = 7,
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate coordination metrics over the last N days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conditions = ["created_at >= ?"]
        params: list = [cutoff]
        if project:
            conditions.append("project = ?")
            params.append(project)

        where = " AND ".join(conditions)

        with self._lock:
            # Raw counts per metric
            rows = self._conn.execute(
                f"""SELECT metric_name, SUM(metric_value)
                    FROM coord_metrics WHERE {where}
                    GROUP BY metric_name ORDER BY SUM(metric_value) DESC""",
                params,
            ).fetchall()
        counts: Dict[str, int] = {r[0]: r[1] for r in rows}

        # Derived rates
        total_claims = counts.get("file_claimed", 0)
        conflicts = counts.get("conflict_detected", 0)
        conflict_rate = (conflicts / total_claims * 100) if total_claims > 0 else 0.0

        handoffs_written = counts.get("handoff_written", 0)
        handoffs_read = counts.get("handoff_read", 0)
        handoff_read_rate = (handoffs_read / handoffs_written * 100) if handoffs_written > 0 else 0.0

        gate_checks = sum(v for k, v in counts.items() if k.startswith("gate_check_"))
        gate_skips = counts.get("gate_skipped", 0)
        gate_skip_rate = (gate_skips / (gate_checks + gate_skips) * 100) if (gate_checks + gate_skips) > 0 else 0.0

        # Per-operation gate breakdown (reads action from metadata JSON)
        gate_by_action: Dict[str, Dict[str, int]] = {}
        try:
            with self._lock:
                gate_rows = self._conn.execute(
                    f"""SELECT metric_name, metadata, SUM(metric_value)
                        FROM coord_metrics
                        WHERE {where}
                          AND (metric_name LIKE 'gate_check_%' OR metric_name = 'gate_skipped')
                          AND metadata IS NOT NULL
                        GROUP BY metric_name, json_extract(metadata, '$.action')""",
                    params,
                ).fetchall()
            for name, meta_json, total in gate_rows:
                meta = _safe_json_loads(meta_json)
                action = meta.get("action", "unknown")
                if action not in gate_by_action:
                    gate_by_action[action] = {"checks": 0, "skips": 0}
                if name.startswith("gate_check_"):
                    gate_by_action[action]["checks"] += total
                elif name == "gate_skipped":
                    gate_by_action[action]["skips"] += total
        except Exception:
            pass  # Per-operation breakdown is best-effort

        gate_skip_by_action = {}
        for action, vals in gate_by_action.items():
            denom = vals["checks"] + vals["skips"]
            gate_skip_by_action[action] = {
                "checks": vals["checks"],
                "skips": vals["skips"],
                "skip_rate": round(vals["skips"] / denom * 100, 1) if denom > 0 else 0.0,
            }

        return {
            "period_days": days,
            "counts": counts,
            "rates": {
                "conflict_rate": round(conflict_rate, 1),
                "handoff_read_rate": round(handoff_read_rate, 1),
                "gate_skip_rate": round(gate_skip_rate, 1),
            },
            "totals": {
                "total_claims": total_claims,
                "total_conflicts": conflicts,
                "total_gate_checks": gate_checks,
                "total_handoffs": handoffs_written,
            },
            "gate_by_action": gate_skip_by_action,
        }

    def _prune_metrics(self) -> int:
        """Delete metrics older than METRICS_RETENTION_DAYS. Call inside _lock."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.METRICS_RETENTION_DAYS)).isoformat()
        cursor = self._conn.execute("DELETE FROM coord_metrics WHERE created_at < ?", (cutoff,))
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Structured Handoffs
    # ------------------------------------------------------------------

    HANDOFF_RETENTION_DAYS = 30

    def create_handoff(
        self,
        session_id: str,
        project: Optional[str] = None,
        completed_tasks: Optional[List[str]] = None,
        blocked_items: Optional[List[str]] = None,
        key_context: Optional[str] = None,
        next_steps: Optional[List[str]] = None,
        files_modified: Optional[List[str]] = None,
        decisions_made: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a structured handoff for the next session.

        Auto-enriches with git state and active file claims if not provided.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Auto-enrich files_modified from active file claims
        if files_modified is None:
            try:
                claims = self.get_session_claims(session_id)
                claimed_files = claims.get("file_claims", [])
                if claimed_files:
                    files_modified = claimed_files
            except Exception:
                pass

        # Auto-enrich git state
        git_branch = None
        git_dirty: List[str] = []
        if project:
            git_state = self._capture_git_state(project)
            git_branch = git_state.get("git_branch")
            git_dirty = git_state.get("git_dirty_files", [])

        with self._lock:
            cursor = self._conn.execute(
                """INSERT INTO coord_handoffs
                   (session_id, project, completed_tasks, blocked_items, key_context,
                    next_steps, files_modified, decisions_made, git_branch,
                    git_dirty_files, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    project,
                    json.dumps(completed_tasks or []),
                    json.dumps(blocked_items or []),
                    key_context,
                    json.dumps(next_steps or []),
                    json.dumps(files_modified or []),
                    json.dumps(decisions_made or []),
                    git_branch,
                    json.dumps(git_dirty),
                    now,
                ),
            )
            self._commit()

        self._cloud_fire(
            "insert_handoff", session_id, project,
            json.dumps(completed_tasks or []), json.dumps(blocked_items or []),
            key_context, json.dumps(next_steps or []),
            json.dumps(files_modified or []), json.dumps(decisions_made or []),
            git_branch, json.dumps(git_dirty), now,
        )
        self.record_metric("handoff_written", session_id=session_id, project=project)
        return {
            "id": cursor.lastrowid,
            "session_id": session_id,
            "project": project,
            "git_branch": git_branch,
            "files_modified": files_modified or [],
            "created_at": now,
        }

    def get_latest_handoff(
        self,
        project: Optional[str] = None,
        reader_session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent handoff, optionally for a project.

        Marks it as read by reader_session_id if provided.
        """
        if project:
            row = self._conn.execute(
                """SELECT id, session_id, project, completed_tasks, blocked_items,
                          key_context, next_steps, files_modified, decisions_made,
                          git_branch, git_dirty_files, created_at, read_by
                   FROM coord_handoffs WHERE project = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (project,),
            ).fetchone()
        else:
            row = self._conn.execute(
                """SELECT id, session_id, project, completed_tasks, blocked_items,
                          key_context, next_steps, files_modified, decisions_made,
                          git_branch, git_dirty_files, created_at, read_by
                   FROM coord_handoffs
                   ORDER BY created_at DESC LIMIT 1""",
            ).fetchone()

        if not row:
            return None

        handoff = {
            "id": row[0],
            "session_id": row[1],
            "project": row[2],
            "completed_tasks": _safe_json_loads(row[3], []),
            "blocked_items": _safe_json_loads(row[4], []),
            "key_context": row[5],
            "next_steps": _safe_json_loads(row[6], []),
            "files_modified": _safe_json_loads(row[7], []),
            "decisions_made": _safe_json_loads(row[8], []),
            "git_branch": row[9],
            "git_dirty_files": _safe_json_loads(row[10], []),
            "created_at": row[11],
            "read_by": _safe_json_loads(row[12], []),
        }

        # Mark as read
        if reader_session_id and reader_session_id not in handoff["read_by"]:
            read_by = handoff["read_by"] + [reader_session_id]
            with self._lock:
                self._conn.execute(
                    "UPDATE coord_handoffs SET read_by = ? WHERE id = ?",
                    (json.dumps(read_by), row[0]),
                )
                self._commit()
            handoff["read_by"] = read_by
            self.record_metric("handoff_read", session_id=reader_session_id, project=handoff.get("project"))

        return handoff

    def _prune_handoffs(self) -> int:
        """Delete handoffs older than HANDOFF_RETENTION_DAYS. Call inside _lock."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.HANDOFF_RETENTION_DAYS)).isoformat()
        cursor = self._conn.execute("DELETE FROM coord_handoffs WHERE created_at < ?", (cutoff,))
        return cursor.rowcount

    def _prune_ended_sessions(self) -> int:
        """Delete ended sessions older than 24h. Call inside _lock.

        Ended sessions are kept briefly so _get_last_session_info can surface
        predecessor context in the personal greeting. After 24h they are no
        longer useful for that purpose.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        # Collect IDs before deletion so we can sync to cloud
        old_ids = [
            r[0] for r in self._conn.execute(
                "SELECT session_id FROM coord_sessions WHERE status = 'ended' AND last_heartbeat < ?",
                (cutoff,),
            ).fetchall()
        ]
        cursor = self._conn.execute(
            "DELETE FROM coord_sessions WHERE status = 'ended' AND last_heartbeat < ?",
            (cutoff,),
        )
        # Sync deletions to Supabase (outside caller holds _lock, so defer cloud fire)
        if old_ids:
            self._pruned_session_ids = old_ids
        return cursor.rowcount

    # ------------------------------------------------------------------
    # External Action Registry (v5) — prevents duplicate deploys, submissions, etc.
    # ------------------------------------------------------------------

    def check_external_action(
        self, action_type: str, action_target: str
    ) -> Dict[str, Any]:
        """Check if an external action has already been claimed or completed.

        No lock needed (read-only). Ignores actions older than 24h (TTL).
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        row = self._conn.execute(
            """SELECT id, session_id, status, created_at, completed_at, result
               FROM coord_external_actions
               WHERE action_type = ? AND action_target = ?
                 AND status IN ('claimed', 'completed', 'abandoned')
                 AND created_at > ?
               ORDER BY created_at DESC LIMIT 1""",
            (action_type, action_target, cutoff),
        ).fetchone()

        if not row:
            return {"exists": False}

        return {
            "exists": True,
            "action_id": row[0],
            "session_id": row[1],
            "status": row[2],
            "created_at": row[3],
            "completed_at": row[4],
            "result": row[5],
        }

    def claim_external_action(
        self,
        session_id: str,
        action_type: str,
        action_target: str,
        params: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically claim an external action to prevent duplicate execution.

        CAS-style: checks for existing active action, then inserts if none found.
        Claimed actions expire after 30 min (stale claim protection).
        Completed actions block re-claim for 24h.
        """
        self._ensure_registered(session_id)
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        claim_cutoff = (now - timedelta(minutes=30)).isoformat()
        complete_cutoff = (now - timedelta(hours=24)).isoformat()

        with self._lock:
            # Check for existing claimed action (within 30 min)
            row = self._conn.execute(
                """SELECT id, session_id, status, created_at, completed_at
                   FROM coord_external_actions
                   WHERE action_type = ? AND action_target = ?
                     AND status = 'claimed' AND created_at > ?
                   ORDER BY created_at DESC LIMIT 1""",
                (action_type, action_target, claim_cutoff),
            ).fetchone()
            if row:
                return {
                    "success": False,
                    "error": "Already claimed",
                    "claimed_by": row[1],
                    "action_id": row[0],
                    "created_at": row[3],
                }

            # Check for existing completed action (within 24h)
            row = self._conn.execute(
                """SELECT id, session_id, completed_at, result
                   FROM coord_external_actions
                   WHERE action_type = ? AND action_target = ?
                     AND status = 'completed' AND created_at > ?
                   ORDER BY created_at DESC LIMIT 1""",
                (action_type, action_target, complete_cutoff),
            ).fetchone()
            if row:
                return {
                    "success": False,
                    "error": "Already completed",
                    "completed_by": row[1],
                    "action_id": row[0],
                    "completed_at": row[2],
                    "result": row[3],
                }

            # No active action — insert new claim
            cursor = self._conn.execute(
                """INSERT INTO coord_external_actions
                   (action_type, action_target, session_id, status, params, created_at)
                   VALUES (?, ?, ?, 'claimed', ?, ?)""",
                (action_type, action_target, session_id, params, now_iso),
            )
            self._commit()

        return {
            "success": True,
            "action_id": cursor.lastrowid,
            "action_type": action_type,
            "action_target": action_target,
        }

    def complete_external_action(
        self,
        action_id: int,
        session_id: str,
        result: Optional[str] = None,
        success: bool = True,
    ) -> Dict[str, Any]:
        """Mark a claimed external action as completed or failed.

        Only the session that claimed the action can complete it.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        new_status = "completed" if success else "failed"

        with self._lock:
            row = self._conn.execute(
                "SELECT session_id, status FROM coord_external_actions WHERE id = ?",
                (action_id,),
            ).fetchone()

            if not row:
                return {"success": False, "error": "Action not found"}
            if row[0] != session_id:
                return {
                    "success": False,
                    "error": "Action is owned by another session",
                    "owned_by": row[0],
                }
            if row[1] != "claimed":
                return {
                    "success": False,
                    "error": f"Action is already '{row[1]}', not 'claimed'",
                }

            self._conn.execute(
                """UPDATE coord_external_actions
                   SET status = ?, completed_at = ?, result = ?
                   WHERE id = ? AND session_id = ?""",
                (new_status, now_iso, result, action_id, session_id),
            )
            self._commit()

        return {
            "success": True,
            "action_id": action_id,
            "status": new_status,
        }

    # ------------------------------------------------------------------
    # Goal persistence + drift detection (v6)
    # ------------------------------------------------------------------

    def create_goal(
        self,
        session_id: str,
        title: str,
        description: str,
        project: str,
        target_files: Optional[List[str]] = None,
        target_modules: Optional[List[str]] = None,
        success_criteria: Optional[List[str]] = None,
        parent_goal_id: Optional[int] = None,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Create a persistent goal with immutable anchor for drift detection."""
        self._ensure_registered(session_id, project)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            if parent_goal_id is not None:
                parent = self._conn.execute(
                    "SELECT id, status FROM coord_goals WHERE id = ?",
                    (parent_goal_id,),
                ).fetchone()
                if not parent:
                    return {"success": False, "error": f"Parent goal #{parent_goal_id} not found"}
                if parent[1] != "active":
                    return {"success": False, "error": f"Parent goal #{parent_goal_id} is '{parent[1]}', not 'active'"}

            cursor = self._conn.execute(
                """INSERT INTO coord_goals
                   (title, description, project, status, created_by, created_at, updated_at,
                    parent_goal_id, original_description, target_files, target_modules,
                    success_criteria, priority, metadata)
                   VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')""",
                (
                    title, description, project, session_id, now, now,
                    parent_goal_id, description,
                    json.dumps(target_files) if target_files else None,
                    json.dumps(target_modules) if target_modules else None,
                    json.dumps(success_criteria) if success_criteria else None,
                    priority,
                ),
            )
            goal_id = cursor.lastrowid
            self._commit()

        return {
            "success": True,
            "goal_id": goal_id,
            "title": title,
            "parent_goal_id": parent_goal_id,
        }

    def evolve_goal(
        self,
        goal_id: int,
        session_id: str,
        new_description: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Evolve a goal: abandon old, create new with lineage preserved."""
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            old = self._conn.execute(
                """SELECT title, project, original_description, target_files,
                          target_modules, success_criteria, priority, parent_goal_id
                   FROM coord_goals WHERE id = ? AND status = 'active'""",
                (goal_id,),
            ).fetchone()
            if not old:
                return {"success": False, "error": f"Active goal #{goal_id} not found"}

            title, project, orig_desc, tf, tm, sc, prio, parent_id = old

            # Abandon old goal
            self._conn.execute(
                "UPDATE coord_goals SET status = 'abandoned', updated_at = ? WHERE id = ?",
                (now, goal_id),
            )

            # Create evolved goal preserving the original anchor
            cursor = self._conn.execute(
                """INSERT INTO coord_goals
                   (title, description, project, status, created_by, created_at, updated_at,
                    parent_goal_id, evolved_from_id, evolution_reason,
                    original_description, target_files, target_modules,
                    success_criteria, priority, metadata)
                   VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')""",
                (
                    title, new_description, project, session_id, now, now,
                    parent_id, goal_id, reason,
                    orig_desc, tf, tm, sc, prio,
                ),
            )
            new_goal_id = cursor.lastrowid

            # Reassign linked tasks to the new goal
            self._conn.execute(
                "UPDATE coord_tasks SET goal_id = ? WHERE goal_id = ?",
                (new_goal_id, goal_id),
            )
            self._commit()

        return {
            "success": True,
            "new_goal_id": new_goal_id,
            "evolved_from_id": goal_id,
            "reason": reason,
        }

    def complete_goal(
        self,
        goal_id: int,
        session_id: str,
    ) -> Dict[str, Any]:
        """Complete a goal. Auto-completes parent if all siblings are done."""
        now = datetime.now(timezone.utc).isoformat()
        parent_completed = False

        with self._lock:
            row = self._conn.execute(
                "SELECT status, parent_goal_id FROM coord_goals WHERE id = ?",
                (goal_id,),
            ).fetchone()
            if not row:
                return {"success": False, "error": f"Goal #{goal_id} not found"}
            if row[0] != "active":
                return {"success": False, "error": f"Goal #{goal_id} is '{row[0]}', not 'active'"}

            self._conn.execute(
                "UPDATE coord_goals SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, goal_id),
            )

            # Check parent: if all children completed, auto-complete parent
            parent_id = row[1]
            if parent_id is not None:
                siblings_pending = self._conn.execute(
                    "SELECT COUNT(*) FROM coord_goals WHERE parent_goal_id = ? AND status = 'active'",
                    (parent_id,),
                ).fetchone()
                if siblings_pending and siblings_pending[0] == 0:
                    self._conn.execute(
                        "UPDATE coord_goals SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ? AND status = 'active'",
                        (now, now, parent_id),
                    )
                    parent_completed = True

            self._commit()

        return {"success": True, "goal_id": goal_id, "parent_completed": parent_completed}

    def list_goals(
        self,
        project: Optional[str] = None,
        status: str = "active",
        include_children: bool = False,
    ) -> List[Dict[str, Any]]:
        """List goals with optional project/status filter."""
        params: list = []
        clauses = []
        if project:
            clauses.append("project = ?")
            params.append(project)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if not include_children:
            clauses.append("parent_goal_id IS NULL")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT id, title, description, project, status, created_by, created_at, "
            f"updated_at, completed_at, parent_goal_id, evolved_from_id, "
            f"original_description, target_files, target_modules, success_criteria, priority "
            f"FROM coord_goals {where} ORDER BY priority DESC, created_at ASC",
            params,
        ).fetchall()

        goals = []
        for r in rows:
            goals.append({
                "id": r[0], "title": r[1], "description": r[2], "project": r[3],
                "status": r[4], "created_by": r[5], "created_at": r[6],
                "updated_at": r[7], "completed_at": r[8],
                "parent_goal_id": r[9], "evolved_from_id": r[10],
                "original_description": r[11],
                "target_files": _safe_json_loads(r[12], []),
                "target_modules": _safe_json_loads(r[13], []),
                "success_criteria": _safe_json_loads(r[14], []),
                "priority": r[15],
            })
        return goals

    def get_goal(self, goal_id: int) -> Optional[Dict[str, Any]]:
        """Get a goal with linked tasks and child goals."""
        row = self._conn.execute(
            "SELECT id, title, description, project, status, created_by, created_at, "
            "updated_at, completed_at, parent_goal_id, evolved_from_id, evolution_reason, "
            "original_description, target_files, target_modules, success_criteria, priority "
            "FROM coord_goals WHERE id = ?",
            (goal_id,),
        ).fetchone()
        if not row:
            return None

        goal: Dict[str, Any] = {
            "id": row[0], "title": row[1], "description": row[2], "project": row[3],
            "status": row[4], "created_by": row[5], "created_at": row[6],
            "updated_at": row[7], "completed_at": row[8],
            "parent_goal_id": row[9], "evolved_from_id": row[10],
            "evolution_reason": row[11], "original_description": row[12],
            "target_files": _safe_json_loads(row[13], []),
            "target_modules": _safe_json_loads(row[14], []),
            "success_criteria": _safe_json_loads(row[15], []),
            "priority": row[16],
        }

        # Linked tasks
        task_rows = self._conn.execute(
            "SELECT id, title, status, session_id, progress FROM coord_tasks WHERE goal_id = ?",
            (goal_id,),
        ).fetchall()
        goal["tasks"] = [
            {"id": t[0], "title": t[1], "status": t[2], "session_id": t[3], "progress": t[4] or 0}
            for t in task_rows
        ]

        # Child goals
        child_rows = self._conn.execute(
            "SELECT id, title, status FROM coord_goals WHERE parent_goal_id = ?",
            (goal_id,),
        ).fetchall()
        goal["children"] = [{"id": c[0], "title": c[1], "status": c[2]} for c in child_rows]

        return goal

    def link_task_to_goal(self, task_id: int, goal_id: int) -> Dict[str, Any]:
        """Link an existing task to a goal."""
        with self._lock:
            task = self._conn.execute("SELECT id FROM coord_tasks WHERE id = ?", (task_id,)).fetchone()
            if not task:
                return {"success": False, "error": f"Task #{task_id} not found"}
            goal = self._conn.execute("SELECT id FROM coord_goals WHERE id = ?", (goal_id,)).fetchone()
            if not goal:
                return {"success": False, "error": f"Goal #{goal_id} not found"}
            self._conn.execute("UPDATE coord_tasks SET goal_id = ? WHERE id = ?", (goal_id, task_id))
            self._commit()
        return {"success": True, "task_id": task_id, "goal_id": goal_id}

    # --- Drift detection signals ---

    def _drift_file_scope(self, goal_id: int) -> float:
        """File scope divergence: Jaccard distance between declared and actual files."""
        row = self._conn.execute(
            "SELECT target_files FROM coord_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if not row or not row[0]:
            return 0.0
        declared = set(_safe_json_loads(row[0], []))
        if not declared:
            return 0.0

        actual_rows = self._conn.execute(
            """SELECT DISTINCT fc.file_path FROM coord_file_claims fc
               JOIN coord_tasks t ON t.session_id = fc.session_id
               WHERE t.goal_id = ? AND t.status = 'in_progress'""",
            (goal_id,),
        ).fetchall()
        actual = {r[0] for r in actual_rows}
        if not actual:
            return 0.0

        intersection = declared & actual
        union = declared | actual
        if not union:
            return 0.0
        return round(1.0 - len(intersection) / len(union), 3)

    def _drift_task_sprawl(self, goal_id: int) -> float:
        """Task sprawl: ratio of open to completed tasks linked to this goal."""
        row = self._conn.execute(
            """SELECT
                 SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END),
                 SUM(CASE WHEN status IN ('pending', 'in_progress') THEN 1 ELSE 0 END)
               FROM coord_tasks WHERE goal_id = ?""",
            (goal_id,),
        ).fetchone()
        if not row or (not row[0] and not row[1]):
            return 0.0
        completed = row[0] or 0
        open_tasks = row[1] or 0
        if completed == 0 and open_tasks == 0:
            return 0.0
        return round(min(open_tasks / max(completed, 1) / 3.0, 1.0), 3)

    def _drift_evolution_depth(self, goal_id: int) -> float:
        """Evolution depth: how many times this goal's lineage has evolved."""
        row = self._conn.execute(
            """WITH RECURSIVE chain AS (
                 SELECT id, evolved_from_id, 0 as depth FROM coord_goals WHERE id = ?
                 UNION ALL
                 SELECT g.id, g.evolved_from_id, c.depth + 1
                 FROM coord_goals g JOIN chain c ON g.id = c.evolved_from_id
               )
               SELECT MAX(depth) FROM chain""",
            (goal_id,),
        ).fetchone()
        depth = row[0] if row and row[0] else 0
        return round(min(depth / 3.0, 1.0), 3)

    def _drift_stall(self, goal_id: int) -> float:
        """Stall detection: tasks with low progress and no recent file activity."""
        now = datetime.now(timezone.utc)
        rows = self._conn.execute(
            """SELECT t.progress, t.claimed_at,
                 (SELECT MAX(fc.last_activity) FROM coord_file_claims fc
                  WHERE fc.session_id = t.session_id) as last_file_activity
               FROM coord_tasks t
               WHERE t.goal_id = ? AND t.status = 'in_progress'""",
            (goal_id,),
        ).fetchall()
        if not rows:
            return 0.0

        for progress, claimed_at, last_activity in rows:
            if (progress or 0) >= 50:
                continue
            ts = last_activity or claimed_at
            if not ts:
                continue
            try:
                last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last).total_seconds() > 900:  # 15 minutes
                    return 1.0
            except (ValueError, TypeError):
                continue
        return 0.0

    def _drift_tool_pattern_shift(self, goal_id: int) -> float:
        """Tool usage pattern shift: Jensen-Shannon divergence between recent vs historical.

        Compares each active session's recent (30min) tool distribution against
        its full historical distribution. Returns max JSD across sessions.
        Returns 0.0 if fewer than 10 audit entries for any session.
        """
        import math as _math

        # Find sessions active on this goal's tasks
        session_rows = self._conn.execute(
            """SELECT DISTINCT t.session_id FROM coord_tasks t
               WHERE t.goal_id = ? AND t.status = 'in_progress' AND t.session_id IS NOT NULL""",
            (goal_id,),
        ).fetchall()
        if not session_rows:
            return 0.0

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        max_jsd = 0.0

        for (sess_id,) in session_rows:
            # Historical tool distribution
            hist_rows = self._conn.execute(
                "SELECT tool_name, COUNT(*) FROM coord_audit WHERE session_id = ? GROUP BY tool_name",
                (sess_id,),
            ).fetchall()
            total_hist = sum(r[1] for r in hist_rows)
            if total_hist < 10:
                continue

            # Recent (30min) tool distribution
            recent_rows = self._conn.execute(
                "SELECT tool_name, COUNT(*) FROM coord_audit WHERE session_id = ? AND created_at > ? GROUP BY tool_name",
                (sess_id, cutoff),
            ).fetchall()
            total_recent = sum(r[1] for r in recent_rows)
            if total_recent < 3:
                continue

            # Build probability distributions
            all_tools = set(r[0] for r in hist_rows) | set(r[0] for r in recent_rows)
            hist_dist = {r[0]: r[1] / total_hist for r in hist_rows}
            recent_dist = {r[0]: r[1] / total_recent for r in recent_rows}

            # Jensen-Shannon divergence (pure Python)
            jsd = 0.0
            for tool in all_tools:
                p = recent_dist.get(tool, 0.0)
                q = hist_dist.get(tool, 0.0)
                m = (p + q) / 2.0
                if m > 0:
                    if p > 0:
                        jsd += 0.5 * p * _math.log(p / m)
                    if q > 0:
                        jsd += 0.5 * q * _math.log(q / m)

            # JSD is in [0, ln(2)] ~ [0, 0.693]; normalize to [0, 1]
            normalized = min(jsd / _math.log(2), 1.0) if _math.log(2) > 0 else 0.0
            max_jsd = max(max_jsd, normalized)

        return round(max_jsd, 3)

    def _drift_inter_agent_divergence(self, goal_id: int) -> float:
        """Inter-agent file divergence: average Jaccard distance of file touches.

        Measures alignment between agents working on the same goal.
        Returns 0.0 if fewer than 2 agents are active.
        """
        rows = self._conn.execute(
            """SELECT fc.session_id, fc.file_path FROM coord_file_claims fc
               JOIN coord_tasks t ON t.session_id = fc.session_id
               WHERE t.goal_id = ? AND t.status = 'in_progress'""",
            (goal_id,),
        ).fetchall()
        if not rows:
            return 0.0

        # Build session -> files mapping
        session_files: Dict[str, set] = {}
        for sess_id, file_path in rows:
            session_files.setdefault(sess_id, set()).add(file_path)

        sessions = list(session_files.keys())
        if len(sessions) < 2:
            return 0.0

        # Average Jaccard distance across all pairs
        total_distance = 0.0
        pair_count = 0
        for i in range(len(sessions)):
            for j in range(i + 1, len(sessions)):
                files_a = session_files[sessions[i]]
                files_b = session_files[sessions[j]]
                union = files_a | files_b
                if not union:
                    continue
                intersection = files_a & files_b
                distance = 1.0 - len(intersection) / len(union)
                total_distance += distance
                pair_count += 1

        if pair_count == 0:
            return 0.0
        return round(total_distance / pair_count, 3)

    def _classify_drift(
        self, goal_id: int, signals: Dict[str, float], composite: float
    ) -> str:
        """Classify drift into actionable type.

        Returns one of: none, stall, divergence, healthy_exploration, scope_creep.
        """
        if composite < 0.3:
            return "none"
        if signals.get("stall", 0) >= 0.8 and all(
            signals.get(s, 0) < 0.3 for s in ("file_scope", "task_sprawl", "tool_pattern_shift")
        ):
            return "stall"
        if signals.get("inter_agent_divergence", 0) >= 0.6 and signals.get("file_scope", 0) < 0.5:
            return "divergence"

        file_scope = signals.get("file_scope", 0)
        task_sprawl = signals.get("task_sprawl", 0)
        tool_shift = signals.get("tool_pattern_shift", 0)

        if file_scope >= 0.5:
            # Check if out-of-scope files share directory prefix with targets
            # (heuristic: if touching nearby files, likely healthy exploration)
            if task_sprawl < 0.3 and tool_shift < 0.3:
                # Additional refinement: check if files are in same directory tree
                row = self._conn.execute(
                    "SELECT target_files FROM coord_goals WHERE id = ?", (goal_id,)
                ).fetchone()
                if row and row[0]:
                    try:
                        target_files = json.loads(row[0])
                        target_dirs = {f.rsplit("/", 1)[0] for f in target_files if "/" in f}
                        actual_rows = self._conn.execute(
                            """SELECT DISTINCT fc.file_path FROM coord_file_claims fc
                               JOIN coord_tasks t ON t.session_id = fc.session_id
                               WHERE t.goal_id = ? AND t.status = 'in_progress'""",
                            (goal_id,),
                        ).fetchall()
                        actual_files = {r[0] for r in actual_rows}
                        out_of_scope = actual_files - set(target_files)
                        if out_of_scope and target_dirs:
                            nearby = sum(
                                1 for f in out_of_scope
                                if any(f.startswith(d) for d in target_dirs)
                            )
                            if nearby >= len(out_of_scope) * 0.5:
                                return "healthy_exploration"
                    except (json.JSONDecodeError, TypeError):
                        pass
                return "healthy_exploration"
            if task_sprawl >= 0.5 or tool_shift >= 0.5:
                return "scope_creep"

        return "scope_creep"

    def check_drift(self, goal_id: int) -> Dict[str, Any]:
        """Compute composite drift score for a goal. Pure SQL, no LLM calls.

        Returns {goal_id, drift_score (0-1), signals: {name: score},
                 alert_level (none|watch|warning|critical), drift_type}
        """
        # Cache check (5 minutes)
        cache_key = f"drift_{goal_id}"
        now = time.monotonic()
        if cache_key in self._drift_cache_times and now - self._drift_cache_times[cache_key] < 300:
            return self._drift_cache[cache_key]

        signals = {
            "file_scope": self._drift_file_scope(goal_id),
            "task_sprawl": self._drift_task_sprawl(goal_id),
            "evolution_depth": self._drift_evolution_depth(goal_id),
            "stall": self._drift_stall(goal_id),
            "tool_pattern_shift": self._drift_tool_pattern_shift(goal_id),
            "inter_agent_divergence": self._drift_inter_agent_divergence(goal_id),
        }
        composite = (
            signals["file_scope"] * 0.25
            + signals["task_sprawl"] * 0.20
            + signals["evolution_depth"] * 0.10
            + signals["stall"] * 0.20
            + signals["tool_pattern_shift"] * 0.15
            + signals["inter_agent_divergence"] * 0.10
        )
        alert = (
            "critical" if composite > 0.7 else
            "warning" if composite > 0.5 else
            "watch" if composite > 0.3 else
            "none"
        )
        drift_type = self._classify_drift(goal_id, signals, composite)
        result = {
            "goal_id": goal_id,
            "drift_score": round(composite, 3),
            "signals": signals,
            "alert_level": alert,
            "drift_type": drift_type,
        }
        self._drift_cache[cache_key] = result
        self._drift_cache_times[cache_key] = now
        return result

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Decision Register (v8) — authoritative shared state for alignment
    # ------------------------------------------------------------------

    def register_decision(
        self,
        session_id: str,
        project: str,
        domain: str,
        decision: str,
        rationale: Optional[str] = None,
        goal_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register an authoritative decision for a domain.

        Auto-supersedes any existing active decision in the same (project, domain).
        Runs cross-domain contradiction detection for sibling domains.
        Broadcasts to peers via the message bus.
        """
        self._ensure_registered(session_id, project)
        now = datetime.now(timezone.utc).isoformat()
        superseded_ids: List[int] = []
        contradiction_warnings: List[str] = []

        with self._lock:
            # Layer 1: Same-domain auto-supersession
            existing = self._conn.execute(
                "SELECT id, decision FROM coord_decisions "
                "WHERE project = ? AND domain = ? AND status = 'active'",
                (project, domain),
            ).fetchall()
            for row in existing:
                self._conn.execute(
                    "UPDATE coord_decisions SET status = 'superseded', superseded_at = ? "
                    "WHERE id = ?",
                    (now, row[0]),
                )
                superseded_ids.append(row[0])

            # Insert new decision
            meta_json = json.dumps(metadata) if metadata else None
            cursor = self._conn.execute(
                "INSERT INTO coord_decisions "
                "(domain, project, decision, rationale, decided_by, goal_id, "
                "status, created_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                (domain, project, decision, rationale, session_id,
                 goal_id, now, meta_json),
            )
            decision_id = cursor.lastrowid

            # Update superseded_by pointers
            for old_id in superseded_ids:
                self._conn.execute(
                    "UPDATE coord_decisions SET superseded_by = ? WHERE id = ?",
                    (decision_id, old_id),
                )

            # Layer 2: Cross-domain contradiction (sibling domains)
            parent_domain = domain.rsplit("/", 1)[0] if "/" in domain else None
            if parent_domain:
                siblings = self._conn.execute(
                    "SELECT id, domain, decision FROM coord_decisions "
                    "WHERE project = ? AND domain LIKE ? AND domain != ? "
                    "AND status = 'active'",
                    (project, parent_domain + "/%", domain),
                ).fetchall()
                if siblings:
                    try:
                        from omega.contradictions import detect_contradictions
                        sibling_texts = [s[2] for s in siblings]
                        results = detect_contradictions(decision, sibling_texts)
                        for i, cr in enumerate(results):
                            if cr.confidence >= 0.4:
                                contradiction_warnings.append(
                                    f"Potential contradiction with decision #{siblings[i][0]} "
                                    f"(domain={siblings[i][1]}): {cr.explanation}"
                                )
                    except ImportError:
                        pass  # Contradiction detection is optional
                    except Exception:
                        pass  # Best-effort

            self._commit()

        self._cloud_fire(
            "insert_decision", domain, project, decision, rationale,
            session_id, goal_id, "active", now, meta_json,
        )

        # Broadcast to peers
        try:
            self.send_message(
                from_session=session_id,
                msg_type="inform",
                project=project,
                subject=f"[DECISION] {domain}: {decision[:100]}",
                body=f"Domain: {domain}\nDecision: {decision}\nRationale: {rationale or 'N/A'}",
            )
        except Exception:
            pass  # Broadcast is best-effort

        # Forward dual-write: mirror into memories table for welcome/query visibility
        try:
            from omega.bridge import auto_capture as _ac
            _decision_content = f"[{domain}] {decision}"
            _ac_meta = {
                "source": "coord_dual_write",
                "coord_decision_id": decision_id,
                "domain": domain,
                "project": project,
            }
            if rationale:
                _ac_meta["rationale"] = rationale
            _ac(
                content=_decision_content,
                event_type="decision",
                session_id=session_id,
                project=project,
                metadata=_ac_meta,
            )
        except Exception:
            pass  # Dual-write is best-effort; coord_decisions is authoritative

        result: Dict[str, Any] = {
            "success": True,
            "decision_id": decision_id,
            "domain": domain,
            "superseded": superseded_ids,
        }
        if contradiction_warnings:
            result["contradiction_warnings"] = contradiction_warnings
        return result

    def query_decisions(
        self,
        project: str,
        domain: Optional[str] = None,
        status: str = "active",
        goal_id: Optional[int] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Query decisions, with optional domain prefix matching."""
        clauses = ["project = ?"]
        params: list = [project]

        if domain:
            clauses.append("domain LIKE ?")
            params.append(domain + "%")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if goal_id is not None:
            clauses.append("goal_id = ?")
            params.append(goal_id)

        where = " AND ".join(clauses)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, domain, project, decision, rationale, decided_by, "
                f"goal_id, status, superseded_by, created_at, superseded_at, metadata "
                f"FROM coord_decisions WHERE {where} "
                f"ORDER BY created_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()

        return [
            {
                "id": r[0], "domain": r[1], "project": r[2], "decision": r[3],
                "rationale": r[4], "decided_by": r[5], "goal_id": r[6],
                "status": r[7], "superseded_by": r[8], "created_at": r[9],
                "superseded_at": r[10], "metadata": _safe_json_loads(r[11]),
            }
            for r in rows
        ]

    def get_decision(self, decision_id: int) -> Optional[Dict[str, Any]]:
        """Get a single decision with its supersession chain."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, domain, project, decision, rationale, decided_by, "
                "goal_id, status, superseded_by, created_at, superseded_at, metadata "
                "FROM coord_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        if not row:
            return None

        result = {
            "id": row[0], "domain": row[1], "project": row[2], "decision": row[3],
            "rationale": row[4], "decided_by": row[5], "goal_id": row[6],
            "status": row[7], "superseded_by": row[8], "created_at": row[9],
            "superseded_at": row[10], "metadata": _safe_json_loads(row[11]),
        }

        # Build supersession chain (walk backwards)
        chain = []
        with self._lock:
            prev_rows = self._conn.execute(
                "SELECT id, decision, status, created_at FROM coord_decisions "
                "WHERE superseded_by = ? ORDER BY created_at ASC",
                (decision_id,),
            ).fetchall()
        for pr in prev_rows:
            chain.append({
                "id": pr[0], "decision": pr[1], "status": pr[2], "created_at": pr[3],
            })
        if chain:
            result["supersession_chain"] = chain
        return result

    def revoke_decision(
        self,
        decision_id: int,
        session_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Revoke an active decision."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT status, project, domain, decision FROM coord_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
            if not row:
                return {"success": False, "error": f"Decision {decision_id} not found"}
            if row[0] != "active":
                return {"success": False, "error": f"Decision {decision_id} is already {row[0]}"}

            # Merge revocation info into existing metadata (Python-side to
            # avoid requiring SQLite 3.38+ json_patch function).
            existing_meta = self._conn.execute(
                "SELECT metadata FROM coord_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
            merged = _safe_json_loads(existing_meta[0] if existing_meta else None)
            merged["revoked_by"] = session_id
            if reason:
                merged["revoke_reason"] = reason
            self._conn.execute(
                "UPDATE coord_decisions SET status = 'revoked', superseded_at = ?, "
                "metadata = ? WHERE id = ?",
                (now, json.dumps(merged), decision_id),
            )
            self._commit()

        # Broadcast revocation
        try:
            self.send_message(
                from_session=session_id,
                msg_type="inform",
                project=row[1],
                subject=f"[DECISION-REVOKED] {row[2]}: {row[3][:80]}",
                body=f"Decision #{decision_id} revoked. Reason: {reason or 'N/A'}",
            )
        except Exception:
            pass

        return {"success": True, "decision_id": decision_id, "status": "revoked"}

    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection, flushing WAL pages first."""
        try:
            self._cloud_executor.shutdown(wait=False)
        except Exception:
            pass
        try:
            self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception:
            pass
        try:
            self._conn.close()
        except Exception:
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton (lazy, like bridge._get_store)
# ---------------------------------------------------------------------------

_manager: Optional[CoordinationManager] = None
_manager_lock = threading.Lock()


def get_manager() -> CoordinationManager:
    """Get or create the singleton CoordinationManager, auto-reconnecting on dead DB."""
    global _manager
    with _manager_lock:
        if _manager is None:
            # Disable cloud sync in test environments to prevent test data pollution
            cloud = "PYTEST_CURRENT_TEST" not in os.environ
            _manager = CoordinationManager(cloud_sync=cloud)
            return _manager
        # Health check inside lock: prevents two threads from both seeing dead conn
        try:
            _manager._conn.execute("SELECT 1")
        except Exception as e:
            # "database is locked" means the connection is alive but contended —
            # return it as-is instead of triggering a reconnect storm
            if isinstance(e, sqlite3.OperationalError) and "database is locked" in str(e):
                logger.debug("get_manager health check: database locked (connection alive)")
                return _manager
            logger.warning("CoordinationManager DB connection dead, reconnecting")
            old_conn = _manager._conn
            try:
                old_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                pass
            try:
                old_conn.close()
            except Exception:
                pass
            del old_conn
            # Retry with exponential backoff (handles transient WAL locks)
            reconnected = False
            exc = None
            for attempt in range(3):
                try:
                    _manager._conn = _manager._connect()
                    reconnected = True
                    logger.info("CoordinationManager reconnected after %d attempt(s)", attempt + 1)
                    break
                except Exception as e:
                    exc = e
                    logger.warning("Reconnect attempt %d/3 failed: %s", attempt + 1, exc)
                    if attempt < 2:
                        time.sleep(2 ** attempt)  # 1s, 2s backoff
            if not reconnected:
                logger.error("CoordinationManager unable to reconnect after 3 attempts")
                _manager = None  # Reset singleton for next lazy init
                raise RuntimeError("CoordinationManager reconnection failed") from exc
    return _manager


def close_manager() -> None:
    """Close the singleton manager (for cleanup/testing)."""
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.close()
            _manager = None
