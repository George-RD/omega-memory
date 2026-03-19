# Admin Projects Tab — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Projects" tab to the admin dashboard that shows a project-scoped session timeline, answering "where did I leave off?" and "what did I do?" using existing coordination data.

**Architecture:** Left panel project list + main area with Resume Bar (latest handoff next_steps) + scrollable session timeline. Two new API endpoints aggregate coordination data by project. Dashboard tab loses its project grid; keeps health/ambient.

**Tech Stack:** Next.js 14 (App Router), TypeScript, Supabase (coord_* tables), Tailwind CSS, existing admin component patterns.

**Design doc:** `docs/plans/2026-02-28-admin-projects-tab-design.md`

---

### Task 1: Add "projects" to Tab type union and Sidebar registration

**Files:**
- Modify: `app/admin/lib/types.ts:3` (Tab type)
- Modify: `app/admin/components/shell/Sidebar.tsx` (primaryItems array)

**Step 1: Add "projects" to Tab union**

In `app/admin/lib/types.ts`, line 3, change:
```ts
export type Tab = "dashboard" | "feed" | "actions" | "insights" | "docs" | "jobs" | "settings" | "coordination" | "entities" | "llm-usage";
```
to:
```ts
export type Tab = "dashboard" | "projects" | "feed" | "actions" | "insights" | "docs" | "jobs" | "settings" | "coordination" | "entities" | "llm-usage";
```

**Step 2: Add Sidebar entry**

In `app/admin/components/shell/Sidebar.tsx`, add to `primaryItems` array at index 1 (after Dashboard, before Feed):

```tsx
{
  id: "projects" as Tab,
  label: "Projects",
  icon: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z" />
    </svg>
  ),
},
```

**Step 3: Add valid tab to resolveTab()**

In `app/admin/page.tsx`, line 71, add `"projects"` to the valid tabs array:
```ts
const valid: Tab[] = ["dashboard", "projects", "feed", "actions", "insights", "docs", "jobs", "settings", "coordination", "entities", "llm-usage"];
```

**Step 4: Verify TypeScript compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors (or only pre-existing ones).

**Step 5: Commit**

```bash
git add app/admin/lib/types.ts app/admin/components/shell/Sidebar.tsx app/admin/page.tsx
git commit -m "feat(admin): register Projects tab in sidebar and type system"
```

---

### Task 2: Create `/api/admin/projects/list` endpoint

**Files:**
- Create: `app/api/admin/projects/list/route.ts`

**Step 1: Create the endpoint**

Follow the exact pattern from `/api/admin/coordination/route.ts`. This endpoint aggregates `coord_sessions` by project, counts sessions and active tasks, and maps to display names via `projectConfig.ts`.

```ts
import { NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import { PROJECTS, getSessionNamesForProject } from "@/app/admin/components/dashboard/projectConfig";

export const dynamic = "force-dynamic";

export interface ProjectListItem {
  id: string;
  name: string;
  category: string;
  lastActive: string | null;
  sessionCount: number;
  activeTaskCount: number;
  hasActiveSession: boolean;
}

export async function GET() {
  try {
    const db = supabaseServer();

    // Fetch all sessions (no time filter — we want totals)
    const [sessionsRes, tasksRes] = await Promise.all([
      db
        .from("coord_sessions")
        .select("session_id, project, status, started_at, last_heartbeat")
        .order("last_heartbeat", { ascending: false })
        .limit(2000),
      db
        .from("coord_tasks")
        .select("id, project, status")
        .in("status", ["pending", "in_progress"]),
    ]);

    const sessions = sessionsRes.data ?? [];
    const tasks = tasksRes.data ?? [];

    // Build a map: project path -> session names from projectConfig
    const projectMap = new Map<string, ProjectListItem>();

    for (const proj of PROJECTS) {
      const sessionNames = getSessionNamesForProject(proj.id);
      const matchingSessions = sessions.filter((s) =>
        sessionNames.some((name) => s.project?.includes(name))
      );
      const matchingTasks = tasks.filter((t) =>
        sessionNames.some((name) => t.project?.includes(name))
      );

      const lastSession = matchingSessions[0]; // already sorted by last_heartbeat desc
      const hasActive = matchingSessions.some((s) => s.status === "active");

      projectMap.set(proj.id, {
        id: proj.id,
        name: proj.name,
        category: proj.category,
        lastActive: lastSession?.last_heartbeat ?? null,
        sessionCount: matchingSessions.length,
        activeTaskCount: matchingTasks.length,
        hasActiveSession: hasActive,
      });
    }

    // Sort by lastActive descending (most recent first), nulls last
    const projects = Array.from(projectMap.values()).sort((a, b) => {
      if (!a.lastActive && !b.lastActive) return 0;
      if (!a.lastActive) return 1;
      if (!b.lastActive) return -1;
      return new Date(b.lastActive).getTime() - new Date(a.lastActive).getTime();
    });

    return NextResponse.json(
      { projects },
      { headers: { "Cache-Control": "s-maxage=60, stale-while-revalidate=120" } }
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: msg, projects: [] }, { status: 500 });
  }
}
```

**Step 2: Verify endpoint**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: Clean compile.

**Step 3: Commit**

```bash
git add app/api/admin/projects/list/route.ts
git commit -m "feat(admin): add /api/admin/projects/list endpoint"
```

---

### Task 3: Create `/api/admin/projects/timeline` endpoint

**Files:**
- Create: `app/api/admin/projects/timeline/route.ts`

**Step 1: Create the endpoint**

This is the core endpoint — aggregates sessions + handoffs + decisions + git events per project into a unified timeline.

```ts
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import { getSessionNamesForProject } from "@/app/admin/components/dashboard/projectConfig";
import type {
  CoordinationSession,
  CoordinationHandoff,
  CoordinationDecision,
  CoordinationGitEvent,
} from "@/app/admin/lib/types";

export const dynamic = "force-dynamic";

export interface ProjectTimelineEntry {
  session: CoordinationSession;
  handoff: CoordinationHandoff | null;
  decisions: CoordinationDecision[];
  gitEvents: CoordinationGitEvent[];
  durationMinutes: number;
}

export interface ProjectTimelineResponse {
  entries: ProjectTimelineEntry[];
  total: number;
  project: string;
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const project = params.get("project");
  const limit = Math.min(parseInt(params.get("limit") ?? "20", 10), 100);
  const offset = parseInt(params.get("offset") ?? "0", 10);
  const since = params.get("since"); // ISO timestamp

  if (!project) {
    return NextResponse.json(
      { error: "project parameter required", entries: [], total: 0, project: "" },
      { status: 400 }
    );
  }

  try {
    const db = supabaseServer();
    const sessionNames = getSessionNamesForProject(project);

    // Build an OR filter for project names
    // coord_sessions.project is a path — match any sessionName substring
    // We use .or() with ilike for flexible matching
    const orFilter = sessionNames.map((n) => `project.ilike.%${n}%`).join(",");

    // 1. Get total count
    const countQuery = db
      .from("coord_sessions")
      .select("session_id", { count: "exact", head: true });
    if (orFilter) countQuery.or(orFilter);
    if (since) countQuery.gte("started_at", since);
    const { count: total } = await countQuery;

    // 2. Get paginated sessions
    const sessionsQuery = db
      .from("coord_sessions")
      .select("*")
      .order("started_at", { ascending: false })
      .range(offset, offset + limit - 1);
    if (orFilter) sessionsQuery.or(orFilter);
    if (since) sessionsQuery.gte("started_at", since);
    const { data: sessions } = await sessionsQuery;

    if (!sessions || sessions.length === 0) {
      return NextResponse.json(
        { entries: [], total: 0, project },
        { headers: { "Cache-Control": "no-store" } }
      );
    }

    const sessionIds = sessions.map((s: CoordinationSession) => s.session_id);

    // 3. Fetch related data in parallel
    const [handoffsRes, decisionsRes, gitEventsRes] = await Promise.all([
      db
        .from("coord_handoffs")
        .select("id, session_id, project, completed_tasks, blocked_items, key_context, next_steps, files_modified, decisions_made, git_branch, git_dirty_files, created_at, read_by")
        .in("session_id", sessionIds)
        .order("created_at", { ascending: false }),
      db
        .from("coord_decisions")
        .select("id, domain, project, decision, rationale, decided_by, goal_id, status, superseded_by, created_at, superseded_at")
        .in("decided_by", sessionIds)
        .order("created_at", { ascending: false }),
      db
        .from("coord_git_events")
        .select("id, session_id, project, event_type, commit_hash, branch, message, created_at")
        .in("session_id", sessionIds)
        .order("created_at", { ascending: false }),
    ]);

    const handoffs = handoffsRes.data ?? [];
    const decisions = decisionsRes.data ?? [];
    const gitEvents = gitEventsRes.data ?? [];

    // 4. Assemble timeline entries
    const entries: ProjectTimelineEntry[] = sessions.map((session: CoordinationSession) => {
      const handoff = handoffs.find(
        (h: CoordinationHandoff) => h.session_id === session.session_id
      ) ?? null;

      const sessionDecisions = decisions.filter(
        (d: CoordinationDecision) => d.decided_by === session.session_id
      );

      const sessionGitEvents = gitEvents.filter(
        (g: CoordinationGitEvent) => g.session_id === session.session_id
      );

      // Calculate duration
      const start = new Date(session.started_at).getTime();
      const end = handoff
        ? new Date(handoff.created_at).getTime()
        : new Date(session.last_heartbeat).getTime();
      const durationMinutes = Math.round((end - start) / 60000);

      return { session, handoff, decisions: sessionDecisions, gitEvents: sessionGitEvents, durationMinutes };
    });

    return NextResponse.json(
      { entries, total: total ?? 0, project } satisfies ProjectTimelineResponse,
      { headers: { "Cache-Control": "no-store" } }
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: msg, entries: [], total: 0, project },
      { status: 500 }
    );
  }
}
```

**Step 2: Verify endpoint compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: Clean compile.

**Step 3: Commit**

```bash
git add app/api/admin/projects/timeline/route.ts
git commit -m "feat(admin): add /api/admin/projects/timeline endpoint"
```

---

### Task 4: Create ProjectList component (left panel)

**Files:**
- Create: `app/admin/components/projects/ProjectList.tsx`

**Step 1: Create the component**

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";

interface ProjectListItem {
  id: string;
  name: string;
  category: string;
  lastActive: string | null;
  sessionCount: number;
  activeTaskCount: number;
  hasActiveSession: boolean;
}

interface Props {
  selectedProject: string | null;
  onSelectProject: (id: string) => void;
}

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return "30d+";
}

export default function ProjectList({ selectedProject, onSelectProject }: Props) {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/projects/list");
      const data = await res.json();
      setProjects(data.projects ?? []);
    } catch {
      // silent fail — retry on next poll
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
    const interval = setInterval(fetchProjects, 60_000);
    return () => clearInterval(interval);
  }, [fetchProjects]);

  // Auto-select most recent project on first load
  useEffect(() => {
    if (!selectedProject && projects.length > 0) {
      onSelectProject(projects[0].id);
    }
  }, [projects, selectedProject, onSelectProject]);

  const STALE_THRESHOLD = 30 * 24 * 60 * 60 * 1000; // 30 days
  const activeProjects = projects.filter(
    (p) => p.lastActive && Date.now() - new Date(p.lastActive).getTime() < STALE_THRESHOLD
  );
  const staleProjects = projects.filter(
    (p) => !p.lastActive || Date.now() - new Date(p.lastActive).getTime() >= STALE_THRESHOLD
  );

  if (loading) {
    return (
      <div className="w-60 shrink-0 border-r border-white/10 p-4">
        <div className="text-sm text-white/40 animate-pulse">Loading projects…</div>
      </div>
    );
  }

  return (
    <div className="w-60 shrink-0 border-r border-white/10 overflow-y-auto">
      <div className="p-3 pb-2">
        <h2 className="text-xs font-semibold text-white/50 uppercase tracking-wider">Projects</h2>
      </div>

      {activeProjects.map((p) => (
        <button
          key={p.id}
          onClick={() => onSelectProject(p.id)}
          className={`w-full text-left px-3 py-2.5 border-l-2 transition-colors ${
            selectedProject === p.id
              ? "border-amber-400 bg-white/5"
              : "border-transparent hover:bg-white/[0.03]"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  p.hasActiveSession ? "bg-green-400" : "bg-white/20"
                }`}
              />
              <span className="text-sm font-medium text-white/90">{p.name}</span>
            </div>
            <span className="text-[11px] text-white/30">{relativeTime(p.lastActive)}</span>
          </div>
          <div className="ml-3.5 mt-0.5 text-[11px] text-white/30">
            {p.sessionCount} sessions · {p.activeTaskCount} tasks
          </div>
        </button>
      ))}

      {staleProjects.length > 0 && (
        <>
          <div className="mx-3 my-2 border-t border-white/5" />
          {staleProjects.map((p) => (
            <button
              key={p.id}
              onClick={() => onSelectProject(p.id)}
              className={`w-full text-left px-3 py-2 border-l-2 transition-colors ${
                selectedProject === p.id
                  ? "border-amber-400 bg-white/5"
                  : "border-transparent hover:bg-white/[0.03]"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-white/10" />
                  <span className="text-sm text-white/40">{p.name}</span>
                </div>
                <span className="text-[11px] text-white/20">{relativeTime(p.lastActive)}</span>
              </div>
            </button>
          ))}
        </>
      )}
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 3: Commit**

```bash
git add app/admin/components/projects/ProjectList.tsx
git commit -m "feat(admin): add ProjectList sidebar component"
```

---

### Task 5: Create ResumeBar component

**Files:**
- Create: `app/admin/components/projects/ResumeBar.tsx`

**Step 1: Create the component**

```tsx
"use client";

import type { ProjectTimelineEntry } from "./types";

interface Props {
  entry: ProjectTimelineEntry | null;
  loading: boolean;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function parseJsonArray(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function ResumeBar({ entry, loading }: Props) {
  if (loading) {
    return (
      <div className="rounded-lg border border-white/10 bg-white/[0.02] p-4 animate-pulse">
        <div className="h-4 w-48 bg-white/10 rounded" />
        <div className="h-3 w-64 bg-white/5 rounded mt-3" />
      </div>
    );
  }

  if (!entry?.handoff) {
    return (
      <div className="rounded-lg border border-white/5 bg-white/[0.01] p-4">
        <p className="text-sm text-white/30">No recent activity for this project.</p>
      </div>
    );
  }

  const { session, handoff } = entry;
  const nextSteps = parseJsonArray(handoff.next_steps);
  const blockedItems = parseJsonArray(handoff.blocked_items);
  const filesModified = parseJsonArray(handoff.files_modified);

  return (
    <div className="rounded-lg border border-amber-400/20 bg-amber-400/[0.03] p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-amber-400 text-sm font-medium">Pick up where you left off</span>
        </div>
        <span className="text-[11px] text-white/30">{relativeTime(handoff.created_at)}</span>
      </div>

      <p className="text-sm text-white/70 mb-1">
        Last session: <span className="text-white/90">{session.task || "Untitled session"}</span>
      </p>

      {(handoff.git_branch || filesModified.length > 0) && (
        <p className="text-xs text-white/30 mb-3">
          {handoff.git_branch && (
            <span className="font-mono">{handoff.git_branch}</span>
          )}
          {handoff.git_branch && filesModified.length > 0 && " · "}
          {filesModified.length > 0 && `${filesModified.length} files modified`}
        </p>
      )}

      {nextSteps.length > 0 && (
        <div className="mb-2">
          <p className="text-xs font-medium text-white/50 mb-1">Next steps:</p>
          <ul className="space-y-0.5">
            {nextSteps.map((step, i) => (
              <li key={i} className="text-sm text-white/70 flex items-start gap-1.5">
                <span className="text-white/20 mt-0.5 text-xs">•</span>
                {step}
              </li>
            ))}
          </ul>
        </div>
      )}

      {blockedItems.length > 0 && (
        <div className="mt-2 rounded bg-amber-400/10 px-3 py-2">
          <p className="text-xs font-medium text-amber-400/80 mb-0.5">Blocked:</p>
          {blockedItems.map((item, i) => (
            <p key={i} className="text-sm text-amber-300/70">{item}</p>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Create shared types file**

Create `app/admin/components/projects/types.ts`:

```ts
import type {
  CoordinationSession,
  CoordinationHandoff,
  CoordinationDecision,
  CoordinationGitEvent,
} from "../../lib/types";

export interface ProjectTimelineEntry {
  session: CoordinationSession;
  handoff: CoordinationHandoff | null;
  decisions: CoordinationDecision[];
  gitEvents: CoordinationGitEvent[];
  durationMinutes: number;
}
```

**Step 3: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 4: Commit**

```bash
git add app/admin/components/projects/ResumeBar.tsx app/admin/components/projects/types.ts
git commit -m "feat(admin): add ResumeBar and shared types for Projects tab"
```

---

### Task 6: Create SessionCard component

**Files:**
- Create: `app/admin/components/projects/SessionCard.tsx`

**Step 1: Create the component**

This is the main timeline entry — a collapsible card showing what happened in a single session.

```tsx
"use client";

import { useState } from "react";
import type { ProjectTimelineEntry } from "./types";
import type { CoordinationDecision, CoordinationGitEvent } from "../../lib/types";

interface Props {
  entry: ProjectTimelineEntry;
  index: number;
  isLatest: boolean;
}

function parseJsonArray(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function formatDuration(mins: number): string {
  if (mins < 1) return "<1m";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  const rem = mins % 60;
  return rem > 0 ? `${hrs}h ${rem}m` : `${hrs}h`;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
    ", " +
    d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function CollapsibleSection({
  label,
  icon,
  count,
  defaultOpen,
  children,
}: {
  label: string;
  icon: string;
  count: number;
  defaultOpen: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (count === 0) return null;

  return (
    <div className="border-t border-white/5">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2 text-xs text-white/50 hover:text-white/70 transition-colors"
      >
        <span>
          {icon} {label} ({count})
        </span>
        <span className="text-[10px]">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

export default function SessionCard({ entry, index, isLatest }: Props) {
  const [expanded, setExpanded] = useState(isLatest);
  const { session, handoff, decisions, gitEvents, durationMinutes } = entry;

  const completedTasks = parseJsonArray(handoff?.completed_tasks);
  const decisionsMade = parseJsonArray(handoff?.decisions_made);
  const filesModified = parseJsonArray(handoff?.files_modified);
  const nextSteps = parseJsonArray(handoff?.next_steps);
  const blockedItems = parseJsonArray(handoff?.blocked_items);

  return (
    <div className={`rounded-lg border transition-colors ${
      isLatest ? "border-white/10 bg-white/[0.03]" : "border-white/5 bg-white/[0.01]"
    }`}>
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-3"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[11px] text-white/20 font-mono shrink-0">#{index}</span>
            <span className="text-sm text-white/90 truncate">
              {session.task || "Untitled session"}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-2">
            <span className="text-[11px] text-white/30">{formatDuration(durationMinutes)}</span>
            <span className="text-[11px] text-white/20">{formatTimestamp(session.started_at)}</span>
            <span className="text-[10px] text-white/20">{expanded ? "▾" : "▸"}</span>
          </div>
        </div>
        {handoff?.git_branch && (
          <div className="mt-1 ml-6">
            <span className="text-[11px] font-mono text-white/20">{handoff.git_branch}</span>
          </div>
        )}
      </button>

      {/* Expandable body */}
      {expanded && (
        <div>
          <CollapsibleSection
            label="Completed"
            icon="✓"
            count={completedTasks.length}
            defaultOpen={isLatest}
          >
            <ul className="space-y-1">
              {completedTasks.map((task, i) => (
                <li key={i} className="text-sm text-white/60 flex items-start gap-1.5">
                  <span className="text-green-400/60 text-xs mt-0.5">✓</span>
                  {task}
                </li>
              ))}
            </ul>
          </CollapsibleSection>

          <CollapsibleSection
            label="Decisions"
            icon="◆"
            count={decisions.length + decisionsMade.length}
            defaultOpen={false}
          >
            {decisions.map((d: CoordinationDecision) => (
              <div key={d.id} className="mb-2 last:mb-0">
                <p className="text-sm text-white/60">{d.decision}</p>
                {d.rationale && (
                  <p className="text-xs text-white/30 mt-0.5 italic">{d.rationale}</p>
                )}
              </div>
            ))}
            {/* Fallback to handoff decisions_made if no formal decisions */}
            {decisions.length === 0 &&
              decisionsMade.map((d, i) => (
                <p key={i} className="text-sm text-white/60">{d}</p>
              ))}
          </CollapsibleSection>

          <CollapsibleSection
            label="Files"
            icon="◇"
            count={filesModified.length}
            defaultOpen={false}
          >
            <ul className="space-y-0.5">
              {filesModified.slice(0, 8).map((f, i) => (
                <li key={i} className="text-xs font-mono text-white/40 truncate">{f}</li>
              ))}
              {filesModified.length > 8 && (
                <li className="text-xs text-white/20">+{filesModified.length - 8} more</li>
              )}
            </ul>
          </CollapsibleSection>

          <CollapsibleSection
            label="Commits"
            icon="⟠"
            count={gitEvents.length}
            defaultOpen={false}
          >
            {gitEvents
              .filter((g: CoordinationGitEvent) => g.event_type === "commit")
              .map((g: CoordinationGitEvent) => (
                <div key={g.id} className="flex items-start gap-2 mb-1 last:mb-0">
                  <span className="text-xs font-mono text-amber-400/50 shrink-0">
                    {g.commit_hash?.slice(0, 7) ?? "—"}
                  </span>
                  <span className="text-sm text-white/50 truncate">{g.message}</span>
                </div>
              ))}
          </CollapsibleSection>

          {isLatest && blockedItems.length > 0 && (
            <div className="border-t border-white/5 px-4 py-2">
              <p className="text-xs font-medium text-amber-400/60 mb-1">Blocked:</p>
              {blockedItems.map((item, i) => (
                <p key={i} className="text-sm text-amber-300/50">{item}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 3: Commit**

```bash
git add app/admin/components/projects/SessionCard.tsx
git commit -m "feat(admin): add SessionCard component with collapsible sections"
```

---

### Task 7: Create SessionTimeline and StatsHeader components

**Files:**
- Create: `app/admin/components/projects/SessionTimeline.tsx`
- Create: `app/admin/components/projects/StatsHeader.tsx`

**Step 1: Create StatsHeader**

```tsx
"use client";

import type { ProjectTimelineEntry } from "./types";

type TimeRange = "all" | "week" | "month";

interface Props {
  entries: ProjectTimelineEntry[];
  total: number;
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

export default function StatsHeader({ entries, total, timeRange, onTimeRangeChange }: Props) {
  const totalDecisions = entries.reduce((acc, e) => acc + e.decisions.length, 0);
  const totalCommits = entries.reduce(
    (acc, e) => acc + e.gitEvents.filter((g) => g.event_type === "commit").length,
    0
  );

  const ranges: { id: TimeRange; label: string }[] = [
    { id: "all", label: "All" },
    { id: "week", label: "This week" },
    { id: "month", label: "This month" },
  ];

  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-3 text-[11px] text-white/30">
        <span>{total} sessions</span>
        <span>·</span>
        <span>{totalDecisions} decisions</span>
        <span>·</span>
        <span>{totalCommits} commits</span>
      </div>
      <div className="flex items-center gap-1">
        {ranges.map((r) => (
          <button
            key={r.id}
            onClick={() => onTimeRangeChange(r.id)}
            className={`px-2 py-0.5 rounded text-[11px] transition-colors ${
              timeRange === r.id
                ? "bg-white/10 text-white/70"
                : "text-white/30 hover:text-white/50"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Create SessionTimeline**

```tsx
"use client";

import SessionCard from "./SessionCard";
import type { ProjectTimelineEntry } from "./types";

interface Props {
  entries: ProjectTimelineEntry[];
  total: number;
  loading: boolean;
  onLoadMore: () => void;
}

export default function SessionTimeline({ entries, total, loading, onLoadMore }: Props) {
  if (loading && entries.length === 0) {
    return (
      <div className="space-y-3 mt-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-lg border border-white/5 bg-white/[0.01] p-4 animate-pulse">
            <div className="h-4 w-64 bg-white/10 rounded" />
            <div className="h-3 w-40 bg-white/5 rounded mt-2" />
          </div>
        ))}
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-white/30">No sessions found for this project.</p>
      </div>
    );
  }

  // Number sessions in reverse (oldest = #1)
  const startNumber = total - entries.length + 1;

  return (
    <div className="space-y-2 mt-3">
      {entries.map((entry, i) => (
        <SessionCard
          key={entry.session.session_id}
          entry={entry}
          index={total - i}
          isLatest={i === 0}
        />
      ))}

      {entries.length < total && (
        <button
          onClick={onLoadMore}
          disabled={loading}
          className="w-full py-2 text-sm text-white/30 hover:text-white/50 transition-colors disabled:opacity-50"
        >
          {loading ? "Loading…" : `Load more (${total - entries.length} remaining)`}
        </button>
      )}
    </div>
  );
}
```

**Step 3: Verify they compile**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 4: Commit**

```bash
git add app/admin/components/projects/SessionTimeline.tsx app/admin/components/projects/StatsHeader.tsx
git commit -m "feat(admin): add SessionTimeline and StatsHeader components"
```

---

### Task 8: Create ProjectsView container component

**Files:**
- Create: `app/admin/components/projects/ProjectsView.tsx`
- Create: `app/admin/components/projects/index.ts`

**Step 1: Create the main container**

This orchestrates all sub-components and manages data fetching.

```tsx
"use client";

import { useState, useCallback, useEffect } from "react";
import ProjectList from "./ProjectList";
import ResumeBar from "./ResumeBar";
import StatsHeader from "./StatsHeader";
import SessionTimeline from "./SessionTimeline";
import type { ProjectTimelineEntry } from "./types";

type TimeRange = "all" | "week" | "month";

function sinceForRange(range: TimeRange): string | null {
  if (range === "all") return null;
  const now = new Date();
  if (range === "week") {
    const d = new Date(now);
    d.setDate(d.getDate() - 7);
    return d.toISOString();
  }
  // month
  const d = new Date(now);
  d.setMonth(d.getMonth() - 1);
  return d.toISOString();
}

export default function ProjectsView() {
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [entries, setEntries] = useState<ProjectTimelineEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [timeRange, setTimeRange] = useState<TimeRange>("all");
  const [offset, setOffset] = useState(0);

  const fetchTimeline = useCallback(
    async (project: string, append: boolean = false) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ project, limit: "20" });
        if (append) params.set("offset", String(offset + 20));
        const since = sinceForRange(timeRange);
        if (since) params.set("since", since);

        const res = await fetch(`/api/admin/projects/timeline?${params}`);
        const data = await res.json();

        if (append) {
          setEntries((prev) => [...prev, ...(data.entries ?? [])]);
          setOffset((prev) => prev + 20);
        } else {
          setEntries(data.entries ?? []);
          setOffset(0);
        }
        setTotal(data.total ?? 0);
      } catch {
        // silent fail
      } finally {
        setLoading(false);
      }
    },
    [timeRange, offset]
  );

  // Fetch when project or time range changes
  useEffect(() => {
    if (selectedProject) {
      setEntries([]);
      setOffset(0);
      fetchTimeline(selectedProject, false);
    }
  }, [selectedProject, timeRange]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleLoadMore = () => {
    if (selectedProject) fetchTimeline(selectedProject, true);
  };

  return (
    <div className="flex h-full">
      <ProjectList
        selectedProject={selectedProject}
        onSelectProject={setSelectedProject}
      />

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {selectedProject ? (
          <>
            <ResumeBar entry={entries[0] ?? null} loading={loading && entries.length === 0} />

            <StatsHeader
              entries={entries}
              total={total}
              timeRange={timeRange}
              onTimeRangeChange={setTimeRange}
            />

            <SessionTimeline
              entries={entries}
              total={total}
              loading={loading}
              onLoadMore={handleLoadMore}
            />
          </>
        ) : (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-white/30">Select a project to view its timeline.</p>
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Create barrel export**

Create `app/admin/components/projects/index.ts`:
```ts
export { default } from "./ProjectsView";
```

**Step 3: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 4: Commit**

```bash
git add app/admin/components/projects/
git commit -m "feat(admin): add ProjectsView container with data fetching"
```

---

### Task 9: Wire Projects tab into admin page

**Files:**
- Modify: `app/admin/page.tsx`

**Step 1: Add dynamic import**

After the existing dynamic imports (around line 30), add:

```tsx
const Projects = dynamic(() => import("./components/projects"), { loading: () => <TabSkeleton /> });
```

**Step 2: Add conditional render**

In the conditional render section (around line 435-479), add the `projects` case. It should get **full bleed** rendering (like coordination) since it has its own sidebar panel:

```tsx
{active === "projects" && <Projects />}
```

This should go in the full-bleed section (before the `<main>` wrapper), similar to how `coordination` is rendered. The Projects tab manages its own layout (flex with left panel).

Specifically, find the pattern:
```tsx
{active === "coordination" && <Coordination ... />}
```
And add after it:
```tsx
{active === "projects" && (
  <div className="absolute inset-0">
    <Projects />
  </div>
)}
```

**Step 3: Add max-width for "projects" if rendered inside main**

If the coordination full-bleed pattern doesn't apply cleanly, alternatively render inside `<main>` and skip max-width constraint — the ProjectsView manages its own width via flex.

**Step 4: Verify the page compiles and renders**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`
Then: `cd ~/Projects/omega/website && npx next build 2>&1 | tail -20`

**Step 5: Commit**

```bash
git add app/admin/page.tsx
git commit -m "feat(admin): wire Projects tab into admin page with full-bleed layout"
```

---

### Task 10: Remove project grid from Dashboard tab

**Files:**
- Modify: `app/admin/components/Dashboard.tsx` (or wherever ProjectGrid is imported)

**Step 1: Read current Dashboard.tsx to understand imports**

Read `app/admin/components/Dashboard.tsx` to see how ProjectGrid is imported and used.

**Step 2: Remove ProjectGrid rendering**

Remove the `<ProjectGrid>` component and its related state (`pausedIds`, `onTogglePause` handler) from the Dashboard. Keep:
- System Health Report Card
- Ambient status display
- Suggestions panel (if it exists independently of projects)

Do NOT delete the ProjectGrid or projectConfig files — ProjectList still imports from projectConfig.

**Step 3: Verify the Dashboard still renders**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 4: Commit**

```bash
git add app/admin/components/Dashboard.tsx
git commit -m "refactor(admin): remove project grid from Dashboard (moved to Projects tab)"
```

---

### Task 11: Final build verification and smoke test

**Step 1: Run full TypeScript check**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty`
Expected: Clean (zero errors).

**Step 2: Run Next.js build**

Run: `cd ~/Projects/omega/website && npx next build 2>&1 | tail -30`
Expected: Build succeeds, `/admin` page compiles.

**Step 3: Check for hardcoded counts in tests**

Run: `cd ~/Projects/omega && grep -r "tab.*count\|assert.*len.*tab\|num_tabs\|TAB_COUNT" tests/ --include="*.py" --include="*.ts" --include="*.tsx"`
If any test files assert a count of tabs, update them from 10 to 11.

**Step 4: Final commit (if any fixes needed)**

```bash
git add -A  # only if fixing test assertions
git commit -m "fix: update tab count assertions for new Projects tab"
```
