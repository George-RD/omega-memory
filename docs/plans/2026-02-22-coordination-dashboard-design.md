# Coordination Dashboard Design

**Date**: 2026-02-22
**Status**: Approved
**Audience**: Admin (Jason's personal use)
**Approach**: New admin tab + @xyflow/react

## Context

OMEGA's multi-agent coordination system tracks sessions, file claims, intents, tasks, and messages in SQLite (`coord_*` tables). Currently there is no visual representation of this data. The goal is to build an interactive node graph that shows which agents are active and what files they've claimed, inspired by DetectFlow's orchestration visualization pattern.

## Architecture

New "Coordination" tab (8th tab) in the existing `/admin` dashboard, lazy-loaded like all other tabs.

### Components

```
website/app/admin/
  coordination/
    CoordinationTab.tsx          # Main lazy-loaded container
    CoordinationFlow.tsx         # React Flow graph wrapper
    nodes/
      AgentNode.tsx              # Custom node for active sessions
      FileNode.tsx               # Custom node for claimed files
    useCoordinationData.ts       # Polling hook (5s interval)

website/app/api/admin/coordination/
    route.ts                     # API endpoint (reads coord_ tables)
```

### Node Types

**Agent nodes** (from `coord_sessions`):
- Fields: session_id, project, status, task, last_heartbeat
- Color: green (active), yellow (idle), red (stale, heartbeat >2min)
- Dimmed at 80% opacity if heartbeat >10min
- Visual: larger rounded rectangle

**File nodes** (from `coord_file_claims`):
- Fields: file_path (truncated), claimed_at
- Visual: smaller pill shape
- Grouped by directory if >50 claims

### Edges

- Agent -> File: solid animated line ("claims" relationship)
- Agent -> Agent: dashed line (future, from `coord_messages`)

### Layout

- Agents as larger nodes on the left column
- Files as smaller nodes on the right column
- Auto-layout via dagre or simple column positioning
- Unclaimed agents shown as standalone nodes

### API Endpoint

`GET /api/admin/coordination`

```typescript
interface CoordinationResponse {
  sessions: Array<{
    session_id: string;
    project: string;
    status: string;
    task: string;
    last_heartbeat: string;
    started_at: string;
  }>;
  file_claims: Array<{
    file_path: string;
    session_id: string;
    task: string;
    claimed_at: string;
  }>;
}
```

Reads from `~/.omega/omega.db` with `timeout=5`. If DB locked, returns server-side cached response (in-memory, 5s TTL).

### Polling

`useCoordinationData` hook:
- Fetches `/api/admin/coordination` every 5 seconds
- Returns `{ sessions, fileClaims, isLoading, error }`
- Transforms into React Flow nodes + edges on each poll
- React Flow preserves node positions across updates (internal diffing)

### Visual Style

- Admin color tokens: gold accent (#FFB000), canvas/surface/ink
- Agent nodes: status dot + session ID + project + current task
- File nodes: truncated path pill
- Edges: animated dashed lines for active claims
- Click any node for detail panel (reuse existing DetailPanel pattern)

### Error Handling

- DB locked: 5s timeout, return cached response
- No sessions: empty state ("No active agent sessions")
- Stale sessions: red status dot (>2min), dimmed opacity (>10min)
- Many nodes: group files by directory if >50 claims

## Scope

### In Scope
- Live view of active agent sessions as nodes
- File claims as connected nodes
- Auto-refresh every 5 seconds
- Color-coded status (active/idle/stale)
- Click-to-drill detail panel

### Out of Scope
- Task graph visualization
- Message flow visualization
- Historical playback
- Coordination controls (read-only only, no killing sessions)
- Intent visualization

## Dependencies

- `@xyflow/react` (MIT license, ~150KB)
- `dagre` (MIT, for auto-layout, optional)

## Inspiration

- SOC Prime DetectFlow: interactive node graph with status-coded nodes and flow direction
- ComposioHQ agent-orchestrator: tmux-based dashboard (table view, simpler)
