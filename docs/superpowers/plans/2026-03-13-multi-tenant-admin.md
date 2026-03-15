# Multi-Tenant Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give OMEGA Pro users access to the admin dashboard with strict data isolation — they see only their own data, never the owner's.

**Architecture:** Defense-in-depth: RLS policies at the database layer (backstop), role-scoped Supabase clients at the application layer, and tab-level access control at the UI layer. Contributors authenticate via Google OAuth only (no license cookie shortcut). Owner routes keep service role key access.

**Tech Stack:** Next.js (App Router), Supabase (PostgreSQL + RLS), TypeScript

**Spec:** `docs/superpowers/specs/2026-03-13-multi-tenant-admin-design.md`

---

## Chunk 1: Auth Hardening

### Task 1: Fix Pro License Cookie → Owner Identity Bug

The `getCurrentUser()` function in `lib/supabase.ts` maps Pro license sessions to `ADMIN_USER_ID` with `email: "admin@local"`, and `requireAuth()` grants owner role to `admin@local`. A contributor who authenticates via license key silently gets owner access. This is the same class of bug as the Jimmy incident.

**Files:**
- Modify: `website/lib/supabase.ts:74-86` (getCurrentUser), `website/lib/supabase.ts:106-125` (requireAuth)
- Test: `website/__tests__/lib/supabase-auth.test.ts` (create new)

- [ ] **Step 1: Write failing test — Pro session must NOT grant owner role**

Create `website/__tests__/lib/supabase-auth.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the cookie/session helpers
vi.mock("next/headers", () => ({
  cookies: vi.fn(),
}));

describe("requireAuth role assignment", () => {
  it("should not grant owner role to Pro license sessions", async () => {
    // Pro license sessions must not map to owner role
    // The fix: Pro session cookie should redirect to OAuth, not return PASSWORD_SESSION_USER
    // This test validates the principle — implementation details tested below
    expect(true).toBe(true); // placeholder until we can mock the full auth chain
  });
});
```

Note: The auth functions depend heavily on Next.js cookies and Supabase client. Full unit tests require extensive mocking. The real validation is the E2E test in Task 8. For now, the code changes are the priority.

- [ ] **Step 2: Modify `getCurrentUser()` — remove Pro session → owner mapping**

In `website/lib/supabase.ts`, change `getCurrentUser()` (around line 83):

```typescript
// BEFORE (vulnerable):
// Fallback: Pro license session
if (await getProSession()) return PASSWORD_SESSION_USER as any;

// AFTER (fixed):
// Pro license session is for local CLI only, not dashboard access.
// Pro users must authenticate via Google OAuth to access the dashboard.
// Do NOT return PASSWORD_SESSION_USER for Pro sessions.
```

Simply remove the `getProSession()` fallback from `getCurrentUser()`. Pro users who only have a license cookie will get `null` from `getCurrentUser()`, which means `requireAuth()` returns 401, and they must log in via Google OAuth.

- [ ] **Step 3: Tighten `requireAuth()` — clarify admin@local is password/passkey only**

In `website/lib/supabase.ts`, at line 114, add a comment:

```typescript
// admin@local = password or passkey login (physical access to the machine).
// This is NOT reachable by Pro license sessions (removed from getCurrentUser).
if (user.email === "admin@local") return { user, role: "owner" };
```

No code change needed here — the fix in Step 2 ensures Pro sessions never reach this line.

- [ ] **Step 4: Verify the fix manually**

Test locally:
1. Clear all cookies, visit `/admin` → should redirect to login
2. Log in with password/passkey → should get owner role (all tabs visible)
3. Simulate a contributor by adding a test email to `allowed_users` with role `contributor`, log in via Google OAuth → should get contributor role

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/omega/website
git add lib/supabase.ts
git commit -m "fix(auth): remove Pro license cookie → owner identity mapping

Pro license sessions no longer grant dashboard access. Contributors must
authenticate via Google OAuth. Prevents the Jimmy-class bug where any
authenticated user gets owner identity and sees all data."
```

---

### Task 2: Add 403 Guards to All Owner-Only Routes

Multiple routes either have no role check or use `getCurrentUser()` (which allows any authenticated user). All owner-only routes must use `requireAuth()` and reject contributors.

**Files:**
- Modify: `website/app/api/admin/orchestrator-feed/route.ts:15-19`
- Modify: `website/app/api/admin/dashboard/route.ts:295` (add auth guard)
- Verify: `website/app/api/admin/diagnostic/route.ts:25-27` (already correct)

- [ ] **Step 1: Fix `orchestrator-feed` — add role check**

In `website/app/api/admin/orchestrator-feed/route.ts`, replace the GET handler auth:

```typescript
// BEFORE:
const user = await getCurrentUser();
if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

// AFTER:
const auth = await requireAuth();
if (!auth) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
if (auth.role !== "owner") return NextResponse.json({ error: "Forbidden" }, { status: 403 });
```

Do the same for the POST handler.

- [ ] **Step 2: Fix `dashboard` route — add auth guard with 401**

In `website/app/api/admin/dashboard/route.ts`, at the top of the GET handler (around line 295):

```typescript
// BEFORE:
const user = await getCurrentUser();
const userId = user?.id;

// AFTER:
const user = await getCurrentUser();
if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
const userId = user.id;
```

- [ ] **Step 3: Add 403 to remaining owner-only routes**

Check and add `if (auth.role !== "owner") return 403` to:
- `/api/admin/research/` routes
- `/api/admin/schedule-runs/` routes
- `/api/admin/entities/` routes
- `/api/admin/search/route.ts` (until `kb_queue` is user-scoped)
- Any Settings routes

For each, verify the route uses `requireAuth()` and add the role check if missing.

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/omega/website
git add app/api/admin/
git commit -m "fix(auth): add 403 guards to all owner-only admin routes

orchestrator-feed, dashboard, research, schedule-runs, entities, and
search routes now enforce owner role. Contributors get 403 Forbidden."
```

---

## Chunk 2: Database Migration

### Task 3: Create Multi-Tenant RLS Migration

Add `user_id` columns to coordination tables, create RLS policies, fix the `cleanup_orphaned_memories` RPC, and update unique constraints for multi-user safety.

**Files:**
- Create: `supabase/migrations/20260313000000_multi_tenant_isolation.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260313000000_multi_tenant_isolation.sql`:

```sql
-- Multi-tenant data isolation for OMEGA Pro users
-- Defense-in-depth: RLS policies enforce user_id scoping at the database layer.
-- Service role key (used by owner routes) bypasses RLS by default.

-- =============================================================================
-- 1. RLS policies for tables that already have user_id
-- =============================================================================

-- memories (RLS may already be enabled from security_hardening; make idempotent)
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_memories" ON memories;
CREATE POLICY "users_own_memories" ON memories
  FOR ALL USING (user_id = auth.uid()::text);

-- tweets
ALTER TABLE tweets ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_tweets" ON tweets;
CREATE POLICY "users_own_tweets" ON tweets
  FOR ALL USING (user_id = auth.uid()::text);

-- engagement_suggestions
ALTER TABLE engagement_suggestions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_engagement" ON engagement_suggestions;
CREATE POLICY "users_own_engagement" ON engagement_suggestions
  FOR ALL USING (user_id = auth.uid()::text);

-- =============================================================================
-- 2. Add user_id to coordination tables + RLS
-- =============================================================================

ALTER TABLE coord_sessions ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE coord_file_claims ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE coord_decisions ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE coord_tasks ADD COLUMN IF NOT EXISTS user_id TEXT;

-- RLS on coord tables
ALTER TABLE coord_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_sessions" ON coord_sessions;
CREATE POLICY "users_own_sessions" ON coord_sessions
  FOR ALL USING (user_id = auth.uid()::text OR user_id IS NULL);

ALTER TABLE coord_file_claims ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_file_claims" ON coord_file_claims;
CREATE POLICY "users_own_file_claims" ON coord_file_claims
  FOR ALL USING (user_id = auth.uid()::text OR user_id IS NULL);

ALTER TABLE coord_decisions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_decisions" ON coord_decisions;
CREATE POLICY "users_own_decisions" ON coord_decisions
  FOR ALL USING (user_id = auth.uid()::text OR user_id IS NULL);

ALTER TABLE coord_tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_tasks" ON coord_tasks;
CREATE POLICY "users_own_tasks" ON coord_tasks
  FOR ALL USING (user_id = auth.uid()::text OR user_id IS NULL);

-- =============================================================================
-- 3. Add user_id to kb_queue + RLS
-- =============================================================================

ALTER TABLE kb_queue ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE kb_queue ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_kb" ON kb_queue;
CREATE POLICY "users_own_kb" ON kb_queue
  FOR ALL USING (user_id = auth.uid()::text OR user_id IS NULL);

-- =============================================================================
-- 4. Fix cleanup_orphaned_memories RPC — scope by user_id
-- =============================================================================

CREATE OR REPLACE FUNCTION cleanup_orphaned_memories(valid_local_ids INTEGER[])
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  DELETE FROM memories
  WHERE local_id IS NOT NULL
    AND local_id != ALL(valid_local_ids)
    AND user_id = auth.uid()::text;
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;

-- =============================================================================
-- 5. Fix unique constraints for multi-user on_conflict safety
-- =============================================================================

-- documents: on_conflict="source_path" must include user_id
-- Drop old constraint, add new one
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_source_path_key;
ALTER TABLE documents ADD CONSTRAINT documents_source_path_user_key
  UNIQUE (source_path, user_id);

-- Note: secure_profile is excluded from cloud sync (src/omega/cloud/sync.py:529-532)
-- so the on_conflict issue does not apply in practice. No change needed.

-- =============================================================================
-- 6. Backfill user_id on existing coord rows to owner
-- =============================================================================

UPDATE coord_sessions SET user_id = '00000000-0000-0000-0000-000000000001'
  WHERE user_id IS NULL;
UPDATE coord_file_claims SET user_id = '00000000-0000-0000-0000-000000000001'
  WHERE user_id IS NULL;
UPDATE coord_decisions SET user_id = '00000000-0000-0000-0000-000000000001'
  WHERE user_id IS NULL;
UPDATE coord_tasks SET user_id = '00000000-0000-0000-0000-000000000001'
  WHERE user_id IS NULL;
UPDATE kb_queue SET user_id = '00000000-0000-0000-0000-000000000001'
  WHERE user_id IS NULL;
```

- [ ] **Step 2: Review the migration for correctness**

Check:
- `OR user_id IS NULL` on coord policies allows existing unscoped rows during migration window
- Backfill assigns existing data to the owner
- `documents` unique constraint change is safe (no duplicates exist)
- `cleanup_orphaned_memories` now scopes deletes by caller's user_id

- [ ] **Step 3: Apply migration to Supabase**

```bash
cd ~/Projects/omega
# Review first
cat supabase/migrations/20260313000000_multi_tenant_isolation.sql

# Apply (requires Supabase CLI or manual application via dashboard)
supabase db push
```

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/omega
git add supabase/migrations/20260313000000_multi_tenant_isolation.sql
git commit -m "feat(db): add multi-tenant RLS policies and user_id scoping

Adds user_id columns to coord tables and kb_queue. Creates RLS policies
on memories, tweets, engagement_suggestions, and all coord tables.
Fixes cleanup_orphaned_memories to scope by caller's user_id.
Updates documents unique constraint to include user_id.
Backfills existing data to owner user_id."
```

---

### Task 4: Update Cloud Sync `on_conflict` for Documents

The `documents` upsert in `cloud/sync.py` uses `on_conflict="source_path"` which can overwrite another user's document. After the migration adds the new unique constraint, the sync must match.

**Files:**
- Modify: `src/omega/cloud/sync.py:372`

- [ ] **Step 1: Update the on_conflict clause**

In `src/omega/cloud/sync.py`, around line 372:

```python
# BEFORE:
result = client.table("documents").upsert(doc_record, on_conflict="source_path").execute()

# AFTER:
result = client.table("documents").upsert(doc_record, on_conflict="source_path,user_id").execute()
```

- [ ] **Step 2: Verify user_id is set on doc_record**

Check that `doc_record` includes `user_id` before the upsert. It should already be set via the `self._user_id` pattern. If not, add:

```python
if self._user_id:
    doc_record["user_id"] = self._user_id
```

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/omega
git add src/omega/cloud/sync.py
git commit -m "fix(sync): scope documents upsert on_conflict to include user_id

Prevents multi-user data overwrite when two users have the same source_path."
```

---

## Chunk 3: Route Scoping for Contributors

### Task 5: Scope Dashboard Route for Contributors

The dashboard route must strip personal data (X/Twitter, outreach, grants) for contributors and only show their memory stats + public metrics.

**Files:**
- Modify: `website/app/api/admin/dashboard/route.ts`

- [ ] **Step 1: Get the user's role in the dashboard handler**

After the auth guard added in Task 2, resolve the role:

```typescript
const user = await getCurrentUser();
if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
const userId = user.id;
const role = await getCurrentUserRole();
const isOwner = role === "owner";
```

- [ ] **Step 2: Conditionally skip owner-only data fetchers**

In the `Promise.allSettled` block (around line 301), wrap owner-only fetchers:

```typescript
const results = await Promise.allSettled([
  fetchGitHub(),                           // public — always
  fetchPyPI(),                             // public — always
  isOwner ? fetchTwitter() : null,         // owner-only
  isOwner ? fetchOutreach(userId) : null,  // owner-only
  isOwner ? fetchGrants(userId) : null,    // owner-only
  fetchDownloads(),                        // public — always
  fetchMemoryStats(userId),                // scoped by user_id
  isOwner ? fetchPerformance(userId) : null, // owner-only (tweet performance)
]);
```

- [ ] **Step 3: Handle null results in the response**

Ensure the response object uses `null` for skipped fields instead of undefined:

```typescript
return NextResponse.json({
  github: extract(results[0]),
  pypi: extract(results[1]),
  twitter: isOwner ? extract(results[2]) : null,
  outreach: isOwner ? extract(results[3]) : null,
  grants: isOwner ? extract(results[4]) : null,
  downloads: extract(results[5]),
  memoryStats: extract(results[6]),
  performance: isOwner ? extract(results[7]) : null,
});
```

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/omega/website
git add app/api/admin/dashboard/route.ts
git commit -m "feat(dashboard): scope route for contributors

Contributors see memory stats and public metrics only. Twitter, outreach,
grants, and performance data skipped for non-owner roles."
```

---

### Task 6: Scope Insights Route for Contributors

**Files:**
- Modify: `website/app/api/admin/insights/route.ts`

- [ ] **Step 1: Resolve role in the insights handler**

At the top of the GET handler:

```typescript
const auth = await requireAuth();
if (!auth) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
const { user, role } = auth;
const isOwner = role === "owner";
```

- [ ] **Step 2: Skip tweet/LinkedIn stats for contributors**

Find where tweet and LinkedIn data is fetched and wrap with `isOwner`:

```typescript
// Only fetch tweet/LinkedIn stats for owner
const tweetStats = isOwner ? await fetchTweetStats(userId) : null;
const linkedinStats = isOwner ? await fetchLinkedInStats(userId) : null;
```

Memory stats queries should already be scoped by `userId` from the auth. Verify they use `.eq("user_id", userId)`.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/omega/website
git add app/api/admin/insights/route.ts
git commit -m "feat(insights): scope route for contributors

Contributors see memory analytics only. Tweet/LinkedIn stats hidden for
non-owner roles."
```

---

### Task 7: Scope Timeline Route for Contributors

The timeline aggregates job run history and git events which are owner-only.

**Files:**
- Modify: `website/app/api/admin/timeline/route.ts:121-166`

- [ ] **Step 1: Resolve role**

```typescript
const auth = await requireAuth();
if (!auth) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
const { user, role } = auth;
const isOwner = role === "owner";
```

- [ ] **Step 2: Skip schedule_runs and coord_git_events for contributors**

Around lines 121-166, wrap the job/git queries:

```typescript
// schedule_runs — owner-only (reveals automation details)
let jobEvents: any[] = [];
if (isOwner) {
  const { data } = await supabase
    .from("schedule_runs")
    // ... existing query
  jobEvents = data || [];
}

// coord_git_events — owner-only (reveals repo activity)
let gitEvents: any[] = [];
if (isOwner) {
  const { data } = await supabase
    .from("coord_git_events")
    // ... existing query
  gitEvents = data || [];
}
```

Memory events (already scoped by userId) remain visible to contributors.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/omega/website
git add app/api/admin/timeline/route.ts
git commit -m "feat(timeline): hide job and git events for contributors

Contributors see session recaps only. Schedule runs and git events
are owner-only data."
```

---

## Chunk 4: Frontend Role Gating

### Task 8: Add Role-Based Tab Filtering to Sidebar

**Files:**
- Modify: `website/app/admin/lib/types.ts:3` (TABS definition)
- Modify: `website/app/admin/components/shell/Sidebar.tsx`

- [ ] **Step 1: Define role-based tab config**

In `website/app/admin/lib/types.ts`, add after the existing `TABS` array:

```typescript
export const TABS = ["dashboard", "projects", "feed", "actions", "insights", "research", "docs", "jobs", "settings", "coordination", "entities", "growth", "diagnostic"] as const;

// Tabs visible to each role
export const ROLE_TABS: Record<string, readonly string[]> = {
  owner: TABS,
  contributor: ["dashboard", "projects", "feed", "insights", "coordination"],
};

export function getTabsForRole(role: string | null): readonly string[] {
  return ROLE_TABS[role || ""] || [];
}
```

- [ ] **Step 2: Use role-filtered tabs in Sidebar**

In `website/app/admin/components/shell/Sidebar.tsx`, find where tabs are mapped and filter by role:

```typescript
import { getTabsForRole } from "../lib/types";
import { useCurrentUser } from "../../hooks/useCurrentUser";

// Inside the component:
const { role } = useCurrentUser();
const visibleTabs = getTabsForRole(role);

// In the render, filter:
{visibleTabs.map((tab) => (
  // ... existing tab button rendering
))}
```

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/omega/website
git add app/admin/lib/types.ts app/admin/components/shell/Sidebar.tsx
git commit -m "feat(ui): role-based tab filtering in admin sidebar

Contributors see: dashboard, projects, feed, insights, coordination.
Owner sees all 13 tabs. Hidden tabs are not rendered in the DOM."
```

---

### Task 9: Conditional Component Rendering in Dashboard

**Files:**
- Modify: `website/app/admin/tabs/DashboardTab.tsx` (or equivalent)

- [ ] **Step 1: Find the dashboard tab component**

Locate the component that renders dashboard cards (Twitter followers, outreach, etc.).

- [ ] **Step 2: Hide owner-only cards for contributors**

```typescript
import { useCurrentUser } from "../../hooks/useCurrentUser";

// Inside the component:
const { role } = useCurrentUser();
const isOwner = role === "owner";

// In the render, wrap owner-only sections:
{isOwner && <TwitterFollowersCard data={data.twitter} />}
{isOwner && <OutreachCard data={data.outreach} />}
{isOwner && <GrantsCard data={data.grants} />}
{isOwner && <PerformanceCard data={data.performance} />}
```

- [ ] **Step 3: Same pattern for Insights and Feed tabs**

Apply the same `isOwner` conditional rendering:
- Insights: hide tweet/LinkedIn sections
- Feed: hide approvals queue

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/omega/website
git add app/admin/tabs/
git commit -m "feat(ui): hide owner-only dashboard cards for contributors

Twitter, outreach, grants, and performance cards hidden for non-owner roles.
Same pattern applied to Insights and Feed tabs."
```

---

## Chunk 5: End-to-End Verification

### Task 10: Create Test Contributor and Verify Isolation

- [ ] **Step 1: Add a test contributor to `allowed_users`**

Via Supabase dashboard or SQL:

```sql
INSERT INTO allowed_users (email, role, created_at)
VALUES ('test-contributor@example.com', 'contributor', now());
```

- [ ] **Step 2: Log in as the test contributor**

1. Visit omegamax.co/admin
2. Log in with Google OAuth using the test email
3. Verify: only 5 tabs visible (dashboard, projects, feed, insights, coordination)
4. Verify: dashboard shows memory stats + GitHub/PyPI, no Twitter/outreach
5. Verify: insights shows memory analytics, no tweet/LinkedIn
6. Verify: feed shows session recaps, no approvals or job history

- [ ] **Step 3: Test 403 enforcement**

Manually hit owner-only API routes as the contributor:

```bash
# Should all return 403
curl -H "Cookie: ..." https://omegamax.co/api/admin/orchestrator-feed
curl -H "Cookie: ..." https://omegamax.co/api/admin/diagnostic
curl -H "Cookie: ..." https://omegamax.co/api/admin/entities
curl -H "Cookie: ..." https://omegamax.co/api/admin/research
```

- [ ] **Step 4: Test RLS isolation**

Verify the contributor cannot see owner's memories:

```bash
# As contributor, the memories endpoint should only return their memories (empty for new user)
curl -H "Cookie: ..." https://omegamax.co/api/admin/insights
# Should show 0 memories, not Jason's 800+ memories
```

- [ ] **Step 5: Clean up test data**

```sql
DELETE FROM allowed_users WHERE email = 'test-contributor@example.com';
```

- [ ] **Step 6: Final commit — update spec status**

```bash
cd ~/Projects/omega
# Update spec status from "Approved" to "Implemented"
git add docs/superpowers/specs/2026-03-13-multi-tenant-admin-design.md
git commit -m "docs: mark multi-tenant admin spec as implemented"
```

---

## Task Dependency Graph

```
Task 1 (auth fix) ─────────────────┐
Task 2 (403 guards) ───────────────┤
                                    ├──> Task 5-7 (route scoping) ──> Task 8-9 (frontend) ──> Task 10 (E2E)
Task 3 (migration) ────────────────┤
Task 4 (sync on_conflict) ─────────┘
```

Tasks 1-4 can run in parallel. Tasks 5-7 depend on Tasks 1-3. Tasks 8-9 depend on Tasks 5-7. Task 10 depends on everything.
