# Session Tracing Design

> Always-on, lightweight session tracing for debugging agent behavior.
> Inspired by [@lt0gt's trace viewing prototype](https://x.com/lt0gt/status/2025031631589789854).

**Date**: 2026-02-22
**Status**: Approved
**Tier**: Pro-only

## Goals

- Primary: Debug agent behavior ("why did the agent do X?") by replaying full tool call sequences.
- Secondary: Audit trail for pro users in the admin dashboard (viewer deferred).

## Decisions

- Always-on (no opt-in toggle). Lightweight capture, zero user friction.
- Extend existing `coord_audit` table (no new table).
- Data first, dashboard viewer later.
- No full input/output storage; `input_size` gives signal without cost.

## Schema Migration

4 new nullable columns on `coord_audit`:

```sql
ALTER TABLE coord_audit ADD COLUMN latency_ms INTEGER;
ALTER TABLE coord_audit ADD COLUMN call_index INTEGER;
ALTER TABLE coord_audit ADD COLUMN result_status TEXT DEFAULT 'ok';
ALTER TABLE coord_audit ADD COLUMN input_size INTEGER;
```

- `latency_ms`: Wall-clock time for the tool call (estimated from hook timing).
- `call_index`: Sequential counter per session (1, 2, 3...) for ordering.
- `result_status`: `ok`, `error`, or `timeout` derived from tool output.
- `input_size`: Byte length of tool_input.

All nullable so existing rows are unaffected.

## Capture Point

New `handle_trace_capture()` handler registered as PostToolUse with empty matcher (all tools):

```json
{"script": "fast_hook.py trace_capture", "timeout": 2000, "matcher": ""}
```

The handler:
1. Increments per-session `call_index` counter (in-memory dict keyed by session_id).
2. Classifies `result_status` from tool_output (regex: Traceback, Error:, exit code, timed out).
3. Computes `input_size` from `len(tool_input)`.
4. Writes one row to `coord_audit` via extended `log_audit()`.

Overhead: <1ms per tool call (single SQLite INSERT).

## log_audit() Extension

```python
def log_audit(self, session_id, tool_name, arguments,
              result_summary=None, latency_ms=None,
              call_index=None, result_status="ok", input_size=None):
```

Existing callers unaffected (new params default to None).

## Query Interface

1. Extended `query_audit()` includes new columns in SELECT.
2. New `mode="trace"` in `omega_query` formats output as session timeline:

```
Session abc123 -- 47 tool calls, 12.3s total, 2 errors

 #1  0ms    Read        src/omega/bridge.py           ok     2.1KB
 #2  45ms   Grep        pattern="def store"           ok     0.3KB
 #3  120ms  Edit        src/omega/server/handlers.py  ok     1.5KB
 ...
 #31 8200ms Bash        pytest -x                     error  4.2KB
```

Retention: Follows existing `AUDIT_RETENTION_DAYS` cleanup.

## Files Changed

| Component | Change | File |
|---|---|---|
| Schema + migration | 4 ALTERs in `_ensure_tables()` | `coordination.py` |
| Capture handler | New `handle_trace_capture()` | `hook_server/trace.py` (new) |
| Hook dispatch | Register + wire fallback | `core.py`, `fast_hook.py` |
| Hook config | New PostToolUse entry | `data/hooks.json` |
| Audit writer | Extend `log_audit()` | `coordination.py` |
| Query | Add `mode="trace"` | `handlers.py` |
| Tests | Schema, capture, query | `tests/test_trace.py` (new) |

## Explicitly Deferred

- Admin dashboard trace viewer (ship data first).
- PreToolUse timing (would need paired start/end tracking).
- Full input/output storage (input_size is sufficient).
- Span tree / nested tracing (not needed until multi-agent nesting).
