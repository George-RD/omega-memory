# Project Detail Visualization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an interactive master-detail view to the admin Projects tab with a Mermaid architecture diagram, session heatmap, and decision timeline when clicking a project card.

**Architecture:** `ProjectsView` gains a `viewMode` state that toggles between the card grid and a new `ProjectDetailView`. The detail view fetches architecture data from a new API endpoint, renders Mermaid via CDN, and reuses existing Detail* sidebar components inline.

**Tech Stack:** Next.js 15, React, Mermaid.js 11 (CDN), Tailwind CSS, Supabase

**Security note:** The Mermaid diagram component uses Mermaid's official `render()` API which returns sanitized SVG. The SVG output is set via a ref's innerHTML. This is the standard Mermaid integration pattern and the SVG is generated locally from our own server-generated syntax (not user input). The mermaidSyntax is built server-side from coordination table data only.

---

### Task 1: Add types for architecture response

**Files:**
- Modify: `website/app/admin/components/projects/types.ts`

**Step 1: Add architecture types to types.ts**

Add at the end of `types.ts`:

```typescript
// ─── Architecture Detail View ──────────────────────────────

export interface ArchitectureModule {
  path: string;
  fileCount: number;
  recentCommits: number;
  health: "active" | "recent" | "dormant";
}

export interface ArchitectureEdge {
  from: string;
  to: string;
  weight: number;
}

export interface SessionHeatmapEntry {
  date: string;
  hour: number;
  count: number;
}

export interface ArchitectureResponse {
  modules: ArchitectureModule[];
  edges: ArchitectureEdge[];
  mermaidSyntax: string;
  sessionHeatmap: SessionHeatmapEntry[];
}
```

**Step 2: Verify types compile**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -5`
Expected: No new errors

**Step 3: Commit**

```bash
git add website/app/admin/components/projects/types.ts
git commit -m "feat(admin): add architecture response types for project detail view"
```

---

### Task 2: Create architecture API endpoint

**Files:**
- Create: `website/app/api/admin/projects/[id]/architecture/route.ts`

**Step 1: Create the API route**

Create `website/app/api/admin/projects/[id]/architecture/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer, getCurrentUser } from "@/lib/supabase";
import { getProjects, pathMatchesProject } from "@/lib/project-resolver";
import type {
  ArchitectureModule,
  ArchitectureEdge,
  SessionHeatmapEntry,
} from "@/app/admin/components/projects/types";

export const dynamic = "force-dynamic";

/** Group a file path into its module (first 2-3 directory segments). */
function toModule(filePath: string): string {
  const parts = filePath.split("/").filter(Boolean);
  // Strip common prefixes
  const start = parts.findIndex(
    (p) => !["Users", "Projects", "home", "."].includes(p),
  );
  const relevant = parts.slice(start >= 0 ? start : 0);
  // Take first 2 segments for grouping (e.g., "src/omega" or "website/app")
  return relevant.slice(0, 2).join("/") || filePath;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id: projectId } = await params;
    const db = supabaseServer();
    const allProjects = await getProjects();
    const project = allProjects.find((p) => p.id === projectId);

    if (!project) {
      return NextResponse.json(
        { error: "Project not found", modules: [], edges: [], mermaidSyntax: "", sessionHeatmap: [] },
        { status: 404 },
      );
    }

    const now = new Date();
    const days7 = new Date(now.getTime() - 7 * 86400000).toISOString();
    const days30 = new Date(now.getTime() - 30 * 86400000).toISOString();
    const days14 = new Date(now.getTime() - 14 * 86400000).toISOString();

    // Parallel fetch: sessions (for heatmap), git events (for modules), file claims
    const [sessionsRes, gitRes, handoffsRes, claimsRes] = await Promise.all([
      db
        .from("coord_sessions")
        .select("session_id, project, started_at, status")
        .gte("started_at", days14)
        .order("started_at", { ascending: false })
        .limit(500),
      db
        .from("coord_git_events")
        .select("id, session_id, project, event_type, message, created_at")
        .eq("event_type", "commit")
        .gte("created_at", days30)
        .order("created_at", { ascending: false })
        .limit(300),
      db
        .from("coord_handoffs")
        .select("session_id, project, files_modified, created_at")
        .gte("created_at", days30)
        .order("created_at", { ascending: false })
        .limit(200),
      db
        .from("coord_file_claims")
        .select("file_path, session_id, claimed_at")
        .order("claimed_at", { ascending: false })
        .limit(200),
    ]);

    const sessions = (sessionsRes.data ?? []).filter((s) =>
      pathMatchesProject(s.project, project),
    );
    const gitEvents = (gitRes.data ?? []).filter((g) =>
      pathMatchesProject(g.project, project),
    );
    const handoffs = (handoffsRes.data ?? []).filter((h) =>
      pathMatchesProject(h.project, project),
    );
    const sessionIds = new Set(sessions.map((s) => s.session_id));
    const fileClaims = (claimsRes.data ?? []).filter((c) =>
      sessionIds.has(c.session_id),
    );

    // --- Build modules from files_modified + file_claims ---
    const moduleFileCount = new Map<string, Set<string>>();
    const moduleCommitCount = new Map<string, number>();
    const moduleLastSeen = new Map<string, number>();

    // From handoffs.files_modified
    for (const h of handoffs) {
      let files: string[] = [];
      try {
        files = JSON.parse(h.files_modified ?? "[]");
      } catch { /* skip */ }
      if (!Array.isArray(files)) continue;

      for (const f of files) {
        if (typeof f !== "string") continue;
        const mod = toModule(f);
        if (!moduleFileCount.has(mod)) moduleFileCount.set(mod, new Set());
        moduleFileCount.get(mod)!.add(f);
        const ts = new Date(h.created_at).getTime();
        if (!moduleLastSeen.has(mod) || ts > moduleLastSeen.get(mod)!) {
          moduleLastSeen.set(mod, ts);
        }
      }
    }

    // From git commits (count per module based on session's files)
    for (const g of gitEvents) {
      const handoff = handoffs.find((h) => h.session_id === g.session_id);
      if (!handoff) continue;
      let files: string[] = [];
      try {
        files = JSON.parse(handoff.files_modified ?? "[]");
      } catch { /* skip */ }
      if (!Array.isArray(files)) continue;
      const mods = new Set(files.filter((f) => typeof f === "string").map(toModule));
      for (const mod of mods) {
        moduleCommitCount.set(mod, (moduleCommitCount.get(mod) ?? 0) + 1);
      }
    }

    // From active file claims
    for (const c of fileClaims) {
      const mod = toModule(c.file_path);
      if (!moduleFileCount.has(mod)) moduleFileCount.set(mod, new Set());
      moduleFileCount.get(mod)!.add(c.file_path);
      const ts = new Date(c.claimed_at).getTime();
      if (!moduleLastSeen.has(mod) || ts > moduleLastSeen.get(mod)!) {
        moduleLastSeen.set(mod, ts);
      }
    }

    // Build module list
    const sevenDaysAgo = now.getTime() - 7 * 86400000;
    const thirtyDaysAgo = now.getTime() - 30 * 86400000;

    const modules: ArchitectureModule[] = Array.from(moduleFileCount.entries())
      .map(([path, files]) => {
        const lastSeen = moduleLastSeen.get(path) ?? 0;
        const health: ArchitectureModule["health"] =
          lastSeen >= sevenDaysAgo ? "active" : lastSeen >= thirtyDaysAgo ? "recent" : "dormant";
        return {
          path,
          fileCount: files.size,
          recentCommits: moduleCommitCount.get(path) ?? 0,
          health,
        };
      })
      .sort((a, b) => b.recentCommits - a.recentCommits || b.fileCount - a.fileCount);

    // --- Build co-change edges ---
    const edges: ArchitectureEdge[] = [];
    const edgeMap = new Map<string, number>();

    for (const h of handoffs) {
      let files: string[] = [];
      try {
        files = JSON.parse(h.files_modified ?? "[]");
      } catch { /* skip */ }
      if (!Array.isArray(files)) continue;
      const mods = [...new Set(files.filter((f) => typeof f === "string").map(toModule))];
      for (let i = 0; i < mods.length; i++) {
        for (let j = i + 1; j < mods.length; j++) {
          const key = [mods[i], mods[j]].sort().join("|||");
          edgeMap.set(key, (edgeMap.get(key) ?? 0) + 1);
        }
      }
    }

    for (const [key, weight] of edgeMap.entries()) {
      if (weight < 2) continue;
      const [from, to] = key.split("|||");
      edges.push({ from, to, weight });
    }
    edges.sort((a, b) => b.weight - a.weight);

    // --- Generate Mermaid syntax ---
    const mermaidLines: string[] = ["flowchart TD"];

    // Group modules by first segment for subgraphs
    const groups = new Map<string, ArchitectureModule[]>();
    for (const mod of modules) {
      const group = mod.path.split("/")[0];
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group)!.push(mod);
    }

    // classDefs - semi-transparent fills, no color: in classDef
    mermaidLines.push("  classDef active fill:#05966933,stroke:#059669,stroke-width:2px");
    mermaidLines.push("  classDef recent fill:#d9770633,stroke:#d97706,stroke-width:1.5px");
    mermaidLines.push("  classDef dormant fill:#64748b11,stroke:#64748b44,stroke-width:1px");

    const nodeId = (path: string) => path.replace(/[^a-zA-Z0-9]/g, "_");

    for (const [group, mods] of groups.entries()) {
      if (mods.length === 1 && groups.size > 1) {
        const mod = mods[0];
        const id = nodeId(mod.path);
        const label = mod.path.split("/").pop() ?? mod.path;
        mermaidLines.push(`  ${id}["${label}"]:::${mod.health}`);
      } else {
        mermaidLines.push(`  subgraph ${nodeId(group)}["${group}"]`);
        for (const mod of mods) {
          const id = nodeId(mod.path);
          const label = mod.path.split("/").slice(1).join("/") || mod.path;
          mermaidLines.push(`    ${id}["${label}"]:::${mod.health}`);
        }
        mermaidLines.push("  end");
      }
    }

    for (const edge of edges.slice(0, 15)) {
      const fromId = nodeId(edge.from);
      const toId = nodeId(edge.to);
      if (edge.weight >= 5) {
        mermaidLines.push(`  ${fromId} ==> ${toId}`);
      } else {
        mermaidLines.push(`  ${fromId} --> ${toId}`);
      }
    }

    const mermaidSyntax = mermaidLines.join("\n");

    // --- Session heatmap (14 days x 24 hours) ---
    const sessionHeatmap: SessionHeatmapEntry[] = [];
    const heatmapMap = new Map<string, number>();

    for (const s of sessions) {
      const d = new Date(s.started_at);
      const dateStr = d.toISOString().slice(0, 10);
      const hour = d.getUTCHours();
      const key = `${dateStr}:${hour}`;
      heatmapMap.set(key, (heatmapMap.get(key) ?? 0) + 1);
    }

    for (const [key, count] of heatmapMap.entries()) {
      const [date, hourStr] = key.split(":");
      sessionHeatmap.push({ date, hour: parseInt(hourStr, 10), count });
    }

    return NextResponse.json(
      { modules, edges, mermaidSyntax, sessionHeatmap },
      { headers: { "Cache-Control": "s-maxage=120, stale-while-revalidate=300" } },
    );
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: msg, modules: [], edges: [], mermaidSyntax: "", sessionHeatmap: [] },
      { status: 500 },
    );
  }
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -10`
Expected: No errors in the new route file

**Step 3: Commit**

```bash
git add website/app/api/admin/projects/\[id\]/architecture/route.ts
git commit -m "feat(admin): add architecture API endpoint deriving modules from coordination data"
```

---

### Task 3: Create ArchitectureDiagram component (Mermaid)

**Files:**
- Create: `website/app/admin/components/projects/ArchitectureDiagram.tsx`

**Step 1: Create the Mermaid diagram component**

Note: This component uses Mermaid's `render()` API which returns sanitized SVG from our server-generated syntax. The SVG is injected into a container ref. This is the standard Mermaid React integration pattern documented at mermaid.js.org. The input syntax is generated server-side from coordination table data only, not from user input.

Create `website/app/admin/components/projects/ArchitectureDiagram.tsx`:

```typescript
"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface ArchitectureDiagramProps {
  mermaidSyntax: string;
  onNodeClick?: (modulePath: string) => void;
}

export default function ArchitectureDiagram({
  mermaidSyntax,
  onNodeClick,
}: ArchitectureDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Load and render Mermaid
  useEffect(() => {
    if (!mermaidSyntax || !containerRef.current) return;

    let cancelled = false;

    async function render() {
      try {
        // Dynamic import from CDN
        const mermaidModule = await import(
          /* webpackIgnore: true */
          "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"
        );
        const mermaid = mermaidModule.default;

        mermaid.initialize({
          startOnLoad: false,
          theme: "base",
          look: "classic",
          themeVariables: {
            primaryColor: "#134e4a",
            primaryBorderColor: "#14b8a6",
            primaryTextColor: "#f0fdfa",
            secondaryColor: "#1e293b",
            secondaryBorderColor: "#059669",
            secondaryTextColor: "#f1f5f9",
            tertiaryColor: "#27201a",
            tertiaryBorderColor: "#d97706",
            tertiaryTextColor: "#fef3c7",
            lineColor: "#64748b",
            fontSize: "14px",
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            noteBkgColor: "#1e293b",
            noteTextColor: "#f1f5f9",
            noteBorderColor: "#fbbf24",
          },
        });

        const id = `mermaid-${Date.now()}`;
        const { svg } = await mermaid.render(id, mermaidSyntax);

        if (cancelled || !containerRef.current) return;

        // Mermaid render() returns sanitized SVG from our server-generated syntax
        containerRef.current.replaceChildren();
        const template = document.createElement("template");
        template.innerHTML = svg;
        if (template.content.firstChild) {
          containerRef.current.appendChild(template.content.firstChild);
        }
        setLoading(false);

        // Attach click handlers to nodes
        if (onNodeClick) {
          const nodes = containerRef.current.querySelectorAll(".node");
          nodes.forEach((node) => {
            const nodeEl = node as HTMLElement;
            nodeEl.style.cursor = "pointer";
            nodeEl.addEventListener("click", () => {
              const nodeIdAttr = nodeEl.id?.replace(/^flowchart-/, "").replace(/-\d+$/, "");
              if (nodeIdAttr) onNodeClick(nodeIdAttr.replace(/_/g, "/"));
            });
          });
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to render diagram");
          setLoading(false);
        }
      }
    }

    render();
    return () => { cancelled = true; };
  }, [mermaidSyntax, onNodeClick]);

  // Zoom with Ctrl+scroll
  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      setScale((s) => Math.min(3, Math.max(0.3, s + delta)));
    },
    [],
  );

  // Pan with drag
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setDragging(true);
    setDragStart({ x: e.clientX - translate.x, y: e.clientY - translate.y });
  }, [translate]);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging) return;
      setTranslate({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    },
    [dragging, dragStart],
  );

  const handleMouseUp = useCallback(() => setDragging(false), []);

  const resetView = useCallback(() => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-red-400/20 bg-red-400/[0.04] p-4">
        <p className="text-xs text-red-400/70">Diagram error: {error}</p>
        <pre className="mt-2 text-[10px] text-white/30 overflow-auto max-h-32 font-mono">
          {mermaidSyntax}
        </pre>
      </div>
    );
  }

  return (
    <div className="relative rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
      {/* Zoom controls */}
      <div className="absolute top-3 right-3 z-10 flex items-center gap-1">
        <button
          onClick={() => setScale((s) => Math.min(3, s + 0.2))}
          className="h-7 w-7 rounded-md bg-white/[0.06] text-white/40 hover:text-white/70 hover:bg-white/[0.1] flex items-center justify-center text-sm transition-colors"
          title="Zoom in"
        >
          +
        </button>
        <button
          onClick={() => setScale((s) => Math.max(0.3, s - 0.2))}
          className="h-7 w-7 rounded-md bg-white/[0.06] text-white/40 hover:text-white/70 hover:bg-white/[0.1] flex items-center justify-center text-sm transition-colors"
          title="Zoom out"
        >
          -
        </button>
        <button
          onClick={resetView}
          className="h-7 rounded-md bg-white/[0.06] text-white/40 hover:text-white/70 hover:bg-white/[0.1] flex items-center justify-center text-[10px] px-2 transition-colors"
          title="Reset view"
        >
          Reset
        </button>
      </div>

      {/* Diagram container */}
      <div
        className="min-h-[300px] flex items-center justify-center p-6"
        style={{ cursor: dragging ? "grabbing" : "grab" }}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {loading && (
          <div className="text-xs text-white/20 animate-pulse">Loading diagram...</div>
        )}
        <div
          ref={containerRef}
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
            transformOrigin: "center center",
            transition: dragging ? "none" : "transform 0.15s ease-out",
          }}
          className="[&_.nodeLabel]:!text-white/80 [&_.edgeLabel]:!text-white/50 [&_.edgeLabel_rect]:!fill-[var(--color-canvas)]"
        />
      </div>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -5`
Expected: No errors (the CDN import may show a TS warning for the dynamic URL import — acceptable)

**Step 3: Commit**

```bash
git add website/app/admin/components/projects/ArchitectureDiagram.tsx
git commit -m "feat(admin): add ArchitectureDiagram component with Mermaid, zoom/pan, node click"
```

---

### Task 4: Create SessionHeatmap component

**Files:**
- Create: `website/app/admin/components/projects/SessionHeatmap.tsx`

**Step 1: Create the SVG heatmap component**

Create `website/app/admin/components/projects/SessionHeatmap.tsx`:

```typescript
"use client";

import { useMemo, useState } from "react";
import type { SessionHeatmapEntry } from "./types";

interface SessionHeatmapProps {
  data: SessionHeatmapEntry[];
}

const CELL_SIZE = 18;
const CELL_GAP = 3;
const LABEL_WIDTH = 32;
const HOURS = [0, 3, 6, 9, 12, 15, 18, 21];
const HOUR_LABELS = ["12a", "3a", "6a", "9a", "12p", "3p", "6p", "9p"];

export default function SessionHeatmap({ data }: SessionHeatmapProps) {
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);

  const { dates, maxCount, grid } = useMemo(() => {
    const dates: string[] = [];
    const now = new Date();
    for (let i = 13; i >= 0; i--) {
      const d = new Date(now.getTime() - i * 86400000);
      dates.push(d.toISOString().slice(0, 10));
    }

    const grid = new Map<string, number>();
    let maxCount = 1;
    for (const entry of data) {
      const key = `${entry.date}:${entry.hour}`;
      grid.set(key, entry.count);
      if (entry.count > maxCount) maxCount = entry.count;
    }

    return { dates, maxCount, grid };
  }, [data]);

  const width = LABEL_WIDTH + dates.length * (CELL_SIZE + CELL_GAP);
  const height = 20 + HOURS.length * (CELL_SIZE + CELL_GAP);

  function cellColor(count: number): string {
    if (count === 0) return "rgba(255,255,255,0.03)";
    const intensity = Math.min(count / maxCount, 1);
    const alpha = 0.15 + intensity * 0.55;
    return `rgba(20, 184, 166, ${alpha})`;
  }

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">
        Session Activity (14 days)
      </h3>
      <div className="overflow-x-auto">
        <svg width={width} height={height} className="block">
          {HOURS.map((hour, hi) => (
            <text
              key={hour}
              x={LABEL_WIDTH - 4}
              y={20 + hi * (CELL_SIZE + CELL_GAP) + CELL_SIZE / 2 + 4}
              textAnchor="end"
              className="fill-white/20 text-[9px]"
              style={{ fontFamily: "ui-monospace, monospace" }}
            >
              {HOUR_LABELS[hi]}
            </text>
          ))}

          {dates.map((date, di) =>
            HOURS.map((hour, hi) => {
              const count = grid.get(`${date}:${hour}`) ?? 0;
              const x = LABEL_WIDTH + di * (CELL_SIZE + CELL_GAP);
              const y = 20 + hi * (CELL_SIZE + CELL_GAP);
              return (
                <rect
                  key={`${date}-${hour}`}
                  x={x}
                  y={y}
                  width={CELL_SIZE}
                  height={CELL_SIZE}
                  rx={3}
                  fill={cellColor(count)}
                  stroke="rgba(255,255,255,0.04)"
                  strokeWidth={0.5}
                  className="transition-colors"
                  onMouseEnter={(e) => {
                    const dayLabel = new Date(date + "T00:00:00Z").toLocaleDateString("en-US", {
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                    });
                    setTooltip({
                      x: e.clientX,
                      y: e.clientY,
                      text: `${dayLabel} ${HOUR_LABELS[hi]}: ${count} session${count !== 1 ? "s" : ""}`,
                    });
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              );
            }),
          )}

          {dates.map((date, di) => {
            if (di % 2 !== 0) return null;
            const d = new Date(date + "T00:00:00Z");
            const label = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
            return (
              <text
                key={`label-${date}`}
                x={LABEL_WIDTH + di * (CELL_SIZE + CELL_GAP) + CELL_SIZE / 2}
                y={12}
                textAnchor="middle"
                className="fill-white/15 text-[8px]"
                style={{ fontFamily: "ui-monospace, monospace" }}
              >
                {label}
              </text>
            );
          })}
        </svg>
      </div>

      {tooltip && (
        <div
          className="fixed z-[100] rounded px-2 py-1 bg-black/90 text-[10px] text-white/80 pointer-events-none border border-white/[0.08]"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -5`
Expected: No errors

**Step 3: Commit**

```bash
git add website/app/admin/components/projects/SessionHeatmap.tsx
git commit -m "feat(admin): add SessionHeatmap SVG component for 14-day activity grid"
```

---

### Task 5: Create DecisionTimeline component

**Files:**
- Create: `website/app/admin/components/projects/DecisionTimeline.tsx`

**Step 1: Create the vertical timeline component**

Create `website/app/admin/components/projects/DecisionTimeline.tsx`:

```typescript
"use client";

import type { DecisionItem } from "./types";
import { relativeTime } from "./utils";

interface DecisionTimelineProps {
  decisions: DecisionItem[];
  onDecisionClick?: (decisionId: number) => void;
}

const DOMAIN_COLORS: Record<string, string> = {
  general: "bg-blue-400/20 text-blue-400/80 border-blue-400/30",
  architecture: "bg-teal-400/20 text-teal-400/80 border-teal-400/30",
  implementation: "bg-green-400/20 text-green-400/80 border-green-400/30",
  testing: "bg-amber-400/20 text-amber-400/80 border-amber-400/30",
  deployment: "bg-red-400/20 text-red-400/80 border-red-400/30",
  design: "bg-purple-400/20 text-purple-400/80 border-purple-400/30",
};

const DEFAULT_DOMAIN_COLOR = "bg-white/[0.06] text-white/40 border-white/[0.08]";

export default function DecisionTimeline({
  decisions,
  onDecisionClick,
}: DecisionTimelineProps) {
  if (decisions.length === 0) return null;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-4">
        Decision Timeline ({decisions.length})
      </h3>
      <div className="relative">
        <div className="absolute left-[7px] top-2 bottom-2 w-px bg-white/[0.08]" />
        <div className="space-y-3">
          {decisions.map((d) => {
            const domainColor = DOMAIN_COLORS[d.domain] ?? DEFAULT_DOMAIN_COLOR;
            return (
              <button
                key={d.id}
                onClick={() => onDecisionClick?.(d.id)}
                className="relative flex items-start gap-3 pl-5 w-full text-left group hover:bg-white/[0.02] rounded-lg py-1.5 pr-2 transition-colors"
              >
                <span className="absolute left-[4px] top-3 h-[7px] w-[7px] rounded-full bg-white/20 ring-2 ring-[var(--color-canvas)] group-hover:bg-white/40 transition-colors" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${domainColor}`}>
                      {d.domain}
                    </span>
                    <span className="text-[10px] text-white/20 ml-auto flex-shrink-0">
                      {relativeTime(d.createdAt)}
                    </span>
                  </div>
                  <p className="text-xs text-white/55 leading-relaxed line-clamp-2">
                    {d.decision}
                  </p>
                  {d.rationale && (
                    <p className="text-[11px] text-white/25 leading-relaxed mt-0.5 line-clamp-1 italic">
                      {d.rationale}
                    </p>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -5`
Expected: No errors

**Step 3: Commit**

```bash
git add website/app/admin/components/projects/DecisionTimeline.tsx
git commit -m "feat(admin): add DecisionTimeline component with domain-colored vertical timeline"
```

---

### Task 6: Create DetailSidebar (inline sidebar reusing existing Detail* components)

**Files:**
- Create: `website/app/admin/components/projects/DetailSidebar.tsx`

**Step 1: Create the inline sidebar component**

Create `website/app/admin/components/projects/DetailSidebar.tsx`:

```typescript
"use client";

import { useState } from "react";
import type { ProjectOverview } from "./types";
import DetailBlockers from "./DetailBlockers";
import DetailTasks from "./DetailTasks";
import DetailDecisions from "./DetailDecisions";
import DetailActivity from "./DetailActivity";
import DetailFiles from "./DetailFiles";

interface DetailSidebarProps {
  project: ProjectOverview;
  moduleFilter?: string | null;
  onClearFilter?: () => void;
}

type SidebarSection = "tasks" | "decisions" | "activity" | "files";

export default function DetailSidebar({
  project,
  moduleFilter,
  onClearFilter,
}: DetailSidebarProps) {
  const [expandedSection, setExpandedSection] = useState<SidebarSection | null>(null);

  const filteredFileClaims = moduleFilter
    ? project.fileClaims.filter((c) => c.filePath.includes(moduleFilter))
    : project.fileClaims;

  const filteredActivity = moduleFilter
    ? project.activity.filter(
        (a) => a.type !== "session" || a.summary.toLowerCase().includes(moduleFilter.toLowerCase()),
      )
    : project.activity;

  const toggleSection = (section: SidebarSection) => {
    setExpandedSection((prev) => (prev === section ? null : section));
  };

  return (
    <div className="h-full overflow-y-auto space-y-3 pr-1">
      {moduleFilter && (
        <div className="flex items-center gap-2 rounded-lg bg-teal-400/[0.08] border border-teal-400/20 px-3 py-1.5">
          <span className="text-[10px] text-teal-400/70 font-medium truncate">
            Filtered: {moduleFilter}
          </span>
          <button
            onClick={onClearFilter}
            className="ml-auto text-[10px] text-teal-400/50 hover:text-teal-400/80 transition-colors flex-shrink-0"
          >
            Clear
          </button>
        </div>
      )}

      <DetailBlockers blockedItems={project.latestHandoff?.blockedItems ?? []} />

      <SidebarCollapsible
        title="Tasks"
        count={project.tasks.pending + project.tasks.inProgress}
        expanded={expandedSection === "tasks"}
        onToggle={() => toggleSection("tasks")}
      >
        <DetailTasks tasks={project.tasks} />
      </SidebarCollapsible>

      <SidebarCollapsible
        title="Decisions"
        count={project.decisions.length}
        expanded={expandedSection === "decisions"}
        onToggle={() => toggleSection("decisions")}
      >
        <DetailDecisions decisions={project.decisions} />
      </SidebarCollapsible>

      <SidebarCollapsible
        title="Activity"
        count={filteredActivity.length}
        expanded={expandedSection === "activity"}
        onToggle={() => toggleSection("activity")}
      >
        <DetailActivity activity={filteredActivity} />
      </SidebarCollapsible>

      <SidebarCollapsible
        title="Files in Play"
        count={filteredFileClaims.length}
        expanded={expandedSection === "files"}
        onToggle={() => toggleSection("files")}
      >
        <DetailFiles fileClaims={filteredFileClaims} />
      </SidebarCollapsible>

      <div className="h-6" />
    </div>
  );
}

interface SidebarCollapsibleProps {
  title: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

function SidebarCollapsible({
  title,
  count,
  expanded,
  onToggle,
  children,
}: SidebarCollapsibleProps) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.015]">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-white/[0.02] transition-colors rounded-lg"
      >
        <span className="text-xs font-semibold text-white/50 uppercase tracking-wider">
          {title}
        </span>
        <div className="flex items-center gap-2">
          {count > 0 && (
            <span className="text-[10px] text-white/25 tabular-nums">{count}</span>
          )}
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            className={`text-white/20 transition-transform ${expanded ? "rotate-180" : ""}`}
          >
            <path d="M2 3.5l3 3 3-3" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />
          </svg>
        </div>
      </button>
      {expanded && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -5`
Expected: No errors

**Step 3: Commit**

```bash
git add website/app/admin/components/projects/DetailSidebar.tsx
git commit -m "feat(admin): add DetailSidebar with collapsible sections and module filtering"
```

---

### Task 7: Create ProjectDetailView (master-detail container)

**Files:**
- Create: `website/app/admin/components/projects/ProjectDetailView.tsx`

**Step 1: Create the detail view container**

Create `website/app/admin/components/projects/ProjectDetailView.tsx`:

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import type { ProjectOverview, ArchitectureResponse } from "./types";
import { HEALTH_THEME } from "./utils";
import ArchitectureDiagram from "./ArchitectureDiagram";
import SessionHeatmap from "./SessionHeatmap";
import DecisionTimeline from "./DecisionTimeline";
import DetailSidebar from "./DetailSidebar";

interface ProjectDetailViewProps {
  project: ProjectOverview;
  onBack: () => void;
}

export default function ProjectDetailView({
  project,
  onBack,
}: ProjectDetailViewProps) {
  const [archData, setArchData] = useState<ArchitectureResponse | null>(null);
  const [archLoading, setArchLoading] = useState(true);
  const [moduleFilter, setModuleFilter] = useState<string | null>(null);

  const theme = HEALTH_THEME[project.health];

  const fetchArch = useCallback(async () => {
    try {
      const res = await fetch(`/api/admin/projects/${project.id}/architecture`);
      if (res.ok) {
        const data = await res.json();
        setArchData(data);
      }
    } catch {
      // Silent fail
    } finally {
      setArchLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    setArchLoading(true);
    setArchData(null);
    setModuleFilter(null);
    fetchArch();
  }, [fetchArch]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onBack();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onBack]);

  const handleNodeClick = useCallback((modulePath: string) => {
    setModuleFilter((prev) => (prev === modulePath ? null : modulePath));
  }, []);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-white/[0.06] flex-shrink-0">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/70 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M8.5 3L4.5 7l4 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <div className="h-4 w-px bg-white/[0.08]" />
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium ${theme.badge}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${theme.dot}`} />
          {theme.label}
        </span>
        <h1 className="text-sm font-semibold text-white/90">{project.name}</h1>
        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/[0.06] text-white/30">
          {project.category}
        </span>
        <div className="ml-auto flex items-center gap-3">
          <KpiPill label="Sessions (7d)" value={project.sessionCount7d} />
          <KpiPill label="Commits (30d)" value={project.commitCount30d} />
          <KpiPill label="Decisions" value={project.decisionCount30d} />
        </div>
      </div>

      {/* Main + Sidebar */}
      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 min-w-0 overflow-y-auto p-6 space-y-4">
          {/* Architecture Diagram */}
          <div>
            <h3 className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">
              Architecture
            </h3>
            {archLoading ? (
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] h-[300px] flex items-center justify-center">
                <span className="text-xs text-white/20 animate-pulse">Loading architecture...</span>
              </div>
            ) : archData?.mermaidSyntax ? (
              <ArchitectureDiagram
                mermaidSyntax={archData.mermaidSyntax}
                onNodeClick={handleNodeClick}
              />
            ) : (
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] h-[200px] flex items-center justify-center">
                <span className="text-xs text-white/20">No architecture data available yet</span>
              </div>
            )}
          </div>

          {/* Session Heatmap */}
          {archData?.sessionHeatmap && archData.sessionHeatmap.length > 0 && (
            <SessionHeatmap data={archData.sessionHeatmap} />
          )}

          {/* Decision Timeline */}
          {project.decisions.length > 0 && (
            <DecisionTimeline decisions={project.decisions} />
          )}
        </div>

        {/* Sidebar */}
        <div className="w-[340px] flex-shrink-0 border-l border-white/[0.06] p-4">
          <DetailSidebar
            project={project}
            moduleFilter={moduleFilter}
            onClearFilter={() => setModuleFilter(null)}
          />
        </div>
      </div>
    </div>
  );
}

function KpiPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-right">
      <div className="text-xs font-semibold text-white/70 tabular-nums">{value}</div>
      <div className="text-[9px] text-white/25">{label}</div>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -5`
Expected: No errors

**Step 3: Commit**

```bash
git add website/app/admin/components/projects/ProjectDetailView.tsx
git commit -m "feat(admin): add ProjectDetailView master-detail container with arch, heatmap, timeline, sidebar"
```

---

### Task 8: Wire ProjectDetailView into ProjectsView

**Files:**
- Modify: `website/app/admin/components/projects/ProjectsView.tsx`

**Step 1: Add import and viewMode state**

Add import after line 6 (`import ProjectDetailDrawer from "./ProjectDetailDrawer";`):

```typescript
import ProjectDetailView from "./ProjectDetailView";
```

Add state after line 14 (`const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);`):

```typescript
const [viewMode, setViewMode] = useState<"grid" | "detail">("grid");
```

**Step 2: Add handler functions**

Replace lines 36-38 (the `selectedProject` derivation) with:

```typescript
  const selectedProject = selectedProjectId
    ? projects.find((p) => p.id === selectedProjectId) ?? null
    : null;

  const handleSelectProject = (id: string) => {
    setSelectedProjectId(id);
    setViewMode("detail");
  };

  const handleBack = () => {
    setViewMode("grid");
    setSelectedProjectId(null);
  };
```

**Step 3: Add detail view conditional before the grid return**

After the loading block (after the `if (loading) { ... }` block that ends around line 54), add:

```typescript
  // Detail view
  if (viewMode === "detail" && selectedProject) {
    return (
      <div className="h-full">
        <ProjectDetailView project={selectedProject} onBack={handleBack} />
      </div>
    );
  }
```

**Step 4: Update onClickItem and onSelectProject to use handleSelectProject**

In the grid return block, change:
- `onClickItem={setSelectedProjectId}` to `onClickItem={handleSelectProject}`
- `onSelectProject={setSelectedProjectId}` to `onSelectProject={handleSelectProject}`

**Step 5: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -10`
Expected: No errors

**Step 6: Commit**

```bash
git add website/app/admin/components/projects/ProjectsView.tsx
git commit -m "feat(admin): wire ProjectDetailView into ProjectsView with grid/detail toggle"
```

---

### Task 9: Build and smoke test

**Step 1: Run full type check**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --pretty 2>&1 | tail -20`
Expected: No errors in any new files

**Step 2: Run build**

Run: `cd ~/Projects/omega/website && npm run build 2>&1 | tail -30`
Expected: Build succeeds. New API route `api/admin/projects/[id]/architecture` appears in output.

**Step 3: Visual smoke test checklist**

Deploy to Vercel and verify:
1. Admin > Projects shows card grid as before
2. Clicking a project card transitions to detail view
3. Back button and Escape key return to grid
4. Architecture diagram renders with module subgraphs
5. Heatmap shows session activity with hover tooltips
6. Decision timeline is visible with domain badges
7. Sidebar sections expand/collapse
8. Clicking a diagram node shows filter pill in sidebar
9. "Clear" button removes the filter
10. NeedsAttentionBar items also open detail view

**Step 4: Fix any issues and commit**

```bash
git add -u
git commit -m "fix(admin): address build issues in project detail visualization"
```
