# Jobs Tab Completeness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Jobs tab a complete, accurate, live operational dashboard for all 32 scheduled jobs across 7 sources.

**Architecture:** Seed all missing jobs into the `schedules` Supabase table with `metadata.source` tags. Wire heartbeat calls into worker.ts, Vercel API routes, and the Python maintenance pipeline. Make remote-defined jobs (GitHub Actions, Vercel, maintenance) read-only in the UI. Enhance `/api/notify` to alert on job failures.

**Tech Stack:** TypeScript (Next.js), Python 3.11, Supabase, Vercel crons, GitHub Actions

---

### Task 1: Create Shared Heartbeat Helper

**Files:**
- Create: `website/lib/heartbeat.ts`

**Step 1: Create the heartbeat helper**

```typescript
import { supabaseServer } from "@/lib/supabase";

/**
 * Update a schedule's heartbeat in Supabase.
 * Called after a job completes (from worker.ts or Vercel API routes).
 */
export async function sendHeartbeat(
  label: string,
  status: "ok" | "error" = "ok",
): Promise<void> {
  try {
    const sb = supabaseServer();
    await sb
      .from("schedules")
      .update({ last_status: status, last_run_at: new Date().toISOString() })
      .eq("label", label);
  } catch (err) {
    // Best-effort: never let heartbeat failure crash the job
    console.error(`[heartbeat] failed for ${label}:`, err);
  }
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit lib/heartbeat.ts 2>&1 | head -20`

**Step 3: Commit**

```bash
git add website/lib/heartbeat.ts
git commit -m "feat(jobs): add shared heartbeat helper for schedule status updates"
```

---

### Task 2: Wire Heartbeat into worker.ts (GitHub Actions)

**Files:**
- Modify: `website/scripts/worker.ts`

**Step 1: Add label mapping and heartbeat call**

At the top of `worker.ts` (after line 14), add the job-to-label mapping:

```typescript
const JOB_LABEL_MAP: Record<string, string> = {
  "generate-hourly": "com.omega.github.generate-hourly",
  "process-events": "com.omega.github.process-events",
  "publish": "com.omega.github.publish",
  "x-brief": "com.omega.github.x-brief",
  "inbox-sync": "com.omega.github.inbox-sync",
  "inbox-followups": "com.omega.github.inbox-followups",
  "generate-omega": "com.omega.github.omega-generate",
};
```

**Step 2: Add heartbeat call at end of runJob**

Replace the final log line at line 340 (`console.log(\`[worker] job ${job} completed...`):

```typescript
  const elapsed = Date.now() - t0;
  console.log(`[worker] job ${job} completed in ${elapsed}ms`);

  // Report heartbeat to schedules table
  const label = JOB_LABEL_MAP[job];
  if (label) {
    try {
      const { sendHeartbeat } = await import("@/lib/heartbeat");
      await sendHeartbeat(label, "ok");
      console.log(`[worker] heartbeat sent: ${label}`);
    } catch (err) {
      console.error(`[worker] heartbeat failed:`, err);
    }
  }
```

**Step 3: Add error heartbeat in the catch block**

At line 343 (the `.catch` handler), before `process.exit(1)`:

```typescript
runJob(JOB_NAME).catch(async (err) => {
  console.error(`[worker] FATAL:`, err);
  const label = JOB_LABEL_MAP[JOB_NAME];
  if (label) {
    try {
      const { sendHeartbeat } = await import("@/lib/heartbeat");
      await sendHeartbeat(label, "error");
    } catch { /* best effort */ }
  }
  process.exit(1);
});
```

**Step 4: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 5: Commit**

```bash
git add website/scripts/worker.ts
git commit -m "feat(jobs): wire heartbeat into worker.ts for GitHub Actions jobs"
```

---

### Task 3: Wire Heartbeat into Vercel Cron API Routes

**Files:**
- Modify: `website/app/api/digest/route.ts`
- Modify: `website/app/api/notify/route.ts`
- Modify: `website/app/api/process-events/route.ts`
- Modify: `website/app/api/optimize-slots/route.ts`
- Modify: `website/app/api/process-reply-queue/route.ts`

For each route, add a heartbeat call at the end of successful execution and on error. Pattern:

**Step 1: Add heartbeat to `/api/process-events/route.ts`**

```typescript
import { sendHeartbeat } from "@/lib/heartbeat";
```

After `return NextResponse.json(summary)` (success path, line 16):
```typescript
  try {
    const summary = await processPendingEvents(10);
    console.log(`[process-events] processed=${summary.processed} completed=${summary.completed} failed=${summary.failed} retrying=${summary.retrying}`);
    await sendHeartbeat("com.omega.vercel.process-events");
    return NextResponse.json(summary);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("[process-events] error:", message);
    await sendHeartbeat("com.omega.vercel.process-events", "error");
    return NextResponse.json({ error: message }, { status: 500 });
  }
```

**Step 2: Add heartbeat to `/api/digest/route.ts`**

Import `sendHeartbeat`. Add `await sendHeartbeat("com.omega.vercel.digest")` before the final `return` in the success path. Add error heartbeat in catch blocks.

**Step 3: Add heartbeat to `/api/notify/route.ts`**

Import `sendHeartbeat`. Add `await sendHeartbeat("com.omega.vercel.notify")` before each `return NextResponse.json(...)`.

**Step 4: Add heartbeat to `/api/optimize-slots/route.ts`**

Import `sendHeartbeat`. Add `await sendHeartbeat("com.omega.vercel.optimize-slots")` before the final return.

**Step 5: Add heartbeat to `/api/process-reply-queue/route.ts`**

Import `sendHeartbeat`. Add `await sendHeartbeat("com.omega.vercel.process-reply-queue")` before the final return.

**Step 6: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 7: Commit**

```bash
git add website/app/api/digest/route.ts website/app/api/notify/route.ts website/app/api/process-events/route.ts website/app/api/optimize-slots/route.ts website/app/api/process-reply-queue/route.ts
git commit -m "feat(jobs): wire heartbeat into all 5 Vercel cron API routes"
```

---

### Task 4: Wire Heartbeat into Python Maintenance Pipeline

**Files:**
- Modify: `src/omega/server/hook_server/maintenance.py`

**Step 1: Add heartbeat function**

After the imports (around line 32), add:

```python
def _send_heartbeat(stage_name: str, status: str = "ok") -> None:
    """Best-effort heartbeat to Supabase schedules table."""
    try:
        import os
        import httpx
        url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return
        label = f"com.omega.maintenance.{stage_name.replace('_', '-')}"
        httpx.post(
            f"{url}/rest/v1/schedules",
            params={"label": f"eq.{label}"},
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"last_status": status, "last_run_at": datetime.now(timezone.utc).isoformat()},
            timeout=5,
        )
    except Exception:
        pass  # Never crash maintenance for heartbeat
```

**Step 2: Call heartbeat after each stage completes**

In `MaintenancePipeline._run_stage` (around line 287), after a stage completes successfully (where `step.status = StepStatus.COMPLETED` is set), add:

```python
_send_heartbeat(stage.name, "ok")
```

And after failure (where `step.status = StepStatus.FAILED` is set), add:

```python
_send_heartbeat(stage.name, "error")
```

**Step 3: Verify it passes tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/ -x -q 2>&1 | tail -5`

**Step 4: Commit**

```bash
git add src/omega/server/hook_server/maintenance.py
git commit -m "feat(jobs): wire heartbeat into maintenance pipeline stages"
```

---

### Task 5: Create Unified Seed Script

**Files:**
- Create: `website/scripts/seed-all-schedules.py`

**Step 1: Write the seed script**

This script upserts all 32 jobs from all 7 sources into the `schedules` table. It replaces the need to run `seed-schedules.py` and `seed-cowork-schedules.py` separately.

```python
#!/usr/bin/env python3
"""Unified seed: upsert ALL scheduled jobs into Supabase schedules table.

Sources: launchd plists, cowork tasks, manual jobs, GitHub Actions,
Vercel crons, and maintenance pipeline stages.

Usage:
    python3 scripts/seed-all-schedules.py
"""

import json
import os
import sys
from pathlib import Path

# Load .env.local if available
env_file = Path(__file__).resolve().parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("pip install httpx", file=sys.stderr)
    sys.exit(1)


def upsert(client: httpx.Client, url: str, headers: dict, schedules: list[dict], source: str) -> None:
    """Upsert a batch of schedules, injecting source into metadata."""
    for s in schedules:
        meta = s.get("metadata") or {}
        meta["source"] = source
        s["metadata"] = meta
        resp = client.post(
            url,
            headers={**headers, "Prefer": "resolution=merge-duplicates"},
            json=s,
        )
        status = "OK" if resp.status_code in (200, 201) else f"ERR {resp.status_code}"
        print(f"  [{status}] {s['label']} ({s['name']})")


# ─── GitHub Actions: cron-jobs.yml ─────────────────────
GITHUB_ACTIONS_MAIN = [
    {
        "label": "com.omega.github.process-events",
        "name": "Process Events",
        "description": "Processes pending_events table (morning run)",
        "schedule_type": "calendar",
        "calendar_hour": 11, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "npx tsx scripts/worker.ts process-events",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.github.generate-hourly",
        "name": "Generate Tweets",
        "description": "Generates tweets for scheduled time slots",
        "schedule_type": "calendar",
        "calendar_hour": 12, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "npx tsx scripts/worker.ts generate-hourly",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.github.publish",
        "name": "Publish",
        "description": "Publishes approved tweets to X and LinkedIn, collects metrics",
        "schedule_type": "calendar",
        "calendar_hour": 14, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "npx tsx scripts/worker.ts publish",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.github.inbox-sync",
        "name": "Inbox Sync",
        "description": "Syncs Gmail inbox items (paired with publish)",
        "schedule_type": "calendar",
        "calendar_hour": 14, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "npx tsx scripts/worker.ts inbox-sync",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.github.inbox-followups",
        "name": "Inbox Follow-ups",
        "description": "Scans high-score inbox threads for follow-up opportunities",
        "schedule_type": "calendar",
        "calendar_hour": 15, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "npx tsx scripts/worker.ts inbox-followups",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.github.x-brief",
        "name": "X Brief (GH Actions)",
        "description": "AI news scan via Grok, stores to memories, emails brief",
        "schedule_type": "calendar",
        "calendar_hour": 0, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "npx tsx scripts/worker.ts x-brief",
        "last_status": "unknown",
    },
]

# ─── GitHub Actions: omega-crons.yml ──────────────────
GITHUB_ACTIONS_OMEGA = [
    {
        "label": "com.omega.github.omega-generate",
        "name": "Omega Generate",
        "description": "Generates 4 @omega_memory tweets for the day (8 AM ET)",
        "schedule_type": "calendar",
        "calendar_hour": 20, "calendar_minute": 5, "calendar_weekday": None,
        "enabled": True,
        "command": "npx tsx scripts/worker.ts generate-omega",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.github.omega-publish",
        "name": "Omega Publish",
        "description": "Publishes due @omega_memory tweets (4x daily ET schedule)",
        "schedule_type": "interval",
        "interval_seconds": 14400,
        "calendar_hour": None, "calendar_minute": None, "calendar_weekday": None,
        "enabled": True,
        "command": "npx tsx scripts/worker.ts publish",
        "last_status": "unknown",
    },
]

# ─── Vercel Crons ─────────────────────────────────────
VERCEL_CRONS = [
    {
        "label": "com.omega.vercel.digest",
        "name": "Daily Digest",
        "description": "Emails a digest of notable OMEGA memories from the last 24h",
        "schedule_type": "calendar",
        "calendar_hour": 23, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "POST /api/digest (Vercel cron)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.vercel.notify",
        "name": "Alert Scanner",
        "description": "Checks for overdue reminders, publish failures, stuck batches, and job failures",
        "schedule_type": "calendar",
        "calendar_hour": 3, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "POST /api/notify (Vercel cron)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.vercel.optimize-slots",
        "name": "Slot Optimizer",
        "description": "Weekly optimization of tweet posting hours from engagement data",
        "schedule_type": "calendar",
        "calendar_hour": 11, "calendar_minute": 0, "calendar_weekday": 0,
        "enabled": True,
        "command": "GET /api/optimize-slots (Vercel cron)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.vercel.process-reply-queue",
        "name": "Reply Queue",
        "description": "Sends approved engagement replies and reply-to-reply alerts",
        "schedule_type": "calendar",
        "calendar_hour": 20, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "GET /api/process-reply-queue (Vercel cron)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.vercel.process-events",
        "name": "Event Processor (Vercel)",
        "description": "Processes up to 10 pending events per invocation",
        "schedule_type": "calendar",
        "calendar_hour": 15, "calendar_minute": 0, "calendar_weekday": None,
        "enabled": True,
        "command": "GET /api/process-events (Vercel cron)",
        "last_status": "unknown",
    },
]

# ─── Maintenance Pipeline ─────────────────────────────
MAINTENANCE = [
    {
        "label": "com.omega.maintenance.consolidate",
        "name": "Memory Consolidation",
        "description": "Consolidates related memories into summaries",
        "schedule_type": "interval",
        "interval_seconds": 7 * 86400,
        "calendar_hour": None, "calendar_minute": None, "calendar_weekday": None,
        "enabled": True,
        "command": "session-triggered (maintenance pipeline)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.maintenance.compact",
        "name": "Store Compaction",
        "description": "Deduplicates and prunes the memory store",
        "schedule_type": "interval",
        "interval_seconds": 14 * 86400,
        "calendar_hour": None, "calendar_minute": None, "calendar_weekday": None,
        "enabled": True,
        "command": "session-triggered (maintenance pipeline)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.maintenance.backup",
        "name": "Memory Backup",
        "description": "Exports memories to JSON, rotates last 4 backups",
        "schedule_type": "interval",
        "interval_seconds": 7 * 86400,
        "calendar_hour": None, "calendar_minute": None, "calendar_weekday": None,
        "enabled": True,
        "command": "session-triggered (maintenance pipeline)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.maintenance.doctor",
        "name": "FTS5 Doctor",
        "description": "FTS5 integrity check and health diagnostics",
        "schedule_type": "interval",
        "interval_seconds": 7 * 86400,
        "calendar_hour": None, "calendar_minute": None, "calendar_weekday": None,
        "enabled": True,
        "command": "session-triggered (maintenance pipeline)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.maintenance.doc-scan",
        "name": "Document Scanner",
        "description": "Scans documents folder for new files to ingest",
        "schedule_type": "interval",
        "interval_seconds": 3600,
        "calendar_hour": None, "calendar_minute": None, "calendar_weekday": None,
        "enabled": True,
        "command": "session-triggered (maintenance pipeline)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.maintenance.cloud-pull",
        "name": "Cloud Pull",
        "description": "Pulls new memories from Supabase cloud sync",
        "schedule_type": "interval",
        "interval_seconds": 86400,
        "calendar_hour": None, "calendar_minute": None, "calendar_weekday": None,
        "enabled": True,
        "command": "session-triggered (maintenance pipeline)",
        "last_status": "unknown",
    },
    {
        "label": "com.omega.maintenance.surfacing-gc",
        "name": "Surfacing GC",
        "description": "Cleans stale surfacing counter files",
        "schedule_type": "interval",
        "interval_seconds": 0,
        "calendar_hour": None, "calendar_minute": None, "calendar_weekday": None,
        "enabled": True,
        "command": "session-triggered (every session)",
        "last_status": "unknown",
    },
]


def main():
    url = f"{SUPABASE_URL}/rest/v1/schedules"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client() as client:
        print("─── GitHub Actions (cron-jobs.yml) ───")
        upsert(client, url, headers, GITHUB_ACTIONS_MAIN, "github_actions")

        print("\n─── GitHub Actions (omega-crons.yml) ───")
        upsert(client, url, headers, GITHUB_ACTIONS_OMEGA, "github_actions")

        print("\n─── Vercel Crons ───")
        upsert(client, url, headers, VERCEL_CRONS, "vercel_cron")

        print("\n─── Maintenance Pipeline ───")
        upsert(client, url, headers, MAINTENANCE, "maintenance")

    print(f"\nDone. {len(GITHUB_ACTIONS_MAIN) + len(GITHUB_ACTIONS_OMEGA) + len(VERCEL_CRONS) + len(MAINTENANCE)} jobs seeded.")
    print("Verify at https://omegamax.co/admin > Jobs tab.")


if __name__ == "__main__":
    main()
```

**Step 2: Run the seed script**

Run: `cd ~/Projects/omega/website && python3 scripts/seed-all-schedules.py`
Expected: All 20 new jobs upserted successfully

**Step 3: Commit**

```bash
git add website/scripts/seed-all-schedules.py
git commit -m "feat(jobs): add unified seed script for all 20 missing jobs"
```

---

### Task 6: Update ownerBadge for New Sources

**Files:**
- Modify: `website/app/admin/components/jobs/jobUtils.ts:203-216`
- Modify: `website/app/admin/components/jobs/atoms.tsx:67-87`

**Step 1: Update `ownerBadge` in `jobUtils.ts`**

Replace `ownerBadge` function (lines 203-216):

```typescript
export function ownerBadge(label: string): { text: string; cls: string } {
  if (label.startsWith("com.omega.github"))
    return { text: "github", cls: "bg-[#238636]/15 text-[#58a65c]" };
  if (label.startsWith("com.omega.vercel"))
    return { text: "vercel", cls: "bg-[#0070f3]/15 text-[#4da3ff]" };
  if (label.startsWith("com.omega.maintenance"))
    return { text: "maint", cls: "bg-type-observation/15 text-type-observation" };
  if (label.startsWith("com.omega.cowork"))
    return { text: "cowork", cls: "bg-type-lesson/15 text-type-lesson" };
  if (label.startsWith("com.omega"))
    return { text: "omega", cls: "bg-gold/[0.12] text-gold" };
  if (label.startsWith("com.claude"))
    return { text: "claude", cls: "bg-type-decision/15 text-type-decision" };
  if (label.startsWith("com.magma"))
    return {
      text: "magma",
      cls: "bg-type-preference/15 text-type-preference",
    };
  return { text: "system", cls: "bg-surface-elevated text-ink-tertiary" };
}
```

**Step 2: Update `OwnerBadge` component in `atoms.tsx`**

Replace the `OwnerBadge` function (lines 67-87) to use the shared `ownerBadge` function from jobUtils:

```typescript
import { type JobStatus, STATUS_CONFIG, ownerBadge } from "./jobUtils";

// ... (existing StatusPill, ScheduleChip, ToggleSwitch unchanged)

export function OwnerBadge({ label }: { label: string }) {
  const { text, cls } = ownerBadge(label);
  return (
    <span className={`text-[14px] font-semibold px-2.5 py-0.5 rounded-full ${cls}`}>
      {text}
    </span>
  );
}
```

**Step 3: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`

**Step 4: Commit**

```bash
git add website/app/admin/components/jobs/jobUtils.ts website/app/admin/components/jobs/atoms.tsx
git commit -m "feat(jobs): add github, vercel, maint owner badges for new job sources"
```

---

### Task 7: Remove pending_changes and "syncing" Badge

**Files:**
- Modify: `website/app/api/schedules/route.ts:29-65` (PATCH handler)
- Modify: `website/app/api/schedules/route.ts:72-97` (DELETE handler)
- Modify: `website/app/admin/components/jobs/JobRow.tsx:53-58`

**Step 1: Remove pending_changes from PATCH handler**

In `route.ts`, remove line 49:
```typescript
  update.pending_changes = { action: "edit", fields: update, queued_at: new Date().toISOString() };
```

Replace with:
```typescript
  // Clear any stale pending_changes on edit
  update.pending_changes = null;
```

**Step 2: Remove pending_changes from DELETE handler**

In `route.ts`, change the DELETE update (lines 83-86) from:
```typescript
    .update({
      enabled: false,
      pending_changes: { action: "delete", queued_at: new Date().toISOString() },
    })
```
To:
```typescript
    .update({
      enabled: false,
      pending_changes: null,
    })
```

**Step 3: Remove "syncing" badge from JobRow**

In `JobRow.tsx`, remove lines 22 and 53-58:

Remove `const isPending = schedule.pending_changes !== null;` (line 22)

Remove the syncing badge JSX:
```tsx
            {isPending && (
              <span className="text-[14px] font-medium text-type-reminder/80 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-type-reminder animate-pulse" />
                syncing
              </span>
            )}
```

**Step 4: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`

**Step 5: Commit**

```bash
git add website/app/api/schedules/route.ts website/app/admin/components/jobs/JobRow.tsx
git commit -m "fix(jobs): remove pending_changes queue (no consumer existed)"
```

---

### Task 8: Make Remote Jobs Read-Only in UI

**Files:**
- Modify: `website/app/admin/components/jobs/jobUtils.ts` (add helper)
- Modify: `website/app/admin/components/jobs/JobDetailPanel.tsx`

**Step 1: Add source helper to jobUtils.ts**

After the `ownerBadge` function, add:

```typescript
/** Sources where the schedule is defined in code and not editable from UI. */
const READ_ONLY_SOURCES = new Set(["github_actions", "vercel_cron", "maintenance"]);

export function isReadOnly(s: Schedule): boolean {
  const source = (s.metadata as Record<string, unknown>)?.source;
  return typeof source === "string" && READ_ONLY_SOURCES.has(source);
}

export function sourceLabel(s: Schedule): string | null {
  const source = (s.metadata as Record<string, unknown>)?.source;
  if (source === "github_actions") return "Defined in GitHub Actions workflow";
  if (source === "vercel_cron") return "Defined in vercel.json";
  if (source === "maintenance") return "Session-triggered maintenance stage";
  return null;
}
```

**Step 2: Update JobDetailPanel to show read-only mode**

Import the new helpers:
```typescript
import {
  type Schedule,
  type ScheduleMetadata,
  type AccountInfo,
  computeStatus,
  humanSchedule,
  isReadOnly,
  sourceLabel,
} from "./jobUtils";
```

Replace the Schedule editor section (lines 662-669) with:

```tsx
        {/* Schedule editor or read-only notice */}
        <section>
          <h3 className="text-[14px] text-ink-faint uppercase tracking-wider font-medium mb-3">
            Schedule
          </h3>
          {isReadOnly(schedule) ? (
            <div className="text-[15px] text-ink-tertiary bg-surface-elevated rounded-lg p-4 border border-edge/50">
              <div className="font-mono mb-2">{humanSchedule(schedule)}</div>
              <div className="text-[14px] text-ink-faint">
                {sourceLabel(schedule)}. To change the schedule, edit the source file directly.
              </div>
            </div>
          ) : (
            <ScheduleEditor
              schedule={schedule}
              onSave={(fields) => onUpdate(schedule.id, fields)}
            />
          )}
        </section>
```

Replace the Delete section (lines 694-700) with:

```tsx
        {/* Delete (only for editable jobs) */}
        {!isReadOnly(schedule) && (
          <div className="pt-4 border-t border-edge">
            <DeleteSection
              name={schedule.name}
              onDelete={() => onDelete(schedule.id)}
            />
          </div>
        )}
```

**Step 3: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`

**Step 4: Commit**

```bash
git add website/app/admin/components/jobs/jobUtils.ts website/app/admin/components/jobs/JobDetailPanel.tsx
git commit -m "feat(jobs): read-only mode for github/vercel/maintenance jobs"
```

---

### Task 9: Enhance /api/notify with Job Failure Alerts

**Files:**
- Modify: `website/app/api/notify/route.ts`

**Step 1: Add schedule_failure check**

After the "Check schedule failures (batches stuck)" block (after line 107), add a new check:

```typescript
  // Check job failures (schedules with last_status = "error")
  if (categories.includes("schedule_failure")) {
    const { data: failedJobs } = await db
      .from("schedules")
      .select("id, label, name, last_run_at")
      .eq("last_status", "error")
      .eq("enabled", true)
      .limit(10);

    for (const j of failedJobs || []) {
      alerts.push({
        data: {
          title: `Job failed: ${j.name}`,
          body: `${j.label} reported an error${j.last_run_at ? ` at ${timeAgo(new Date(j.last_run_at))}` : ""}. Check the Jobs tab for details.`,
          type: "schedule_failure",
          adminTab: "jobs",
        },
        memoryId: j.id,
      });
    }
  }
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`

**Step 3: Commit**

```bash
git add website/app/api/notify/route.ts
git commit -m "feat(jobs): add job failure alerts to /api/notify"
```

---

### Task 10: Update Status Model for Maintenance Jobs

**Files:**
- Modify: `website/app/admin/components/jobs/jobUtils.ts`

**Step 1: Update computeStatus for maintenance jobs**

The maintenance jobs have large intervals (7d, 14d) and are session-triggered, so the "late" detection needs wider grace. Update `computeStatus` (lines 62-80):

```typescript
export function computeStatus(s: Schedule): JobStatus {
  if (!s.enabled) return "paused";
  if (s.last_status === "error") return "error";
  if (!s.last_run_at || s.last_status === "unknown") return "new";

  const source = (s.metadata as Record<string, unknown>)?.source;

  // Check if overdue
  const nextRun = computeNextRun(s);
  if (nextRun) {
    let grace: number;
    if (source === "maintenance") {
      // Maintenance jobs get 2x their interval as grace (session-triggered, not time-exact)
      grace = (s.interval_seconds ?? 0) * 1000;
    } else if (s.schedule_type === "calendar") {
      grace = s.calendar_weekday != null ? WEEKLY_GRACE_MS : DAILY_GRACE_MS;
    } else {
      grace = INTERVAL_GRACE_MS;
    }
    if (Date.now() > nextRun.getTime() + grace) return "late";
  }

  return "healthy";
}
```

**Step 2: Verify it compiles**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit 2>&1 | head -20`

**Step 3: Commit**

```bash
git add website/app/admin/components/jobs/jobUtils.ts
git commit -m "feat(jobs): widen grace period for maintenance jobs in status model"
```

---

### Task 11: Build and Verify

**Files:** None (verification only)

**Step 1: Run full build**

Run: `cd ~/Projects/omega/website && npm run build 2>&1 | tail -20`
Expected: Build succeeds

**Step 2: Run lint**

Run: `cd ~/Projects/omega/website && npm run lint 2>&1 | tail -10`
Expected: No errors

**Step 3: Run the seed script to populate all missing jobs**

Run: `cd ~/Projects/omega/website && python3 scripts/seed-all-schedules.py`
Expected: 20 jobs upserted

**Step 4: Deploy to Vercel**

Run: `cd ~/Projects/omega/website && vercel --prod 2>&1 | tail -10`
Expected: Deployed successfully

**Step 5: Verify the Jobs tab**

Open https://omegamax.co/admin > Jobs tab. Verify:
- All 32 jobs are listed
- GitHub Actions jobs show "github" badge
- Vercel cron jobs show "vercel" badge
- Maintenance jobs show "maint" badge
- Clicking a GitHub Actions job shows "Defined in GitHub Actions workflow" instead of ScheduleEditor
- Toggle still works on all jobs
- No "syncing" badge appears anywhere

**Step 6: Final commit**

```bash
git commit --allow-empty -m "chore: jobs tab completeness verified and deployed"
```
