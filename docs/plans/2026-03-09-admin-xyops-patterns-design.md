# Admin Dashboard: xyOps-Inspired Patterns

Date: 2026-03-09
Status: Approved
Inspired by: [pixlcore/xyops](https://github.com/pixlcore/xyops) (DevOps monitoring platform)

## Features

### 1. Contextual Alert Bundling

Expand each problem/alert in the Dashboard Problems Panel into a rich card that auto-bundles related context. Context is lazy-loaded via `/api/admin/alert-context/[alertType]` on expand (not bundled in ambient-status polling).

Alert types and their bundled context:
- **Failing job**: last 3 run logs, error message, schedule config, retry action
- **Failed tweet**: rejected content, rejection reason, recent successful tweets, re-queue action
- **Memory spike**: 5 most recent memories causing the spike, types, storing agent
- **Cloud sync gap**: last successful sync timestamp, unsynced record count, force-sync action
- **Coordination conflict**: file path, both agents' session IDs, intents, resolution options

UI: Expandable cards in Problems Panel. Click to expand triggers context fetch. AmbientToast also gets richer content for high-severity alerts.

Files: `Dashboard.tsx` (Problems Panel), `AmbientToast.tsx`, new API route `app/api/admin/alert-context/route.ts`

### 2. One-Click Action Buttons on Alerts

Action buttons on each problem card:
- "Retry" on failed jobs (calls existing schedule-runs API)
- "Force Sync" on cloud sync gaps
- "Dismiss" / "Snooze 1h" on non-critical alerts (localStorage + optional Supabase persist)
- "View Agent" on coordination conflicts (switches to Coordination tab with agent selected)
- "Re-queue" on failed tweets (calls existing approvals API)

No new backend endpoints needed — wires UI to existing APIs.

Files: `Dashboard.tsx`, shared `AlertActionButton` component

### 3. Hook Pipeline Visualization

Directed graph showing hook execution flow as a visual pipeline in the Diagnostic tab.

- Nodes: each hook type (session_start, pre_edit, post_edit, pre_push, session_stop, etc.)
- Edges: execution order with timing (ms)
- Node colors: green (success), red (error), gray (not triggered)
- Click node: shows last N executions with payloads and outputs
- Data: hook execution logs from fast_hook.py, served via new `/api/admin/hook-pipeline` endpoint

Implementation: SVG-based directed graph (no ReactFlow dependency — keep it lightweight). Horizontal left-to-right layout.

Files: New `HookPipeline.tsx` component, new section in `Diagnostic.tsx`, new API route `app/api/admin/hook-pipeline/route.ts`

### 4. Incident Timeline with Correlated Events

Unified chronological view merging events across subsystems. New mode in the Feed tab (toggle: "Memories" | "Timeline").

Event sources:
- Coordination: agent joins, file claims, task completions
- Memory: stores, queries, spikes
- Jobs: runs, failures, completions
- Hooks: guards triggered, edits blocked
- Git: commits, pushes

Features:
- Color-coded event type pills
- Filter by: time range, agent, project, event type
- Click event to drill into relevant tab with context
- Aggregates from existing API endpoints (coordination/*, ambient-status, schedule-runs, memories)

Files: New `IncidentTimeline.tsx` component, new API route `app/api/admin/timeline/route.ts`, modification to Feed tab to add mode toggle

### 5. Persistent Alert History

Store alert events in Supabase `admin_alerts` table. New section in Diagnostic tab.

Schema:
```sql
create table admin_alerts (
  id uuid primary key default gen_random_uuid(),
  type text not null,
  severity text not null default 'warning',
  title text not null,
  detail jsonb,
  status text not null default 'active', -- active, resolved, dismissed, snoozed
  snoozed_until timestamptz,
  resolved_at timestamptz,
  created_at timestamptz not null default now()
);
create index idx_admin_alerts_status on admin_alerts(status);
create index idx_admin_alerts_created on admin_alerts(created_at desc);
```

Features:
- Persist alerts from ambient-status polling (deduplicate by type + 1h window)
- Show history: timestamp, type, severity, status, recurrence count
- Pattern detection: "cloud sync failed 3 times this week" surfaced as a meta-alert

Files: New Supabase migration, new `AlertHistory.tsx` section in Diagnostic, modification to ambient-status polling to persist alerts

## Implementation Order

1. Feature 1 + 2 (Contextual Alert Bundling + Action Buttons) — paired, biggest UX win
2. Feature 3 (Hook Pipeline Visualization) — most novel addition
3. Feature 4 (Incident Timeline) — highest effort
4. Feature 5 (Persistent Alert History) — requires DB migration, do last

## Non-Goals

- No WebSocket/SSE migration (keep polling)
- No new tab (features slot into existing tabs)
- No RBAC changes
- No changes to the Python backend or hook system itself
