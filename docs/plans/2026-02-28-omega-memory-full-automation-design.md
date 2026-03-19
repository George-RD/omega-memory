# @omega_memory Full Automation Design

**Date**: 2026-02-28
**Status**: Approved
**Scope**: Fully automate @omega_memory X account — 2-3 tweets/day + 3-5 replies/day

## Problem

The @omega_memory pipeline generates content and reply suggestions, but every item requires manual admin approval. This creates a daily 20-30 min overhead and delays posting. The account should run autonomously with a 30-minute veto window as the only human touchpoint.

## Design Decisions

- **Reply target selection**: Scan tiered target accounts (Tier 1/2/3 from `engagement_targets` table), not keyword discovery
- **Safety model**: Delayed auto-publish with 30-min veto window (not fire-and-forget, not push notifications)
- **@jasonsosa unchanged**: All automation is scoped to `omega_memory` only

## Architecture

```
GENERATE (GH Actions)              VETO WINDOW (30 min)           PUBLISH (Vercel cron)
========================           =====================           =====================

generate-omega (1x/day)            Admin dashboard                 publish cron (5x/day)
  Claude drafts 3 tweets   ──>     Veto within 30 min?    ──>     Posts to X at slot time
  Score >= 7: auto-approve          (status: approved)              getDueTweets() picks up
  Score < 7: stays pending          (scheduled_for + 30m)

scan-and-reply (3x/day)            Admin dashboard                 process-reply-queue (every 15m)
  Fetch target tweets       ──>     Veto within 30 min?    ──>     Sends via fallback chain
  Filter for relevance              (status: approved)              (quote tweet -> standalone)
  Generate reply w/ Claude          (scheduled_send_at + 30m)
  Cap: 2 per scan, 5/day

daily-summary (1x/day)
  Email recap of all omega_memory activity from last 24h
```

## Component Details

### 1. Tweet Auto-Approval

**Where**: `lib/generate.ts` — after `insertTweet` / `insertThreadTweets`

**Logic**: When `account === "omega_memory"` and best score >= 7:
- Set `status: "approved"` (instead of `"pending"`)
- Set `scheduled_for: original_slot_time + 30min`

When best score < 7:
- Keep `status: "pending"` for manual review (do NOT use the weak attempt automatically)

**Volume**: Reduce from 4 to 3 slots/day:
- `OMEGA_DEFAULT_SLOT_HOURS`: `[8, 12, 16, 19]` -> `[9, 16, 20]` (ET)
- `MAX_OMEGA_SLOTS` in worker.ts: 4 -> 3
- Corresponding vercel.json publish crons: remove 1, adjust times

### 2. Target Account Scanning

**New file**: `lib/target-scanner.ts`

**Responsibilities**:
- `fetchTargetTweets(account: XAccount)`: Read targets from `engagement_targets` (filtered by `x_account`), fetch each target's recent tweets via X API v2 `GET /2/users/:id/tweets` (last 6 hours)
- `filterRelevantTweets(tweets)`: Claude fast-tier relevance check — is this about AI agents, memory, MCP, developer tools?
- `dedup(tweets)`: Skip tweets already in `engagement_suggestions` table
- Returns: Array of relevant, non-duplicate tweet objects ready for reply generation

**X API rate limits**: User tweet timeline is 900 req/15min. With ~15 targets across 3 tiers, 3 scans/day = 45 requests — well within limits.

### 3. Scan-and-Reply Route

**New file**: `app/api/omega/scan-and-reply/route.ts`

**`GET` handler** (Vercel cron, Bearer CRON_SECRET auth):
1. Check `getEngagementQuota("omega_memory")` — skip if at daily limit
2. Call `fetchTargetTweets("omega_memory")`
3. Call `filterRelevantTweets(tweets)` — Claude fast-tier relevance filter
4. Call `dedup(tweets)` — skip already-suggested source_tweet_ids
5. Take top 2 (sorted by target tier, then recency)
6. For each: `generateReplySuggestion(tweet, "omega_memory")`
7. Insert into `engagement_suggestions` with:
   - `status: "approved"`
   - `scheduled_send_at: now + 30min`
   - `x_account: "omega_memory"`
   - `metadata: { auto_generated: true, target_tier: N }`
8. Return JSON summary

**Schedule**: 3x/day — `0 14 * * *`, `0 18 * * *`, `0 22 * * *` (9 AM, 1 PM, 5 PM ET)

**`maxDuration`**: 120s (multiple X API calls + Claude calls)

### 4. Quota Enforcement

**Where**: `lib/engagement.ts` — inside `sendApprovedReply`

**Change**: Before sending, call `getEngagementQuota(account)`. If `at_limit === true`, update suggestion to `status: "quota_exceeded"` instead of sending. This prevents the 15-min cron from over-sending if multiple scan runs queued items on the same day.

### 5. Daily Summary Email

**New file**: `app/api/omega/daily-summary/route.ts`

**`GET` handler** (Vercel cron):
1. Query tweets: `x_account = "omega_memory" AND published_at >= 24h ago`
2. Query engagement_suggestions: `x_account = "omega_memory" AND sent_at >= 24h ago`
3. Query vetoed: `x_account = "omega_memory" AND status = "rejected" AND updated_at >= 24h ago`
4. Format email with sections: Posts (text + metrics), Replies (target + text + type), Vetoed (if any)
5. Send via `sendEmail` (Resend)

**Schedule**: `0 1 * * *` (8 AM ICT daily)

**`maxDuration`**: 30s (DB queries + email send)

### 6. Vercel Cron Changes

**vercel.json additions**:
```json
{"path": "/api/omega/scan-and-reply", "schedule": "0 14 * * *"},
{"path": "/api/omega/scan-and-reply", "schedule": "0 18 * * *"},
{"path": "/api/omega/scan-and-reply", "schedule": "0 22 * * *"},
{"path": "/api/omega/daily-summary",  "schedule": "0 1 * * *"}
```

**vercel.json modifications** (omega publish slots 4 -> 3):
- Remove: `"5 13 * * *"` (8 AM ET slot)
- Keep: `"35 17 * * *"` -> change to `"0 14 * * *"` (9 AM ET)
- Keep: `"5 21 * * *"` -> change to `"0 21 * * *"` (4 PM ET)
- Keep: `"35 0 * * *"` -> change to `"0 1 * * *"` (8 PM ET)

Wait — the publish cron is shared for both accounts. The `getDueTweets()` call returns tweets for ALL accounts. So we don't need per-account publish crons. The main daily publish at `0 7 * * *` plus the 3 omega-time publishes cover both accounts. Adjustments:
- Remove `5 13 * * *` omega publish (generate-omega on GH Actions still runs at 13:05 UTC)
- Adjust remaining 3 omega publish times to match new slot hours + 30min veto

### 7. Files Summary

| File | Action |
|------|--------|
| `lib/target-scanner.ts` | Create — X API target scanning + relevance filter |
| `app/api/omega/scan-and-reply/route.ts` | Create — cron endpoint for auto-reply pipeline |
| `app/api/omega/daily-summary/route.ts` | Create — daily email summary |
| `lib/generate.ts` | Modify — auto-approve omega_memory tweets (score >= 7, +30min delay) |
| `lib/schedule.ts` | Modify — `OMEGA_DEFAULT_SLOT_HOURS` [8,12,16,19] -> [9,16,20] |
| `lib/engagement.ts` | Modify — quota enforcement in `sendApprovedReply` |
| `scripts/worker.ts` | Modify — `MAX_OMEGA_SLOTS` 4 -> 3 |
| `website/vercel.json` | Modify — add 4 crons, adjust 3 omega publish times |
| `scripts/seed-all-schedules.py` | Modify — add new job DB records |

### 8. What Stays Manual

- **@jasonsosa**: entirely manual, no changes
- **omega_memory tweets scoring < 7**: manual review required
- **Target tier management**: admin UI
- **Engagement quota adjustment**: DB / admin UI
- **Veto**: check admin dashboard within 30 min of generation (items show as "approved, pending publish")
