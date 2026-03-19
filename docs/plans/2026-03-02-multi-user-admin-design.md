# Multi-User Admin with Google Auth + Per-User Data Isolation

**Date**: 2026-03-02
**Status**: Approved
**Approach**: Supabase Auth Native (Google OAuth)

## Summary

Transform the single-owner OMEGA admin dashboard into a multi-user platform where each user has their own isolated workspace — memories, X accounts, email, content pipeline — with shared project memory access gated by GitHub collaborator status.

## Key Decisions

| Decision | Choice |
|---|---|
| Auth provider | Google OAuth via Supabase Auth |
| Access control | Invite-only email whitelist (`allowed_users` table) |
| Data visibility | Strict per-user isolation + shared project toggle |
| Project sharing | GitHub collaborator access (cached in `project_collaborators`) |
| Ops controls | Per-user — each user connects their own X/email and manages their own pipeline |
| Owner role | System admin only (whitelist management, global config) |
| Password fallback | Kept for break-glass owner access |
| Data sharing | Zero — new users start with empty workspace, no inherited data/keys |

## Hard Constraints

- **No data sharing on onboarding**: New users see zero memories, zero API keys, zero account credentials from existing users. RLS enforces this at the database level.
- **No env var access**: Per-user secrets live in Supabase Vault via `user_integrations`. Env vars are owner break-glass only.
- **Self-service onboarding**: After email is whitelisted, users handle everything themselves via onboarding wizard.

## Authentication Flow

```
Browser → /admin/login → "Sign in with Google"
  → supabase.auth.signInWithOAuth({ provider: 'google' })
  → Google OAuth consent screen
  → Redirect to /auth/callback
  → /auth/callback:
      1. Exchange code for Supabase session
      2. Check email against allowed_users table
         → Not whitelisted: "Access denied, contact admin"
         → Whitelisted: continue
      3. Call ensure_user_settings(auth.uid(), name)
      4. Supabase session cookie set by @supabase/ssr
      5. Redirect to /admin (or onboarding wizard if first login)

Password fallback (owner only):
  → POST /api/auth/login with password
  → HMAC session cookie (existing flow, unchanged)
```

### proxy.ts Changes

The middleware checks Supabase session first, falls back to HMAC cookie:

```
1. Read Supabase auth cookies via @supabase/ssr
2. If valid Supabase session → allow (attach user_id to request)
3. Else check omega_admin_session HMAC cookie (existing flow)
4. Else redirect to login
```

## Data Isolation Model

### Per-User RLS

All user-scoped tables get `user_id UUID REFERENCES auth.users(id)`.

```sql
-- Personal data: strict isolation
CREATE POLICY "users_own_data" ON memories FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
```

### Shared Project Memories

```sql
-- Shared project memories: visible to GitHub collaborators
CREATE POLICY "shared_project_memories" ON memories FOR SELECT
  USING (
    metadata->>'shared' = 'true'
    AND is_project_collaborator(auth.uid(), project)
  );
```

The `is_project_collaborator()` function checks the `project_collaborators` cache table, which is periodically synced from GitHub API.

### Tables Requiring user_id Column

| Table | Notes |
|---|---|
| `memories` | Core memory storage |
| `tweets` | Per-user content pipeline |
| `engagement_suggestions` | Scoped to user's X accounts |
| `pending_events` | Jobs tied to user's integrations |
| `job_approvals` | Approval queue per user |
| `weekly_reports` | Per-user reports |
| `sync_state` | Keyed by `(table_name, user_id)` |
| `memory_embeddings` | Inherits isolation via FK + RLS join |
| `memory_edges` | Same |

### New Tables

```sql
-- Email whitelist + role
CREATE TABLE allowed_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'contributor',  -- 'owner' | 'contributor'
  invited_by UUID REFERENCES auth.users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- GitHub collaborator cache for project sharing
CREATE TABLE project_collaborators (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  github_repo TEXT NOT NULL,
  project_name TEXT NOT NULL,       -- maps to entity_id
  synced_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, github_repo)
);
```

## Role-Based UI

| Tab | Owner | Contributor |
|---|---|---|
| Dashboard | All metrics | Their own metrics |
| Projects | All projects | GitHub collaborator projects |
| Memories | Own + shared toggle | Own + shared toggle |
| Coordination | All agents | Own agents |
| Insights | All | Own + shared project |
| Diagnostics | Full | Full |
| Feed | Own X accounts | Own X accounts |
| Actions | Own approval queue | Own approval queue |
| Growth | Own X metrics | Own X metrics |
| Entities | All | GitHub collaborator projects |
| Jobs | Own scheduled jobs | Own scheduled jobs |
| Settings | Global + personal | Personal only |

Owner-only capabilities (not visible as tabs but gated in Settings):
- Manage `allowed_users` whitelist
- Global system configuration
- Supabase project settings

## Self-Service Onboarding

### Prerequisite (Owner Action)

Owner adds email to `allowed_users` via admin Settings > User Management.

### Onboarding Wizard (New User, Self-Service)

Triggered on first login (detected by empty `user_integrations` for their `user_id`).

```
Welcome to OMEGA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1: Profile
  → Name, timezone, avatar (pre-filled from Google account)

Step 2: Connect X (optional, do later from Settings)
  → OAuth flow to link their X account(s)
  → Keys stored in user_integrations via Supabase Vault

Step 3: Connect Email (optional, do later from Settings)
  → Gmail OAuth or SMTP credentials
  → Stored in user_integrations via Supabase Vault

Step 4: Install OMEGA locally (optional, do later)
  → pip install omega-memory
  → omega config set user-id <supabase-uuid>
  → Links local ~/.omega/ to their cloud account for sync
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

After completing (or skipping optional steps), the wizard flag clears and user lands on their empty-but-functional dashboard.

## Technical Changes

### New Package

- `@supabase/ssr` — cookie-aware Supabase client for Next.js server components and route handlers

### Supabase Dashboard Config

- Enable Google Auth provider
- Set Google OAuth Client ID + Secret (from Google Cloud Console)
- Configure redirect URL: `https://omegamax.co/auth/callback`

### New/Modified Files

| File | Change |
|---|---|
| `website/lib/supabase.ts` | Add `createUserClient(cookies)` using `@supabase/ssr` |
| `website/proxy.ts` | Add Supabase session verification before HMAC fallback |
| `website/app/admin/login/page.tsx` | Add "Sign in with Google" button |
| `website/app/auth/callback/route.ts` | **New** — OAuth callback handler |
| `website/app/admin/page.tsx` | Fetch user role, conditional UI |
| `website/app/admin/onboarding/page.tsx` | **New** — setup wizard |
| `website/app/admin/settings/users/` | **New** — whitelist management (owner only) |
| `website/app/admin/settings/integrations/` | **New** — per-user X/email connection UI |
| `website/app/api/admin/*` | Replace `supabaseServer()` with user-scoped client |
| `supabase/migrations/YYYYMMDD_multi_user.sql` | Schema: user_id columns, RLS, new tables |
| `src/omega/cloud/sync.py` | Include `user_id` in push payload |
| `~/.omega/config.json` | Add `user_id` field for local-to-cloud identity link |

### Migration Strategy

- All existing data (memories, tweets, events) gets owner's `user_id` backfilled
- Existing env var credentials continue working as owner fallback
- No data visible to new users — they start fresh

### What Stays Unchanged

- Local SQLite schema (single-user per machine)
- Python MCP server (local, single-user)
- Cron routes (CRON_SECRET bearer token, but jobs reference user_id for integrations)
- WebAuthn passkeys (optional convenience for owner)
