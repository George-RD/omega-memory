# Projects Tab Kanban Rehaul — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat table-first projects tab with a kanban board default view, side drawer, and full-page project workspace.

**Architecture:** Kanban board with 5 computed columns (Blocked/Active Now/This Week/Steady/Parked) as default view, keeping existing Cards and List as alternates. Click opens a SlideDrawer with project context; "Open Full" transitions to a full-page tabbed workspace. All data from existing `/api/admin/projects/overview` endpoint — no API changes.

**Tech Stack:** TypeScript, React, Next.js 15, Tailwind CSS. Reuses existing components: SlideDrawer, Sparkline, NeedsAttentionBar, ArchitectureDiagram, SessionHeatmap, Detail* sub-components.

**Spec:** `docs/superpowers/specs/2026-03-15-projects-tab-rehaul-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `utils.ts` | Modify | Add `BoardColumn` type, `getProjectColumn()`, `isActiveWithin()`, `getSparkColor()` |
| `types.ts` | Modify | Export `BoardColumn` type |
| `SummaryStrip.tsx` | Create | Extract from inline in ProjectsView — portfolio stat cards |
| `ActivityTimeline.tsx` | Create | Extract from inline in ProjectsView — expandable activity list with decisions |
| `ProjectDetailSections.tsx` | Create | Shared sections: stat cards, blockers, next steps — used by drawer and full view |
| `ProjectBoardCard.tsx` | Create | Compact kanban card with health dot, sparkline, context line, pills |
| `ProjectBoard.tsx` | Create | Kanban board layout — 5 columns, search filtering, empty states |
| `ProjectDrawer.tsx` | Create | Side drawer replacing ProjectDetailDrawer — uses SlideDrawer, composes detail sections |
| `ProjectFullView.tsx` | Create | Full-page workspace with Overview/Tasks/Activity/Architecture tabs |
| `ProjectsView.tsx` | Modify | Orchestrator — view mode toggle (board/cards/list), drawer state, full-view navigation, pushState/popstate |
| `ProjectDetailDrawer.tsx` | Delete | Replaced by ProjectDrawer.tsx |

---

## Chunk 1: Foundation (utils, types, extracted components)

### Task 1: Add board column utilities to utils.ts and types.ts

**Files:**
- Modify: `website/app/admin/components/projects/utils.ts`
- Modify: `website/app/admin/components/projects/types.ts`

- [ ] **Step 1: Add BoardColumn type to types.ts**

At the end of `types.ts`, add:

```typescript
export type BoardColumn = "blocked" | "active-now" | "this-week" | "steady" | "parked";
```

- [ ] **Step 2: Add column utilities to utils.ts**

At the end of `utils.ts`, add:

```typescript
import type { BoardColumn } from "./types";

export function isActiveWithin(p: ProjectOverview, hours: number): boolean {
  if (!p.lastActive) return false;
  return Date.now() - new Date(p.lastActive).getTime() < hours * 3600000;
}

export function getProjectColumn(p: ProjectOverview): BoardColumn {
  if (p.health === "blocked" || p.tasks.blocked > 0) return "blocked";
  if (p.hasActiveSession || isActiveWithin(p, 24)) return "active-now";
  if (isActiveWithin(p, 7 * 24)) return "this-week";
  if (isProjectActive(p)) return "steady";
  return "parked";
}

export function getSparkColor(momentum: Momentum): string {
  return momentum === "up" ? "rgba(74, 222, 128, 0.6)"
    : momentum === "cooling" ? "rgba(251, 191, 36, 0.6)"
    : momentum === "stalled" ? "rgba(248, 113, 113, 0.5)"
    : "rgba(255, 255, 255, 0.3)";
}
```

- [ ] **Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add website/app/admin/components/projects/utils.ts website/app/admin/components/projects/types.ts
git commit -m "feat: add board column utilities and BoardColumn type"
```

### Task 2: Extract SummaryStrip to its own file

**Files:**
- Create: `website/app/admin/components/projects/SummaryStrip.tsx`
- Modify: `website/app/admin/components/projects/ProjectsView.tsx`

- [ ] **Step 1: Create SummaryStrip.tsx**

Copy the `SummaryStrip` function (lines 376-411 of current `ProjectsView.tsx`) into a new file. Add `"use client"` directive and proper imports:

```typescript
"use client";

import type { ProjectOverview } from "./types";
import { computeMomentum, MOMENTUM_THEME } from "./utils";
```

Export as default: `export default function SummaryStrip(...)`.

Props interface:
```typescript
interface SummaryStripProps {
  projects: ProjectOverview[];
  dormantCount: number;
  attentionCount: number;
}
```

The component body is identical to the existing inline `SummaryStrip` in `ProjectsView.tsx`.

- [ ] **Step 2: Update ProjectsView.tsx imports**

Remove the inline `SummaryStrip` function definition (lines 374-411). Add import:

```typescript
import SummaryStrip from "./SummaryStrip";
```

- [ ] **Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add website/app/admin/components/projects/SummaryStrip.tsx website/app/admin/components/projects/ProjectsView.tsx
git commit -m "refactor: extract SummaryStrip to own file"
```

### Task 3: Extract ActivityTimeline to its own file

**Files:**
- Create: `website/app/admin/components/projects/ActivityTimeline.tsx`
- Modify: `website/app/admin/components/projects/ProjectsView.tsx`

- [ ] **Step 1: Create ActivityTimeline.tsx**

Copy the `ActivityTimeline` function (lines 94-210 of current `ProjectsView.tsx`) plus the `ChevronIcon` helper it uses into a new file. Add proper imports:

```typescript
"use client";

import { useState } from "react";
import type { DecisionItem, ActivityItem } from "./types";
import { relativeTime, humanize, humanizeDecision, isNoiseActivity } from "./utils";
```

Export as default: `export default function ActivityTimeline(...)`.

Props interface:
```typescript
interface ActivityTimelineProps {
  activity: ActivityItem[];
  decisions: DecisionItem[];
}
```

Keep the inline `ChevronIcon` as a private helper within the file (it's also used in ProjectsView table rows, so both files will have their own copy — this is fine, it's 6 lines).

- [ ] **Step 2: Update ProjectsView.tsx**

Remove the inline `ActivityTimeline` function definition. Add import:

```typescript
import ActivityTimeline from "./ActivityTimeline";
```

Keep the `ChevronIcon` in `ProjectsView.tsx` since the table rows still use it.

- [ ] **Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add website/app/admin/components/projects/ActivityTimeline.tsx website/app/admin/components/projects/ProjectsView.tsx
git commit -m "refactor: extract ActivityTimeline to own file"
```

### Task 4: Create ProjectDetailSections (shared drawer/full-view sections)

**Files:**
- Create: `website/app/admin/components/projects/ProjectDetailSections.tsx`

- [ ] **Step 1: Create ProjectDetailSections.tsx**

This file exports reusable section components used by both the drawer and full-view Overview tab. Extract and consolidate from existing inline `ProjectDetailPanel` in `ProjectsView.tsx`:

```typescript
"use client";

import type { ProjectOverview } from "./types";
import { relativeTime, humanize, humanizeDecision, computeMomentum, MOMENTUM_THEME } from "./utils";
import Sparkline from "./Sparkline";

// ─── Stat Cards ──────────────────────────────────────────────

interface StatCardsProps {
  project: ProjectOverview;
}

export function StatCards({ project }: StatCardsProps) {
  const totalTasks = project.tasks.pending + project.tasks.inProgress + project.tasks.completed + project.tasks.blocked + project.tasks.failed;
  const hasTasks = totalTasks > 0;
  const handoff = project.latestHandoff;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
      {project.sessionCount30d > 0 && (
        <div className="rounded-lg bg-surface-elevated/40 px-3 py-2.5 border border-edge-subtle/30">
          <div className="text-[20px] font-light tabular-nums text-ink">{project.sessionCount30d}</div>
          <div className="text-[11px] font-mono uppercase tracking-wider text-ink-faint mt-0.5">Sessions</div>
          <div className="text-[11px] text-ink-faint/50">30 days</div>
        </div>
      )}
      {project.commitCount30d > 0 && (
        <div className="rounded-lg bg-surface-elevated/40 px-3 py-2.5 border border-edge-subtle/30">
          <div className="text-[20px] font-light tabular-nums text-ink">{project.commitCount30d}</div>
          <div className="text-[11px] font-mono uppercase tracking-wider text-ink-faint mt-0.5">Commits</div>
          <div className="text-[11px] text-ink-faint/50">30 days</div>
        </div>
      )}
      {project.decisionCount30d > 0 && (
        <div className="rounded-lg bg-surface-elevated/40 px-3 py-2.5 border border-edge-subtle/30">
          <div className="text-[20px] font-light tabular-nums text-ink">{project.decisionCount30d}</div>
          <div className="text-[11px] font-mono uppercase tracking-wider text-ink-faint mt-0.5">Decisions</div>
          <div className="text-[11px] text-ink-faint/50">30 days</div>
        </div>
      )}
      {hasTasks && (
        <div className="rounded-lg bg-surface-elevated/40 px-3 py-2.5 border border-edge-subtle/30">
          <div className="text-[20px] font-light tabular-nums text-ink">
            {project.tasks.completed}<span className="text-[14px] text-ink-faint">/{totalTasks}</span>
          </div>
          <div className="text-[11px] font-mono uppercase tracking-wider text-ink-faint mt-0.5">Tasks Done</div>
          {handoff?.blockedItems?.length ? (
            <div className="text-[11px] text-type-error">{handoff.blockedItems.length} blocked</div>
          ) : (
            <div className="text-[11px] text-ink-faint/50">{Math.round((project.tasks.completed / totalTasks) * 100)}%</div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Blockers Section ────────────────────────────────────────

interface BlockersSectionProps {
  blockedItems: string[];
}

export function BlockersSection({ blockedItems }: BlockersSectionProps) {
  if (blockedItems.length === 0) return null;
  return (
    <div>
      <span className="text-[13px] font-mono text-type-error uppercase tracking-wider">
        Blockers ({blockedItems.length})
      </span>
      <div className="mt-2 space-y-1.5">
        {blockedItems.map((item, i) => (
          <div key={i} className="flex items-start gap-2.5">
            <span className="text-type-error mt-0.5 shrink-0">!</span>
            <span className="text-[15px] text-type-error leading-snug">{humanize(item)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Next Steps Section ──────────────────────────────────────

interface NextStepsSectionProps {
  nextSteps: string[];
}

export function NextStepsSection({ nextSteps }: NextStepsSectionProps) {
  if (nextSteps.length === 0) return null;
  return (
    <div>
      <span className="text-[13px] font-mono text-type-reminder uppercase tracking-wider">
        Next Steps ({nextSteps.length})
      </span>
      <div className="mt-2 space-y-1.5">
        {nextSteps.map((step, i) => (
          <div key={i} className="flex items-start gap-2.5">
            <span className="text-type-reminder font-mono text-[14px] mt-0.5 shrink-0 w-5 text-right">{i + 1}.</span>
            <span className="text-[15px] text-ink-secondary leading-snug">{humanize(step)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Decisions Section ───────────────────────────────────────

interface DecisionsSectionProps {
  decisions: { id: number; decision: string; createdAt: string }[];
  limit?: number;
}

export function DecisionsSection({ decisions, limit = 3 }: DecisionsSectionProps) {
  if (decisions.length === 0) return null;
  return (
    <div>
      <span className="text-[13px] font-mono text-ink-faint uppercase tracking-wider">
        Key Decisions
      </span>
      <div className="mt-2 space-y-2">
        {decisions.slice(0, limit).map((d) => (
          <div key={d.id} className="border-b border-edge-subtle/30 pb-2 last:border-0">
            <span className="text-[12px] text-ink-faint font-mono">{relativeTime(d.createdAt)}</span>
            <p className="text-[15px] text-ink-secondary leading-snug mt-0.5">{humanizeDecision(d.decision)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add website/app/admin/components/projects/ProjectDetailSections.tsx
git commit -m "feat: add shared ProjectDetailSections for drawer and full view"
```

---

## Chunk 2: Kanban Board

### Task 5: Create ProjectBoardCard

**Files:**
- Create: `website/app/admin/components/projects/ProjectBoardCard.tsx`

- [ ] **Step 1: Create ProjectBoardCard.tsx**

```typescript
"use client";

import type { ProjectOverview } from "./types";
import { relativeTime, HEALTH_THEME, getContextLine, computeMomentum, MOMENTUM_THEME, getSparkColor } from "./utils";
import Sparkline from "./Sparkline";

interface ProjectBoardCardProps {
  project: ProjectOverview;
  onClick: () => void;
}

export default function ProjectBoardCard({ project, onClick }: ProjectBoardCardProps) {
  const theme = HEALTH_THEME[project.health];
  const context = getContextLine(project);
  const momentum = computeMomentum(project);
  const mTheme = MOMENTUM_THEME[momentum];
  const sparkColor = getSparkColor(momentum);

  const totalTasks = project.tasks.pending + project.tasks.inProgress + project.tasks.completed + project.tasks.blocked + project.tasks.failed;
  const progressPct = totalTasks > 0
    ? Math.round((project.tasks.completed / totalTasks) * 100)
    : project.launchProgress;
  const showProgress = progressPct > 0;

  const blockedCount = project.tasks.blocked;
  const inProgressCount = project.tasks.inProgress;

  const healthBg = project.health === "blocked" ? "bg-red-400/[0.03]"
    : project.health === "attention" ? "bg-amber-400/[0.03]"
    : "";

  return (
    <button
      onClick={onClick}
      data-project-id={project.id}
      className={`group w-full flex flex-col gap-2.5 rounded-lg border p-4 text-left transition-all hover:shadow-[var(--shadow-card-hover)] cursor-pointer ${theme.border} bg-[var(--color-surface)] ${healthBg}`}
    >
      {/* Row 1: Health dot + name + time + momentum */}
      <div className="flex items-center gap-2">
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span className={`h-2.5 w-2.5 rounded-full ${theme.dot}`} />
          {project.hasActiveSession && (
            <span className="absolute inset-0 animate-ping rounded-full bg-green-400/60" />
          )}
        </span>
        <span className={`text-[14px] font-semibold truncate ${
          project.health === "blocked" ? "text-red-400/90" : "text-white/90"
        }`}>
          {project.name}
        </span>
        <span className="ml-auto flex items-center gap-1.5 shrink-0">
          <span className="text-[11px] text-white/40 font-mono">{relativeTime(project.lastActive)}</span>
          <span className={`text-[12px] font-mono ${mTheme.cls}`}>{mTheme.icon}</span>
        </span>
      </div>

      {/* Row 2: Sparkline + progress */}
      <div className="flex items-center gap-2.5">
        <Sparkline data={project.sparkline} color={sparkColor} width={60} height={20} />
        {showProgress && (
          <>
            <div className="flex-1 h-1 rounded-full bg-surface-elevated overflow-hidden">
              <div
                className={`h-full rounded-full ${progressPct >= 80 ? "bg-type-lesson/60" : progressPct >= 40 ? "bg-type-reminder/50" : "bg-ink-faint/30"}`}
                style={{ width: `${Math.max(progressPct, 3)}%` }}
              />
            </div>
            <span className="text-[11px] font-mono tabular-nums text-ink-faint">{progressPct}%</span>
          </>
        )}
      </div>

      {/* Row 3: Context line */}
      {context && (
        <p className={`text-[13px] line-clamp-2 leading-relaxed ${
          context.type === "blocker" ? "text-red-400/70" :
          context.type === "next" ? "text-amber-400/70" :
          "text-white/50"
        }`}>
          {context.type === "blocker" && (
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-400 mr-1.5 relative top-[-1px]" />
          )}
          {context.type === "next" ? `Next: ${context.text}` : context.text}
        </p>
      )}

      {/* Row 4: Action pills */}
      <div className="flex flex-wrap items-center gap-1.5">
        {blockedCount > 0 && (
          <span className="text-[11px] px-1.5 py-0.5 rounded bg-red-400/10 text-red-400/70">
            {blockedCount} blocked
          </span>
        )}
        {inProgressCount > 0 && (
          <span className="text-[11px] px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400/70">
            {inProgressCount} in progress
          </span>
        )}
        {project.hasActiveSession && (
          <span className="text-[11px] px-1.5 py-0.5 rounded bg-green-400/10 text-green-400/70 ml-auto">
            agent working
          </span>
        )}
      </div>
    </button>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add website/app/admin/components/projects/ProjectBoardCard.tsx
git commit -m "feat: add ProjectBoardCard for kanban board"
```

### Task 6: Create ProjectBoard

**Files:**
- Create: `website/app/admin/components/projects/ProjectBoard.tsx`

- [ ] **Step 1: Create ProjectBoard.tsx**

```typescript
"use client";

import { useMemo } from "react";
import type { ProjectOverview, BoardColumn } from "./types";
import { getProjectColumn } from "./utils";
import ProjectBoardCard from "./ProjectBoardCard";

interface ProjectBoardProps {
  projects: ProjectOverview[];
  searchQuery: string;
  onSelectProject: (projectId: string) => void;
}

const COLUMNS: { key: BoardColumn; label: string; accent: string; accentLine: string }[] = [
  { key: "blocked",    label: "Blocked",    accent: "text-type-error",    accentLine: "bg-type-error/60" },
  { key: "active-now", label: "Active Now", accent: "text-type-lesson",   accentLine: "bg-type-lesson/60" },
  { key: "this-week",  label: "This Week",  accent: "text-type-reminder", accentLine: "bg-type-reminder/60" },
  { key: "steady",     label: "Steady",     accent: "text-ink-faint",     accentLine: "bg-ink-faint/30" },
  { key: "parked",     label: "Parked",     accent: "text-ink-faint/50",  accentLine: "bg-ink-faint/15" },
];

export default function ProjectBoard({ projects, searchQuery, onSelectProject }: ProjectBoardProps) {
  const query = searchQuery.toLowerCase().trim();

  const filtered = useMemo(() => {
    if (!query) return projects;
    return projects.filter((p) =>
      p.name.toLowerCase().includes(query) ||
      p.category.toLowerCase().includes(query) ||
      p.health.includes(query) ||
      (p.summary?.toLowerCase().includes(query) ?? false)
    );
  }, [projects, query]);

  const columns = useMemo(() => {
    const grouped: Record<BoardColumn, ProjectOverview[]> = {
      "blocked": [], "active-now": [], "this-week": [], "steady": [], "parked": [],
    };
    for (const p of filtered) {
      grouped[getProjectColumn(p)].push(p);
    }
    // Sort each column by lastActive descending, nulls last
    for (const col of Object.values(grouped)) {
      col.sort((a, b) => {
        const aTime = a.lastActive ? new Date(a.lastActive).getTime() : 0;
        const bTime = b.lastActive ? new Date(b.lastActive).getTime() : 0;
        return bTime - aTime;
      });
    }
    return grouped;
  }, [filtered]);

  const totalFiltered = filtered.length;

  // All columns empty
  if (totalFiltered === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-[15px] text-ink-faint">
          {query ? "No projects match your filter." : "No projects registered. Projects appear automatically from coordination sessions."}
        </p>
      </div>
    );
  }

  return (
    <div className="flex gap-5 overflow-x-auto pb-4 min-h-[400px]">
      {COLUMNS.map(({ key, label, accent, accentLine }) => {
        const cards = columns[key];
        const isEmpty = cards.length === 0;

        return (
          <div
            key={key}
            className={`flex flex-col shrink-0 ${isEmpty ? "w-[120px]" : "w-[280px]"} transition-all`}
          >
            {/* Column header */}
            <div className="mb-3">
              <span className={`text-[12px] font-mono uppercase tracking-wider ${accent}`}>
                {label} ({cards.length})
              </span>
              <div className={`h-[2px] mt-1.5 rounded-full ${accentLine}`} />
            </div>

            {/* Cards */}
            {!isEmpty && (
              <div className="flex flex-col gap-4">
                {cards.map((p) => (
                  <ProjectBoardCard
                    key={p.id}
                    project={p}
                    onClick={() => onSelectProject(p.id)}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add website/app/admin/components/projects/ProjectBoard.tsx
git commit -m "feat: add ProjectBoard kanban layout with 5 columns"
```

---

## Chunk 3: Drawer & Full View

### Task 7: Create ProjectDrawer

**Files:**
- Create: `website/app/admin/components/projects/ProjectDrawer.tsx`

- [ ] **Step 1: Create ProjectDrawer.tsx**

This replaces `ProjectDetailDrawer.tsx`. Uses the existing `SlideDrawer` component from `components/SlideDrawer.tsx` and composes the shared detail sections.

```typescript
"use client";

import type { ProjectOverview } from "./types";
import { relativeTime, HEALTH_THEME, computeMomentum, MOMENTUM_THEME, getSparkColor } from "./utils";
import SlideDrawer from "../SlideDrawer";
import Sparkline from "./Sparkline";
import { StatCards, BlockersSection, NextStepsSection, DecisionsSection } from "./ProjectDetailSections";
import ActivityTimeline from "./ActivityTimeline";

interface ProjectDrawerProps {
  project: ProjectOverview | null;
  onClose: () => void;
  onOpenFull: (projectId: string) => void;
}

export default function ProjectDrawer({ project, onClose, onOpenFull }: ProjectDrawerProps) {
  if (!project) return null;

  const theme = HEALTH_THEME[project.health];
  const momentum = computeMomentum(project);
  const mTheme = MOMENTUM_THEME[momentum];
  const sparkColor = getSparkColor(momentum);
  const handoff = project.latestHandoff;

  return (
    <SlideDrawer open={!!project} onClose={onClose} title={project.name} width="xl">
      <div className="h-full overflow-y-auto p-5 space-y-5">
        {/* Open Full link */}
        <div className="flex justify-end">
          <button
            onClick={() => onOpenFull(project.id)}
            className="text-[13px] text-gold hover:text-gold-dim transition-colors font-mono"
          >
            Open Full &rarr;
          </button>
        </div>

        {/* Identity */}
        <div>
          <div className="flex items-center gap-2.5">
            <span className={`h-3 w-3 rounded-full ${theme.dot}`} />
            <h2 className="text-[20px] font-light text-ink tracking-tight">{project.name}</h2>
          </div>
          <p className="text-[14px] text-ink-faint mt-1">
            Last active {relativeTime(project.lastActive)}
            <span className="mx-1.5 text-ink-faint/30">&middot;</span>
            {project.sessionCount30d} sessions / 30d
            <span className="mx-1.5 text-ink-faint/30">&middot;</span>
            <span className={`font-mono ${mTheme.cls}`}>{mTheme.icon} {mTheme.label}</span>
          </p>
        </div>

        {/* Stat Cards */}
        <StatCards project={project} />

        {/* Full-width sparkline */}
        <div>
          <Sparkline data={project.sparkline} color={sparkColor} width={480} height={40} />
        </div>

        {/* Blockers */}
        {handoff?.blockedItems && <BlockersSection blockedItems={handoff.blockedItems} />}

        {/* Next Steps */}
        {handoff?.nextSteps && <NextStepsSection nextSteps={handoff.nextSteps} />}

        {/* Recent Work */}
        <ActivityTimeline activity={project.activity.slice(0, 8)} decisions={project.decisions.slice(0, 3)} />

        {/* Key Decisions */}
        <DecisionsSection decisions={project.decisions} limit={3} />
      </div>
    </SlideDrawer>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add website/app/admin/components/projects/ProjectDrawer.tsx
git commit -m "feat: add ProjectDrawer with shared detail sections"
```

### Task 8: Create ProjectFullView

**Files:**
- Create: `website/app/admin/components/projects/ProjectFullView.tsx`

- [ ] **Step 1: Create ProjectFullView.tsx**

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import type { ProjectOverview } from "./types";
import { HEALTH_THEME, computeMomentum, MOMENTUM_THEME, getSparkColor, relativeTime, humanize } from "./utils";
import Sparkline from "./Sparkline";
import { StatCards, BlockersSection, NextStepsSection, DecisionsSection } from "./ProjectDetailSections";
import ActivityTimeline from "./ActivityTimeline";

const ArchitectureDiagram = dynamic(() => import("./ArchitectureDiagram"), { ssr: false });
const SessionHeatmap = dynamic(() => import("./SessionHeatmap"), { ssr: false });

type FullViewTab = "overview" | "tasks" | "activity" | "architecture";

interface ProjectFullViewProps {
  project: ProjectOverview;
  onBack: () => void;
}

const TABS: { key: FullViewTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "tasks", label: "Tasks" },
  { key: "activity", label: "Activity" },
  { key: "architecture", label: "Architecture" },
];

export default function ProjectFullView({ project, onBack }: ProjectFullViewProps) {
  const [activeTab, setActiveTab] = useState<FullViewTab>("overview");
  const [archData, setArchData] = useState<{ mermaidSyntax: string; sessionHeatmap: any[] } | null>(null);
  const [archLoading, setArchLoading] = useState(false);
  const [archError, setArchError] = useState<string | null>(null);

  const theme = HEALTH_THEME[project.health];
  const momentum = computeMomentum(project);
  const mTheme = MOMENTUM_THEME[momentum];
  const sparkColor = getSparkColor(momentum);
  const handoff = project.latestHandoff;

  // Fetch architecture data on tab switch
  useEffect(() => {
    if (activeTab !== "architecture" || archData) return;
    setArchLoading(true);
    fetch(`/api/admin/projects/${project.id}/architecture`)
      .then((r) => r.ok ? r.json() : Promise.reject("Failed to load"))
      .then((data) => setArchData(data))
      .catch((e) => setArchError(String(e)))
      .finally(() => setArchLoading(false));
  }, [activeTab, project.id, archData]);

  // Listen for popstate (browser back button)
  useEffect(() => {
    const handler = () => onBack();
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, [onBack]);

  // Build task lists
  const tasks = project.tasks;
  const totalTasks = tasks.pending + tasks.inProgress + tasks.completed + tasks.blocked + tasks.failed;
  const remainingItems = tasks.items
    .filter((t) => ["blocked", "in_progress", "pending"].includes(t.status))
    .sort((a, b) => {
      const order: Record<string, number> = { blocked: 0, in_progress: 1, pending: 2 };
      return (order[a.status] ?? 3) - (order[b.status] ?? 3);
    });
  const completedItems = tasks.items.filter((t) => t.status === "completed");

  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="px-8 pt-6 pb-4 border-b border-edge-subtle">
        <div className="flex items-center justify-between">
          <button onClick={onBack} className="text-[14px] text-ink-faint hover:text-ink transition-colors">
            &larr; Back to Projects
          </button>
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${theme.dot}`} />
            <span className="text-[13px] text-ink-faint font-mono">{theme.label}</span>
            <span className={`text-[13px] font-mono ${mTheme.cls}`}>{mTheme.icon} {mTheme.label}</span>
          </div>
        </div>
        <h1 className="text-[28px] font-light text-ink tracking-tight mt-3">{project.name}</h1>
        <p className="text-[14px] text-ink-faint mt-1">
          Last active {relativeTime(project.lastActive)}
          <span className="mx-1.5 text-ink-faint/30">&middot;</span>
          {project.sessionCount30d} sessions / 30d
        </p>

        {/* Tab bar */}
        <div className="flex gap-1 mt-5">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-4 py-2 text-[14px] rounded-t-lg transition-colors ${
                activeTab === key
                  ? "bg-surface-elevated text-ink border-b-2 border-gold"
                  : "text-ink-faint hover:text-ink-secondary"
              }`}
            >
              {label}
              {key === "tasks" && totalTasks > 0 && (
                <span className="ml-1.5 text-[12px] font-mono text-ink-faint">{totalTasks}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="px-8 py-6 space-y-6">
        {activeTab === "overview" && (
          <>
            <StatCards project={project} />
            <Sparkline data={project.sparkline} color={sparkColor} width={700} height={48} />
            {handoff?.blockedItems && <BlockersSection blockedItems={handoff.blockedItems} />}
            {handoff?.nextSteps && <NextStepsSection nextSteps={handoff.nextSteps} />}
            <DecisionsSection decisions={project.decisions} limit={5} />
          </>
        )}

        {activeTab === "tasks" && (
          totalTasks > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div>
                <span className="text-[13px] font-mono text-ink-faint uppercase tracking-wider">
                  Remaining ({remainingItems.length})
                </span>
                <div className="mt-3 space-y-2">
                  {remainingItems.map((t) => (
                    <div key={t.id} className="flex items-start gap-2.5">
                      <span className={`mt-0.5 shrink-0 ${
                        t.status === "blocked" ? "text-type-error" :
                        t.status === "in_progress" ? "text-type-reminder" :
                        "text-ink-faint"
                      }`}>
                        {t.status === "blocked" ? "!" : t.status === "in_progress" ? "\u25B6" : "\u25CB"}
                      </span>
                      <span className={`text-[15px] leading-snug ${
                        t.status === "blocked" ? "text-type-error" : "text-ink-secondary"
                      }`}>{humanize(t.title)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <span className="text-[13px] font-mono text-ink-faint uppercase tracking-wider">
                  Completed ({completedItems.length})
                </span>
                <div className="mt-3 space-y-2">
                  {completedItems.map((t) => (
                    <div key={t.id} className="flex items-start gap-2.5">
                      <span className="text-type-lesson mt-0.5 shrink-0">&#10003;</span>
                      <span className="text-[15px] text-ink-secondary leading-snug">{humanize(t.title)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-[15px] text-ink-faint">No tasks tracked for this project.</p>
          )
        )}

        {activeTab === "activity" && (
          <ActivityTimeline activity={project.activity} decisions={project.decisions} />
        )}

        {activeTab === "architecture" && (
          <div className="space-y-6">
            {archLoading && (
              <div className="space-y-3">
                <div className="h-[300px] rounded-lg bg-white/[0.03] animate-pulse" />
                <div className="h-[200px] rounded-lg bg-white/[0.03] animate-pulse" />
              </div>
            )}
            {archError && (
              <div className="p-4 rounded-lg bg-type-error/10 border border-type-error/20 text-type-error text-[15px]">
                {archError}
                <button onClick={() => { setArchError(null); setArchData(null); }} className="ml-3 underline">Retry</button>
              </div>
            )}
            {archData && (
              <>
                {archData.mermaidSyntax && <ArchitectureDiagram mermaidSyntax={archData.mermaidSyntax} />}
                {archData.sessionHeatmap?.length > 0 && <SessionHeatmap data={archData.sessionHeatmap} />}
              </>
            )}
            {!archLoading && !archError && !archData && (
              <p className="text-[15px] text-ink-faint">No architecture data available.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Check SessionHeatmap props**

Before committing, verify `SessionHeatmap` accepts `data` prop by reading the component. If the prop name is different (e.g., `entries`), update accordingly.

Run: `head -20 ~/Projects/omega/website/app/admin/components/projects/SessionHeatmap.tsx`

- [ ] **Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add website/app/admin/components/projects/ProjectFullView.tsx
git commit -m "feat: add ProjectFullView with tabbed workspace"
```

---

## Chunk 4: Wire It All Together

### Task 9: Rewrite ProjectsView as orchestrator

**Files:**
- Modify: `website/app/admin/components/projects/ProjectsView.tsx`
- Delete: `website/app/admin/components/projects/ProjectDetailDrawer.tsx`

- [ ] **Step 1: Rewrite ProjectsView.tsx**

Replace the entire file. The new version is the orchestrator — it manages view mode (board/cards/list), drawer state, full-view state, and URL sync. It strips out all inline component definitions (SummaryStrip, ActivityTimeline, ProjectDetailPanel, ProjectHoverPreview) which have been extracted to their own files.

Key changes from old to new:
- Default `viewMode` is `"board"` (was `"list"`)
- New state: `selectedProjectId` (for drawer), `fullViewProjectId` (for full page)
- Removes: `expandedId`, `dormantExpanded`, inline `SummaryStrip`, inline `ActivityTimeline`, inline `ProjectDetailPanel`, inline `ProjectHoverPreview`
- `useKeyboardNav` gets `enabled: !selectedProjectId && !fullViewProjectId`
- Full-view transition uses `pushState`; mount reads URL params for deep-link restore
- Board view filters use `searchQuery` consistently across all 3 views
- Non-parked projects passed to `SummaryStrip`
- `getProjectColumn` used to split parked vs non-parked for SummaryStrip

```typescript
"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import type { ProjectOverview, AttentionItem } from "./types";
import { isProjectActive, getProjectColumn } from "./utils";
import { useKeyboardNav } from "../../hooks/useKeyboardNav";
import SummaryStrip from "./SummaryStrip";
import NeedsAttentionBar from "./NeedsAttentionBar";
import ProjectBoard from "./ProjectBoard";
import ProjectOverviewGrid from "./ProjectOverviewGrid";
import ProjectDrawer from "./ProjectDrawer";
import ProjectFullView from "./ProjectFullView";

// ─── Inline List View (preserved from existing table code) ──
// Keep the existing table rendering as a lazy-loaded component or inline.
// For now, import it from a separate file or keep inline.
// Since the list view is large (~200 lines), we keep it inline in this file
// but behind a viewMode guard. The table code is unchanged from current.

// NOTE: The full table code (HealthDot, ProgressBar, ChevronIcon, table markup)
// stays in this file inside the {viewMode === "list" && ...} block.
// It's the same code as the current implementation — just wrapped in the conditional.

import Sparkline from "./Sparkline";
import { relativeTime, HEALTH_THEME, humanize, isNoiseActivity, computeMomentum, MOMENTUM_THEME, getSparkColor } from "./utils";
import { Fragment } from "react";

function HealthDot({ health, active }: { health: string; active?: boolean }) {
  const theme = HEALTH_THEME[health as keyof typeof HEALTH_THEME] ?? HEALTH_THEME.stale;
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0">
      <span className={`h-2.5 w-2.5 rounded-full ${theme.dot}`} />
      {active && <span className="absolute inset-0 animate-ping rounded-full bg-green-400/60" />}
    </span>
  );
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const color = pct >= 80 ? "bg-type-lesson/60" : pct >= 40 ? "bg-type-reminder/50" : "bg-ink-faint/30";
  return (
    <div className="flex items-center gap-2.5 min-w-[140px]">
      <div className="flex-1 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.max(pct, 2)}%` }} />
      </div>
      <span className="text-[14px] font-mono tabular-nums text-ink-faint w-10 text-right">{pct}%</span>
    </div>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg className={`w-4 h-4 text-ink-tertiary transition-transform duration-150 ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
    </svg>
  );
}

// ─── View Toggle ─────────────────────────────────────────────

type ViewMode = "board" | "cards" | "list";

function ViewToggle({ mode, onChange }: { mode: ViewMode; onChange: (m: ViewMode) => void }) {
  const btn = (m: ViewMode, title: string, icon: React.ReactNode) => (
    <button
      onClick={() => onChange(m)}
      className={`px-2.5 py-1.5 transition-colors ${mode === m ? "bg-surface-elevated text-ink" : "text-ink-faint hover:text-ink-secondary"}`}
      title={title}
    >
      {icon}
    </button>
  );

  return (
    <div className="flex items-center rounded-lg border border-edge overflow-hidden">
      {btn("board", "Board view", (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <rect x="1" y="1" width="3.5" height="14" rx="1" stroke="currentColor" strokeWidth="1.1" />
          <rect x="6.25" y="1" width="3.5" height="10" rx="1" stroke="currentColor" strokeWidth="1.1" />
          <rect x="11.5" y="1" width="3.5" height="7" rx="1" stroke="currentColor" strokeWidth="1.1" />
        </svg>
      ))}
      {btn("cards", "Card view", (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <rect x="1.5" y="1.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
          <rect x="9.5" y="1.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
          <rect x="1.5" y="9.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
          <rect x="9.5" y="9.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      ))}
      {btn("list", "List view", (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      ))}
    </div>
  );
}

// ─── Main Orchestrator ───────────────────────────────────────

export default function ProjectsView() {
  const [projects, setProjects] = useState<ProjectOverview[]>([]);
  const [needsAttention, setNeedsAttention] = useState<AttentionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("board");

  // Drawer state
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  // Full-page view state
  const [fullViewProjectId, setFullViewProjectId] = useState<string | null>(null);

  // For list view only
  const [listExpandedId, setListExpandedId] = useState<string | null>(null);
  const [dormantExpanded, setDormantExpanded] = useState(false);

  const fetchOverview = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/projects/overview");
      if (!res.ok) throw new Error("API error");
      const data = await res.json();
      setProjects(data.projects ?? []);
      setNeedsAttention(data.needsAttention ?? []);
    } catch {
      setError("Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview();
    const interval = setInterval(fetchOverview, 60_000);
    return () => clearInterval(interval);
  }, [fetchOverview]);

  // Deep-link restore on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const projectParam = params.get("project");
    if (projectParam) {
      setFullViewProjectId(projectParam);
    }
  }, []);

  // Derive non-parked projects for SummaryStrip
  const nonParked = useMemo(
    () => projects.filter((p) => getProjectColumn(p) !== "parked"),
    [projects],
  );
  const parkedCount = projects.length - nonParked.length;

  // For list view: split active/dormant
  const query = searchQuery.toLowerCase();
  const filtered = projects.filter((p) =>
    !query || p.name.toLowerCase().includes(query) || (p.summary?.toLowerCase().includes(query) ?? false)
  );
  const active = filtered.filter((p) => isProjectActive(p)).sort((a, b) => {
    if (a.health === "blocked" && b.health !== "blocked") return -1;
    if (b.health === "blocked" && a.health !== "blocked") return 1;
    const aTime = a.lastActive ? new Date(a.lastActive).getTime() : 0;
    const bTime = b.lastActive ? new Date(b.lastActive).getTime() : 0;
    return bTime - aTime;
  });
  const dormant = filtered.filter((p) => !isProjectActive(p));

  // Keyboard nav for list view
  const allProjectIds = useMemo(
    () => [...active.map((p) => p.id), ...dormant.map((p) => p.id)],
    [active, dormant],
  );

  const { focusedId } = useKeyboardNav({
    dataAttribute: "data-project-id",
    ids: viewMode === "list" ? allProjectIds : [],
    onSelect: (id) => {
      if (viewMode === "list") {
        setListExpandedId((prev) => (prev === id ? null : id));
      } else {
        setSelectedProjectId(id);
      }
    },
    enabled: !loading && !selectedProjectId && !fullViewProjectId,
  });

  // Drawer helpers
  const selectedProject = selectedProjectId ? projects.find((p) => p.id === selectedProjectId) ?? null : null;
  const fullViewProject = fullViewProjectId ? projects.find((p) => p.id === fullViewProjectId) ?? null : null;

  const openFullView = useCallback((projectId: string) => {
    setSelectedProjectId(null); // close drawer
    setFullViewProjectId(projectId);
    const url = new URL(window.location.href);
    url.searchParams.set("project", projectId);
    window.history.pushState({}, "", url.toString());
  }, []);

  const closeFullView = useCallback(() => {
    setFullViewProjectId(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("project");
    url.searchParams.delete("view");
    window.history.pushState({}, "", url.toString());
  }, []);

  // Loading state
  if (loading) {
    return (
      <div className="p-6 space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-14 rounded-lg bg-white/[0.03] animate-pulse" />
        ))}
      </div>
    );
  }

  // Full-page view (replaces everything)
  if (fullViewProject) {
    return <ProjectFullView project={fullViewProject} onBack={closeFullView} />;
  }

  return (
    <div className="h-full overflow-y-auto px-6 sm:px-8 py-6 space-y-5">
      {error && (
        <div className="p-4 rounded-lg bg-type-error/10 border border-type-error/20 text-type-error text-[15px]">
          {error}
        </div>
      )}

      {/* Summary Stat Strip */}
      <SummaryStrip projects={nonParked} dormantCount={parkedCount} attentionCount={needsAttention.filter((a) => a.severity === "red").length} />

      {/* Needs Attention Banner */}
      <NeedsAttentionBar items={needsAttention} onClickItem={(id) => setSelectedProjectId(id)} />

      {/* Header + view toggle + search */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <h1 className="text-[22px] font-light text-ink tracking-tight">Projects</h1>
          <ViewToggle mode={viewMode} onChange={setViewMode} />
        </div>
        <div className="relative w-56">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint/40" width="14" height="14" viewBox="0 0 14 14" fill="none">
            <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.2" />
            <path d="M9.5 9.5L13 13" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            placeholder="Filter..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-edge bg-surface py-2 pl-9 pr-3 text-[15px] text-ink placeholder:text-ink-faint/40 outline-none focus:border-edge-default transition-colors"
          />
        </div>
      </div>

      {/* Board View */}
      {viewMode === "board" && (
        <ProjectBoard
          projects={projects}
          searchQuery={searchQuery}
          onSelectProject={(id) => setSelectedProjectId(id)}
        />
      )}

      {/* Card View */}
      {viewMode === "cards" && (
        <ProjectOverviewGrid
          projects={projects}
          searchQuery={searchQuery}
          onSelectProject={(id) => setSelectedProjectId(id)}
        />
      )}

      {/* List View — existing table code, kept inline */}
      {viewMode === "list" && (
        <div className="admin-card overflow-hidden">
          {/* TABLE CODE: This is the existing table from the current ProjectsView.
              Copy the entire <table> block (thead + tbody with active rows, dormant section)
              from the current file. The only change: clicking a row opens the drawer
              (setSelectedProjectId) instead of expanding inline. Keep inline expand
              as a secondary interaction for list view.

              For brevity, the implementer should copy lines 551-741 from the current
              ProjectsView.tsx, changing:
              - setExpandedId -> setListExpandedId
              - expandedId -> listExpandedId
              - The ProjectDetailPanel stays inline for list view only
          */}
          <table className="w-full">
            {/* ... existing table code with listExpandedId instead of expandedId ... */}
          </table>
        </div>
      )}

      {/* Side Drawer */}
      <ProjectDrawer
        project={selectedProject}
        onClose={() => setSelectedProjectId(null)}
        onOpenFull={openFullView}
      />
    </div>
  );
}
```

**IMPORTANT for implementer:** The list view table code is large (~190 lines). Copy it from the current `ProjectsView.tsx` (lines 551-741) into the `{viewMode === "list" && ...}` block. Make these substitutions:
- `expandedId` → `listExpandedId`
- `setExpandedId` → `setListExpandedId`
- Keep `ProjectDetailPanel` inline (only used by list view now)
- Keep `HealthDot`, `ProgressBar`, `ChevronIcon`, `ProjectHoverPreview` as helpers at the top of the file (they're only used by the list view)

- [ ] **Step 2: Delete ProjectDetailDrawer.tsx**

```bash
rm ~/Projects/omega/website/app/admin/components/projects/ProjectDetailDrawer.tsx
```

- [ ] **Step 3: Update index.ts barrel export**

Read `website/app/admin/components/projects/index.ts` and ensure it exports `ProjectsView` (default). Remove any `ProjectDetailDrawer` export if present.

- [ ] **Step 4: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

Fix any type errors. Common issues:
- `SessionHeatmap` prop name might be `entries` not `data` — check the component
- `SlideDrawer` import path might need adjustment (it's at `../SlideDrawer` relative to projects/)

- [ ] **Step 5: Full build**

Run: `cd ~/Projects/omega/website && npm run build`

- [ ] **Step 6: Commit**

```bash
git add -A website/app/admin/components/projects/
git commit -m "feat: rewrite ProjectsView as orchestrator with board/drawer/full-view"
```

### Task 10: Verify and deploy

- [ ] **Step 1: Full type check**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

- [ ] **Step 2: Full build**

Run: `cd ~/Projects/omega/website && npm run build`

- [ ] **Step 3: Deploy**

Run: `cd ~/Projects/omega/website && vercel --prod`

- [ ] **Step 4: Verify live**

Open `https://omegamax.co/admin?tab=projects` and verify:
1. Board view loads as default with 5 columns
2. Cards populate correctly in columns
3. View toggle switches between Board/Cards/List
4. Clicking a board card opens the drawer
5. "Open Full" in drawer transitions to full-page view
6. Browser back button returns to board from full view
7. Search filters across all views
8. Summary strip shows correct counts
9. NeedsAttention banner is clickable
