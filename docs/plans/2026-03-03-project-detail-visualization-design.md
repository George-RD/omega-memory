# Project Detail Visualization Design

**Date**: 2026-03-03
**Status**: Approved
**Scope**: Admin dashboard > Projects tab > click-to-detail view with visual diagrams

## Problem

Clicking a project card in the admin Projects tab opens a 480px overlay drawer. The main content area below the cards is empty. There is no visual representation of project architecture, activity patterns, or decision history. The drawer is a flat list of text data with no spatial understanding.

## Solution

Replace the card grid with a master-detail view when a project is selected. The detail view has:
- **Main area (~65%)**: Stacked visualization panels (architecture diagram, session heatmap, decision timeline)
- **Inline sidebar (~35%, 380px max)**: Clickable/expandable sections reusing existing Detail* sub-components

Back button returns to the card grid.

## Approach

**Client-side Mermaid rendering** (Approach A). Mermaid.js loaded via CDN, lazy-loaded when detail view mounts. Interactive zoom/pan. Dark-mode-aware theming following visual-explainer skill patterns.

## Layout

```
+--------------------------------------------+
| <- Back to Projects    OMEGA  [health] [cat]|
+----------------------------+---------------+
|                            |               |
|  Architecture Diagram      |  Decisions    |
|  (Mermaid flowchart TD)    |  Activity     |
|  [zoom +/-/reset, pan]     |  Tasks        |
|                            |  Files        |
|  -------------------------  |  Blockers     |
|                            |               |
|  Session Activity Heatmap  |  [each section|
|  (SVG grid, 14d x 24h)    |   clickable   |
|                            |   expandable] |
|  -------------------------  |               |
|                            |  [module      |
|  Decision Timeline         |   filter pill |
|  (vertical CSS)            |   when node   |
|                            |   clicked]    |
+----------------------------+---------------+
```

## Data Sources

### Existing (no new API needed for sidebar)
- `ProjectOverview` from `GET /api/admin/projects/overview` has: decisions, fileClaims, activity, tasks, latestHandoff, sparkline
- All sidebar drill-down uses data already in memory

### New API: `GET /api/admin/projects/[id]/architecture`

Returns architecture data derived from coordination tables:

```typescript
interface ArchitectureModule {
  path: string;        // e.g. "src/omega/server"
  fileCount: number;
  recentCommits: number;
  health: "active" | "stale" | "dormant";
}

interface ArchitectureEdge {
  from: string;        // module path
  to: string;          // module path
  weight: number;      // co-change frequency
}

interface ArchitectureResponse {
  modules: ArchitectureModule[];
  edges: ArchitectureEdge[];
  mermaidSyntax: string;
  sessionHeatmap: { date: string; hour: number; count: number }[];
}
```

Queries: `coord_git_events` (commit file paths), `coord_file_claims` (active files), `coord_handoffs` (files_modified). Groups by first 2 directory segments. Co-change edges from files modified in same session.

## Visualization Panels

### 1. Architecture Diagram (Mermaid)
- `flowchart TD` with subgraphs per top-level directory
- Node colors: green (active commits in 7d), amber (commits in 30d), grey (dormant)
- `theme: 'base'` with dark-mode themeVariables
- Zoom: +/- buttons, Ctrl+scroll, drag-to-pan
- Click node -> filters sidebar to that module
- ELK layout only if 20+ nodes

### 2. Session Activity Heatmap
- GitHub-contributions style SVG grid
- 14 columns (days) x time-of-day rows
- Intensity fill from transparent to accent color
- Hover tooltip: date + session count
- Data from session timestamps (existing overview data + new hourly breakdown from architecture endpoint)

### 3. Decision Timeline
- Vertical CSS timeline (visual-explainer pattern)
- Domain badge + decision text + relative timestamp
- Color by domain
- Click -> highlights in sidebar Decisions section

## Component Architecture

### New files
| File | Purpose |
|------|---------|
| `ProjectDetailView.tsx` | Master-detail container, back button, main+sidebar grid |
| `ArchitectureDiagram.tsx` | Mermaid renderer with zoom/pan, lazy-loads mermaid.js via CDN |
| `SessionHeatmap.tsx` | SVG heatmap grid |
| `DecisionTimeline.tsx` | Vertical CSS timeline |
| `DetailSidebar.tsx` | Inline sidebar reusing existing Detail* components |

### Modified files
| File | Change |
|------|--------|
| `ProjectsView.tsx` | Add `viewMode` state, conditional render grid vs detail |
| `types.ts` | Add `ArchitectureResponse` interface |

### New API route
| File | Purpose |
|------|---------|
| `app/api/admin/projects/[id]/architecture/route.ts` | Architecture + heatmap data |

## Mermaid Integration (visual-explainer patterns)

- CDN: `https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs`
- Always `theme: 'base'` (only theme where themeVariables fully work)
- Never define `.node` CSS class (Mermaid internal), use `.ve-card`
- Semi-transparent fills for node backgrounds (8-digit hex, alpha 20-44)
- Never set `color:` in classDef (breaks theme switching)
- CSS overrides: `.mermaid .nodeLabel { color: var(--text) !important; }`
- Admin is always dark mode, so hardcode dark themeVariables

## Drill-Down Behavior

| Action | Result |
|--------|--------|
| Click architecture node | Filter sidebar to that module's files/activity |
| Click decision (timeline) | Highlight in sidebar Decisions section |
| Click decision (sidebar) | Expand to show full rationale |
| Click activity item | Show handoff context + files modified |
| Click task | Show progress detail |
| Click file path | Copy to clipboard |
| "Clear filter" pill | Remove module filter, show all data |

## Anti-Patterns Avoided (visual-explainer)

- No Inter/Roboto fonts (use admin's existing font stack)
- No violet/indigo/fuchsia accents
- No emoji section headers
- No gradient text headings
- No animated glowing shadows
- No uniform card grid with identical styling
- Vary visual weight: architecture diagram is hero (elevated), heatmap is body, timeline is compact

## Dependencies

- `mermaid@11` (CDN, lazy-loaded, ~150KB)
- No other new dependencies
- Reuses all existing Detail* sub-components
