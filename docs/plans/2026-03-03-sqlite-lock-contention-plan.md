# SQLite Lock Contention Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate "database is locked" errors when running 8-10 concurrent Claude Code sessions against `~/.omega/omega.db`.

**Architecture:** Six tactical fixes targeting the identified root causes: batch high-frequency audit writes, align timeouts, fix a race condition, standardize bare connections, switch startup checkpoint mode, and add timer jitter. All changes stay within the current single-SQLite architecture.

**Tech Stack:** Python 3.11, sqlite3 stdlib, threading, OMEGA MCP server

---

### Task 1: Batch `coord_audit` writes (highest impact)

**Files:**
- Modify: `src/omega/coordination.py:3787-3827` (`log_audit` method)
- Modify: `src/omega/server/hook_server/trace.py:34-73` (`handle_trace_capture`)
- Test: `tests/test_coordination.py`

**Step 1: Add audit buffer and flush method to CoordinationManager**

In `src/omega/coordination.py`, add an `_audit_buffer` list and a flush method. Place the buffer, lock, and constants near the `__init__` method.

```python
# Near top of CoordinationManager class, in __init__:
self._audit_buffer: list[tuple] = []
self._audit_buffer_lock = threading.Lock()
self._audit_last_flush = time.monotonic()

# Constants (module-level):
_AUDIT_BATCH_SIZE = 20
_AUDIT_FLUSH_INTERVAL_S = 30
```

**Step 2: Rewrite `log_audit` to buffer instead of write**

Replace the existing `log_audit` method (lines 3787-3827):

```python
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

    # Cloud fire is fire-and-forget, still per-row
    if session_id:
        self._cloud_fire(
            "insert_audit", session_id, tool_name, result_summary,
            now, call_index, result_status, input_size, latency_ms,
        )

    return 0  # No real rowid until flush
```

**Step 3: Add `flush_audit_buffer` method**

```python
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
```

**Step 4: Add `import time` to coordination.py imports**

At the top of `coordination.py`, ensure `import time` is present.

**Step 5: Flush audit buffer on session stop**

In the `session_stop` method of CoordinationManager (find with `def session_stop`), add a call to `self.flush_audit_buffer()` at the very start of the method, before any status updates.

**Step 6: Add time-based flush to the coordination tick**

In `src/omega/server/mcp_server.py`, function `_run_coordination_tick()` (line 369), add after the stale cleanup:

```python
# Flush audit buffer on every tick (time-based fallback)
try:
    mgr.flush_audit_buffer()
except Exception as e:
    logger.debug("Audit buffer flush failed: %s", e)
```

**Step 7: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_coordination.py -x -v`
Expected: All pass

**Step 8: Commit**

```bash
git add src/omega/coordination.py src/omega/server/mcp_server.py
git commit -m "perf: batch coord_audit writes to reduce lock contention"
```

---

### Task 2: Align CoordinationManager timeouts (trivial, high impact)

**Files:**
- Modify: `src/omega/coordination.py:195-203`

**Step 1: Change timeout from 5 to 30**

In `_connect()` method (line 195-203), change:

```python
# Before:
conn = secure_connect(
    self.db_path,
    timeout=5,
    ...
)
...
conn.execute("PRAGMA busy_timeout=5000")  # 5s

# After:
conn = secure_connect(
    self.db_path,
    timeout=30,
    ...
)
...
conn.execute("PRAGMA busy_timeout=30000")  # 30s — match SQLiteStore
```

**Step 2: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_coordination.py -x -v`
Expected: All pass

**Step 3: Commit**

```bash
git add src/omega/coordination.py
git commit -m "fix: align CoordinationManager busy_timeout to 30s (was 5s)"
```

---

### Task 3: Fix ThompsonBandit race condition

**Files:**
- Modify: `src/omega/thompson.py:47-62,79-104,204-234`
- Test: `tests/test_thompson.py` (if exists, else `tests/`)

**Step 1: Add a `_locked_commit` helper**

Replace `_get_conn` method and add a helper:

```python
def _get_conn(self):
    store = self._get_store()
    return store._conn

def _locked_execute_and_commit(self, *statements):
    """Execute SQL statements under the store's lock, then commit."""
    store = self._get_store()
    with store._lock:
        for sql, params in statements:
            store._conn.execute(sql, params)
        store._conn.commit()
```

**Step 2: Update `_ensure_arm` to use locked commit**

```python
def _ensure_arm(self, arm_id: str, arm_type: str, context: Optional[str] = None) -> None:
    """Create arm if it doesn't exist."""
    now = datetime.now(timezone.utc).isoformat()
    self._locked_execute_and_commit(
        ("""INSERT OR IGNORE INTO thompson_arms
            (arm_id, arm_type, alpha, beta, total_trials, total_successes,
             last_updated, context)
            VALUES (?, ?, ?, ?, 0, 0, ?, ?)""",
         (arm_id, arm_type, DEFAULT_ALPHA, DEFAULT_BETA, now, context)),
    )
```

**Step 3: Update `record_outcome` to use locked commit**

Replace the raw `conn.execute` + `conn.commit()` calls (lines 81-104) with `_locked_execute_and_commit`:

```python
def record_outcome(self, arm_id, arm_type, success, context=None):
    self._ensure_arm(arm_id, arm_type, context)
    now = datetime.now(timezone.utc).isoformat()

    if success:
        sql = """UPDATE thompson_arms
                 SET alpha = alpha + 1, total_trials = total_trials + 1,
                     total_successes = total_successes + 1, last_updated = ?
                 WHERE arm_id = ?"""
    else:
        sql = """UPDATE thompson_arms
                 SET beta = beta + 1, total_trials = total_trials + 1,
                     last_updated = ?
                 WHERE arm_id = ?"""

    self._locked_execute_and_commit((sql, (now, arm_id)))

    # Read back (reads are safe without lock in WAL mode)
    conn = self._get_conn()
    row = conn.execute(
        "SELECT alpha, beta, total_trials, total_successes FROM thompson_arms WHERE arm_id = ?",
        (arm_id,),
    ).fetchone()
    if row:
        return {"arm_id": arm_id, "alpha": row[0], "beta": row[1],
                "total_trials": row[2], "total_successes": row[3],
                "success_rate": row[3] / max(row[2], 1)}
    return {"arm_id": arm_id, "error": "arm not found after update"}
```

**Step 4: Update `decay_arms` to use locked commit**

Replace the raw `conn.execute` loop + `conn.commit()` (lines 211-234):

```python
def decay_arms(self, factor: float = 0.99) -> int:
    conn = self._get_conn()
    now = datetime.now(timezone.utc).isoformat()
    rows = conn.execute("SELECT arm_id, alpha, beta FROM thompson_arms").fetchall()

    updates = []
    for arm_id, alpha, beta_val in rows:
        new_alpha = max(DEFAULT_ALPHA, alpha * factor)
        new_beta = max(DEFAULT_BETA, beta_val * factor)
        if new_alpha != alpha or new_beta != beta_val:
            updates.append((
                """UPDATE thompson_arms SET alpha = ?, beta = ?, last_updated = ?
                   WHERE arm_id = ?""",
                (new_alpha, new_beta, now, arm_id),
            ))

    if updates:
        self._locked_execute_and_commit(*updates)
    return len(updates)
```

**Step 5: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -k thompson -x -v`
Expected: All pass (or no tests found, which is fine)

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x --timeout=60`
Expected: Full suite passes

**Step 6: Commit**

```bash
git add src/omega/thompson.py
git commit -m "fix: ThompsonBandit acquires store._lock before commit"
```

---

### Task 4: Standardize bare sqlite3.connect() calls

**Files:**
- Modify: `hooks/session_stop.py:46`
- Modify: `hooks/surface_memories.py:559`
- Modify: `src/omega/server/hook_server/utils.py:445`
- Modify: `src/omega/server/hook_server/session.py:102`
- Modify: `src/omega/server/hook_server/maintenance.py:186,520`

**Step 1: Read each file to find the exact bare connect call and its context**

Read each file around the line numbers above. Each bare `sqlite3.connect()` needs two PRAGMAs added immediately after:

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
```

And increase `timeout` to at least 10 (currently 1-2 in some files).

**Step 2: Fix `hooks/session_stop.py:46`**

Change `timeout=2` to `timeout=10` and add PRAGMAs after the connect call.

**Step 3: Fix `hooks/surface_memories.py:559`**

Change `timeout=1` to `timeout=10` and add PRAGMAs after the connect call.

**Step 4: Fix `src/omega/server/hook_server/utils.py:445`**

Keep `timeout=30`, add `PRAGMA busy_timeout=30000` and `PRAGMA journal_mode=WAL`.

**Step 5: Fix `src/omega/server/hook_server/session.py:102`**

Change `timeout=2` to `timeout=10` and add PRAGMAs.

**Step 6: Fix `src/omega/server/hook_server/maintenance.py:186,520`**

These already have `timeout=30`. Add `PRAGMA busy_timeout=30000` and `PRAGMA journal_mode=WAL` after each connect.

**Step 7: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x --timeout=60`
Expected: All pass

**Step 8: Commit**

```bash
git add hooks/session_stop.py hooks/surface_memories.py src/omega/server/hook_server/utils.py src/omega/server/hook_server/session.py src/omega/server/hook_server/maintenance.py
git commit -m "fix: add WAL + busy_timeout to all bare sqlite3.connect() calls"
```

---

### Task 5: Startup checkpoint TRUNCATE -> PASSIVE

**Files:**
- Modify: `src/omega/sqlite_store/_base.py:340`

**Step 1: Change TRUNCATE to PASSIVE**

At line 340, change:

```python
# Before:
result = self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()

# After:
result = self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
```

**Step 2: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x --timeout=60`
Expected: All pass

**Step 3: Commit**

```bash
git add src/omega/sqlite_store/_base.py
git commit -m "perf: startup WAL checkpoint TRUNCATE -> PASSIVE (non-blocking)"
```

---

### Task 6: Add jitter to heartbeat and coordination timers

**Files:**
- Modify: `src/omega/server/mcp_server.py:433-441` (`_coordination_loop`)
- Modify: `src/omega/coordination.py` (heartbeat debounce)

**Step 1: Add jitter to coordination loop**

In `src/omega/server/mcp_server.py`, function `_coordination_loop()` (line 433):

```python
import random

async def _coordination_loop():
    """Periodic coordination maintenance — runs even during idle."""
    loop = asyncio.get_running_loop()
    while True:
        # Jitter: 60-90s to desynchronize across processes
        await asyncio.sleep(60 + random.uniform(0, 30))
        try:
            await loop.run_in_executor(_SQLITE_EXECUTOR, _run_coordination_tick)
        except Exception as e:
            logger.debug("Coordination loop tick failed: %s", e)
```

**Step 2: Verify `random` is already imported in mcp_server.py, or add it**

Check imports at top of file. Add `import random` if missing.

**Step 3: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x --timeout=60`
Expected: All pass

**Step 4: Commit**

```bash
git add src/omega/server/mcp_server.py
git commit -m "perf: add jitter to coordination loop timer (60-90s)"
```

---

### Task 7: Final verification

**Step 1: Run full test suite**

Run: `cd ~/Projects/omega && python3.11 -m pytest -x`
Expected: All pass with 0 failures

**Step 2: Manual smoke test**

Open 4+ Claude Code sessions simultaneously. In each, run a few tool calls. Verify:
- No "database is locked" errors in `~/.omega/logs/`
- WAL file stays under 10MB: `ls -lh ~/.omega/omega.db-wal`
- `omega_store` and `omega_query` work from all sessions

**Step 3: Final commit if any fixups needed, then push**

```bash
cd ~/Projects/omega && git push
```
