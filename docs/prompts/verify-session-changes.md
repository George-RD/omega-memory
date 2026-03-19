# Verification Prompt: Session dea24af Changes

> Paste this into your next Claude Code session to verify everything works.

## Context

Session on Feb 24, 2026 shipped two main features:

1. **3D Memory Graph** (`/admin/memories/graph`) - Interactive force-directed 3D visualization of OMEGA memories using `react-force-graph-3d` + Three.js
2. **Coordination task visibility** - Fixed "No task reported" on admin dashboard by backfilling `coord_sessions.task` from `announce_intent()` and exposing `omega_update_task` MCP tool

## Verification Checklist

### 1. Memory Graph (live at omegamax.co)

- [ ] Navigate to `omegamax.co/admin/memories/graph` - page loads without crash (no AFRAME error)
- [ ] 3D graph renders with colored nodes (blue=decision, green=lesson, red=error, etc.)
- [ ] Nodes cluster by project (visible grouping)
- [ ] Header bar shows project filter chips with labels like "omega", "element1" (NOT full filesystem paths)
- [ ] Each chip shows a count badge (e.g. "omega 342")
- [ ] Only projects with 5+ memories appear (no single-letter or noise projects)
- [ ] Clicking a chip filters the graph to that project
- [ ] Clicking a node opens the detail panel and camera flies to it
- [ ] Search box filters nodes by content
- [ ] Node count updates in the top-right corner

### 2. Coordination Task Field

Run these tests from `~/Projects/omega/`:

```bash
# All coordination tests should pass (246 + 90 = 336 tests)
python3.11 -m pytest tests/test_coordination.py -x -q
python3.11 -m pytest tests/test_uat_coordination.py -x -q

# Verify handler count is 44 and schema parity holds
python3.11 -m pytest tests/test_uat_coordination.py -k "handler_count or handler_schema_parity" -v
python3.11 -m pytest tests/test_tool_schemas.py::TestHandlerParity::test_coord_handler_parity -v
```

Then verify the backfill works end-to-end:

```python
# Quick smoke test in Python
import sys; sys.path.insert(0, "src")
from omega.coordination import CoordinationManager
mgr = CoordinationManager(":memory:")

# Register a session with no task
mgr.register_session("test-sess-1", pid=1234, project="/test")
sessions = mgr.list_sessions()
assert sessions[0]["task"] is None, "Session should start with no task"

# Announce an intent - should backfill the session task
result = mgr.announce_intent("test-sess-1", "fixing the login bug", target_files=["auth.py"])
assert result["success"]

# Verify task was backfilled
sessions = mgr.list_sessions()
assert sessions[0]["task"] == "fixing the login bug", f"Task should be backfilled, got: {sessions[0]['task']}"

# Second intent should NOT overwrite (only fills if empty)
mgr.announce_intent("test-sess-1", "refactoring the database layer")
sessions = mgr.list_sessions()
assert sessions[0]["task"] == "fixing the login bug", "Task should not change on subsequent intents"

# Explicit update_session_task should always work
mgr.update_session_task("test-sess-1", "new explicit task")
sessions = mgr.list_sessions()
assert sessions[0]["task"] == "new explicit task", "Explicit update should override"

print("All coordination task tests passed!")
```

### 3. New MCP Tool

Verify `omega_update_task` is registered:

```python
from omega.server.coord_schemas import COORD_TOOL_SCHEMAS
from omega.server.coord_handlers import COORD_HANDLERS
names = {s["name"] for s in COORD_TOOL_SCHEMAS}
assert "omega_update_task" in names, "Schema missing"
assert "omega_update_task" in COORD_HANDLERS, "Handler missing"
print("omega_update_task tool registered correctly")
```

### 4. Build Check

```bash
cd ~/Projects/omega/website && npm run build
```

Should complete with no errors. The memory graph page uses `next/dynamic` with `ssr: false` to avoid Three.js SSR issues.

### 5. Admin Dashboard

- [ ] Navigate to `omegamax.co/admin` - coordination panel should show active sessions
- [ ] Sessions that have edited files should now show a task description instead of "No task reported"
- [ ] New sessions will auto-populate task on first file edit (via `announce_intent` backfill)

## Key Files Changed

| File | Change |
|------|--------|
| `src/omega/coordination.py` | Added `update_session_task_if_empty()`, backfill call in `announce_intent()` |
| `src/omega/server/coord_handlers.py` | Added `handle_update_task`, registered in `COORD_HANDLERS` |
| `src/omega/server/coord_schemas.py` | Added `omega_update_task` tool schema |
| `tests/test_uat_coordination.py` | Updated handler count 43 -> 44 |
| `website/app/admin/memories/graph/*` | Full 3D graph implementation (page, hook, component, detail panel) |
| `website/app/api/admin/memories/graph/route.ts` | API endpoint with project filtering and label extraction |
