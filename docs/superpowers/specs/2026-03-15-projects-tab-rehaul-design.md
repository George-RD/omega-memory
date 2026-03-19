# Projects Tab Rehaul — Design Spec

## Context

The projects tab in the OMEGA admin dashboard is underutilized. It currently shows a flat table with expandable rows, plus a card grid view. Despite recent improvements (summary strip, sparklines, momentum indicators, hover previews), the layout doesn't surface actionable insights or support quick scanning of portfolio health.

**Inspiration:** AppFlowly CRM (Behance) — kanban workspace, progressive disclosure, generous spacing, semantic color coding, multi-view flexibility.

## Design Direction

Kanban board as the default view, blending command center urgency (what needs me now?) with workspace depth (drill into any project). Three-tier progressive disclosure:

```
Board (scan, 5s)  →  Drawer (context, 10s)  →  Full Page (deep work, minutes)
```

## Information Architecture

### Board Columns (blended grouping)

| Column | Contains | Logic | Accent |
|--------|----------|-------|--------|
| **Blocked** | Projects with `health === "blocked"` or `tasks.blocked > 0` | Health-driven | Red |
| **Active Now** | Has active agent session OR activity within 24h | Engagement-driven | Green |
| **This Week** | Last active within 7 days, not in above columns | Temporal | Amber |
| **Steady** | Active in 30 days but not this week | Temporal | Neutral |
| **Parked** | No sessions, no commits, no pending tasks in 30d | Dormant | Dimmed |

Cards within each column sorted by last active (most recent first). Projects with `lastActive === null` sort to the bottom.

### Empty States

- **Empty column**: Collapses to a thin header showing `COLUMN (0)` — no cards, just the label and a muted accent line.
- **All columns empty** (no projects): Full-board empty state — centered message: "No projects registered. Projects appear automatically from coordination sessions."
- **All projects parked**: Only the Parked column has cards, others collapsed. No special treatment — this accurately represents the portfolio state.
- **Search filters all cards**: If the search query matches zero projects, show "No projects match your filter" centered in the board area, all columns hidden.

### View Modes

Three modes accessible via toolbar toggle: `Board | Cards | List`

- **Board** (default): Kanban columns described above
- **Cards**: Existing `ProjectOverviewGrid` component
- **List**: Existing table view with sparklines and momentum

All three share the same data from `/api/admin/projects/overview`. No new API routes needed.

### Persistent Elements (visible across all views, hidden in full-page view)

- `SummaryStrip`: 4 stat cards (Active, Blocked, Tasks Open, Momentum) at top. **Receives only non-parked projects** — parked projects are excluded from active portfolio metrics.
- `NeedsAttentionBar`: Alert banner for projects needing attention

## Board Card Design

Compact, information-dense cards inside kanban columns.

### Card Anatomy

```
┌─────────────────────────────────┐
│ ● OMEGA                   2h ↑ │  Row 1: health dot, name, time, momentum
│                                 │
│ ▁▂▃▅▇▅▃  ████████░░ 72%       │  Row 2: sparkline + progress bar
│                                 │
│ Next: Fix cloud sync pipeline   │  Row 3: context line (2-line clamp)
│                                 │
│ [2 blocked] [3 in progress]     │  Row 4: action pills + session badge
│                        🟢 agent │
└─────────────────────────────────┘
```

### Card Content Priority

1. **Health dot** — color from `HEALTH_THEME`
2. **Project name** — bold, truncated
3. **Relative time** — mono, faint
4. **Momentum icon** — from `MOMENTUM_THEME`
5. **Sparkline** — 60px wide, color-coded by momentum
6. **Progress bar** — thin, with percentage. Uses task completion when `totalTasks > 0`, otherwise `launchProgress`. **Hidden entirely** when both are zero (avoids misleading 0% on active projects with no task tracking).
7. **Context line** — blockers (red) > next steps (amber) > summary (muted)
8. **Action pills** — blocked count, in-progress count (only non-zero)
9. **Active session badge** — green pill, right-aligned

### Card Interactions

- **Hover**: Subtle lift + border glow (`--shadow-card-hover`)
- **Click**: Opens side drawer
- **Health-tinted background**: `bg-red-400/[0.03]` for blocked, `bg-amber-400/[0.03]` for attention

### Column Header

```
BLOCKED (2)
━━━━━━━━━━━━━━  (colored accent line)
```

Uppercase mono label, count in parentheses, 2px accent line in column's semantic color.

### Spacing

- Card padding: 16px
- Gap between cards: 16px
- Gap between columns: 20px
- Column min-width: 280px
- Board horizontal scroll on overflow

## Side Drawer

Opens when a board card (or card/list item) is clicked. Slides in from the right.

### Specs

- **Width**: `max-w-[560px] w-full` — takes full width on mobile (`< md`), 560px max on desktop
- **Backdrop**: Board gets semi-transparent overlay, clickable to close
- **Animation**: Slide from right, 200ms ease-out
- **Close triggers**: X button, Escape key (with `stopPropagation` to prevent `useKeyboardNav` collision), backdrop click
- **Reuses existing `SlideDrawer` shell component** (`components/shell/SlideDrawer.tsx`) — wraps drawer content in its slide/backdrop logic. The existing `ProjectDetailDrawer.tsx` is replaced by this new `ProjectDrawer.tsx`.

### Drawer Layout (top to bottom)

1. **Header**: Close button (left) + "Open Full →" link (right)
2. **Identity**: Health dot + project name (large) + subtitle meta (last active, session count)
3. **Stat cards**: 4-column grid — Sessions, Commits, Decisions, Tasks (reuse existing stat card design)
4. **Sparkline**: Full-width, larger (120x40px)
5. **Blockers** (if any): Red-themed list, section label "BLOCKERS (N)"
6. **Next Steps**: Amber-themed numbered list
7. **Recent Work**: Activity timeline (commits, sessions, decisions) — reuse existing `ActivityTimeline` component
8. **Key Decisions**: Last 3 decisions with timestamps

### Content Priority

Blockers and next steps appear before activity — the drawer answers "what needs me?" before "what happened?"

## Full Page Project View

Accessible via "Open Full →" in the drawer. Replaces the board entirely.

### Layout

```
← Back to Projects          OMEGA          ● Healthy  ↑ momentum
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Overview]  [Tasks]  [Activity]  [Architecture]

(Tab content — full width, scrollable)
```

### Tabs

| Tab | Content | Data Source |
|-----|---------|-------------|
| **Overview** | Stat cards + sparkline + blockers + next steps + recent decisions. Drawer content at full width. | `ProjectOverview` |
| **Tasks** | Two-column: Remaining (left, grouped by status) + Completed (right). Status icon + title + priority badge per row. | `tasks.items` |
| **Activity** | Full activity timeline — commits, sessions, decisions interleaved. Expandable rows with file diffs, branch info. | `ActivityTimeline` component |
| **Architecture** | Mermaid diagram + session heatmap. Lazy-loaded. | `ArchitectureDiagram` + `SessionHeatmap` |

### Navigation State

- **No URL changes for drawer** — drawer is transient, component state only.
- **Full-page view uses `pushState`** — adds `?tab=projects&project=<id>&view=<tabName>` via `pushState` (not `replaceState`), so the browser back button returns to the board. This is intentionally different from the admin shell's `replaceState` pattern because the full-page view is a navigation-level transition.
- **Mount-time restore**: On mount, `ProjectsView` reads `project` and `view` from `window.location.search`. If both are present, it opens the full-page view directly (enables deep-linking and refresh).
- **Back button handler**: `ProjectFullView` listens for `popstate` events. When the user hits browser back, it closes the full view and restores the board. The board is hidden (not unmounted) so scroll position is preserved.
- **Keyboard nav disabled when drawer is open**: `useKeyboardNav` receives `enabled: !drawerOpen && !fullViewOpen` to prevent `Escape`/`j`/`k` collisions.

### Spacing

`px-8 py-6`, 24px gaps between sections, full-width content area.

### Keyboard Navigation

- **List view**: Existing `j`/`k`/`Enter`/`Escape` linear navigation (unchanged)
- **Board view**: Same linear `j`/`k` navigation, traversing cards left-to-right, top-to-bottom across columns (flattened order). No 2D arrow-key navigation — keeps implementation simple, and the board is primarily a mouse/scan interface.
- **Drawer open**: All keyboard nav disabled. Only `Escape` (handled by drawer with `stopPropagation`) is active.
- **Full-page view**: No keyboard nav — standard browser behavior.

## Component Architecture

### New Files

| File | Purpose |
|------|---------|
| `ProjectBoard.tsx` | Kanban board — columns, layout, card container |
| `ProjectBoardCard.tsx` | Compact kanban card |
| `ProjectDrawer.tsx` | Side drawer — replaces existing `ProjectDetailDrawer.tsx`. Uses `SlideDrawer` shell component. |
| `ProjectFullView.tsx` | Full-page workspace with horizontal tab navigation |
| `SummaryStrip.tsx` | Extracted from inline in `ProjectsView.tsx` for reuse |
| `ActivityTimeline.tsx` | Extracted from inline in `ProjectsView.tsx` for reuse |
| `ProjectDetailSections.tsx` | Shared sections (blockers, next steps, decisions, stat cards) used by drawer and full view |

### Modified Files

| File | Changes |
|------|---------|
| `ProjectsView.tsx` | Becomes orchestrator — manages view mode, drawer state, full-view navigation. Strips out inline components. Adds `pushState`/`popstate` for full-view. |
| `utils.ts` | Add `getProjectColumn`, `isActiveWithin`, export `BoardColumn` type |
| `types.ts` | Add `BoardColumn` type export |

### Deleted Files

| File | Reason |
|------|--------|
| `ProjectDetailDrawer.tsx` | Replaced by `ProjectDrawer.tsx` |

### Reused As-Is

| File | Used In |
|------|---------|
| `Sparkline.tsx` | Board cards, drawer, full view |
| `NeedsAttentionBar.tsx` | Above all views |
| `ProjectOverviewGrid.tsx` | Cards view mode |
| `ProjectOverviewCard.tsx` | Cards view mode |
| `ArchitectureDiagram.tsx` | Full-view Architecture tab (lazy-loaded) |
| `SessionHeatmap.tsx` | Full-view Architecture tab (lazy-loaded) |

### State Flow

```
ProjectsView (orchestrator)
  ├── viewMode: "board" | "cards" | "list"
  ├── selectedProjectId: string | null        → opens drawer
  ├── fullViewProjectId: string | null        → opens full page
  │
  ├── <SummaryStrip />                        (always visible, except in full view)
  ├── <NeedsAttentionBar />                   (always visible, except in full view)
  │
  ├── if fullViewProjectId:
  │     └── <ProjectFullView onBack={close} />
  │
  ├── else:
  │     ├── <ViewToggle />
  │     ├── <ProjectBoard />  |  <ProjectOverviewGrid />  |  <Table />
  │     └── <ProjectDrawer />  (overlay when selectedProjectId is set)
```

### New Utility Function

```typescript
type BoardColumn = "blocked" | "active-now" | "this-week" | "steady" | "parked";

function getProjectColumn(p: ProjectOverview): BoardColumn {
  if (p.health === "blocked" || p.tasks.blocked > 0) return "blocked";
  if (p.hasActiveSession || isActiveWithin(p, 24)) return "active-now";
  if (isActiveWithin(p, 7 * 24)) return "this-week";
  if (isProjectActive(p)) return "steady";  // has pending work or 30d activity
  return "parked";
}

// Note: column assignment uses `lastActive` timestamp exclusively for temporal
// columns, not `sessionCount7d` (which counts sessions, not recency).
// `isProjectActive()` is the fallback for "steady" — it checks sessionCount30d,
// commitCount30d, AND pending tasks, so projects with only pending work (no
// sessions/commits) correctly land in "steady" rather than "parked".

function isActiveWithin(p: ProjectOverview, hours: number): boolean {
  if (!p.lastActive) return false;
  return Date.now() - new Date(p.lastActive).getTime() < hours * 3600000;
}
```

## Design Tokens

All components use the existing midnight-gold theme from `globals.css` and `admin-theme.css`:

- Cards: `admin-card` class
- Backgrounds: `--color-surface`, `--color-surface-elevated`
- Borders: `--color-edge`, `--color-edge-subtle`
- Text: `--color-ink`, `--color-ink-secondary`, `--color-ink-faint`
- Accent: `--color-gold`
- Semantic: `--color-type-error` (blocked), `--color-type-lesson` (healthy), `--color-type-reminder` (attention)
- Shadows: `--shadow-card`, `--shadow-card-hover`
- Typography: `--font-sans` (Outfit), `--font-mono` (JetBrains Mono)
- Spacing rhythm: 4/8/16/20/24px (AppFlowly-aligned)

## No API Changes

All data comes from the existing `/api/admin/projects/overview` endpoint. The `ProjectOverview` type already contains all fields needed (sparkline, tasks, activity, decisions, handoffs, health, session counts).

## Out of Scope

- Drag-and-drop reordering on the board (future enhancement)
- Custom column configuration
- Project creation/editing from the UI
- Kanban persistence (column assignments are computed, not stored)
