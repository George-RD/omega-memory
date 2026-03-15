# Admin Projects Tab — Design Document

**Date**: 2026-02-28
**Status**: Approved
**Goal**: Move project visibility from Dashboard to a dedicated Projects tab. Provide a session-based timeline that answers "where did I leave off?" and "what did I do?"

---

## Motivation

The current Dashboard tab mixes system health with project overview cards. The project cards show static config data and sparse metrics but don't answer the two most important questions for a user returning to their projects:

1. **Where did I leave off?** — What was I working on, what's next, what's blocked?
2. **What did I do?** — Session history, decisions made, files touched, commits.

The OMEGA coordination system already captures rich structured data via `coord_handoffs` (completed_tasks, blocked_items, key_context, next_steps, files_modified, decisions_made), `coord_sessions`, `coord_decisions`, and `coord_git_events`. This tab surfaces that data in a human-readable timeline.

---

## Architecture

### Tab Registration

- New tab ID: `"projects"`
- Registered in `primaryItems` in Sidebar (position 2, after Dashboard)
- Dashboard tab **keeps** System Health Report Card + ambient status bar, **loses** the project cards grid
- URL: `/admin?tab=projects`

### Layout

```
┌───────────────────────────────────────────────────────────────┐
│ ┌──────────────┐  ┌───────────────────────────────────────┐   │
│ │ Project List  │  │  Resume Bar                           │   │
│ │ (~240px)      │  ├───────────────────────────────────────┤   │
│ │               │  │  Stats Header                         │   │
│ │ • OMEGA     ←─│  ├───────────────────────────────────────┤   │
│ │ • Website    │  │                                       │   │
│ │ • Element1   │  │  Session Timeline                     │   │
│ │ • kokyo      │  │  (scrollable, newest first)           │   │
│ │ ┄┄┄┄┄┄┄┄┄┄┄ │  │                                       │   │
│ │ • polymarket │  │                                       │   │
│ └──────────────┘  └───────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Project List Panel (Left)

**File**: `app/admin/components/projects/ProjectList.tsx`

Each project entry:
- **Name** + relative timestamp ("2h ago", "3d ago")
- **Session count** (total) + **active task count**
- **Status dot**: green = active session now, default = idle
- Sorted by last activity (most recent first)
- Stale projects (30d+ inactive) grouped below a divider
- Selected project highlighted with gold bar (matching sidebar pattern)
- Auto-selects most recently active project on mount

**Data source**: New `/api/admin/projects/list` endpoint.

### 2. Resume Bar

**File**: `app/admin/components/projects/ResumeBar.tsx`

Shows the most recent handoff for the selected project:
- **Task description** from the session
- **Branch** + **file count** from handoff
- **Next steps** (array, rendered as a list) — the "pick up here" signal
- **Blocked items** (amber warning, only if non-empty)
- **Timestamp** (relative)
- Collapses to "No recent activity" if no handoffs exist for the project

**Data source**: Most recent entry from `coord_handoffs` for the selected project.

### 3. Stats Header

**File**: `app/admin/components/projects/StatsHeader.tsx`

Compact single row:
- Total sessions · Total decisions · Total commits · Project age ("Since Oct")
- Time range filter chips: [All] [This week] [This month]

### 4. Session Timeline

**File**: `app/admin/components/projects/SessionTimeline.tsx`

Chronological list of session cards (newest first).

**Session Card** (`SessionCard.tsx`):
- **Header**: session number, task description, timestamp, duration, branch
- **Collapsible sections**:
  - ✓ **Completed tasks** — from `handoff.completed_tasks`
  - ◆ **Decisions** — from `handoff.decisions_made` + linked `coord_decisions` (with rationale)
  - ◇ **Files modified** — from `handoff.files_modified` (truncated with "+N more")
  - ⟠ **Commits** — from `coord_git_events` (hash + message)
  - ⏭ **Next steps** — from `handoff.next_steps` (only on most recent session)
  - ⚠ **Blocked** — from `handoff.blocked_items` (only if non-empty)
- Most recent session: expanded. All others: collapsed.
- Sessions without handoffs: show minimal card (task + timestamp only)
- Pagination: 20 per page, "Load more" button

---

## API Endpoints

### `GET /api/admin/projects/list`

Returns all projects with summary stats.

```typescript
interface ProjectListItem {
  id: string;           // canonical project name
  name: string;         // display name
  category: string;     // from projectConfig
  lastActive: string;   // ISO timestamp
  sessionCount: number;
  activeTaskCount: number;
  hasActiveSession: boolean;
}
```

**Implementation**: Queries `coord_sessions` grouped by project, joins with `coord_tasks` for active count. Maps project paths to display names using `projectConfig.ts` `sessionNames`.

### `GET /api/admin/projects/timeline`

Query params:
- `project` (required): canonical project name
- `limit` (default 20): sessions per page
- `offset` (default 0): pagination offset
- `since` (optional): ISO timestamp for time filtering

```typescript
interface ProjectTimelineEntry {
  session: CoordinationSession;
  handoff: CoordinationHandoff | null;
  decisions: CoordinationDecision[];
  gitEvents: CoordinationGitEvent[];
  durationMinutes: number;  // calculated: handoff.created_at - session.started_at
}

interface ProjectTimelineResponse {
  entries: ProjectTimelineEntry[];
  total: number;
  project: string;
}
```

**Implementation**: Queries `coord_sessions` WHERE project matches, ordered by `started_at DESC`. For each session, LEFT JOINs `coord_handoffs`, `coord_decisions`, and `coord_git_events` by `session_id`.

---

## Dashboard Changes

Remove from Dashboard tab:
- `ProjectGrid` component (the 3-column project cards)
- `DetailPanel` component (row-level project expansion)
- `projectConfig.ts` moves to shared location (used by both Dashboard health and Projects tab)

Keep on Dashboard tab:
- System Health Report Card (grading A–F)
- Ambient Status Bar (active agents, memory sparkline, conflicts)
- Suggestions panel (if any remain non-project-specific)

---

## File Structure

```
app/admin/components/projects/
├── ProjectsView.tsx         # Main container (layout, state management)
├── ProjectList.tsx           # Left panel: project navigator
├── ResumeBar.tsx             # "Where I left off" hero component
├── StatsHeader.tsx           # Session/decision/commit counts + filters
├── SessionTimeline.tsx       # Scrollable list of session cards
└── SessionCard.tsx           # Individual session entry with collapsible sections

app/api/admin/projects/
├── list/route.ts             # GET: project list with summary stats
└── timeline/route.ts         # GET: session timeline for a project
```

---

## Sidebar Registration

```typescript
// In primaryItems array:
{ id: "projects", label: "Projects", icon: FolderIcon }
// Position: after Dashboard, before Feed
```

Badge: Show count of projects with unread handoffs (handoffs where `read_by` doesn't include the current "user"). Optional — can ship without this initially.

---

## Data Flow

1. Tab loads → fetch `/api/admin/projects/list` → render Project List
2. Auto-select most recently active project
3. Fetch `/api/admin/projects/timeline?project=omega&limit=20`
4. Render Resume Bar from first entry's handoff
5. Render Session Timeline from all entries
6. User clicks different project → re-fetch timeline
7. User clicks time filter → re-fetch with `since` param

---

## Non-Goals (for this iteration)

- Task board / Kanban view (future enhancement)
- Drag-and-drop task reordering
- Creating/editing tasks from the UI
- Real-time updates (polling on 60s interval is sufficient)
- Mobile-optimized layout (desktop-first, responsive later)
