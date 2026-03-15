# Jobs Tab Completeness Fix

**Date**: 2026-02-27
**Status**: Approved
**Scope**: Admin dashboard Jobs tab, worker heartbeat, seed scripts, notification enhancement

## Problem

The Jobs tab shows 12 seeded jobs but is missing 20+ jobs from GitHub Actions, Vercel crons, and the Python maintenance pipeline. Status is always "new" because no heartbeat calls exist. Edits queue `pending_changes` with no consumer. Notifications don't cover job failures.

## Design Decisions

### 1. Seed All Missing Jobs

Create `seed-all-schedules.py` that upserts all job sources into the `schedules` table:

| Source | Label prefix | Count | `metadata.source` |
|--------|-------------|-------|--------------------|
| launchd | `com.omega.*`, `com.claude.*`, `com.magma.*` | 7 | `launchd` |
| Cowork | `com.omega.cowork.*` | 4 | `cowork` |
| Manual | `com.omega.blog-threads` | 1 | `manual` |
| GitHub Actions (cron-jobs.yml) | `com.omega.github.*` | 6 | `github_actions` |
| GitHub Actions (omega-crons.yml) | `com.omega.github.omega-*` | 2 | `github_actions` |
| Vercel crons | `com.omega.vercel.*` | 5 | `vercel_cron` |
| Maintenance pipeline | `com.omega.maintenance.*` | 7 | `maintenance` |

**GitHub Actions jobs to seed** (from `cron-jobs.yml`):
- `com.omega.github.process-events` - Daily 11:00 ICT
- `com.omega.github.generate-hourly` - Daily 12:00 ICT
- `com.omega.github.publish` - Daily 14:00 ICT
- `com.omega.github.inbox-followups` - Daily 15:00 ICT
- `com.omega.github.inbox-sync` - Daily 14:00 ICT (paired with publish)
- `com.omega.github.x-brief` - Daily 00:00 ICT

**GitHub Actions jobs to seed** (from `omega-crons.yml`):
- `com.omega.github.omega-generate` - Daily 20:00 ICT (8 AM ET)
- `com.omega.github.omega-publish` - 4x daily (12:30/4:00/7:30 PM ET + with generate)

**Vercel crons to seed** (from `vercel.json`):
- `com.omega.vercel.digest` - Daily 16:00 UTC
- `com.omega.vercel.notify` - Daily 20:00 UTC
- `com.omega.vercel.optimize-slots` - Weekly Sun 04:00 UTC
- `com.omega.vercel.process-reply-queue` - Daily 13:00 UTC
- `com.omega.vercel.process-events` - Daily 08:00 UTC

**Maintenance stages to seed**:
- `com.omega.maintenance.consolidate` - Every 7d (session-triggered)
- `com.omega.maintenance.compact` - Every 14d
- `com.omega.maintenance.backup` - Every 7d
- `com.omega.maintenance.doctor` - Every 7d
- `com.omega.maintenance.doc-scan` - Every 1h
- `com.omega.maintenance.cloud-pull` - Every 24h
- `com.omega.maintenance.surfacing-gc` - Every session

### 2. Wire Heartbeat Calls

**worker.ts** (GitHub Actions): Add heartbeat call at end of `runJob()`. Map job names to labels:
```
generate-hourly -> com.omega.github.generate-hourly
process-events  -> com.omega.github.process-events
publish         -> com.omega.github.publish
x-brief         -> com.omega.github.x-brief
inbox-sync      -> com.omega.github.inbox-sync
inbox-followups -> com.omega.github.inbox-followups
generate-omega  -> com.omega.github.omega-generate
```

Call: `POST ${SITE_URL}/api/schedules/heartbeat` with `{ label, status: "ok"|"error" }`.

**Vercel API routes**: Add heartbeat call at end of each handler (notify, digest, optimize-slots, process-reply-queue, process-events).

**Maintenance pipeline**: Add heartbeat call in `maintenance.py` after each stage completes.

### 3. Make Remote Jobs Read-Only

Jobs with `metadata.source` in `["github_actions", "vercel_cron", "maintenance"]`:
- Hide ScheduleEditor in JobDetailPanel
- Hide DeleteSection
- Show a "Defined in code" note instead
- Toggle still works (controls `enabled` flag in DB, used by the API route to skip)

### 4. Remove `pending_changes` Queue

- Remove `pending_changes` assignment from PATCH route (line 49)
- Remove `pending_changes` assignment from DELETE route (line 85)
- Remove "syncing" badge from JobRow (line 53-58)
- Add disclaimer text in detail panel for launchd jobs: "Schedule shown here. Restart the launchd agent to apply changes."

### 5. Enhance Failure Notifications

Add to `/api/notify` route:
- New `schedule_failure` category: query `schedules` table for `last_status = 'error'` and `enabled = true`
- Generate alert for each failed job with link to Jobs tab

### 6. UI Updates

**ownerBadge** in `jobUtils.ts`: Add badges for new label prefixes:
- `com.omega.github` -> "github" badge (blue)
- `com.omega.vercel` -> "vercel" badge (teal)
- `com.omega.maintenance` -> "maint" badge (purple)

**JobList header**: Update "9 active" to correctly count and show grouped counts.

**Status model for maintenance jobs**: Since these are session-triggered, not time-scheduled:
- `computeNextRun` returns `null` for maintenance jobs (no predictable next run)
- `computeStatus` uses a wider grace period (2x the interval gate) for staleness detection
- Display "last ran Xd ago" instead of "next run" for these jobs

## Files to Modify

| File | Change |
|------|--------|
| `website/scripts/seed-all-schedules.py` | **NEW** - unified seed script |
| `website/scripts/worker.ts` | Add heartbeat call at end of runJob |
| `website/app/api/schedules/route.ts` | Remove pending_changes from PATCH/DELETE |
| `website/app/api/notify/route.ts` | Add schedule_failure check |
| `website/app/admin/components/jobs/jobUtils.ts` | New badges, maintenance status model |
| `website/app/admin/components/jobs/JobRow.tsx` | Remove "syncing" badge |
| `website/app/admin/components/jobs/JobDetailPanel.tsx` | Read-only mode for remote jobs |
| `website/app/admin/components/jobs/JobList.tsx` | Minor header update |
| `src/omega/server/hook_server/maintenance.py` | Add heartbeat calls after each stage |
| Vercel API routes (5 files) | Add heartbeat calls |
