# Multi-Tenant Admin Dashboard for OMEGA Pro Users

**Date:** 2026-03-13
**Status:** Approved (rev 2 — post-review)
**Author:** Jason Sosa + Claude

## Context

OMEGA has its first paying Pro customer. The admin dashboard at omegamax.co/admin is currently single-user (Jason only). Pro users need access to view their own data — but must never see Jason's personal data.

### Jimmy Incident (Lesson Learned)

Jimmy was added as an `allowed_user` via Google OAuth. He logged in successfully but could see Jason's memories in the graph and feed. Root cause: authentication does not equal isolation. Admin routes use `supabaseServer()` with the service role key (bypasses RLS), and `user_id` scoping was not enforced on all queries. This design applies defense-in-depth to prevent recurrence.

## Design Principles

1. **Authentication != Isolation** — A legitimate user must only see their own data
2. **Defense-in-depth** — RLS at the database layer is the backstop, not application code
3. **Service role key is owner-only** — Pro users never touch it
4. **No secret exposure** — X API keys, Gemini key, and personal credentials are never accessible to Pro users
5. **Fail closed** — If role/scope is unclear, deny access

## 1. Authentication & Identity

### Flow

1. Pro user installs OMEGA, runs `omega activate <license-key>`
2. Activation calls our API, creates a Supabase user (or links existing), returns a `user_id`
3. `user_id` is stored locally in the Pro user's OMEGA config
4. Cloud sync pushes their memories to Supabase under their `user_id`
5. For admin access, Pro user goes to omegamax.co/admin, logs in via Google OAuth
6. OAuth identity is matched to their license/`user_id` in the `allowed_users` table
7. They receive role `contributor` (never `owner`)

### Roles

| Role | Who | Capabilities |
|------|-----|-------------|
| `owner` | Jason only | All tabs, service role key access, full data |
| `contributor` | Pro users | Scoped tabs, RLS-enforced data access, own data only |

### Critical: Pro License Cookie Path (REVIEW FINDING #1)

**Current bug:** `getCurrentUser()` in `lib/supabase.ts` treats the `omega_pro_session` cookie as a password session, mapping it to `ADMIN_USER_ID` (`00000000-0000-0000-0000-000000000001`) with `email: "admin@local"`. The `requireAuth()` function then grants `owner` role to any user with `email === "admin@local"`. This means a Pro user who authenticates via license key gets owner identity and sees all of Jason's data.

**Fix required:** The Pro license cookie path must be eliminated from the admin auth flow. Pro users MUST authenticate via Google OAuth. The `omega_pro_session` cookie is for local CLI access only, not dashboard access. In `getCurrentUser()`, the Pro session fallback must not return `PASSWORD_SESSION_USER`. Instead:
- If the user has a valid Supabase OAuth session → use that (with their real `user_id`)
- If the user has only a Pro license cookie but no OAuth session → redirect to OAuth login
- The `email === "admin@local"` → `owner` shortcut must only apply to password/passkey sessions, not license sessions

### Bootstrap: `allowed_users` Table (REVIEW FINDING #9)

The `allowed_users` RLS policy requires the caller to already exist as an `owner` in the table to perform any operation (including the initial INSERT). The owner row must be inserted using the service role key before the policy takes effect. This is a one-time setup step.

**Deliberate exception:** `getCurrentUserRole()` uses `supabaseServer()` (service role) to read the `allowed_users` table for all users, because the RLS policy blocks contributors from reading even their own row. This is acceptable — the alternative (a SELECT-only policy for the user's own row) would be safer and should be considered in a follow-up.

## 2. Data Isolation Architecture

### Layer 1 — Database (RLS)

Every table holding user data gets an RLS policy: `WHERE user_id = auth.uid()`. Pro user API routes use a user-scoped Supabase client that authenticates as the user. RLS is always enforced. Even if application code has a bug, the database will not return another user's rows.

### Layer 2 — Application

New helper: `supabaseForUser(userId)` — creates a Supabase client that authenticates as the specified user (using their Supabase JWT from the OAuth session). This function does not exist today and must be implemented. The existing `supabaseUser()` reads Supabase auth cookies (standard SSR OAuth session) — `supabaseForUser()` wraps this pattern, returning the user-scoped client for contributors.

**Pattern for all Pro-accessible routes:**
```typescript
const { user, role } = await requireAuth();
const supabase = role === "owner"
  ? supabaseServer()           // owner keeps service role
  : supabaseUser();            // contributor gets RLS-scoped client via OAuth JWT
```

Note: `supabaseUser()` already exists and returns a client scoped to the authenticated OAuth user. For contributors who must authenticate via Google OAuth (per Section 1 fix), this client will enforce RLS correctly. No new `supabaseForUser()` is needed if we ensure contributors always have a live OAuth session.

### Layer 3 — UI

Tab visibility is based on role. No client-side filtering of data that should not have been fetched — the API simply does not return it.

## 3. Tab Access Matrix

| Tab | Owner | Contributor (Pro) | Notes |
|-----|-------|-------------------|-------|
| Dashboard | Full (personal + public) | Their memory stats + public metrics (GitHub/PyPI) | No X/Twitter stats for Pro |
| Insights | Full | Their memory analytics only | No tweet/LinkedIn stats |
| Projects | Full | Their project activity only | |
| Coordination | Full | Their agent sessions only | Blocked until coord user_id migration runs |
| Diagnostic | Full | **Hidden** | Owner-only (current code enforces this; scoping deferred) |
| Feed | Full | Their session recaps only | No approvals queue, no job/git data in timeline |
| Actions/Social | Full | **Hidden** | Owner-only |
| Growth | Full | **Hidden** | Owner-only |
| Research | Full | **Hidden** | Owner-only |
| Jobs/Schedules | Full | **Hidden** | Owner-only |
| Entities | Full | **Hidden** | Owner-only |
| Settings | Full | **Hidden** | Owner-only |
| Docs | Full | **Hidden** | Owner-only |

**Change from rev 1:** Diagnostic moved to owner-only (current code already enforces this; scoping it for contributors is deferred).

## 4. API Route Changes

### Pro-accessible routes (need scoping)

Routes requiring changes:

- `/api/admin/dashboard` — add auth guard (currently no 401 path), strip X/Twitter data for contributors, scope memory stats. `fetchTwitter()` must be skipped entirely for contributors.
- `/api/admin/insights` — scope all memory queries, remove tweet/LinkedIn stats
- `/api/admin/coordination` — scope by user's sessions (blocked on migration)
- `/api/admin/approvals` — 403 for contributors (Feed shows recaps only)
- `/api/admin/timeline` — strip `schedule_runs` and `coord_git_events` for contributors (these leak owner automation data)

### Owner-only routes (403 for contributors)

- `/api/tweets`, `/api/engagement`
- `/api/admin/entities`
- `/api/admin/research`
- `/api/admin/schedule-runs`
- `/api/admin/diagnostic`
- `/api/admin/orchestrator-feed` — currently has no role check; must add 403 for contributors (contains X/Twitter and LinkedIn automation proposals)
- `/api/admin/search` — `kb_queue` results must be scoped or hidden for contributors (see Section 5)
- All Settings routes

### Existing route

- `/api/admin/me` — already exists, returns current user profile/role. Pro users use this to determine tab access.

## 5. Database Migration

### RLS policies for tables with existing `user_id`

```sql
-- memories
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_memories" ON memories
  FOR ALL USING (user_id = auth.uid()::text);

-- tweets
ALTER TABLE tweets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_tweets" ON tweets
  FOR ALL USING (user_id = auth.uid()::text);

-- engagement_suggestions
ALTER TABLE engagement_suggestions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_engagement" ON engagement_suggestions
  FOR ALL USING (user_id = auth.uid()::text);
```

### Tables needing `user_id` column added

```sql
ALTER TABLE coord_sessions ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE coord_file_claims ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE coord_decisions ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE coord_tasks ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE kb_queue ADD COLUMN IF NOT EXISTS user_id TEXT;

-- Then RLS policies on each (same pattern as above)
```

### Fix: `cleanup_orphaned_memories` RPC (REVIEW FINDING #5)

The `cleanup_orphaned_memories` function is `SECURITY DEFINER` and deletes from `memories` by `local_id` with no `user_id` filter. A Pro user's sync client calling this could delete another user's memories. Fix: add `AND user_id = auth.uid()::text` to the DELETE predicate, or accept a `p_user_id` parameter and validate it matches the caller.

### Fix: Cloud sync `on_conflict` scoping (REVIEW FINDINGS #6, #12)

Two tables have `on_conflict` clauses that don't include `user_id`:

- `secure_profile`: upsert on `(category, field_name)` — must be `(category, field_name, user_id)`. Without this, two users with the same category/field overwrite each other. Requires updating the unique constraint.
- `documents`: upsert on `(source_path)` — must be `(source_path, user_id)`. Without this, two users with the same file path overwrite each other. Requires updating the unique constraint.

### Service role bypass

Owner routes use the service role key, which bypasses RLS by default in Supabase. No extra policy needed.

### Cloud sync

The existing `_cloud_fire` in `cloud/sync.py` already sends `user_id` with each row. Pro users' `user_id` is set during `omega activate` and stored in their local config. Verify `user_id` propagation and fix `on_conflict` clauses per above.

### Zero-downtime

All migrations are additive (ADD COLUMN, CREATE POLICY, ALTER CONSTRAINT). No destructive changes.

## 6. Frontend Changes

### Sidebar

```typescript
const ROLE_TABS: Record<string, Tab[]> = {
  owner: [/* all 13 tabs */],
  contributor: ["dashboard", "insights", "projects", "coordination", "feed"],
};
```

Sidebar renders only tabs for the current role. No hidden tabs in the DOM.

### Dashboard tab (contributor view)

- Remove: X/Twitter follower cards, outreach stats, grants pipeline
- Keep: memory count, public GitHub/PyPI metrics, installer downloads

### Insights tab (contributor view)

- Remove: tweet/LinkedIn performance sections
- Keep: memory analytics, session heatmap, project radar (scoped to their data)

### Feed tab (contributor view)

- Remove: approvals queue, job run history, git events
- Keep: session recaps (scoped)

### Coordination tab

No UI changes needed. Same components, data is scoped by the API layer. Tab is blocked until coord tables have `user_id` migration.

### `useCurrentUser` hook

Already returns user + role. Components use `role === "owner"` checks to conditionally render sections.

## 7. Implementation Sequence

Must be done in this order:

1. **Fix auth** — Remove Pro license cookie → owner mapping. Contributors must use Google OAuth.
2. **Database migration** — Add `user_id` columns, RLS policies, fix `on_conflict` constraints, fix `cleanup_orphaned_memories` RPC.
3. **Implement `supabaseUser()` pattern** — All Pro-accessible routes use OAuth-scoped client.
4. **Add 403 guards** — All owner-only routes reject contributors.
5. **Scope Pro-accessible routes** — Dashboard, Insights, Feed, Timeline strip owner-only data.
6. **Frontend role gating** — Sidebar tab filtering, conditional component rendering.
7. **Coordination scoping** — After coord `user_id` migration, enable Coordination tab for contributors.
8. **End-to-end test** — Create a test contributor account, verify zero data leakage.

## Security Checklist

- [ ] Pro license cookie does NOT grant owner identity or dashboard access
- [ ] No Pro user route uses `supabaseServer()` (service role key)
- [ ] All RLS policies enforce `user_id = auth.uid()::text`
- [ ] No X/Twitter API keys accessible from contributor routes
- [ ] No owner-only tab rendered for contributors
- [ ] Owner-only API routes return 403 for contributors
- [ ] `user_id` always derived from session, never from request params
- [ ] Cloud sync propagates correct `user_id` for Pro users
- [ ] `allowed_users` table correctly maps OAuth identity to license/user_id
- [ ] `cleanup_orphaned_memories` RPC scoped by `user_id`
- [ ] `secure_profile` and `documents` `on_conflict` includes `user_id`
- [ ] `orchestrator-feed` route has role check
- [ ] `timeline` route strips job/git data for contributors
- [ ] `kb_queue` scoped by `user_id` or hidden from contributors
- [ ] Dashboard route has explicit 401 for unauthenticated requests
- [ ] `fetchTwitter()` skipped entirely for contributors (not just filtered client-side)

## Review Findings Log

| # | Severity | Issue | Status |
|---|----------|-------|--------|
| 1 | Critical | Pro license cookie grants owner identity | Addressed in Section 1 |
| 2 | Critical | Coordination tab exposes all users' data | Addressed — blocked until migration |
| 3 | Critical | Dashboard has no auth check; leaks Twitter data | Addressed in Section 4 |
| 4 | Critical | `supabaseForUser()` does not exist | Addressed — use existing `supabaseUser()` with OAuth |
| 5 | High | `cleanup_orphaned_memories` RPC deletes across users | Addressed in Section 5 |
| 6 | High | `secure_profile` upsert overwrites other users | Addressed in Section 5 |
| 7 | High | Timeline exposes job/git data to contributors | Addressed in Section 4 |
| 8 | High | `orchestrator-feed` has no role check | Addressed in Section 4 |
| 9 | Medium | `allowed_users` bootstrap gap | Documented in Section 1 |
| 10 | Medium | `kb_queue` not user-scoped | Addressed in Sections 4, 5 |
| 11 | Medium | Diagnostic tab scope mismatch | Fixed — moved to owner-only |
| 12 | Low | `documents` upsert `on_conflict` not user-scoped | Addressed in Section 5 |
