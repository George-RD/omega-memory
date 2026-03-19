# Admin xyOps-Inspired Patterns Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 5 features to the OMEGA admin dashboard inspired by xyOps: contextual alert bundling, one-click alert actions, hook pipeline visualization, incident timeline, and persistent alert history.

**Architecture:** All features slot into existing tabs (Dashboard, Diagnostic, Feed). New API routes under `/api/admin/` serve data. Alert context is lazy-loaded on expand (approach B). No WebSocket migration. Alert history uses a new Supabase table. Hook pipeline uses a lightweight SVG graph (no ReactFlow).

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS, Supabase, SVG for pipeline graph

---

## Task 1: Alert Context Types and API Route

Add the types and API endpoint for lazy-loading alert context.

**Files:**
- Modify: `website/app/admin/lib/types.ts` (add types at end)
- Create: `website/app/api/admin/alert-context/route.ts`

**Step 1: Add alert context types to types.ts**

Add these types at the end of `website/app/admin/lib/types.ts`:

```typescript
// ─── Alert Context (xyOps-inspired) ────────────────────────

export type AlertType = "failing_job" | "failed_post" | "cloud_sync_gap" | "engagement_declining" | "memory_spike" | "coordination_conflict" | "overdue_job" | "cloud_sync_empty";

export interface AlertContextBase {
  type: AlertType;
  title: string;
  severity: "critical" | "warning" | "info";
  timestamp: string;
}

export interface FailingJobContext extends AlertContextBase {
  type: "failing_job";
  detail: {
    jobName: string;
    jobLabel: string;
    lastError: string | null;
    recentRuns: { status: string; startedAt: string; durationMs: number | null; error: string | null }[];
    scheduleType: string;
    intervalSeconds?: number;
  };
}

export interface FailedPostContext extends AlertContextBase {
  type: "failed_post";
  detail: {
    failedCount: number;
    recentFailed: { content: string; reason: string | null; createdAt: string; account: string }[];
    recentSuccessful: { content: string; publishedAt: string; account: string }[];
  };
}

export interface CloudSyncGapContext extends AlertContextBase {
  type: "cloud_sync_gap";
  detail: {
    localCount: number;
    cloudCount: number;
    gapPct: number;
    lastSyncAt: string | null;
    unsyncedCount: number;
  };
}

export interface EngagementDecliningContext extends AlertContextBase {
  type: "engagement_declining";
  detail: {
    currentRate: number;
    previousRate: number;
    recentPosts: { content: string; engagementRate: number; publishedAt: string }[];
  };
}

export interface MemorySpikeContext extends AlertContextBase {
  type: "memory_spike";
  detail: {
    recentMemories: { content: string; memoryType: string; agentId: string | null; createdAt: string }[];
    totalInLastHour: number;
  };
}

export interface CoordinationConflictContext extends AlertContextBase {
  type: "coordination_conflict";
  detail: {
    conflicts: { filePath: string; sessions: { sessionId: string; project: string; intent: string | null }[] }[];
  };
}

export type AlertContext = FailingJobContext | FailedPostContext | CloudSyncGapContext | EngagementDecliningContext | MemorySpikeContext | CoordinationConflictContext | AlertContextBase;

// ─── Alert Actions ──────────────────────────────────────────

export type AlertActionType = "retry_job" | "force_sync" | "dismiss" | "snooze" | "navigate" | "requeue_post";

export interface AlertAction {
  type: AlertActionType;
  label: string;
  /** For navigate: tab to switch to */
  tab?: Tab;
  /** For retry_job: schedule label */
  jobLabel?: string;
  /** Severity styling */
  variant?: "primary" | "secondary" | "danger";
}
```

**Step 2: Create alert-context API route**

Create `website/app/api/admin/alert-context/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer, requireAuth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

/**
 * GET /api/admin/alert-context?type=<alertType>&param=<optional>
 *
 * Lazy-loads contextual data for a specific alert type.
 * Called on-demand when user expands an alert card.
 */
export async function GET(request: NextRequest) {
  const auth = await requireAuth();
  if (!auth) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const params = request.nextUrl.searchParams;
  const type = params.get("type");

  if (!type) {
    return NextResponse.json({ error: "type parameter required" }, { status: 400 });
  }

  const db = supabaseServer();

  try {
    switch (type) {
      case "failing_job": {
        const jobLabel = params.get("job");
        if (!jobLabel) return NextResponse.json({ error: "job parameter required" }, { status: 400 });

        const { data: runs } = await db
          .from("schedule_runs")
          .select("status, started_at, duration_ms, error_message")
          .eq("schedule_label", jobLabel)
          .order("started_at", { ascending: false })
          .limit(3);

        const { data: schedule } = await db
          .from("schedules")
          .select("label, schedule_type, interval_seconds")
          .eq("label", jobLabel)
          .single();

        return NextResponse.json({
          type: "failing_job",
          title: `Job failing: ${jobLabel}`,
          severity: "critical",
          timestamp: new Date().toISOString(),
          detail: {
            jobName: jobLabel,
            jobLabel,
            lastError: runs?.[0]?.error_message ?? null,
            recentRuns: (runs ?? []).map(r => ({
              status: r.status,
              startedAt: r.started_at,
              durationMs: r.duration_ms,
              error: r.error_message ?? null,
            })),
            scheduleType: schedule?.schedule_type ?? "unknown",
            intervalSeconds: schedule?.interval_seconds,
          },
        });
      }

      case "failed_post": {
        const { data: failed } = await db
          .from("tweet_queue")
          .select("content, rejection_reason, created_at, account")
          .eq("status", "failed")
          .order("created_at", { ascending: false })
          .limit(3);

        const { data: successful } = await db
          .from("tweet_queue")
          .select("content, published_at, account")
          .eq("status", "published")
          .order("published_at", { ascending: false })
          .limit(3);

        return NextResponse.json({
          type: "failed_post",
          title: `${(failed ?? []).length} post(s) failed to publish`,
          severity: "critical",
          timestamp: new Date().toISOString(),
          detail: {
            failedCount: (failed ?? []).length,
            recentFailed: (failed ?? []).map(f => ({
              content: f.content?.slice(0, 120) ?? "",
              reason: f.rejection_reason ?? null,
              createdAt: f.created_at,
              account: f.account ?? "unknown",
            })),
            recentSuccessful: (successful ?? []).map(s => ({
              content: s.content?.slice(0, 120) ?? "",
              publishedAt: s.published_at,
              account: s.account ?? "unknown",
            })),
          },
        });
      }

      case "cloud_sync_gap": {
        const { count: localCount } = await db
          .from("memories")
          .select("id", { count: "exact", head: true })
          .eq("user_id", auth.user.id);

        const { count: cloudCount } = await db
          .from("memories")
          .select("id", { count: "exact", head: true })
          .eq("user_id", auth.user.id)
          .not("cloud_synced_at", "is", null);

        const { data: lastSync } = await db
          .from("memories")
          .select("cloud_synced_at")
          .eq("user_id", auth.user.id)
          .not("cloud_synced_at", "is", null)
          .order("cloud_synced_at", { ascending: false })
          .limit(1);

        const local = localCount ?? 0;
        const cloud = cloudCount ?? 0;
        const gapPct = local > 0 ? ((local - cloud) / local) * 100 : 0;

        return NextResponse.json({
          type: "cloud_sync_gap",
          title: `Cloud sync gap: ${gapPct.toFixed(0)}%`,
          severity: gapPct > 25 ? "critical" : "warning",
          timestamp: new Date().toISOString(),
          detail: {
            localCount: local,
            cloudCount: cloud,
            gapPct,
            lastSyncAt: lastSync?.[0]?.cloud_synced_at ?? null,
            unsyncedCount: local - cloud,
          },
        });
      }

      case "engagement_declining": {
        const { data: posts } = await db
          .from("tweet_performance")
          .select("content, engagement_rate, published_at")
          .order("published_at", { ascending: false })
          .limit(5);

        const recent = posts?.slice(0, 3) ?? [];
        const older = posts?.slice(3) ?? [];
        const currentRate = recent.length > 0 ? recent.reduce((s, p) => s + (p.engagement_rate ?? 0), 0) / recent.length : 0;
        const previousRate = older.length > 0 ? older.reduce((s, p) => s + (p.engagement_rate ?? 0), 0) / older.length : 0;

        return NextResponse.json({
          type: "engagement_declining",
          title: `Engagement declining: ${currentRate.toFixed(1)}%`,
          severity: "warning",
          timestamp: new Date().toISOString(),
          detail: {
            currentRate,
            previousRate,
            recentPosts: (posts ?? []).map(p => ({
              content: p.content?.slice(0, 120) ?? "",
              engagementRate: p.engagement_rate ?? 0,
              publishedAt: p.published_at,
            })),
          },
        });
      }

      case "memory_spike": {
        const cutoff = new Date(Date.now() - 60 * 60_000).toISOString();
        const { data: recent, count } = await db
          .from("memories")
          .select("content, memory_type, metadata, created_at", { count: "exact" })
          .eq("user_id", auth.user.id)
          .gte("created_at", cutoff)
          .order("created_at", { ascending: false })
          .limit(5);

        return NextResponse.json({
          type: "memory_spike",
          title: `Memory spike: ${count ?? 0} in last hour`,
          severity: "info",
          timestamp: new Date().toISOString(),
          detail: {
            recentMemories: (recent ?? []).map(m => ({
              content: (m.content ?? "").slice(0, 100),
              memoryType: m.memory_type ?? "unknown",
              agentId: (m.metadata as Record<string, unknown>)?.session_id as string ?? null,
              createdAt: m.created_at,
            })),
            totalInLastHour: count ?? 0,
          },
        });
      }

      case "coordination_conflict": {
        const activeCutoff = new Date(Date.now() - 2 * 60_000).toISOString();

        const { data: sessions } = await db
          .from("coord_sessions")
          .select("session_id, project, task")
          .neq("status", "ended")
          .gte("last_heartbeat", activeCutoff);

        const { data: claims } = await db
          .from("coord_file_claims")
          .select("file_path, session_id");

        const activeIds = new Set((sessions ?? []).map(s => s.session_id));
        const sessionMap = new Map((sessions ?? []).map(s => [s.session_id, s]));

        const fileSessions = new Map<string, string[]>();
        for (const c of claims ?? []) {
          if (activeIds.has(c.session_id)) {
            const arr = fileSessions.get(c.file_path) ?? [];
            arr.push(c.session_id);
            fileSessions.set(c.file_path, arr);
          }
        }

        const conflicts = [...fileSessions.entries()]
          .filter(([, sids]) => sids.length > 1)
          .map(([path, sids]) => ({
            filePath: path,
            sessions: sids.map(sid => {
              const s = sessionMap.get(sid);
              return {
                sessionId: sid,
                project: s?.project ?? "unknown",
                intent: s?.task ?? null,
              };
            }),
          }));

        return NextResponse.json({
          type: "coordination_conflict",
          title: `${conflicts.length} file conflict(s)`,
          severity: conflicts.length > 0 ? "critical" : "info",
          timestamp: new Date().toISOString(),
          detail: { conflicts },
        });
      }

      default:
        return NextResponse.json({ error: `Unknown alert type: ${type}` }, { status: 400 });
    }
  } catch (err: unknown) {
    console.error("[alert-context]", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
```

**Step 3: Verify the types compile**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit --noUnusedLocals false 2>&1 | head -20`
Expected: No errors related to the new types

**Step 4: Commit**

```bash
cd ~/Projects/omega/website
git add app/admin/lib/types.ts app/api/admin/alert-context/route.ts
git commit -m "feat(admin): add alert context types and API route"
```

---

## Task 2: Expandable Problems Panel with Context Cards

Replace the flat `ProblemsPanel` in Dashboard.tsx with expandable alert cards that lazy-load context.

**Files:**
- Create: `website/app/admin/components/dashboard/AlertCard.tsx`
- Modify: `website/app/admin/components/Dashboard.tsx` (lines 72-75, 301-331, 426-459, 786-787)

**Step 1: Create AlertCard component**

Create `website/app/admin/components/dashboard/AlertCard.tsx`:

```typescript
"use client";

import { useState, useCallback } from "react";
import type { AlertContext, AlertType, AlertAction, Tab } from "../../lib/types";

// ─── Map problem text to alert type + params ────────────────

interface AlertMapping {
  type: AlertType;
  params?: Record<string, string>;
  actions: AlertAction[];
}

export function mapProblemToAlert(text: string): AlertMapping | null {
  if (text.match(/job[s]? failing/i)) {
    // Extract job names from "2 jobs failing: job1, job2"
    const match = text.match(/failing:\s*(.+)/);
    const jobName = match?.[1]?.split(",")[0]?.trim() ?? "";
    return {
      type: "failing_job",
      params: { job: jobName },
      actions: [
        { type: "retry_job", label: "Retry", jobLabel: jobName, variant: "primary" },
        { type: "navigate", label: "View Jobs", tab: "jobs" as Tab, variant: "secondary" },
      ],
    };
  }
  if (text.match(/post[s]? failed/i)) {
    return {
      type: "failed_post",
      actions: [
        { type: "requeue_post", label: "Re-queue", variant: "primary" },
        { type: "navigate", label: "View Actions", tab: "actions" as Tab, variant: "secondary" },
      ],
    };
  }
  if (text.match(/cloud sync gap/i) || text.match(/cloud sync has no data/i)) {
    return {
      type: "cloud_sync_gap",
      actions: [
        { type: "force_sync", label: "Force Sync", variant: "primary" },
        { type: "dismiss", label: "Dismiss", variant: "secondary" },
      ],
    };
  }
  if (text.match(/engagement.*declining/i)) {
    return {
      type: "engagement_declining",
      actions: [
        { type: "navigate", label: "View Insights", tab: "insights" as Tab, variant: "primary" },
        { type: "dismiss", label: "Dismiss", variant: "secondary" },
      ],
    };
  }
  if (text.match(/overdue/i)) {
    return {
      type: "overdue_job",
      actions: [
        { type: "navigate", label: "View Jobs", tab: "jobs" as Tab, variant: "secondary" },
      ],
    };
  }
  return null;
}

// ─── Action button styling ──────────────────────────────────

const ACTION_STYLES = {
  primary: "bg-gold/10 text-gold border-gold/20 hover:bg-gold/20",
  secondary: "bg-surface-elevated text-ink-secondary border-edge hover:bg-surface-hover",
  danger: "bg-type-error/10 text-type-error border-type-error/20 hover:bg-type-error/20",
};

// ─── Alert Context Detail Renderers ─────────────────────────

function FailingJobDetail({ detail }: { detail: AlertContext & { type: "failing_job" } }) {
  return (
    <div className="space-y-3">
      {detail.detail.lastError && (
        <div className="px-3 py-2 rounded-lg bg-type-error/[0.05] border border-type-error/10">
          <span className="text-[11px] font-mono text-type-error/60 uppercase tracking-wider">Last Error</span>
          <p className="text-[13px] text-ink-secondary mt-1 font-mono break-all">{detail.detail.lastError}</p>
        </div>
      )}
      <div>
        <span className="text-[11px] font-mono text-ink-faint uppercase tracking-wider">Recent Runs</span>
        <div className="mt-1.5 space-y-1">
          {detail.detail.recentRuns.map((run, i) => (
            <div key={i} className="flex items-center gap-3 text-[12px]">
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${run.status === "error" ? "bg-type-error" : run.status === "ok" ? "bg-type-lesson" : "bg-ink-faint"}`} />
              <span className="text-ink-secondary flex-1">{run.status}</span>
              <span className="text-ink-faint tabular-nums">{run.durationMs ? `${(run.durationMs / 1000).toFixed(1)}s` : "-"}</span>
              <span className="text-ink-faint tabular-nums">{new Date(run.startedAt).toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FailedPostDetail({ detail }: { detail: AlertContext & { type: "failed_post" } }) {
  return (
    <div className="space-y-3">
      {detail.detail.recentFailed.length > 0 && (
        <div>
          <span className="text-[11px] font-mono text-type-error/60 uppercase tracking-wider">Failed</span>
          <div className="mt-1.5 space-y-2">
            {detail.detail.recentFailed.map((f, i) => (
              <div key={i} className="px-3 py-2 rounded-lg bg-type-error/[0.03] border border-type-error/[0.06]">
                <p className="text-[13px] text-ink-secondary line-clamp-2">{f.content}</p>
                {f.reason && <p className="text-[11px] text-type-error/70 mt-1">Reason: {f.reason}</p>}
                <p className="text-[11px] text-ink-faint mt-1">@{f.account}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      {detail.detail.recentSuccessful.length > 0 && (
        <div>
          <span className="text-[11px] font-mono text-type-lesson/60 uppercase tracking-wider">Recent Successful</span>
          <div className="mt-1.5 space-y-1">
            {detail.detail.recentSuccessful.map((s, i) => (
              <div key={i} className="flex items-start gap-2 text-[12px]">
                <span className="w-1.5 h-1.5 rounded-full bg-type-lesson shrink-0 mt-1.5" />
                <span className="text-ink-faint line-clamp-1 flex-1">{s.content}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CloudSyncDetail({ detail }: { detail: AlertContext & { type: "cloud_sync_gap" } }) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-3">
        <div className="text-center">
          <div className="text-[18px] font-light text-ink tabular-nums">{detail.detail.localCount.toLocaleString()}</div>
          <div className="text-[11px] text-ink-faint uppercase">Local</div>
        </div>
        <div className="text-center">
          <div className="text-[18px] font-light text-ink tabular-nums">{detail.detail.cloudCount.toLocaleString()}</div>
          <div className="text-[11px] text-ink-faint uppercase">Cloud</div>
        </div>
        <div className="text-center">
          <div className="text-[18px] font-light text-gold tabular-nums">{detail.detail.unsyncedCount.toLocaleString()}</div>
          <div className="text-[11px] text-ink-faint uppercase">Unsynced</div>
        </div>
      </div>
      {detail.detail.lastSyncAt && (
        <p className="text-[12px] text-ink-faint text-center">Last sync: {new Date(detail.detail.lastSyncAt).toLocaleString()}</p>
      )}
    </div>
  );
}

function MemorySpikeDetail({ detail }: { detail: AlertContext & { type: "memory_spike" } }) {
  return (
    <div>
      <span className="text-[11px] font-mono text-ink-faint uppercase tracking-wider">{detail.detail.totalInLastHour} memories in last hour</span>
      <div className="mt-1.5 space-y-1">
        {detail.detail.recentMemories.map((m, i) => (
          <div key={i} className="flex items-start gap-2 text-[12px]">
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-surface-elevated text-ink-faint border border-edge shrink-0">{m.memoryType}</span>
            <span className="text-ink-secondary line-clamp-1 flex-1">{m.content}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CoordinationConflictDetail({ detail }: { detail: AlertContext & { type: "coordination_conflict" } }) {
  return (
    <div className="space-y-2">
      {detail.detail.conflicts.map((c, i) => (
        <div key={i} className="px-3 py-2 rounded-lg bg-type-error/[0.03] border border-type-error/[0.06]">
          <p className="text-[13px] text-ink font-mono">{c.filePath.split("/").slice(-2).join("/")}</p>
          <div className="mt-1 flex flex-wrap gap-2">
            {c.sessions.map((s, j) => (
              <span key={j} className="text-[11px] px-2 py-0.5 rounded-full bg-surface-elevated border border-edge text-ink-secondary">
                {s.sessionId.slice(0, 8)} ({s.project})
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function AlertContextDetail({ context }: { context: AlertContext }) {
  switch (context.type) {
    case "failing_job": return <FailingJobDetail detail={context as AlertContext & { type: "failing_job" }} />;
    case "failed_post": return <FailedPostDetail detail={context as AlertContext & { type: "failed_post" }} />;
    case "cloud_sync_gap": return <CloudSyncDetail detail={context as AlertContext & { type: "cloud_sync_gap" }} />;
    case "engagement_declining": return null; // Simple text is enough
    case "memory_spike": return <MemorySpikeDetail detail={context as AlertContext & { type: "memory_spike" }} />;
    case "coordination_conflict": return <CoordinationConflictDetail detail={context as AlertContext & { type: "coordination_conflict" }} />;
    default: return null;
  }
}

// ─── Main AlertCard Component ───────────────────────────────

interface AlertCardProps {
  text: string;
  urgent: boolean;
  mapping: AlertMapping;
  onNavigate: (tab: Tab) => void;
}

export default function AlertCard({ text, urgent, mapping, onNavigate }: AlertCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [context, setContext] = useState<AlertContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchContext = useCallback(async () => {
    if (context) return; // Already loaded
    setLoading(true);
    try {
      const params = new URLSearchParams({ type: mapping.type, ...mapping.params });
      const res = await fetch(`/api/admin/alert-context?${params}`);
      if (res.ok) {
        setContext(await res.json());
      }
    } catch {
      // Non-critical
    } finally {
      setLoading(false);
    }
  }, [context, mapping]);

  const handleToggle = useCallback(() => {
    const next = !expanded;
    setExpanded(next);
    if (next) fetchContext();
  }, [expanded, fetchContext]);

  const handleAction = useCallback(async (action: AlertAction) => {
    setActionLoading(action.type);
    try {
      switch (action.type) {
        case "navigate":
          if (action.tab) onNavigate(action.tab);
          break;
        case "dismiss":
          setDismissed(true);
          break;
        case "snooze": {
          setDismissed(true);
          // Store snooze in localStorage
          const snoozed = JSON.parse(localStorage.getItem("admin_snoozed_alerts") ?? "{}");
          snoozed[mapping.type] = Date.now() + 60 * 60_000; // 1 hour
          localStorage.setItem("admin_snoozed_alerts", JSON.stringify(snoozed));
          break;
        }
        case "retry_job":
          if (action.jobLabel) {
            await fetch("/api/schedules/trigger", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ label: action.jobLabel }),
            });
          }
          break;
        case "force_sync":
          await fetch("/api/schedules/trigger", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label: "cloud-sync" }),
          });
          break;
        case "requeue_post":
          // Navigate to actions tab where re-queue is handled
          onNavigate("actions" as Tab);
          break;
      }
    } catch {
      // Silently fail
    } finally {
      setActionLoading(null);
    }
  }, [mapping, onNavigate]);

  if (dismissed) return null;

  return (
    <div className={`rounded-lg transition-all duration-200 ${urgent ? "bg-gold/[0.03]" : ""}`}>
      {/* Header row */}
      <button
        onClick={handleToggle}
        className="flex items-center gap-3 px-3 py-2 w-full text-left cursor-pointer group"
      >
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${urgent ? "bg-gold/60" : "bg-ink-faint/20"}`} />
        <span className={`text-[14px] leading-snug flex-1 ${urgent ? "text-ink font-medium" : "text-ink-faint"}`}>{text}</span>
        <svg
          className={`w-3.5 h-3.5 text-ink-faint transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {/* Expandable context + actions */}
      <div className="grid transition-[grid-template-rows] duration-300 ease-out" style={{ gridTemplateRows: expanded ? "1fr" : "0fr" }}>
        <div className="overflow-hidden">
          <div className="px-3 pb-3 space-y-3">
            <div className="h-px bg-edge-subtle ml-4" />

            {/* Loading state */}
            {loading && (
              <div className="flex items-center gap-2 px-3 py-2">
                <svg className="w-3.5 h-3.5 animate-spin text-ink-faint" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
                </svg>
                <span className="text-[12px] text-ink-faint">Loading context...</span>
              </div>
            )}

            {/* Context detail */}
            {context && <AlertContextDetail context={context} />}

            {/* Action buttons */}
            <div className="flex items-center gap-2 ml-4">
              {mapping.actions.map((action) => (
                <button
                  key={action.type}
                  onClick={() => handleAction(action)}
                  disabled={actionLoading === action.type}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium border transition-colors disabled:opacity-50 ${ACTION_STYLES[action.variant ?? "secondary"]}`}
                >
                  {actionLoading === action.type && (
                    <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
                    </svg>
                  )}
                  {action.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Update Dashboard.tsx to use AlertCard**

In `Dashboard.tsx`, update the `Problem` interface (line 72-75) to add an optional `id`:

```typescript
interface Problem {
  text: string;
  urgent: boolean;
  id?: string; // For keying and dedup
}
```

Replace the `ProblemsPanel` component (lines 428-459) with:

```typescript
function ProblemsPanel({ problems, onNavigate }: { problems: Problem[]; onNavigate: (tab: Tab) => void }) {
  if (problems.length === 0) return null;
  const urgentCount = problems.filter(p => p.urgent).length;

  // Check snoozed alerts
  const snoozed = typeof window !== "undefined" ? JSON.parse(localStorage.getItem("admin_snoozed_alerts") ?? "{}") : {};
  const now = Date.now();

  return (
    <div className="admin-card amber-border-glow p-5">
      <div className="flex items-center gap-2.5 mb-3">
        <span className="text-type-reminder"><AlertIcon /></span>
        <span className="text-[13px] font-mono font-medium text-ink-tertiary uppercase tracking-[0.08em]">Problems</span>
        {urgentCount > 0 && (
          <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded-full bg-gold/10 text-gold border border-gold/[0.1]">
            {urgentCount} urgent
          </span>
        )}
      </div>
      <div className="space-y-0.5">
        {[...problems.filter(p => p.urgent), ...problems.filter(p => !p.urgent)].map((item, i) => {
          const mapping = mapProblemToAlert(item.text);
          // Skip snoozed alerts
          if (mapping && snoozed[mapping.type] && snoozed[mapping.type] > now) return null;

          if (mapping) {
            return (
              <AlertCard
                key={`alert-${i}`}
                text={item.text}
                urgent={item.urgent}
                mapping={mapping}
                onNavigate={onNavigate}
              />
            );
          }
          // Fallback for unmapped problems
          return (
            <div key={`p-${i}`} className={`flex items-center gap-3 ${item.urgent ? "px-3 py-2 rounded-lg bg-gold/[0.03]" : "px-3 py-1.5"}`}>
              <span className={`rounded-full shrink-0 ${item.urgent ? "w-1.5 h-1.5 bg-gold/60" : "w-1 h-1 bg-ink-faint/20"}`} />
              <span className={`text-[14px] leading-snug flex-1 ${item.urgent ? "text-ink font-medium" : "text-ink-faint"}`}>{item.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

Update the `ProblemsPanel` usage at line 787:

```typescript
{/* Problems */}
<ProblemsPanel problems={problems} onNavigate={onNavigate} />
```

Add imports at the top of Dashboard.tsx:

```typescript
import AlertCard, { mapProblemToAlert } from "./dashboard/AlertCard";
```

**Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 4: Commit**

```bash
cd ~/Projects/omega/website
git add app/admin/components/dashboard/AlertCard.tsx app/admin/components/Dashboard.tsx
git commit -m "feat(admin): expandable alert cards with context and actions"
```

---

## Task 3: Hook Pipeline Visualization

Add a directed graph showing hook execution flow to the Diagnostic tab.

**Files:**
- Create: `website/app/admin/components/diagnostic/HookPipeline.tsx`
- Create: `website/app/api/admin/hook-pipeline/route.ts`
- Modify: `website/app/admin/components/Diagnostic.tsx` (add section)
- Modify: `website/app/admin/lib/types.ts` (add types)

**Step 1: Add hook pipeline types to types.ts**

Append to `website/app/admin/lib/types.ts`:

```typescript
// ─── Hook Pipeline ──────────────────────────────────────────

export interface HookExecution {
  hookType: string;
  status: "success" | "error" | "skipped";
  durationMs: number;
  timestamp: string;
  payload?: string | null;
  output?: string | null;
  error?: string | null;
}

export interface HookNode {
  id: string;
  label: string;
  status: "success" | "error" | "inactive";
  executionCount: number;
  avgDurationMs: number;
  lastExecuted: string | null;
  recentExecutions: HookExecution[];
}

export interface HookEdge {
  from: string;
  to: string;
}

export interface HookPipelineData {
  nodes: HookNode[];
  edges: HookEdge[];
  periodDays: number;
}
```

**Step 2: Create hook-pipeline API route**

Create `website/app/api/admin/hook-pipeline/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer, requireAuth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// Hook execution order (DAG)
const HOOK_ORDER = [
  "session_start",
  "pre_edit",
  "post_edit",
  "pre_push",
  "post_push",
  "pre_file_guard",
  "session_stop",
];

const HOOK_EDGES: [string, string][] = [
  ["session_start", "pre_edit"],
  ["pre_edit", "post_edit"],
  ["post_edit", "pre_push"],
  ["pre_push", "post_push"],
  ["pre_edit", "pre_file_guard"],
  ["session_stop", "session_stop"], // self-terminal, removed below
];

// Filter self-edges
const EDGES = HOOK_EDGES.filter(([a, b]) => a !== b);

export async function GET(request: NextRequest) {
  const auth = await requireAuth();
  if (!auth) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const params = request.nextUrl.searchParams;
  const days = Math.min(90, Math.max(1, parseInt(params.get("days") ?? "7", 10)));
  const cutoff = new Date(Date.now() - days * 24 * 60 * 60_000).toISOString();

  const db = supabaseServer();

  try {
    // Query hook executions from schedule_runs or a hook_log table if it exists
    // Fall back to aggregating from audit_log for hook-related entries
    const { data: hookLogs } = await db
      .from("audit_log")
      .select("event_type, metadata, created_at, duration_ms, status")
      .like("event_type", "hook_%")
      .gte("created_at", cutoff)
      .order("created_at", { ascending: false })
      .limit(500);

    // Build node stats from logs
    const nodeStats = new Map<string, { count: number; totalMs: number; errors: number; last: string | null; executions: typeof hookLogs }>();

    for (const hookType of HOOK_ORDER) {
      nodeStats.set(hookType, { count: 0, totalMs: 0, errors: 0, last: null, executions: [] });
    }

    for (const log of hookLogs ?? []) {
      // event_type is like "hook_pre_edit" -> extract "pre_edit"
      const hookType = (log.event_type ?? "").replace(/^hook_/, "");
      let stats = nodeStats.get(hookType);
      if (!stats) {
        stats = { count: 0, totalMs: 0, errors: 0, last: null, executions: [] };
        nodeStats.set(hookType, stats);
      }
      stats.count++;
      stats.totalMs += log.duration_ms ?? 0;
      if (log.status === "error") stats.errors++;
      if (!stats.last || log.created_at > stats.last) stats.last = log.created_at;
      if ((stats.executions?.length ?? 0) < 5) {
        stats.executions?.push(log);
      }
    }

    const nodes = HOOK_ORDER.map(id => {
      const stats = nodeStats.get(id) ?? { count: 0, totalMs: 0, errors: 0, last: null, executions: [] };
      return {
        id,
        label: id.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
        status: stats.count === 0 ? "inactive" as const : stats.errors > 0 ? "error" as const : "success" as const,
        executionCount: stats.count,
        avgDurationMs: stats.count > 0 ? Math.round(stats.totalMs / stats.count) : 0,
        lastExecuted: stats.last,
        recentExecutions: (stats.executions ?? []).slice(0, 5).map(e => ({
          hookType: id,
          status: (e.status === "error" ? "error" : "success") as "success" | "error",
          durationMs: e.duration_ms ?? 0,
          timestamp: e.created_at,
          payload: null,
          output: null,
          error: e.status === "error" ? (e.metadata as Record<string, unknown>)?.error as string ?? null : null,
        })),
      };
    });

    const edges = EDGES.map(([from, to]) => ({ from, to }));

    return NextResponse.json({ nodes, edges, periodDays: days });
  } catch (err: unknown) {
    console.error("[hook-pipeline]", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
```

**Step 3: Create HookPipeline component**

Create `website/app/admin/components/diagnostic/HookPipeline.tsx`:

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import type { HookPipelineData, HookNode } from "../../lib/types";

const NODE_W = 140;
const NODE_H = 56;
const GAP_X = 40;
const GAP_Y = 24;
const PAD = 24;

const STATUS_COLORS = {
  success: { bg: "rgba(94,201,160,0.08)", border: "rgba(94,201,160,0.3)", text: "#5ec9a0", dot: "#5ec9a0" },
  error: { bg: "rgba(240,96,96,0.08)", border: "rgba(240,96,96,0.3)", text: "#f06060", dot: "#f06060" },
  inactive: { bg: "rgba(255,255,255,0.02)", border: "rgba(255,255,255,0.06)", text: "#666", dot: "#444" },
};

// Layout nodes in a horizontal line with pre_file_guard branching down
function layoutNodes(nodes: HookNode[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const mainLine = ["session_start", "pre_edit", "post_edit", "pre_push", "post_push", "session_stop"];
  const branch = ["pre_file_guard"];

  mainLine.forEach((id, i) => {
    positions.set(id, { x: PAD + i * (NODE_W + GAP_X), y: PAD });
  });

  branch.forEach((id) => {
    // Branch down from pre_edit
    const preEditPos = positions.get("pre_edit");
    if (preEditPos) {
      positions.set(id, { x: preEditPos.x, y: preEditPos.y + NODE_H + GAP_Y });
    }
  });

  // Add any nodes not in the predefined layout
  let nextX = PAD + mainLine.length * (NODE_W + GAP_X);
  for (const node of nodes) {
    if (!positions.has(node.id)) {
      positions.set(node.id, { x: nextX, y: PAD });
      nextX += NODE_W + GAP_X;
    }
  }

  return positions;
}

function NodeTooltip({ node }: { node: HookNode }) {
  return (
    <div className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 px-3 py-2 rounded-lg bg-[#1a1b20] border border-white/[0.08] shadow-lg shadow-black/30 whitespace-nowrap text-[12px]">
      <div className="font-medium text-ink mb-1">{node.label}</div>
      <div className="text-ink-secondary">Executions: <span className="text-ink tabular-nums">{node.executionCount}</span></div>
      <div className="text-ink-secondary">Avg: <span className="text-ink tabular-nums">{node.avgDurationMs}ms</span></div>
      {node.lastExecuted && (
        <div className="text-ink-faint mt-1">{new Date(node.lastExecuted).toLocaleString()}</div>
      )}
      {node.recentExecutions.length > 0 && (
        <div className="mt-2 space-y-0.5 border-t border-white/[0.06] pt-1.5">
          <div className="text-[10px] text-ink-faint uppercase tracking-wider">Recent</div>
          {node.recentExecutions.slice(0, 3).map((e, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className={`w-1.5 h-1.5 rounded-full ${e.status === "error" ? "bg-type-error" : "bg-type-lesson"}`} />
              <span className="text-ink-secondary">{e.durationMs}ms</span>
              {e.error && <span className="text-type-error text-[11px] truncate max-w-[150px]">{e.error}</span>}
            </div>
          ))}
        </div>
      )}
      <span className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-t-[5px] border-t-[#1a1b20]" />
    </div>
  );
}

export default function HookPipeline() {
  const [data, setData] = useState<HookPipelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/hook-pipeline?days=7");
      if (res.ok) setData(await res.json());
    } catch {
      // Non-critical
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading && !data) {
    return (
      <section>
        <div className="admin-section-label">Hook Pipeline</div>
        <div className="admin-card h-40 skeleton rounded-xl" />
      </section>
    );
  }

  if (!data) return null;

  const positions = layoutNodes(data.nodes);
  const nodeMap = new Map(data.nodes.map(n => [n.id, n]));

  // Calculate SVG dimensions
  let maxX = 0, maxY = 0;
  for (const pos of positions.values()) {
    maxX = Math.max(maxX, pos.x + NODE_W);
    maxY = Math.max(maxY, pos.y + NODE_H);
  }
  const svgW = maxX + PAD;
  const svgH = maxY + PAD;

  return (
    <section>
      <div className="admin-section-label">Hook Pipeline (7d)</div>
      <div className="admin-card overflow-x-auto">
        <svg width={svgW} height={svgH} className="block">
          {/* Edges */}
          {data.edges.map(({ from, to }, i) => {
            const fromPos = positions.get(from);
            const toPos = positions.get(to);
            if (!fromPos || !toPos) return null;

            const x1 = fromPos.x + NODE_W;
            const y1 = fromPos.y + NODE_H / 2;
            const x2 = toPos.x;
            const y2 = toPos.y + NODE_H / 2;

            // If going downward (branch), use a curved path
            if (y2 > y1 + 10) {
              const midY = y1 + (y2 - y1) / 2;
              return (
                <path
                  key={i}
                  d={`M${x1},${y1} C${x1 + 20},${y1} ${x2 - 20},${midY} ${x2},${y2}`}
                  fill="none"
                  stroke="rgba(255,255,255,0.08)"
                  strokeWidth={1.5}
                  strokeDasharray="4,3"
                />
              );
            }

            return (
              <line
                key={i}
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke="rgba(255,255,255,0.08)"
                strokeWidth={1.5}
              />
            );
          })}

          {/* Arrowheads on edges */}
          {data.edges.map(({ from, to }, i) => {
            const toPos = positions.get(to);
            if (!toPos) return null;
            const x = toPos.x - 2;
            const y = toPos.y + NODE_H / 2;
            return (
              <polygon
                key={`arrow-${i}`}
                points={`${x},${y} ${x - 6},${y - 3} ${x - 6},${y + 3}`}
                fill="rgba(255,255,255,0.08)"
              />
            );
          })}

          {/* Nodes */}
          {data.nodes.map((node) => {
            const pos = positions.get(node.id);
            if (!pos) return null;
            const colors = STATUS_COLORS[node.status];
            const isHovered = hoveredNode === node.id;

            return (
              <g
                key={node.id}
                onMouseEnter={() => setHoveredNode(node.id)}
                onMouseLeave={() => setHoveredNode(null)}
                className="cursor-pointer"
              >
                <rect
                  x={pos.x} y={pos.y}
                  width={NODE_W} height={NODE_H}
                  rx={8}
                  fill={colors.bg}
                  stroke={isHovered ? colors.text : colors.border}
                  strokeWidth={isHovered ? 1.5 : 1}
                />
                {/* Status dot */}
                <circle
                  cx={pos.x + 14} cy={pos.y + NODE_H / 2}
                  r={4}
                  fill={colors.dot}
                />
                {/* Label */}
                <text
                  x={pos.x + 26} y={pos.y + 22}
                  fill={colors.text}
                  fontSize={11}
                  fontFamily="monospace"
                >
                  {node.label}
                </text>
                {/* Count */}
                <text
                  x={pos.x + 26} y={pos.y + 40}
                  fill="rgba(255,255,255,0.3)"
                  fontSize={10}
                  fontFamily="monospace"
                >
                  {node.executionCount > 0 ? `${node.executionCount}x / ${node.avgDurationMs}ms` : "inactive"}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Tooltip rendered as HTML overlay */}
        {hoveredNode && nodeMap.get(hoveredNode) && (
          <div
            className="absolute pointer-events-none"
            style={{
              left: (positions.get(hoveredNode)?.x ?? 0) + NODE_W / 2,
              top: (positions.get(hoveredNode)?.y ?? 0) - 8,
            }}
          >
            <NodeTooltip node={nodeMap.get(hoveredNode)!} />
          </div>
        )}
      </div>
    </section>
  );
}
```

**Step 4: Add HookPipeline to Diagnostic.tsx**

In `Diagnostic.tsx`, add import at top:

```typescript
import HookPipeline from "./diagnostic/HookPipeline";
```

Add after the RecommendationsPanel (around line 413):

```typescript
      {/* Hook Pipeline */}
      <HookPipeline />
```

**Step 5: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`

**Step 6: Commit**

```bash
cd ~/Projects/omega/website
git add app/admin/lib/types.ts app/api/admin/hook-pipeline/route.ts app/admin/components/diagnostic/HookPipeline.tsx app/admin/components/Diagnostic.tsx
git commit -m "feat(admin): hook pipeline visualization in diagnostic tab"
```

---

## Task 4: Incident Timeline

Add a unified event timeline as a new mode in the Feed tab.

**Files:**
- Create: `website/app/api/admin/timeline/route.ts`
- Create: `website/app/admin/components/feed/IncidentTimeline.tsx`
- Modify: `website/app/admin/components/Feed.tsx` (add mode toggle)
- Modify: `website/app/admin/lib/types.ts` (add types)

**Step 1: Add timeline types to types.ts**

Append to `website/app/admin/lib/types.ts`:

```typescript
// ─── Incident Timeline ──────────────────────────────────────

export type TimelineEventSource = "coordination" | "memory" | "job" | "hook" | "git";

export interface TimelineEvent {
  id: string;
  source: TimelineEventSource;
  eventType: string;
  title: string;
  detail: string | null;
  timestamp: string;
  agentId: string | null;
  project: string | null;
  /** For drill-down navigation */
  linkedTab?: Tab;
  linkedId?: string;
}

export interface TimelineData {
  events: TimelineEvent[];
  total: number;
  hasMore: boolean;
}
```

**Step 2: Create timeline API route**

Create `website/app/api/admin/timeline/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer, requireAuth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

/**
 * GET /api/admin/timeline?hours=24&source=all&project=all&limit=50&offset=0
 *
 * Unified timeline merging events from coordination, memory, jobs, hooks, and git.
 */
export async function GET(request: NextRequest) {
  const auth = await requireAuth();
  if (!auth) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const params = request.nextUrl.searchParams;
  const hours = Math.min(168, Math.max(1, parseInt(params.get("hours") ?? "24", 10)));
  const source = params.get("source") ?? "all";
  const project = params.get("project") ?? "all";
  const limit = Math.min(100, Math.max(10, parseInt(params.get("limit") ?? "50", 10)));
  const offset = Math.max(0, parseInt(params.get("offset") ?? "0", 10));

  const cutoff = new Date(Date.now() - hours * 60 * 60_000).toISOString();
  const db = supabaseServer();

  type RawEvent = {
    id: string;
    source: string;
    eventType: string;
    title: string;
    detail: string | null;
    timestamp: string;
    agentId: string | null;
    project: string | null;
    linkedTab?: string;
    linkedId?: string;
  };

  const allEvents: RawEvent[] = [];

  try {
    // 1. Coordination events (sessions, messages, tasks)
    if (source === "all" || source === "coordination") {
      let sessionsQ = db
        .from("coord_sessions")
        .select("session_id, project, status, task, started_at, last_heartbeat")
        .gte("started_at", cutoff)
        .order("started_at", { ascending: false })
        .limit(50);
      if (project !== "all") sessionsQ = sessionsQ.eq("project", project);
      const { data: sessions } = await sessionsQ;

      for (const s of sessions ?? []) {
        allEvents.push({
          id: `coord-session-${s.session_id}`,
          source: "coordination",
          eventType: s.status === "ended" ? "session_ended" : "session_started",
          title: `Agent ${s.status === "ended" ? "ended" : "started"}: ${s.session_id.slice(0, 8)}`,
          detail: s.task,
          timestamp: s.started_at,
          agentId: s.session_id,
          project: s.project,
          linkedTab: "coordination",
        });
      }

      let tasksQ = db
        .from("coord_tasks")
        .select("id, title, status, completed_at, created_at")
        .gte("created_at", cutoff)
        .order("created_at", { ascending: false })
        .limit(30);
      const { data: tasks } = await tasksQ;

      for (const t of tasks ?? []) {
        if (t.completed_at) {
          allEvents.push({
            id: `coord-task-${t.id}`,
            source: "coordination",
            eventType: "task_completed",
            title: `Task completed: ${t.title}`,
            detail: null,
            timestamp: t.completed_at,
            agentId: null,
            project: null,
            linkedTab: "coordination",
            linkedId: String(t.id),
          });
        }
      }
    }

    // 2. Memory events
    if (source === "all" || source === "memory") {
      const { data: memories } = await db
        .from("memories")
        .select("id, content, memory_type, metadata, created_at")
        .eq("user_id", auth.user.id)
        .gte("created_at", cutoff)
        .order("created_at", { ascending: false })
        .limit(30);

      for (const m of memories ?? []) {
        const meta = (m.metadata ?? {}) as Record<string, unknown>;
        allEvents.push({
          id: `memory-${m.id}`,
          source: "memory",
          eventType: `memory_${m.memory_type ?? "stored"}`,
          title: `Memory stored: ${m.memory_type ?? "unknown"}`,
          detail: (m.content ?? "").slice(0, 100),
          timestamp: m.created_at,
          agentId: (meta.session_id as string) ?? null,
          project: (meta.project as string) ?? null,
          linkedTab: "feed",
          linkedId: m.id,
        });
      }
    }

    // 3. Job events
    if (source === "all" || source === "job") {
      const { data: runs } = await db
        .from("schedule_runs")
        .select("id, schedule_label, status, started_at, completed_at, error_message")
        .gte("started_at", cutoff)
        .order("started_at", { ascending: false })
        .limit(30);

      for (const r of runs ?? []) {
        allEvents.push({
          id: `job-${r.id}`,
          source: "job",
          eventType: r.status === "error" ? "job_failed" : r.status === "ok" ? "job_completed" : "job_started",
          title: `Job ${r.status}: ${r.schedule_label}`,
          detail: r.error_message ?? null,
          timestamp: r.completed_at ?? r.started_at,
          agentId: null,
          project: null,
          linkedTab: "jobs",
        });
      }
    }

    // 4. Git events
    if (source === "all" || source === "git") {
      let gitQ = db
        .from("coord_git_events")
        .select("id, session_id, project, event_type, commit_hash, branch, message, created_at")
        .gte("created_at", cutoff)
        .order("created_at", { ascending: false })
        .limit(30);
      if (project !== "all") gitQ = gitQ.eq("project", project);
      const { data: gitEvents } = await gitQ;

      for (const g of gitEvents ?? []) {
        allEvents.push({
          id: `git-${g.id}`,
          source: "git",
          eventType: g.event_type,
          title: `Git ${g.event_type}: ${g.branch ?? ""}`,
          detail: g.message,
          timestamp: g.created_at,
          agentId: g.session_id,
          project: g.project,
          linkedTab: "coordination",
        });
      }
    }

    // Sort by timestamp descending
    allEvents.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

    const total = allEvents.length;
    const paged = allEvents.slice(offset, offset + limit);

    return NextResponse.json({
      events: paged,
      total,
      hasMore: offset + limit < total,
    });
  } catch (err: unknown) {
    console.error("[timeline]", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
```

**Step 3: Create IncidentTimeline component**

Create `website/app/admin/components/feed/IncidentTimeline.tsx`:

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import type { TimelineData, TimelineEvent, TimelineEventSource, Tab } from "../../lib/types";

const SOURCE_STYLES: Record<TimelineEventSource, { color: string; bg: string; label: string }> = {
  coordination: { color: "text-[#60a5fa]", bg: "bg-[#60a5fa]/10", label: "Coordination" },
  memory: { color: "text-gold", bg: "bg-gold/10", label: "Memory" },
  job: { color: "text-type-lesson", bg: "bg-type-lesson/10", label: "Job" },
  hook: { color: "text-[#c084fc]", bg: "bg-[#c084fc]/10", label: "Hook" },
  git: { color: "text-[#fb923c]", bg: "bg-[#fb923c]/10", label: "Git" },
};

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function EventRow({ event, onNavigate }: { event: TimelineEvent; onNavigate?: (tab: Tab, id?: string) => void }) {
  const style = SOURCE_STYLES[event.source];
  const isError = event.eventType.includes("fail") || event.eventType.includes("error");
  const isCompleted = event.eventType.includes("complete") || event.eventType.includes("ok");

  return (
    <div className="flex items-start gap-3 group">
      {/* Timeline line + dot */}
      <div className="flex flex-col items-center shrink-0 w-6">
        <span className={`w-2.5 h-2.5 rounded-full mt-1 shrink-0 ${isError ? "bg-type-error" : isCompleted ? "bg-type-lesson" : "bg-ink-faint/30"}`} />
        <div className="w-px flex-1 bg-edge-subtle min-h-[24px]" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border border-transparent ${style.bg} ${style.color}`}>
            {style.label}
          </span>
          <span className="text-[13px] text-ink font-medium">{event.title}</span>
          <span className="text-[11px] text-ink-faint tabular-nums ml-auto shrink-0">{timeAgo(event.timestamp)}</span>
        </div>
        {event.detail && (
          <p className="text-[12px] text-ink-secondary mt-1 line-clamp-2">{event.detail}</p>
        )}
        <div className="flex items-center gap-3 mt-1">
          {event.agentId && (
            <span className="text-[11px] font-mono text-ink-faint">agent:{event.agentId.slice(0, 8)}</span>
          )}
          {event.project && (
            <span className="text-[11px] text-ink-faint">{event.project}</span>
          )}
          {event.linkedTab && onNavigate && (
            <button
              onClick={() => onNavigate(event.linkedTab!, event.linkedId)}
              className="text-[11px] text-gold/60 hover:text-gold transition-colors opacity-0 group-hover:opacity-100"
            >
              View &rarr;
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

interface IncidentTimelineProps {
  onNavigate?: (tab: Tab, id?: string) => void;
}

export default function IncidentTimeline({ onNavigate }: IncidentTimelineProps) {
  const [data, setData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(24);
  const [sourceFilter, setSourceFilter] = useState<TimelineEventSource | "all">("all");

  const fetchTimeline = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        hours: String(hours),
        source: sourceFilter,
        limit: "50",
      });
      const res = await fetch(`/api/admin/timeline?${params}`);
      if (res.ok) setData(await res.json());
    } catch {
      // Non-critical
    } finally {
      setLoading(false);
    }
  }, [hours, sourceFilter]);

  useEffect(() => { fetchTimeline(); }, [fetchTimeline]);

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Time range */}
        <div className="flex rounded-lg border border-edge overflow-hidden">
          {([6, 24, 72, 168] as const).map((h) => (
            <button
              key={h}
              onClick={() => setHours(h)}
              className={`px-3 py-1.5 text-[12px] font-medium transition-colors ${
                hours === h ? "bg-gold/10 text-gold" : "text-ink-tertiary hover:text-ink-secondary hover:bg-surface-hover"
              }`}
            >
              {h < 24 ? `${h}h` : `${h / 24}d`}
            </button>
          ))}
        </div>

        {/* Source filter */}
        <div className="flex rounded-lg border border-edge overflow-hidden">
          <button
            onClick={() => setSourceFilter("all")}
            className={`px-3 py-1.5 text-[12px] font-medium transition-colors ${
              sourceFilter === "all" ? "bg-gold/10 text-gold" : "text-ink-tertiary hover:text-ink-secondary hover:bg-surface-hover"
            }`}
          >
            All
          </button>
          {(Object.keys(SOURCE_STYLES) as TimelineEventSource[]).map((src) => (
            <button
              key={src}
              onClick={() => setSourceFilter(src)}
              className={`px-3 py-1.5 text-[12px] font-medium transition-colors ${
                sourceFilter === src ? "bg-gold/10 text-gold" : "text-ink-tertiary hover:text-ink-secondary hover:bg-surface-hover"
              }`}
            >
              {SOURCE_STYLES[src].label}
            </button>
          ))}
        </div>

        {/* Event count */}
        {data && (
          <span className="text-[12px] text-ink-faint ml-auto">
            {data.total} event{data.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Loading */}
      {loading && !data && (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="flex gap-3">
              <div className="skeleton w-6 h-6 rounded-full" />
              <div className="flex-1 space-y-2">
                <div className="skeleton h-4 w-3/4 rounded" />
                <div className="skeleton h-3 w-1/2 rounded" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Events */}
      {data && data.events.length === 0 && (
        <div className="text-center py-12 text-[13px] text-ink-faint">
          No events in the last {hours < 24 ? `${hours} hours` : `${hours / 24} days`}
        </div>
      )}

      {data && data.events.length > 0 && (
        <div className="pl-1">
          {data.events.map((event) => (
            <EventRow key={event.id} event={event} onNavigate={onNavigate} />
          ))}
          {data.hasMore && (
            <div className="text-center pt-2">
              <button
                onClick={() => {
                  // Load more by increasing limit
                  // For now, just note there are more
                }}
                className="text-[12px] text-gold/60 hover:text-gold transition-colors"
              >
                {data.total - data.events.length} more events
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

**Step 4: Add mode toggle to Feed.tsx**

At the top of `Feed.tsx`, add import:

```typescript
import IncidentTimeline from "./feed/IncidentTimeline";
```

Inside the `Feed` component, add a mode state after the existing state declarations:

```typescript
const [feedMode, setFeedMode] = useState<"memories" | "timeline">("memories");
```

Add a mode toggle right before the `FeedToolbar` usage, and wrap the feed content in a conditional:

```typescript
{/* Mode toggle */}
<div className="flex items-center gap-1 px-5 pt-4">
  <button
    onClick={() => setFeedMode("memories")}
    className={`px-3 py-1.5 rounded-lg text-[13px] font-medium transition-colors ${
      feedMode === "memories" ? "bg-gold/10 text-gold" : "text-ink-tertiary hover:text-ink-secondary"
    }`}
  >
    Memories
  </button>
  <button
    onClick={() => setFeedMode("timeline")}
    className={`px-3 py-1.5 rounded-lg text-[13px] font-medium transition-colors ${
      feedMode === "timeline" ? "bg-gold/10 text-gold" : "text-ink-tertiary hover:text-ink-secondary"
    }`}
  >
    Timeline
  </button>
</div>

{feedMode === "timeline" ? (
  <div className="px-5 py-4">
    <IncidentTimeline onNavigate={onNavigateToApprovals ? (tab) => {/* handled via parent */} : undefined} />
  </div>
) : (
  /* existing feed content */
)}
```

Note: The exact insertion points depend on the full Feed.tsx structure. The mode toggle goes at the top of the feed content area, and the existing feed body is wrapped in the `feedMode === "memories"` branch.

**Step 5: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`

**Step 6: Commit**

```bash
cd ~/Projects/omega/website
git add app/admin/lib/types.ts app/api/admin/timeline/route.ts app/admin/components/feed/IncidentTimeline.tsx app/admin/components/Feed.tsx
git commit -m "feat(admin): incident timeline in feed tab"
```

---

## Task 5: Persistent Alert History

Add a Supabase table and Diagnostic section for alert history.

**Files:**
- Create: `website/supabase/migrations/20260309000000_admin_alerts.sql`
- Create: `website/app/admin/components/diagnostic/AlertHistory.tsx`
- Modify: `website/app/api/admin/ambient-status/route.ts` (persist alerts)
- Modify: `website/app/admin/components/Diagnostic.tsx` (add section)

**Step 1: Create Supabase migration**

Create `website/supabase/migrations/20260309000000_admin_alerts.sql`:

```sql
-- Persistent alert history for OMEGA admin dashboard
create table if not exists admin_alerts (
  id uuid primary key default gen_random_uuid(),
  type text not null,
  severity text not null default 'warning',
  title text not null,
  detail jsonb default '{}'::jsonb,
  status text not null default 'active',
  snoozed_until timestamptz,
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  user_id uuid references auth.users(id)
);

create index if not exists idx_admin_alerts_status on admin_alerts(status);
create index if not exists idx_admin_alerts_created on admin_alerts(created_at desc);
create index if not exists idx_admin_alerts_type on admin_alerts(type, created_at desc);

-- RLS
alter table admin_alerts enable row level security;

create policy "Authenticated users can read alerts"
  on admin_alerts for select
  to authenticated
  using (true);

create policy "Authenticated users can insert alerts"
  on admin_alerts for insert
  to authenticated
  with check (true);

create policy "Authenticated users can update alerts"
  on admin_alerts for update
  to authenticated
  using (true);
```

**Step 2: Add alert persistence to ambient-status route**

In `website/app/api/admin/ambient-status/route.ts`, add alert persistence after the sparkline calculation (before the final `return NextResponse.json`):

```typescript
    // ─── Persist alerts (deduplicated by type + 1h window) ─────
    const alertsToCheck: { type: string; severity: string; title: string; detail: Record<string, unknown> }[] = [];

    if (fileConflicts.length > 0) {
      alertsToCheck.push({
        type: "coordination_conflict",
        severity: "critical",
        title: `${fileConflicts.length} file conflict(s)`,
        detail: { files: fileConflicts },
      });
    }

    const recentMemoryCount = memoryCountRes.count ?? 0;
    if (recentMemoryCount > 50) {
      alertsToCheck.push({
        type: "memory_spike",
        severity: "info",
        title: `Memory spike: ${recentMemoryCount} in last hour`,
        detail: { count: recentMemoryCount },
      });
    }

    // Persist new alerts (skip if same type exists within last hour)
    for (const alert of alertsToCheck) {
      const oneHourAgo = new Date(now - 60 * 60_000).toISOString();
      const { count } = await db
        .from("admin_alerts")
        .select("id", { count: "exact", head: true })
        .eq("type", alert.type)
        .gte("created_at", oneHourAgo);

      if ((count ?? 0) === 0) {
        await db.from("admin_alerts").insert({
          type: alert.type,
          severity: alert.severity,
          title: alert.title,
          detail: alert.detail,
          user_id: auth.user.id,
        });
      }
    }

    // Auto-resolve: if no file conflicts, resolve any active conflict alerts
    if (fileConflicts.length === 0) {
      await db
        .from("admin_alerts")
        .update({ status: "resolved", resolved_at: new Date().toISOString() })
        .eq("type", "coordination_conflict")
        .eq("status", "active");
    }
```

**Step 3: Create AlertHistory component**

Create `website/app/admin/components/diagnostic/AlertHistory.tsx`:

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";

interface AlertRecord {
  id: string;
  type: string;
  severity: string;
  title: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
}

interface AlertHistoryData {
  alerts: AlertRecord[];
  recurrenceCounts: Record<string, number>;
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-type-error/10 text-type-error border-type-error/20",
  warning: "bg-gold/10 text-gold border-gold/20",
  info: "bg-surface-elevated text-ink-secondary border-edge",
};

const STATUS_STYLES: Record<string, { dot: string; label: string }> = {
  active: { dot: "bg-gold", label: "Active" },
  resolved: { dot: "bg-type-lesson", label: "Resolved" },
  dismissed: { dot: "bg-ink-faint", label: "Dismissed" },
  snoozed: { dot: "bg-[#60a5fa]", label: "Snoozed" },
};

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function AlertHistory() {
  const [data, setData] = useState<AlertHistoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "resolved">("all");

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/alert-history?status=${statusFilter}`);
      if (res.ok) setData(await res.json());
    } catch {
      // Non-critical
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  if (loading && !data) {
    return (
      <section>
        <div className="admin-section-label">Alert History</div>
        <div className="admin-card h-32 skeleton rounded-xl" />
      </section>
    );
  }

  if (!data || data.alerts.length === 0) {
    return (
      <section>
        <div className="admin-section-label">Alert History</div>
        <div className="admin-card px-4 py-8 text-center text-[13px] text-ink-faint">
          No alerts recorded yet
        </div>
      </section>
    );
  }

  // Check for recurring patterns
  const patterns = Object.entries(data.recurrenceCounts)
    .filter(([, count]) => count >= 3)
    .sort((a, b) => b[1] - a[1]);

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <div className="admin-section-label !mb-0">Alert History</div>
        <div className="flex rounded-lg border border-edge overflow-hidden">
          {(["all", "active", "resolved"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-2.5 py-1 text-[11px] font-medium transition-colors capitalize ${
                statusFilter === s ? "bg-gold/10 text-gold" : "text-ink-tertiary hover:text-ink-secondary hover:bg-surface-hover"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Recurring pattern alerts */}
      {patterns.length > 0 && (
        <div className="mb-3 space-y-1.5">
          {patterns.map(([type, count]) => (
            <div key={type} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gold/[0.03] border border-gold/[0.06]">
              <span className="text-[11px] font-mono text-gold/60">Pattern</span>
              <span className="text-[13px] text-ink-secondary flex-1">
                {type.replace(/_/g, " ")} has occurred {count} times this week
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Alert list */}
      <div className="admin-card divide-y divide-edge">
        {data.alerts.map((alert) => {
          const sevStyle = SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.info;
          const statStyle = STATUS_STYLES[alert.status] ?? STATUS_STYLES.active;

          return (
            <div key={alert.id} className="flex items-center gap-3 px-4 py-3">
              <span className={`w-2 h-2 rounded-full shrink-0 ${statStyle.dot}`} />
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border ${sevStyle}`}>
                {alert.severity}
              </span>
              <span className="text-[13px] text-ink-secondary flex-1 truncate">{alert.title}</span>
              <span className="text-[11px] text-ink-faint tabular-nums shrink-0">{timeAgo(alert.created_at)}</span>
              {alert.resolved_at && (
                <span className="text-[10px] text-type-lesson/60 shrink-0">resolved {timeAgo(alert.resolved_at)}</span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
```

**Step 4: Create alert-history API route**

Create `website/app/api/admin/alert-history/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer, requireAuth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const auth = await requireAuth();
  if (!auth) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const params = request.nextUrl.searchParams;
  const status = params.get("status") ?? "all";

  const db = supabaseServer();
  const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60_000).toISOString();

  try {
    let query = db
      .from("admin_alerts")
      .select("id, type, severity, title, status, created_at, resolved_at")
      .gte("created_at", weekAgo)
      .order("created_at", { ascending: false })
      .limit(50);

    if (status !== "all") {
      query = query.eq("status", status);
    }

    const { data: alerts, error } = await query;
    if (error) throw error;

    // Calculate recurrence counts (by type, last 7 days)
    const recurrenceCounts: Record<string, number> = {};
    for (const a of alerts ?? []) {
      recurrenceCounts[a.type] = (recurrenceCounts[a.type] ?? 0) + 1;
    }

    return NextResponse.json({ alerts: alerts ?? [], recurrenceCounts });
  } catch (err: unknown) {
    console.error("[alert-history]", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
```

**Step 5: Add AlertHistory to Diagnostic.tsx**

In `Diagnostic.tsx`, add import:

```typescript
import AlertHistory from "./diagnostic/AlertHistory";
```

Add after HookPipeline (or after QuickStatsPanel):

```typescript
      {/* Alert History */}
      <AlertHistory />
```

**Step 6: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`

**Step 7: Commit**

```bash
cd ~/Projects/omega/website
git add supabase/migrations/20260309000000_admin_alerts.sql app/api/admin/alert-history/route.ts app/api/admin/ambient-status/route.ts app/admin/components/diagnostic/AlertHistory.tsx app/admin/components/Diagnostic.tsx
git commit -m "feat(admin): persistent alert history with pattern detection"
```

---

## Task 6: Final Integration and Build Verification

**Step 1: Run full type check**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`
Expected: Clean

**Step 2: Run lint**

Run: `cd ~/Projects/omega/website && npm run lint`
Expected: Clean or only pre-existing warnings

**Step 3: Run build**

Run: `cd ~/Projects/omega/website && npm run build 2>&1 | tail -20`
Expected: Build succeeds

**Step 4: Final commit if any fixups needed**

```bash
cd ~/Projects/omega/website
git add -u
git commit -m "fix(admin): build fixups for xyops-inspired features"
```
