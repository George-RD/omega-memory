# @omega_memory Full Automation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fully automate @omega_memory X account with 2-3 tweets/day and 3-5 replies/day, using a 30-minute veto window before publishing.

**Architecture:** Three changes layered on existing infrastructure: (1) auto-approve generated tweets with a 30-min delay, (2) new cron that scans target accounts and auto-generates replies, (3) daily summary email. No new queuing systems — reuses existing `publish` and `process-reply-queue` crons.

**Tech Stack:** Next.js API routes (Vercel crons), X API v2 (OAuth 1.0a via `xGet`), Claude Sonnet 4.6 (reply generation), Supabase (DB), Resend via Gmail (email).

---

### Task 1: Reduce omega_memory to 3 slots/day

**Files:**
- Modify: `website/lib/schedule.ts:172`
- Modify: `website/scripts/worker.ts:45`

**Step 1: Update slot hours**

In `website/lib/schedule.ts`, change line 172:

```typescript
// Before:
export const OMEGA_DEFAULT_SLOT_HOURS = [8, 12, 16, 19];

// After:
export const OMEGA_DEFAULT_SLOT_HOURS = [9, 16, 20];
```

**Step 2: Update max slots in worker**

In `website/scripts/worker.ts`, change line 45:

```typescript
// Before:
const MAX_OMEGA_SLOTS = 4;

// After:
const MAX_OMEGA_SLOTS = 3;
```

**Step 3: Update vercel.json omega publish times**

In `website/vercel.json`, replace the 4 omega publish cron entries with 3 entries matching the new slot hours + 30min veto:

```json
{"path": "/api/publish", "schedule": "30 14 * * *"},
{"path": "/api/publish", "schedule": "30 21 * * *"},
{"path": "/api/publish", "schedule": "30 1 * * *"}
```

These are: 9:30 AM ET, 4:30 PM ET, 8:30 PM ET (slot time + 30min veto).

Remove the old 4 omega entries:
- `"5 13 * * *"`, `"35 17 * * *"`, `"5 21 * * *"`, `"35 0 * * *"`

**Step 4: Verify build**

Run: `cd ~/Projects/omega/website && npm run build`
Expected: Build passes.

**Step 5: Commit**

```bash
git add website/lib/schedule.ts website/scripts/worker.ts website/vercel.json
git commit -m "feat(omega): reduce omega_memory to 3 slots/day (9, 16, 20 ET)"
```

---

### Task 2: Auto-approve omega_memory tweets

**Files:**
- Modify: `website/lib/generate.ts:322-370`
- Modify: `website/lib/tweets.ts:85-109` and `111-135`

**Step 1: Add status and scheduled_for override to insertTweet**

In `website/lib/tweets.ts`, modify `insertTweet` (line 85) to accept optional `status` and `scheduled_for_override`:

```typescript
export async function insertTweet(tweet: {
  batch_id: string;
  text: string;
  thread_id?: string | null;
  thread_position?: number;
  content_type: string;
  length_category: string;
  scheduled_for: string;
  day_number: number;
  slot_number: number;
  reply_with_link?: string | null;
  image_suggestion?: string | null;
  engagement_hook?: string | null;
  x_account?: string;
  status?: string;
}): Promise<Tweet> {
  const db = supabaseServer();
  const row: Record<string, unknown> = { x_account: "jasonsosa", ...tweet };
  // Remove undefined status so DB default ("pending") applies when not set
  if (!row.status) delete row.status;
  const { data, error } = await db
    .from("tweets")
    .insert(row)
    .select()
    .single();

  if (error) throw new Error(`Failed to insert tweet: ${error.message}`);
  return data;
}
```

Do the same for `insertThreadTweets` (line 111) — add `status?: string` to the `slot` parameter and pass it through to each row:

```typescript
export async function insertThreadTweets(
  batchId: string,
  threadParts: string[],
  slot: {
    // ... existing fields ...
    x_account?: string;
    status?: string;
  },
): Promise<Tweet[]> {
  const db = supabaseServer();
  const threadId = crypto.randomUUID();
  const account = slot.x_account || "jasonsosa";

  const rows = threadParts.map((text, i) => {
    const row: Record<string, unknown> = {
      batch_id: batchId,
      text,
      thread_id: threadId,
      thread_position: i + 1,
      // ... spread rest of slot fields ...
      x_account: account,
    };
    if (slot.status) row.status = slot.status;
    return row;
  });
  // ... rest unchanged ...
```

**Step 2: Auto-approve in generate.ts**

In `website/lib/generate.ts`, after the quality gate loop (around line 334), add auto-approval logic before the DB save (line 336):

```typescript
  // Auto-approve omega_memory tweets that pass quality gate
  const autoApprove = account === "omega_memory" && bestScore >= MIN_SCORE;
  const VETO_WINDOW_MS = 30 * 60 * 1000; // 30 minutes

  // Step 5: Save to DB
  progress(5, 5, "Saving...");
  const imageSuggestion = (generated.rationale || generated.image_suggestion) as string | undefined;
  const threadParts = generated.thread_parts as string[] | undefined;
  const tweetText = (generated.text as string) || "";

  // For auto-approved tweets, delay scheduled_for by veto window
  const scheduledFor = autoApprove
    ? new Date(new Date(slot.scheduledFor).getTime() + VETO_WINDOW_MS).toISOString()
    : slot.scheduledFor;

  if (slot.lengthCategory === "thread" && threadParts?.length) {
    await insertThreadTweets(batchRow.id, threadParts, {
      content_type: slot.contentType,
      length_category: slot.lengthCategory,
      scheduled_for: scheduledFor,
      day_number: slot.dayNumber,
      slot_number: slot.slotNumber,
      reply_with_link: generated.reply_with_link as string | undefined,
      image_suggestion: imageSuggestion,
      engagement_hook: generated.engagement_hook as string | undefined,
      x_account: account,
      status: autoApprove ? "approved" : undefined,
    });
    log(autoApprove ? "thread auto-approved (30min veto window)" : "thread saved to DB");
  } else {
    await insertTweet({
      batch_id: batchRow.id,
      text: tweetText,
      content_type: slot.contentType,
      length_category: slot.lengthCategory,
      scheduled_for: scheduledFor,
      day_number: slot.dayNumber,
      slot_number: slot.slotNumber,
      reply_with_link: generated.reply_with_link as string | undefined,
      image_suggestion: imageSuggestion,
      engagement_hook: generated.engagement_hook as string | undefined,
      x_account: account,
      status: autoApprove ? "approved" : undefined,
    });
    log(autoApprove ? "tweet auto-approved (30min veto window)" : "tweet saved to DB");
  }
```

**Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npm run build`
Expected: Build passes.

**Step 4: Commit**

```bash
git add website/lib/generate.ts website/lib/tweets.ts
git commit -m "feat(omega): auto-approve omega_memory tweets with 30-min veto window"
```

---

### Task 3: Add user timeline fetch to x-client

**Files:**
- Modify: `website/lib/x-client.ts`

**Step 1: Add getUserTweets function**

Append to `website/lib/x-client.ts` before the closing `isRateLimit` function:

```typescript
/**
 * Fetch recent tweets from a user by their X handle.
 * Uses X API v2 GET /2/users/by/username/:username then /2/users/:id/tweets
 */
export async function getUserRecentTweets(
  handle: string,
  maxResults = 10,
  sinceHoursAgo = 6,
  account: XAccount = DEFAULT_ACCOUNT,
): Promise<{ id: string; text: string; created_at: string }[]> {
  // Step 1: Resolve handle to user ID
  const userRes = await xGet(
    `https://api.twitter.com/2/users/by/username/${handle}`,
    {},
    account,
  ) as { data?: { id: string } };

  if (!userRes.data?.id) return [];

  // Step 2: Fetch recent tweets
  const since = new Date(Date.now() - sinceHoursAgo * 3600_000).toISOString();
  const tweetsRes = await xGet(
    `https://api.twitter.com/2/users/${userRes.data.id}/tweets`,
    {
      max_results: String(Math.min(maxResults, 100)),
      start_time: since,
      "tweet.fields": "created_at,text",
      exclude: "retweets,replies",
    },
    account,
  ) as { data?: { id: string; text: string; created_at: string }[] };

  return tweetsRes.data ?? [];
}
```

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npm run build`
Expected: Build passes.

**Step 3: Commit**

```bash
git add website/lib/x-client.ts
git commit -m "feat(x-client): add getUserRecentTweets for target scanning"
```

---

### Task 4: Create target scanner module

**Files:**
- Create: `website/lib/target-scanner.ts`

**Step 1: Create the module**

Create `website/lib/target-scanner.ts`:

```typescript
import { listTargets } from "./targets";
import { getUserRecentTweets } from "./x-client";
import { supabaseServer } from "./supabase";
import { llmComplete } from "./llm";
import type { XAccount } from "./x-client";
import type { TargetTier } from "./targets";

export interface ScannedTweet {
  id: string;
  text: string;
  created_at: string;
  author_handle: string;
  author_name: string | null;
  target_tier: TargetTier;
}

const RELEVANCE_PROMPT = `You are a relevance filter for an AI memory systems project account (@omega_memory).

Decide if this tweet is relevant enough to reply to. Relevant topics:
- AI agents, multi-agent systems, agent memory
- MCP (Model Context Protocol)
- AI developer tools (Claude Code, Cursor, Copilot, etc.)
- Local-first AI, SQLite for AI, embeddings
- AI infrastructure, LLM orchestration

Reply with ONLY "yes" or "no". Nothing else.`;

/**
 * Scan target accounts for recent relevant tweets.
 * Returns de-duplicated, relevance-filtered tweets sorted by tier then recency.
 */
export async function scanTargets(
  account: XAccount,
  maxPerScan = 2,
  sinceHoursAgo = 6,
): Promise<ScannedTweet[]> {
  // 1. Get active targets for this account
  const targets = await listTargets(undefined, account);
  const activeTargets = targets.filter((t) => t.active);

  // 2. Fetch recent tweets from each target
  const allTweets: ScannedTweet[] = [];
  for (const target of activeTargets) {
    try {
      const tweets = await getUserRecentTweets(
        target.handle,
        5,
        sinceHoursAgo,
        account,
      );
      for (const tweet of tweets) {
        allTweets.push({
          id: tweet.id,
          text: tweet.text,
          created_at: tweet.created_at,
          author_handle: target.handle,
          author_name: target.display_name,
          target_tier: target.tier,
        });
      }
    } catch (err) {
      // Skip targets that fail (suspended accounts, private, rate limit)
      console.error(`Failed to fetch tweets for @${target.handle}:`, err instanceof Error ? err.message : String(err));
    }
  }

  if (allTweets.length === 0) return [];

  // 3. Dedup against existing suggestions
  const db = supabaseServer();
  const tweetIds = allTweets.map((t) => t.id);
  const { data: existing } = await db
    .from("engagement_suggestions")
    .select("source_tweet_id")
    .in("source_tweet_id", tweetIds);

  const existingIds = new Set((existing ?? []).map((e) => e.source_tweet_id));
  const fresh = allTweets.filter((t) => !existingIds.has(t.id));

  if (fresh.length === 0) return [];

  // 4. Relevance filter via Claude fast-tier
  const relevant: ScannedTweet[] = [];
  for (const tweet of fresh) {
    try {
      const response = await llmComplete({
        modelTier: "fast",
        maxTokens: 8,
        system: RELEVANCE_PROMPT,
        prompt: `Tweet by @${tweet.author_handle}: "${tweet.text}"`,
      });
      if (response.trim().toLowerCase() === "yes") {
        relevant.push(tweet);
      }
    } catch {
      // Skip on LLM errors
    }
    // Stop early if we have enough candidates
    if (relevant.length >= maxPerScan * 2) break;
  }

  // 5. Sort by tier (ascending = higher priority first), then recency
  relevant.sort((a, b) => {
    if (a.target_tier !== b.target_tier) return a.target_tier - b.target_tier;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  return relevant.slice(0, maxPerScan);
}
```

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npm run build`
Expected: Build passes.

**Step 3: Commit**

```bash
git add website/lib/target-scanner.ts
git commit -m "feat(omega): add target scanner for automated reply discovery"
```

---

### Task 5: Add quota enforcement to sendApprovedReply

**Files:**
- Modify: `website/lib/engagement.ts:402-416`

**Step 1: Add quota check**

In `website/lib/engagement.ts`, inside `sendApprovedReply` (line 402), add a quota check after fetching the suggestion and before sending:

```typescript
export async function sendApprovedReply(suggestionId: string): Promise<PostResult> {
  const db = supabaseServer();

  // Fetch the suggestion
  const { data: suggestion, error: fetchErr } = await db
    .from("engagement_suggestions")
    .select()
    .eq("id", suggestionId)
    .single();

  if (fetchErr || !suggestion) throw new Error("Suggestion not found");
  if (suggestion.status !== "approved") throw new Error("Suggestion not approved");

  // Enforce daily quota
  const account = (suggestion.x_account || "jasonsosa") as XAccount;
  const quota = await getEngagementQuota(account);
  if (quota.at_limit) {
    await db
      .from("engagement_suggestions")
      .update({ status: "quota_exceeded" })
      .eq("id", suggestionId);
    throw new Error(`Daily quota reached for ${account} (${quota.sent_today}/${quota.remaining + quota.sent_today})`);
  }

  try {
    // ... rest of existing send logic unchanged ...
```

Note: The `EngagementSuggestion` type in `lib/engagement.ts` may need `"quota_exceeded"` added to the status union. Check the type definition and add it if needed.

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npm run build`
Expected: Build passes.

**Step 3: Commit**

```bash
git add website/lib/engagement.ts
git commit -m "feat(omega): enforce daily quota in sendApprovedReply"
```

---

### Task 6: Create scan-and-reply API route

**Files:**
- Create: `website/app/api/omega/scan-and-reply/route.ts`

**Step 1: Create the route**

Create `website/app/api/omega/scan-and-reply/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { scanTargets } from "@/lib/target-scanner";
import { generateReplySuggestion, insertSuggestion, getEngagementQuota } from "@/lib/engagement";
import { startRun, completeRun } from "@/lib/run-tracker";
import type { XAccount } from "@/lib/x-client";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

const ACCOUNT: XAccount = "omega_memory";
const MAX_REPLIES_PER_SCAN = 2;
const VETO_WINDOW_MS = 30 * 60 * 1000; // 30 minutes

export async function GET(request: NextRequest) {
  const auth = request.headers.get("authorization");
  const secret = process.env.CRON_SECRET;
  if (secret && auth !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const LABEL = "com.omega.vercel.scan-and-reply";
  const runId = await startRun(LABEL, "vercel");
  const t0 = Date.now();

  try {
    // Check quota before scanning
    const quota = await getEngagementQuota(ACCOUNT);
    if (quota.at_limit) {
      await completeRun(runId, LABEL, "ok", t0);
      return NextResponse.json({
        scanned: 0,
        generated: 0,
        reason: `Daily quota reached (${quota.sent_today} sent)`,
      });
    }

    // Scan target accounts
    const candidates = await scanTargets(ACCOUNT, MAX_REPLIES_PER_SCAN);

    if (candidates.length === 0) {
      await completeRun(runId, LABEL, "ok", t0);
      return NextResponse.json({ scanned: 0, generated: 0, reason: "No relevant tweets found" });
    }

    // Generate and auto-approve replies
    const results: { handle: string; tweet_id: string; status: string }[] = [];

    for (const tweet of candidates) {
      try {
        const { reply, type } = await generateReplySuggestion(
          { text: tweet.text, author_handle: tweet.author_handle },
          ACCOUNT,
        );

        await insertSuggestion({
          source_tweet_id: tweet.id,
          source_tweet_text: tweet.text,
          source_author_handle: tweet.author_handle,
          source_author_name: tweet.author_name,
          source_tweet_url: `https://x.com/${tweet.author_handle}/status/${tweet.id}`,
          suggested_reply: reply,
          reply_type: type,
          algorithmic_value: "quote_tweet",
          target_tier: tweet.target_tier,
          x_account: ACCOUNT,
        });

        // Auto-approve with veto window
        // The insertSuggestion creates with status "pending" by default.
        // Update to approved with delayed send time.
        const { supabaseServer } = await import("@/lib/supabase");
        const db = supabaseServer();
        const sendAt = new Date(Date.now() + VETO_WINDOW_MS).toISOString();

        // Get the suggestion we just inserted (by source_tweet_id + account)
        const { data: inserted } = await db
          .from("engagement_suggestions")
          .select("id")
          .eq("source_tweet_id", tweet.id)
          .eq("x_account", ACCOUNT)
          .order("created_at", { ascending: false })
          .limit(1)
          .single();

        if (inserted) {
          await db
            .from("engagement_suggestions")
            .update({ status: "approved", scheduled_send_at: sendAt })
            .eq("id", inserted.id);
        }

        results.push({ handle: tweet.author_handle, tweet_id: tweet.id, status: "auto_approved" });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(`Failed to generate reply for @${tweet.author_handle}:`, msg);
        results.push({ handle: tweet.author_handle, tweet_id: tweet.id, status: "error" });
      }
    }

    await completeRun(runId, LABEL, "ok", t0);
    return NextResponse.json({
      scanned: candidates.length,
      generated: results.filter((r) => r.status === "auto_approved").length,
      results,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("Scan-and-reply failed:", msg);
    await completeRun(runId, LABEL, "error", t0);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
```

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npm run build`
Expected: Build passes.

**Step 3: Commit**

```bash
git add website/app/api/omega/scan-and-reply/route.ts
git commit -m "feat(omega): add scan-and-reply cron route for automated engagement"
```

---

### Task 7: Create daily summary email

**Files:**
- Create: `website/app/api/omega/daily-summary/route.ts`

**Step 1: Create the route**

Create `website/app/api/omega/daily-summary/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import { sendGmail } from "@/lib/gmail";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

export async function GET(request: NextRequest) {
  const auth = request.headers.get("authorization");
  const secret = process.env.CRON_SECRET;
  if (secret && auth !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const db = supabaseServer();
  const since = new Date(Date.now() - 24 * 3600_000).toISOString();
  const email = process.env.NOTIFICATION_EMAIL;
  if (!email) {
    return NextResponse.json({ error: "NOTIFICATION_EMAIL not set" }, { status: 500 });
  }

  // Fetch published tweets
  const { data: tweets } = await db
    .from("tweets")
    .select("text, content_type, published_at, x_post_url")
    .eq("x_account", "omega_memory")
    .eq("status", "published")
    .gte("published_at", since)
    .order("published_at", { ascending: true });

  // Fetch sent replies
  const { data: replies } = await db
    .from("engagement_suggestions")
    .select("suggested_reply, source_author_handle, source_tweet_url, reply_type, sent_at, x_reply_url")
    .eq("x_account", "omega_memory")
    .eq("status", "sent")
    .gte("sent_at", since)
    .order("sent_at", { ascending: true });

  // Fetch vetoed items (tweets rejected within veto window)
  const { data: vetoed } = await db
    .from("tweets")
    .select("text, content_type, updated_at")
    .eq("x_account", "omega_memory")
    .eq("status", "rejected")
    .gte("updated_at", since);

  // Fetch vetoed replies
  const { data: vetoedReplies } = await db
    .from("engagement_suggestions")
    .select("suggested_reply, source_author_handle, updated_at")
    .eq("x_account", "omega_memory")
    .eq("status", "rejected")
    .gte("updated_at", since);

  const tweetCount = tweets?.length ?? 0;
  const replyCount = replies?.length ?? 0;
  const vetoCount = (vetoed?.length ?? 0) + (vetoedReplies?.length ?? 0);

  // Build plain HTML email
  const date = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Singapore",
  });

  let html = `<h2>@omega_memory Daily Summary - ${date}</h2>`;
  html += `<p><strong>${tweetCount} posts</strong> | <strong>${replyCount} replies</strong>`;
  if (vetoCount > 0) html += ` | <strong>${vetoCount} vetoed</strong>`;
  html += `</p><hr>`;

  if (tweetCount > 0) {
    html += `<h3>Posts</h3><ul>`;
    for (const t of tweets!) {
      const link = t.x_post_url ? `<a href="${t.x_post_url}">view</a>` : "";
      html += `<li><strong>${t.content_type}</strong>: ${t.text.slice(0, 200)}${t.text.length > 200 ? "..." : ""} ${link}</li>`;
    }
    html += `</ul>`;
  }

  if (replyCount > 0) {
    html += `<h3>Replies</h3><ul>`;
    for (const r of replies!) {
      const link = r.x_reply_url ? `<a href="${r.x_reply_url}">view</a>` : "";
      html += `<li>To @${r.source_author_handle} (${r.reply_type}): ${r.suggested_reply.slice(0, 200)} ${link}</li>`;
    }
    html += `</ul>`;
  }

  if (vetoCount > 0) {
    html += `<h3>Vetoed</h3><ul>`;
    for (const v of vetoed ?? []) {
      html += `<li>[tweet] ${v.text.slice(0, 200)}</li>`;
    }
    for (const v of vetoedReplies ?? []) {
      html += `<li>[reply to @${v.source_author_handle}] ${v.suggested_reply.slice(0, 200)}</li>`;
    }
    html += `</ul>`;
  }

  if (tweetCount === 0 && replyCount === 0) {
    html += `<p>No activity in the last 24 hours.</p>`;
  }

  await sendGmail(email, `[@omega_memory] Daily Summary - ${date}`, html);

  return NextResponse.json({ emailed: true, tweets: tweetCount, replies: replyCount, vetoed: vetoCount });
}
```

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npm run build`
Expected: Build passes.

**Step 3: Commit**

```bash
git add website/app/api/omega/daily-summary/route.ts
git commit -m "feat(omega): add daily summary email for omega_memory activity"
```

---

### Task 8: Wire crons and update seed script

**Files:**
- Modify: `website/vercel.json`
- Modify: `website/scripts/seed-all-schedules.py`

**Step 1: Add new crons to vercel.json**

Add these 4 entries to the `crons` array in `website/vercel.json`:

```json
{"path": "/api/omega/scan-and-reply", "schedule": "0 14 * * *"},
{"path": "/api/omega/scan-and-reply", "schedule": "0 18 * * *"},
{"path": "/api/omega/scan-and-reply", "schedule": "0 22 * * *"},
{"path": "/api/omega/daily-summary",  "schedule": "0 1 * * *"}
```

**Step 2: Add new records to seed-all-schedules.py**

Add to `VERCEL_CRONS` list in `website/scripts/seed-all-schedules.py`:

```python
{
    "label": "com.omega.vercel.scan-and-reply",
    "name": "Omega Scan & Reply",
    "description": "Scans target accounts and auto-generates replies for @omega_memory (3x daily)",
    "schedule_type": "calendar",
    "calendar_hour": 9, "calendar_minute": 0, "calendar_weekday": None,
    "enabled": True,
    "command": "GET /api/omega/scan-and-reply (Vercel cron)",
    "last_status": "unknown",
},
{
    "label": "com.omega.vercel.daily-summary",
    "name": "Omega Daily Summary",
    "description": "Emails daily summary of all @omega_memory posts and replies",
    "schedule_type": "calendar",
    "calendar_hour": 8, "calendar_minute": 0, "calendar_weekday": None,
    "enabled": True,
    "command": "GET /api/omega/daily-summary (Vercel cron)",
    "last_status": "unknown",
},
```

**Step 3: Seed DB records**

Run: `cd ~/Projects/omega/website && python3 scripts/cleanup-wasted-jobs.py` (no-op, just verify).
Then upsert the new records using a one-liner similar to the cleanup script pattern.

**Step 4: Verify build**

Run: `cd ~/Projects/omega/website && npm run build`
Expected: Build passes.

**Step 5: Commit**

```bash
git add website/vercel.json website/scripts/seed-all-schedules.py
git commit -m "feat(omega): wire scan-and-reply and daily-summary crons"
```

---

### Task 9: Update omega-crons.yml for 3-slot generation

**Files:**
- Modify: `.github/workflows/omega-crons.yml`

**Step 1: Adjust generate-omega timing**

The generate-omega GH Action still runs at `5 13 * * *` (8 AM ET). This is fine — it generates 3 tweets (down from 4). No timing change needed, just verify the `MAX_OMEGA_SLOTS = 3` change from Task 1 is committed.

No file changes needed — the worker.ts change in Task 1 already handles this.

**Step 2: Commit (if any changes)**

Skip if no changes.

---

### Task 10: Deploy and verify

**Step 1: Push to remote**

```bash
git push origin main
```

**Step 2: Deploy to Vercel**

```bash
cd ~/Projects/omega/website && npx vercel --prod
```

**Step 3: Verify crons registered**

Check Vercel dashboard or run:
```bash
npx vercel crons ls
```

Expected: 16 crons total (12 existing + 4 new).

**Step 4: Manual smoke test**

Test the scan-and-reply endpoint:
```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://omegamax.co/api/omega/scan-and-reply
```

Expected: JSON with `scanned`, `generated`, `results`.

Test the daily summary:
```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://omegamax.co/api/omega/daily-summary
```

Expected: JSON with `emailed: true` and summary email arrives.

**Step 5: Final commit**

```bash
git commit --allow-empty -m "chore: verify omega_memory full automation deployed"
```
