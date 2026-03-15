# Coordination Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a live interactive node graph in the admin dashboard that visualizes active agent sessions and their file claims, using React Flow.

**Architecture:** New "Coordination" tab (8th tab) in the existing `/admin` dashboard. An API endpoint reads `coord_sessions` and `coord_file_claims` from the local OMEGA SQLite database (`~/.omega/omega.db`). A polling hook fetches every 5 seconds and transforms the data into React Flow nodes and edges. Custom node components render agent sessions (color-coded by heartbeat freshness) and file claims (pill shapes).

**Tech Stack:** @xyflow/react (MIT, ~150KB), Next.js 15 App Router, TypeScript, Tailwind CSS 4

**Design doc:** `docs/plans/2026-02-22-coordination-dashboard-design.md`

---

### Task 1: Install @xyflow/react

**Files:**
- Modify: `website/package.json`

**Step 1: Install the dependency**

Run: `cd ~/Projects/omega/website && npm install @xyflow/react`
Expected: Package added to dependencies in package.json

**Step 2: Verify install**

Run: `cd ~/Projects/omega/website && node -e "require('@xyflow/react')"`
Expected: No errors

**Step 3: Commit**

```bash
cd ~/Projects/omega/website
git add package.json package-lock.json
git commit -m "chore(website): add @xyflow/react for coordination dashboard"
```

---

### Task 2: Add "coordination" to Tab type and types

**Files:**
- Modify: `website/app/admin/lib/types.ts:3` (Tab union)

**Step 1: Verify current build passes**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | tail -5`
Expected: No errors (or existing unrelated ones)

**Step 2: Add "coordination" to Tab union type**

In `website/app/admin/lib/types.ts`, change line 3 from:

```typescript
export type Tab = "dashboard" | "feed" | "actions" | "insights" | "docs" | "jobs" | "settings";
```

to:

```typescript
export type Tab = "dashboard" | "feed" | "actions" | "insights" | "docs" | "jobs" | "settings" | "coordination";
```

**Step 3: Add CoordinationData interface**

Append to the same file:

```typescript
// -- Coordination Dashboard --------------------------------------------------

export interface CoordinationSession {
  session_id: string;
  project: string;
  status: string;
  task: string;
  last_heartbeat: string;
  started_at: string;
}

export interface CoordinationFileClaim {
  file_path: string;
  session_id: string;
  task: string;
  claimed_at: string;
}

export interface CoordinationData {
  sessions: CoordinationSession[];
  file_claims: CoordinationFileClaim[];
}
```

**Step 4: Verify build still passes**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | tail -5`
Expected: No errors. The new "coordination" variant may cause exhaustiveness warnings in existing switch/if chains; those will be fixed in Task 8 when we wire the tab in.

**Step 5: Commit**

```bash
cd ~/Projects/omega/website
git add website/app/admin/lib/types.ts
git commit -m "feat(admin): add coordination tab type and data interfaces"
```

---

### Task 3: Create the API endpoint

**Files:**
- Create: `website/app/api/admin/coordination/route.ts`

**Step 1: Create the API route**

Create `website/app/api/admin/coordination/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { Database } from "better-sqlite3";
import path from "path";
import os from "os";

export const dynamic = "force-dynamic";

// In-memory cache for when DB is locked
let cachedResponse: { data: unknown; ts: number } | null = null;
const CACHE_TTL_MS = 5_000;

function getDb(): Database {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const BetterSqlite3 = require("better-sqlite3");
  const dbPath = path.join(os.homedir(), ".omega", "omega.db");
  return new BetterSqlite3(dbPath, { readonly: true, timeout: 5000 });
}

export async function GET() {
  try {
    const db = getDb();

    const sessions = db
      .prepare(
        `SELECT session_id, project, status, task, last_heartbeat, started_at
         FROM coord_sessions
         ORDER BY last_heartbeat DESC`
      )
      .all();

    const fileClaims = db
      .prepare(
        `SELECT file_path, session_id, task, claimed_at
         FROM coord_file_claims
         ORDER BY claimed_at DESC`
      )
      .all();

    db.close();

    const data = { sessions, file_claims: fileClaims };
    cachedResponse = { data, ts: Date.now() };

    return NextResponse.json(data, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (err: unknown) {
    // If DB is locked or unavailable, return cached response
    if (cachedResponse && Date.now() - cachedResponse.ts < CACHE_TTL_MS) {
      return NextResponse.json(cachedResponse.data, {
        headers: { "Cache-Control": "no-store" },
      });
    }

    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: message, sessions: [], file_claims: [] },
      { status: 500 }
    );
  }
}
```

**Step 2: Check if better-sqlite3 is available**

The website uses Next.js server-side routes. `better-sqlite3` may not be installed. Check:

Run: `cd ~/Projects/omega/website && node -e "require('better-sqlite3')" 2>&1`

If not available, install it:

Run: `cd ~/Projects/omega/website && npm install better-sqlite3 && npm install -D @types/better-sqlite3`

**Alternative approach (if better-sqlite3 is problematic with Next.js bundling):**

Use Node.js built-in `child_process` to call `sqlite3` CLI, or use the `sql.js` (WASM) package. However, `better-sqlite3` is the standard approach for Next.js API routes reading local SQLite.

If `better-sqlite3` causes build issues with Next.js (common with native addons), add to `next.config.ts`:

```typescript
// In the Next.js config
serverExternalPackages: ["better-sqlite3"],
```

**Step 3: Verify the endpoint compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | tail -10`
Expected: No new type errors

**Step 4: Test the endpoint locally (curl after build)**

Since we deploy to Vercel and don't use localhost, verify via build:

Run: `cd ~/Projects/omega/website && npm run build 2>&1 | tail -20`
Expected: Build succeeds, `/api/admin/coordination` route compiled

**Step 5: Commit**

```bash
cd ~/Projects/omega/website
git add website/app/api/admin/coordination/route.ts
# If better-sqlite3 was installed:
git add package.json package-lock.json
# If next.config was modified:
git add next.config.ts
git commit -m "feat(admin): add coordination API endpoint reading coord_sessions/file_claims"
```

---

### Task 4: Create the useCoordinationData polling hook

**Files:**
- Create: `website/app/admin/coordination/useCoordinationData.ts`

**Step 1: Create the directory and hook**

Create `website/app/admin/coordination/useCoordinationData.ts`:

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import type { CoordinationSession, CoordinationFileClaim } from "../lib/types";

interface UseCoordinationDataReturn {
  sessions: CoordinationSession[];
  fileClaims: CoordinationFileClaim[];
  isLoading: boolean;
  error: string | null;
}

export function useCoordinationData(pollInterval = 5000): UseCoordinationDataReturn {
  const [sessions, setSessions] = useState<CoordinationSession[]>([]);
  const [fileClaims, setFileClaims] = useState<CoordinationFileClaim[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/coordination");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessions(data.sessions ?? []);
      setFileClaims(data.file_claims ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fetch failed");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, pollInterval);
    return () => clearInterval(id);
  }, [fetchData, pollInterval]);

  return { sessions, fileClaims, isLoading, error };
}
```

**Step 2: Type-check**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | tail -5`
Expected: No errors

**Step 3: Commit**

```bash
cd ~/Projects/omega/website
git add website/app/admin/coordination/useCoordinationData.ts
git commit -m "feat(admin): add useCoordinationData polling hook (5s interval)"
```

---

### Task 5: Create custom node components (AgentNode, FileNode)

**Files:**
- Create: `website/app/admin/coordination/nodes/AgentNode.tsx`
- Create: `website/app/admin/coordination/nodes/FileNode.tsx`

**Step 1: Create the nodes directory**

Run: `mkdir -p ~/Projects/omega/website/app/admin/coordination/nodes`

**Step 2: Create AgentNode**

Create `website/app/admin/coordination/nodes/AgentNode.tsx`:

```tsx
"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface AgentNodeData {
  sessionId: string;
  project: string;
  status: string;
  task: string;
  lastHeartbeat: string;
  startedAt: string;
  freshness: "active" | "idle" | "stale";
  [key: string]: unknown;
}

const STATUS_COLORS = {
  active: "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]",
  idle: "bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.4)]",
  stale: "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.4)]",
} as const;

function AgentNodeComponent({ data }: NodeProps) {
  const d = data as unknown as AgentNodeData;
  const opacity = d.freshness === "stale" ? "opacity-50" : "opacity-100";

  return (
    <div
      className={`rounded-xl border border-edge bg-surface-elevated px-4 py-3 min-w-[220px] max-w-[280px] ${opacity} transition-opacity`}
    >
      <Handle type="source" position={Position.Right} className="!bg-gold !w-2 !h-2" />

      <div className="flex items-center gap-2 mb-2">
        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${STATUS_COLORS[d.freshness]}`} />
        <span className="text-[12px] font-mono text-ink-secondary truncate">
          {d.sessionId.slice(0, 8)}
        </span>
      </div>

      <div className="text-[13px] font-medium text-ink truncate">{d.project || "unknown"}</div>

      {d.task && (
        <div className="text-[11px] text-ink-tertiary mt-1 truncate" title={d.task}>
          {d.task}
        </div>
      )}
    </div>
  );
}

export default memo(AgentNodeComponent);
```

**Step 3: Create FileNode**

Create `website/app/admin/coordination/nodes/FileNode.tsx`:

```tsx
"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface FileNodeData {
  filePath: string;
  sessionId: string;
  claimedAt: string;
  [key: string]: unknown;
}

function truncatePath(p: string): string {
  const parts = p.split("/");
  if (parts.length <= 3) return p;
  return `.../${parts.slice(-2).join("/")}`;
}

function FileNodeComponent({ data }: NodeProps) {
  const d = data as unknown as FileNodeData;

  return (
    <div className="rounded-full border border-edge bg-surface px-3 py-1.5 max-w-[200px]">
      <Handle type="target" position={Position.Left} className="!bg-gold/60 !w-1.5 !h-1.5" />
      <span className="text-[11px] font-mono text-ink-tertiary truncate block" title={d.filePath}>
        {truncatePath(d.filePath)}
      </span>
    </div>
  );
}

export default memo(FileNodeComponent);
```

**Step 4: Type-check**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | tail -5`
Expected: No errors

**Step 5: Commit**

```bash
cd ~/Projects/omega/website
git add website/app/admin/coordination/nodes/AgentNode.tsx website/app/admin/coordination/nodes/FileNode.tsx
git commit -m "feat(admin): add AgentNode and FileNode custom React Flow components"
```

---

### Task 6: Create CoordinationFlow graph wrapper

**Files:**
- Create: `website/app/admin/coordination/CoordinationFlow.tsx`

**Step 1: Create the graph component**

Create `website/app/admin/coordination/CoordinationFlow.tsx`:

```tsx
"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  type Node,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import AgentNode, { type AgentNodeData } from "./nodes/AgentNode";
import FileNode from "./nodes/FileNode";
import type { CoordinationSession, CoordinationFileClaim } from "../lib/types";

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  file: FileNode,
};

function getAgentFreshness(heartbeat: string): "active" | "idle" | "stale" {
  const diff = Date.now() - new Date(heartbeat).getTime();
  const minutes = diff / 60_000;
  if (minutes < 2) return "active";
  if (minutes < 10) return "idle";
  return "stale";
}

interface CoordinationFlowProps {
  sessions: CoordinationSession[];
  fileClaims: CoordinationFileClaim[];
  onNodeClick?: (type: "agent" | "file", id: string) => void;
}

export default function CoordinationFlow({
  sessions,
  fileClaims,
  onNodeClick,
}: CoordinationFlowProps) {
  const { nodes, edges } = useMemo(() => {
    const agentNodes: Node[] = sessions.map((s, i) => ({
      id: `agent-${s.session_id}`,
      type: "agent",
      position: { x: 50, y: i * 120 + 50 },
      data: {
        sessionId: s.session_id,
        project: s.project,
        status: s.status,
        task: s.task,
        lastHeartbeat: s.last_heartbeat,
        startedAt: s.started_at,
        freshness: getAgentFreshness(s.last_heartbeat),
      } satisfies AgentNodeData,
    }));

    const fileNodes: Node[] = fileClaims.map((f, i) => ({
      id: `file-${f.session_id}-${f.file_path}`,
      type: "file",
      position: { x: 450, y: i * 60 + 50 },
      data: {
        filePath: f.file_path,
        sessionId: f.session_id,
        claimedAt: f.claimed_at,
      },
    }));

    const edgeList: Edge[] = fileClaims.map((f, i) => ({
      id: `edge-${i}`,
      source: `agent-${f.session_id}`,
      target: `file-${f.session_id}-${f.file_path}`,
      animated: true,
      style: { stroke: "rgba(212, 168, 67, 0.4)", strokeWidth: 1.5 },
    }));

    return { nodes: [...agentNodes, ...fileNodes], edges: edgeList };
  }, [sessions, fileClaims]);

  return (
    <div className="w-full h-[600px] rounded-xl border border-edge bg-canvas overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_event, node) => {
          if (!onNodeClick) return;
          const type = node.type === "agent" ? "agent" : "file";
          onNodeClick(type, node.id);
        }}
        fitView
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: "smoothstep" }}
      >
        <Background gap={20} size={1} color="rgba(255,255,255,0.03)" />
      </ReactFlow>
    </div>
  );
}
```

**Step 2: Type-check**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | tail -5`
Expected: No errors

**Step 3: Commit**

```bash
cd ~/Projects/omega/website
git add website/app/admin/coordination/CoordinationFlow.tsx
git commit -m "feat(admin): add CoordinationFlow graph wrapper with auto-layout"
```

---

### Task 7: Create CoordinationTab container

**Files:**
- Create: `website/app/admin/coordination/CoordinationTab.tsx`

**Step 1: Create the tab container**

Create `website/app/admin/coordination/CoordinationTab.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useCoordinationData } from "./useCoordinationData";
import CoordinationFlow from "./CoordinationFlow";

export default function CoordinationTab() {
  const { sessions, fileClaims, isLoading, error } = useCoordinationData();
  const [selectedNode, setSelectedNode] = useState<{
    type: "agent" | "file";
    id: string;
  } | null>(null);

  if (isLoading) {
    return (
      <div className="px-5 pt-6 space-y-4">
        <div className="h-8 w-48 rounded-lg skeleton" />
        <div className="h-[600px] w-full rounded-xl skeleton" />
      </div>
    );
  }

  const activeSessions = sessions.filter((s) => {
    const diff = Date.now() - new Date(s.last_heartbeat).getTime();
    return diff < 10 * 60_000; // <10 min
  });

  const selectedSession =
    selectedNode?.type === "agent"
      ? sessions.find((s) => `agent-${s.session_id}` === selectedNode.id)
      : null;

  const selectedClaim =
    selectedNode?.type === "file"
      ? fileClaims.find(
          (f) => `file-${f.session_id}-${f.file_path}` === selectedNode.id
        )
      : null;

  return (
    <div className="px-5 pt-6 pb-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-lg font-semibold text-ink">Coordination</h1>
          <p className="text-[13px] text-ink-tertiary mt-0.5">
            {activeSessions.length} active session{activeSessions.length !== 1 ? "s" : ""}
            {fileClaims.length > 0 && `, ${fileClaims.length} file claim${fileClaims.length !== 1 ? "s" : ""}`}
          </p>
        </div>
        {error && (
          <span className="text-[12px] text-red-400 bg-red-500/[0.08] px-2.5 py-1 rounded-lg">
            {error}
          </span>
        )}
      </div>

      {/* Empty state */}
      {sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-[400px] rounded-xl border border-edge bg-surface/50">
          <svg
            className="w-12 h-12 text-ink-faint mb-3"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125"
            />
          </svg>
          <p className="text-[14px] text-ink-tertiary">No active agent sessions</p>
          <p className="text-[12px] text-ink-faint mt-1">
            Sessions appear here when agents register via OMEGA coordination
          </p>
        </div>
      ) : (
        /* Graph */
        <CoordinationFlow
          sessions={sessions}
          fileClaims={fileClaims}
          onNodeClick={(type, id) => setSelectedNode({ type, id })}
        />
      )}

      {/* Detail panel */}
      {selectedSession && (
        <div className="mt-4 p-4 rounded-xl border border-edge bg-surface-elevated card-enter">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[12px] font-mono text-ink-secondary">
              {selectedSession.session_id}
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-gold/[0.08] text-gold font-medium">
              {selectedSession.status}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 text-[12px]">
            <div>
              <span className="text-ink-faint">Project</span>
              <p className="text-ink-secondary">{selectedSession.project || "N/A"}</p>
            </div>
            <div>
              <span className="text-ink-faint">Started</span>
              <p className="text-ink-secondary">{new Date(selectedSession.started_at).toLocaleString()}</p>
            </div>
            <div>
              <span className="text-ink-faint">Last heartbeat</span>
              <p className="text-ink-secondary">{new Date(selectedSession.last_heartbeat).toLocaleString()}</p>
            </div>
            <div>
              <span className="text-ink-faint">Task</span>
              <p className="text-ink-secondary truncate" title={selectedSession.task}>
                {selectedSession.task || "N/A"}
              </p>
            </div>
          </div>
        </div>
      )}

      {selectedClaim && (
        <div className="mt-4 p-4 rounded-xl border border-edge bg-surface-elevated card-enter">
          <div className="text-[12px] font-mono text-ink-secondary mb-2">
            {selectedClaim.file_path}
          </div>
          <div className="grid grid-cols-2 gap-3 text-[12px]">
            <div>
              <span className="text-ink-faint">Claimed by</span>
              <p className="text-ink-secondary">{selectedClaim.session_id.slice(0, 8)}</p>
            </div>
            <div>
              <span className="text-ink-faint">Claimed at</span>
              <p className="text-ink-secondary">{new Date(selectedClaim.claimed_at).toLocaleString()}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Type-check**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | tail -5`
Expected: No errors

**Step 3: Commit**

```bash
cd ~/Projects/omega/website
git add website/app/admin/coordination/CoordinationTab.tsx
git commit -m "feat(admin): add CoordinationTab container with detail panel and empty state"
```

---

### Task 8: Wire into admin page, sidebar, and mobile nav

**Files:**
- Modify: `website/app/admin/page.tsx:12-32` (add lazy import, resolveTab, render branch, mobile sidebar list)
- Modify: `website/app/admin/components/shell/Sidebar.tsx:67-87` (add coordination to secondaryItems)
- Modify: `website/app/admin/components/shell/MobileNav.tsx` (no change needed, coordination is desktop-only admin tab)

**Step 1: Add lazy import in page.tsx**

In `website/app/admin/page.tsx`, after the `Settings` dynamic import (line 31), add:

```typescript
const Coordination = dynamic(() => import("./coordination/CoordinationTab"), {
  loading: () => <TabSkeleton />,
});
```

**Step 2: Add "coordination" to resolveTab**

In `website/app/admin/page.tsx`, update the `resolveTab` function. Change the includes array on line 55 from:

```typescript
if (["dashboard", "feed", "actions", "insights", "docs", "jobs", "settings"].includes(raw)) {
```

to:

```typescript
if (["dashboard", "feed", "actions", "insights", "docs", "jobs", "settings", "coordination"].includes(raw)) {
```

**Step 3: Add render branch**

In `website/app/admin/page.tsx`, after the Settings render line (line 391):

```tsx
{active === "settings" && <Settings />}
```

Add:

```tsx
{active === "coordination" && <Coordination />}
```

**Step 4: Update max-width for coordination tab**

In `website/app/admin/page.tsx`, update line 370. Change:

```tsx
<div className={`${active === "dashboard" || active === "docs" ? "max-w-5xl" : "max-w-3xl"} mx-auto relative`}>
```

to:

```tsx
<div className={`${active === "dashboard" || active === "docs" || active === "coordination" ? "max-w-5xl" : "max-w-3xl"} mx-auto relative`}>
```

**Step 5: Add to mobile sidebar list**

In `website/app/admin/page.tsx`, update the mobile sidebar tab list (line 297). Change:

```tsx
{(["dashboard", "feed", "actions", "insights", "docs", "jobs", "settings"] as Tab[]).map((id) => {
  const labels: Record<Tab, string> = { dashboard: "Dashboard", feed: "Feed", actions: "Actions", insights: "Insights", docs: "Docs", jobs: "Jobs", settings: "Settings" };
```

to:

```tsx
{(["dashboard", "feed", "actions", "insights", "docs", "jobs", "coordination", "settings"] as Tab[]).map((id) => {
  const labels: Record<Tab, string> = { dashboard: "Dashboard", feed: "Feed", actions: "Actions", insights: "Insights", docs: "Docs", jobs: "Jobs", coordination: "Coordination", settings: "Settings" };
```

**Step 6: Add to Sidebar secondaryItems**

In `website/app/admin/components/shell/Sidebar.tsx`, add a coordination item to `secondaryItems` array (insert before the "settings" entry at line 77):

```tsx
{
  id: "coordination",
  label: "Coordination",
  icon: (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
    </svg>
  ),
},
```

This uses the Heroicons "arrows-right-left" icon which visually represents coordination/data flow.

**Step 7: Type-check and build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | tail -10`
Expected: No errors

Run: `cd ~/Projects/omega/website && npm run build 2>&1 | tail -20`
Expected: Build succeeds with all routes compiled

**Step 8: Commit**

```bash
cd ~/Projects/omega/website
git add website/app/admin/page.tsx website/app/admin/components/shell/Sidebar.tsx
git commit -m "feat(admin): wire coordination tab into admin dashboard and sidebar nav"
```

---

### Task 9: Build verification and deploy

**Step 1: Full build**

Run: `cd ~/Projects/omega/website && npm run build 2>&1 | tail -30`
Expected: Build succeeds, all routes compile without errors

**Step 2: Lint**

Run: `cd ~/Projects/omega/website && npm run lint 2>&1 | tail -10`
Expected: No lint errors (fix any that appear)

**Step 3: Commit any final fixes**

If there are lint or build fixes needed:

```bash
cd ~/Projects/omega/website
git add <fixed-files>
git commit -m "fix(admin): resolve lint/build issues in coordination dashboard"
```

**Step 4: Deploy to Vercel**

Run: `cd ~/Projects/omega/website && npx vercel --prod 2>&1 | tail -10`
Expected: Deployment succeeds

**Step 5: Verify live**

Navigate to `https://omegamax.co/admin?tab=coordination` in the browser. Expected:
- Coordination tab loads
- Shows either the empty state ("No active agent sessions") or the node graph with active sessions
- If sessions exist, nodes are color-coded by heartbeat freshness
- Clicking a node shows the detail panel

---

## Notes

- **No dagre needed initially**: The simple column positioning (agents at x=50, files at x=450) is sufficient for the typical 2-5 concurrent sessions. dagre can be added later if node counts grow.
- **MobileNav not modified**: The bottom mobile nav only shows 5 primary tabs. Coordination is an admin-only desktop feature, accessible via the sidebar and mobile sidebar overlay.
- **better-sqlite3 on Vercel**: Vercel serverless functions support native Node.js addons. Add `better-sqlite3` to `serverExternalPackages` in next.config to prevent bundling issues. Note: the DB file (`~/.omega/omega.db`) must exist on the Vercel server. Since this is Jason's admin tool running against his local machine, this endpoint will only work when the site is accessed from a deployment that has access to the local filesystem (or when run locally). For Vercel production, this tab will show the error state gracefully.
