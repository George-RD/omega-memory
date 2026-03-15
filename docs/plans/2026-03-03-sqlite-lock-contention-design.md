# SQLite Lock Contention Fix — Design

**Date:** 2026-03-03
**Problem:** With 8-10 concurrent Claude Code sessions, each spawning an `omega.server.mcp_server` process, the shared SQLite database at `~/.omega/omega.db` gets locked and operations fail with "database is locked after 5 retries". The 22MB WAL file confirms checkpoints are failing.

**Approach:** Tactical fixes (Approach A) — fix 6 identified root causes within the current SQLite architecture.

## Root Causes

### 1. `coord_audit` writes on every tool call (Rank 1 contention source)
- `handle_trace_capture()` in `hook_server/trace.py` calls `mgr.log_audit()` on every single tool call
- Each call: `BEGIN IMMEDIATE` + `INSERT coord_audit` + `COMMIT`
- 8-10 sessions each making tool calls = continuous write storm

### 2. CoordinationManager `busy_timeout=5000` (6x lower than SQLiteStore)
- `coordination.py:203` uses `busy_timeout=5000ms` vs SQLiteStore's `30000ms`
- Coordination writes fail first under contention, producing the user-visible errors
- Heartbeats (8-10 every 30s) + file reads + claims all use this short timeout

### 3. ThompsonBandit raw `conn.commit()` without `store._lock`
- `thompson.py` lines 62, 104 call `conn.commit()` directly on `store._conn`
- If store is mid-transaction, this prematurely commits a partial write
- Race condition that can corrupt data

### 4. Bare `sqlite3.connect()` calls in fallback hooks
- `hooks/session_stop.py:46` — `timeout=2`, no WAL, no busy_timeout
- `hooks/surface_memories.py:559` — `timeout=1`, no WAL, no busy_timeout
- `hook_server/utils.py:445` — `timeout=30`, no busy_timeout
- `hook_server/session.py:102` — `timeout=2`, no WAL, no busy_timeout
- These fail immediately under contention

### 5. Startup TRUNCATE checkpoint with 8-10 persistent readers
- `_base.py:340` runs `PRAGMA wal_checkpoint(TRUNCATE)` at startup
- TRUNCATE needs exclusive access — impossible with 8-10 persistent connections
- 8-10 servers starting simultaneously = instant deadlock cluster

### 6. Synchronized heartbeat/coordination timers
- 8-10 processes heartbeat every 30s with no jitter
- Write bursts synchronize, creating periodic lock storms

## Fixes

### Fix 1: Batch `coord_audit` writes
- Buffer audit rows in memory (list)
- Flush every N rows (default 20) or every T seconds (default 30)
- Single `INSERT INTO coord_audit VALUES ...` for the batch
- Flush on session stop (ensure no data loss)
- **File:** `src/omega/server/hook_server/trace.py`, `src/omega/coordination.py`

### Fix 2: Align CoordinationManager timeouts
- Change `coordination.py` `busy_timeout` from 5000 to 30000
- Change `timeout` from 5 to 30
- **File:** `src/omega/coordination.py`

### Fix 3: Fix ThompsonBandit lock acquisition
- Wrap `conn.commit()` calls in `with store._lock:`
- Or use a separate method on SQLiteStore that acquires the lock
- **File:** `src/omega/thompson.py`

### Fix 4: Standardize bare sqlite3.connect() calls
- Create a shared `safe_connect(db_path)` helper that always sets WAL + busy_timeout
- Replace all bare `sqlite3.connect()` calls in hook files
- **Files:** `hooks/session_stop.py`, `hooks/surface_memories.py`, `hook_server/utils.py`, `hook_server/session.py`

### Fix 5: Startup checkpoint TRUNCATE -> PASSIVE
- Change `_base.py` startup checkpoint from TRUNCATE to PASSIVE
- PASSIVE is non-blocking and correct for startup
- Keep periodic TRUNCATE attempts (they'll succeed when contention is lower)
- **File:** `src/omega/sqlite_store/_base.py`

### Fix 6: Add jitter to heartbeat and coordination timers
- Add `random.uniform(0, 15)` seconds jitter to heartbeat interval
- Add `random.uniform(0, 30)` seconds jitter to coordination tick
- Desynchronizes write bursts across processes
- **Files:** `src/omega/server/mcp_server.py`, `src/omega/coordination.py`

## Testing
- Run `pytest -x` after all changes
- Manual test: start 4+ Claude Code sessions simultaneously, verify no lock errors
- Check WAL size stays under 8MB after 10 minutes of concurrent use

## Success Criteria
- Zero "database is locked" errors with 8-10 concurrent sessions
- WAL file size stays under 10MB
- No data loss (audit rows still written, just batched)
