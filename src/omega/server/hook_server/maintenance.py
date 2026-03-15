"""Maintenance pipeline for session-start periodic tasks.

Extracts the 7 maintenance steps from handle_session_start into a structured
pipeline with step-status tracking, error classification, and a dead-letter
queue (DLQ) for transient failures.

Key improvements over the inline try/except approach:
- Rollback on ANY failure for locked stages (not just ImportError)
- Compact aggregates per-type failures instead of bare except: pass
- Per-step timing and status visibility
- Transient failures enqueued to DLQ for retry at next session start
"""

import logging
import random
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from omega.exceptions import HookError

from .utils import (
    _log_hook_error,
    _omega_dir,
    _rollback_marker,
    _should_run_periodic,
    _try_acquire_periodic,
    _update_marker,
)

logger = logging.getLogger("omega.hook_server.maintenance")


def _send_heartbeat(stage_name: str, status: str = "ok") -> None:
    """Best-effort heartbeat to Supabase schedules table."""
    try:
        import os

        import httpx

        url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return
        label = f"com.omega.maintenance.{stage_name.replace('_', '-')}"
        resp = httpx.patch(
            f"{url}/rest/v1/schedules",
            params={"label": f"eq.{label}"},
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"last_status": status, "last_run_at": datetime.now(timezone.utc).isoformat()},
            timeout=5,
        )
        if resp.status_code in (401, 403):
            logger.warning(
                "Heartbeat auth failed for %s (HTTP %d) -- Supabase key may need rotation",
                stage_name, resp.status_code,
            )
    except Exception as exc:
        logger.debug("heartbeat failed for %s: %s", stage_name, exc)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class StepStatus(Enum):
    PENDING = "pending"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ErrorClass(Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


# Exception types that indicate permanent failures (won't resolve without code changes)
_PERMANENT_EXCEPTIONS = (ImportError, ModuleNotFoundError, SyntaxError, PermissionError)


def classify_error(exc: Exception) -> ErrorClass:
    """Classify an exception as transient or permanent.

    Permanent: ImportError, ModuleNotFoundError, SyntaxError, PermissionError
    Transient: everything else (DB locks, network errors, runtime errors)
    """
    if isinstance(exc, _PERMANENT_EXCEPTIONS):
        return ErrorClass.PERMANENT
    return ErrorClass.TRANSIENT


@dataclass
class StageConfig:
    """Configuration for a single maintenance stage."""

    name: str
    fn: Callable[[], Any]
    interval_seconds: int
    use_lock: bool = False
    marker_name: str = ""
    retry_on_failure: bool = True


@dataclass
class StepResult:
    """Result of executing a single maintenance stage."""

    name: str
    status: StepStatus = StepStatus.PENDING
    elapsed_s: float = 0.0
    output: Any = None
    error: Optional[str] = None
    error_class: Optional[ErrorClass] = None


@dataclass
class PipelineResult:
    """Aggregate result of the full maintenance pipeline run."""

    steps: list[StepResult] = field(default_factory=list)
    dlq_processed: int = 0
    dlq_remediated: int = 0
    dlq_exhausted: int = 0
    dlq_pending: int = 0
    total_elapsed_s: float = 0.0

    def get_output(self, step_name: str) -> Any:
        """Get the output of a specific step by name. Returns None if not found."""
        for step in self.steps:
            if step.name == step_name and step.status == StepStatus.COMPLETED:
                return step.output
        return None

    def format_footer(self) -> str:
        """Format a compact footer line for the welcome briefing.

        Format: maintenance: 3/7 ran (consolidate 2.1s, backup 0.8s) | 1 DLQ pending
        """
        ran = [s for s in self.steps if s.status == StepStatus.COMPLETED]
        failed = [s for s in self.steps if s.status == StepStatus.FAILED]
        total = len(self.steps)

        parts = []
        # Step details for completed steps
        step_details = []
        for s in ran:
            step_details.append(f"{s.name} {s.elapsed_s:.1f}s")
        for s in failed:
            step_details.append(f"{s.name} FAILED")

        count_part = f"{len(ran)}/{total} ran"
        if step_details:
            parts.append(f"{count_part} ({', '.join(step_details)})")
        else:
            parts.append(count_part)

        if self.dlq_pending > 0:
            parts.append(f"{self.dlq_pending} DLQ pending")
        if self.dlq_remediated > 0:
            parts.append(f"{self.dlq_remediated} DLQ remediated")
        if self.dlq_exhausted > 0:
            parts.append(f"{self.dlq_exhausted} DLQ exhausted")

        return f"maintenance: {' | '.join(parts)}"


# ---------------------------------------------------------------------------
# DLQ CRUD -- operates on omega.db via its own connection
# ---------------------------------------------------------------------------


def _get_dlq_conn() -> sqlite3.Connection:
    """Get a connection to omega.db for DLQ operations."""
    db_path = _omega_dir() / "omega.db"
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def enqueue_dlq(
    conn: sqlite3.Connection,
    stage_name: str,
    error_class: ErrorClass,
    error_message: str,
) -> None:
    """Enqueue a failed stage to the DLQ.

    Permanent errors are immediately marked as 'exhausted'.
    """
    now = datetime.now(timezone.utc).isoformat()
    status = "exhausted" if error_class == ErrorClass.PERMANENT else "pending"
    conn.execute(
        """INSERT INTO maintenance_dlq
           (stage_name, error_class, error_message, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (stage_name, error_class.value, error_message[:500], status, now, now),
    )
    conn.commit()


def poll_dlq(conn: sqlite3.Connection) -> list[dict]:
    """Poll pending DLQ items that are ready for retry."""
    now = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        """SELECT id, stage_name, error_class, error_message,
                  remediation_attempts, max_remediation
           FROM maintenance_dlq
           WHERE status = 'pending'
             AND (next_retry_at IS NULL OR next_retry_at <= ?)
           ORDER BY created_at ASC""",
        (now,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_dlq_item(
    conn: sqlite3.Connection,
    item_id: int,
    status: str,
    next_retry_at: Optional[str] = None,
) -> None:
    """Update a DLQ item's status and retry timing."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE maintenance_dlq
           SET status = ?, next_retry_at = ?, updated_at = ?,
               remediation_attempts = remediation_attempts + 1
           WHERE id = ?""",
        (status, next_retry_at, now, item_id),
    )
    conn.commit()


def count_dlq_pending(conn: sqlite3.Connection) -> int:
    """Count pending DLQ items."""
    row = conn.execute(
        "SELECT COUNT(*) FROM maintenance_dlq WHERE status = 'pending'"
    ).fetchone()
    return row[0] if row else 0


def _backoff_seconds(attempt: int) -> float:
    """Calculate exponential backoff with jitter, capped at 1 hour.

    Formula: 60s * 2^(attempt-1) * jitter[0.5, 1.5], max 3600s
    """
    base = 60.0 * (2 ** max(0, attempt - 1))
    base = min(base, 3600.0)
    jitter = random.uniform(0.5, 1.5)
    return base * jitter


# ---------------------------------------------------------------------------
# MaintenancePipeline
# ---------------------------------------------------------------------------


class MaintenancePipeline:
    """Linear pipeline for session-start maintenance tasks.

    Executes registered stages in order with:
    - Periodic gating (interval checks via markers)
    - Step status and timing tracking
    - Rollback on failure for locked stages
    - DLQ enqueue on transient failures
    - DLQ processing at pipeline start
    """

    def __init__(self) -> None:
        self._stages: list[StageConfig] = []

    def add_stage(self, config: StageConfig) -> None:
        """Register a named stage."""
        self._stages.append(config)

    def run(self) -> PipelineResult:
        """Execute the pipeline: process DLQ first, then run each stage."""
        result = PipelineResult()
        t0 = time.monotonic()

        # Phase 1: Process DLQ
        try:
            dlq_stats = self._process_dlq()
            result.dlq_processed = dlq_stats[0]
            result.dlq_remediated = dlq_stats[1]
            result.dlq_exhausted = dlq_stats[2]
        except Exception as e:
            _log_hook_error("maintenance_dlq", e)

        # Phase 2: Run each stage
        for stage in self._stages:
            step_result = self._run_stage(stage)
            result.steps.append(step_result)

        # Count remaining pending DLQ items
        try:
            conn = _get_dlq_conn()
            try:
                result.dlq_pending = count_dlq_pending(conn)
            finally:
                conn.close()
        except Exception:
            pass  # DLQ count is best-effort

        result.total_elapsed_s = time.monotonic() - t0
        return result

    def _run_stage(self, stage: StageConfig) -> StepResult:
        """Execute a single stage with gating, timing, and error handling."""
        step = StepResult(name=stage.name)

        # Periodic gating
        old_marker = None
        should_run = False

        try:
            if stage.use_lock and stage.marker_name:
                old_marker = _try_acquire_periodic(stage.marker_name, stage.interval_seconds)
                should_run = old_marker is not None
            elif stage.marker_name:
                should_run = _should_run_periodic(stage.marker_name, stage.interval_seconds)
            else:
                # No gating (e.g., surfacing GC runs every time)
                should_run = True
        except Exception as e:
            _log_hook_error(f"maintenance_gate_{stage.name}", e)
            step.status = StepStatus.SKIPPED
            return step

        if not should_run:
            step.status = StepStatus.SKIPPED
            return step

        # Execute
        step.status = StepStatus.STARTED
        t0 = time.monotonic()
        try:
            step.output = stage.fn()
            step.elapsed_s = time.monotonic() - t0
            step.status = StepStatus.COMPLETED

            # Update marker for non-locked stages (locked stages write marker in _try_acquire_periodic)
            if not stage.use_lock and stage.marker_name:
                _update_marker(stage.marker_name)

            _send_heartbeat(stage.name, "ok")

        except Exception as e:
            step.elapsed_s = time.monotonic() - t0
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.error_class = classify_error(e)
            _log_hook_error(f"maintenance_{stage.name}", e)
            _send_heartbeat(stage.name, "error")

            # Rollback marker for locked stages on ANY failure
            if stage.use_lock and stage.marker_name and old_marker is not None:
                _rollback_marker(stage.marker_name, old_marker)

            # Enqueue to DLQ for retryable stages
            if stage.retry_on_failure:
                try:
                    conn = _get_dlq_conn()
                    try:
                        enqueue_dlq(conn, stage.name, step.error_class, step.error)
                    finally:
                        conn.close()
                except Exception as dlq_err:
                    _log_hook_error("maintenance_dlq_enqueue", dlq_err)

        return step

    def _process_dlq(self) -> tuple[int, int, int]:
        """Process pending DLQ items. Returns (processed, remediated, exhausted)."""
        processed = 0
        remediated = 0
        exhausted = 0

        try:
            conn = _get_dlq_conn()
        except Exception:
            return (0, 0, 0)

        try:
            # Check if table exists (may not if migration hasn't run)
            try:
                conn.execute("SELECT 1 FROM maintenance_dlq LIMIT 1")
            except sqlite3.OperationalError:
                return (0, 0, 0)

            items = poll_dlq(conn)
            if not items:
                return (0, 0, 0)

            # Build stage registry for retrying
            stage_map = {s.name: s for s in self._stages}

            for item in items:
                processed += 1
                stage_name = item["stage_name"]
                attempts = item["remediation_attempts"]
                max_rem = item["max_remediation"]

                if attempts >= max_rem:
                    update_dlq_item(conn, item["id"], "exhausted")
                    exhausted += 1
                    continue

                stage = stage_map.get(stage_name)
                if not stage:
                    update_dlq_item(conn, item["id"], "exhausted")
                    exhausted += 1
                    continue

                # Attempt retry
                try:
                    stage.fn()
                    update_dlq_item(conn, item["id"], "remediated")
                    remediated += 1
                except Exception as e:
                    err_cls = classify_error(e)
                    if err_cls == ErrorClass.PERMANENT:
                        update_dlq_item(conn, item["id"], "exhausted")
                        exhausted += 1
                    else:
                        # Schedule next retry with backoff
                        next_attempt = attempts + 1
                        backoff = _backoff_seconds(next_attempt)
                        next_retry = datetime.fromtimestamp(
                            time.time() + backoff, tz=timezone.utc
                        ).isoformat()
                        update_dlq_item(conn, item["id"], "pending", next_retry)
        finally:
            conn.close()

        return (processed, remediated, exhausted)


# ---------------------------------------------------------------------------
# Stage implementations (wrapped from session.py originals)
# ---------------------------------------------------------------------------


def _do_consolidate() -> None:
    """Run memory consolidation."""
    from omega.bridge import consolidate

    consolidate(prune_days=7, max_summaries=30)


def _do_compact() -> str:
    """Run memory compaction across all event types.

    Aggregates per-type failures instead of silently swallowing them.
    Returns summary string.
    """
    from omega.bridge import compact

    event_types = (
        "advisor_insight",
        "lesson_learned",
        "decision",
        "observation",
        "session_summary",
        "handoff",
        "task_completion",
    )
    failures = []
    succeeded = 0
    for etype in event_types:
        try:
            compact(event_type=etype, similarity_threshold=0.50, min_cluster_size=2)
            succeeded += 1
        except Exception as e:
            failures.append(f"{etype}: {e}")

    if failures:
        raise HookError(
            f"Compact failed for {len(failures)}/{len(event_types)} types: {'; '.join(failures)}"
        )
    return f"compacted {succeeded} types"


def _do_backup() -> str:
    """Run memory backup with rotation."""
    backup_dir = _omega_dir() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"omega-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"

    from omega.bridge import export_memories

    export_memories(filepath=str(dest))

    # Rotate: keep only last 4
    backups = sorted(backup_dir.glob("omega-*.json"), key=lambda p: p.name, reverse=True)
    for b in backups[4:]:
        b.unlink()

    return str(dest)


def _do_doctor() -> str:
    """Run health check. Returns summary string."""
    from omega.bridge import status as omega_status

    s = omega_status()
    issues = []
    if s.get("node_count", 0) == 0:
        issues.append("0 memories")
    if not s.get("vec_enabled"):
        issues.append("vec disabled")

    # FTS5 integrity check
    try:
        db_path = _omega_dir() / "omega.db"
        if db_path.exists():
            _conn = sqlite3.connect(str(db_path), timeout=30)
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA busy_timeout=30000")
            _conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('integrity-check')")
            _conn.close()
    except (OSError, sqlite3.OperationalError):
        issues.append("FTS5 integrity issue")

    if issues:
        return f"doctor: {len(issues)} issue(s)"
    return "doctor: healthy"


def _do_doc_scan() -> str:
    """Scan documents folder for new files to ingest."""
    docs_dir = _omega_dir() / "documents"
    if not docs_dir.exists() or not any(docs_dir.iterdir()):
        return ""

    from omega.knowledge.engine import scan_directory

    result = scan_directory()
    if "ingested" in result.lower() and "0 ingested" not in result:
        return result
    return ""


def _do_reflect_stale() -> str:
    """Find stale memories (never accessed, 14+ days old) and store as insight."""
    try:
        from omega.reflect import find_stale
        from omega.bridge import _get_store, auto_capture

        store = _get_store()
        stale_results = find_stale(store, min_age_days=14, limit=10)
        stale_memories = stale_results.get("stale_memories", [])
        if not stale_memories:
            return "0 stale memories found"

        summary = f"Auto-reflect stale: {len(stale_memories)} memories found (14+ days, 0 access)"
        previews = []
        for mem in stale_memories[:5]:
            content = mem.get("content", "")[:80]
            mem_id = mem.get("node_id", "unknown")
            previews.append(f"  - {mem_id}: {content}")

        detail = summary + "\n" + "\n".join(previews)
        auto_capture(
            content=detail,
            event_type="advisor_insight",
            metadata={
                "source": "auto_reflect_stale",
                "category": "system_insight",
                "stale_count": len(stale_memories),
            },
        )
        return summary
    except Exception as e:
        return f"reflect_stale error: {e}"


def _do_cloud_pull() -> str:
    """Pull from cloud sync."""
    secrets_path = _omega_dir() / "secrets.json"
    if not secrets_path.exists():
        return ""

    from omega.cloud.sync import get_sync

    result = get_sync().pull_all()
    mem_pulled = result.get("memories", {}).get("pulled", 0)
    doc_pulled = result.get("documents", {}).get("pulled", 0)
    total_pulled = mem_pulled + doc_pulled

    if total_pulled > 0:
        parts = []
        if mem_pulled:
            parts.append(f"{mem_pulled} memories")
        if doc_pulled:
            parts.append(f"{doc_pulled} documents")
        return f"cloud: pulled {', '.join(parts)}"
    return ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_session_start_pipeline() -> MaintenancePipeline:
    """Build the standard session-start maintenance pipeline with all 7 stages.

    Stages (in order):
        consolidate, compact, backup, doctor, reflect_stale, doc_scan, cloud_pull
    """
    pipeline = MaintenancePipeline()

    pipeline.add_stage(StageConfig(
        name="consolidate",
        fn=_do_consolidate,
        interval_seconds=3 * 86400,
        use_lock=True,
        marker_name="last-consolidate",
    ))

    pipeline.add_stage(StageConfig(
        name="compact",
        fn=_do_compact,
        interval_seconds=3 * 86400,
        use_lock=True,
        marker_name="last-compact",
    ))

    pipeline.add_stage(StageConfig(
        name="backup",
        fn=_do_backup,
        interval_seconds=7 * 86400,
        use_lock=True,
        marker_name="last-backup",
    ))

    pipeline.add_stage(StageConfig(
        name="doctor",
        fn=_do_doctor,
        interval_seconds=7 * 86400,
        use_lock=False,
        marker_name="last-doctor",
    ))

    pipeline.add_stage(StageConfig(
        name="reflect_stale",
        fn=_do_reflect_stale,
        interval_seconds=604800,  # 7 days
        use_lock=False,
        marker_name="last-reflect-stale",
    ))

    pipeline.add_stage(StageConfig(
        name="doc_scan",
        fn=_do_doc_scan,
        interval_seconds=3600,
        use_lock=False,
        marker_name="last-doc-scan",
    ))

    pipeline.add_stage(StageConfig(
        name="cloud_pull",
        fn=_do_cloud_pull,
        interval_seconds=86400,
        use_lock=False,
        marker_name="last-cloud-pull",
    ))

    return pipeline
