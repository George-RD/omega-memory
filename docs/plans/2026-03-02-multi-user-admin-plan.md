# Multi-User Admin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Google Auth via Supabase Auth with per-user data isolation, invite-only whitelist, and self-service onboarding to the OMEGA admin dashboard.

**Architecture:** Supabase Auth handles Google OAuth and session management. RLS policies enforce per-user data isolation at the database level. A `proxy.ts` middleware validates the Supabase session (with HMAC cookie fallback for owner break-glass). All admin routes switch from the service-role `supabaseServer()` to a user-scoped Supabase client that respects RLS.

**Tech Stack:** Next.js 15 (App Router), @supabase/ssr, Supabase Auth (Google provider), Supabase Vault for secrets, GitHub API for project collaborator checks.

**Design doc:** `docs/plans/2026-03-02-multi-user-admin-design.md`

---

## Task 1: Supabase Migration -- New Tables and user_id Columns

**Files:**
- Create: `supabase/migrations/20260302100000_multi_user_auth.sql`

**Step 1: Write the migration SQL**

```sql
-- Multi-user auth: allowed_users, project_collaborators, user_id on data tables

-- 1. Allowed users whitelist
CREATE TABLE IF NOT EXISTS allowed_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'contributor',
  invited_by UUID REFERENCES auth.users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE allowed_users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "owner_manages_whitelist" ON allowed_users FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM allowed_users au
      WHERE au.email = auth.jwt()->>'email' AND au.role = 'owner'
    )
  );

-- 2. Project collaborators cache
CREATE TABLE IF NOT EXISTS project_collaborators (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  github_username TEXT NOT NULL,
  github_repo TEXT NOT NULL,
  project_name TEXT NOT NULL,
  synced_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, github_repo)
);
ALTER TABLE project_collaborators ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_see_own_collabs" ON project_collaborators FOR SELECT
  USING (user_id = auth.uid());

-- 3. Add user_id to memories
ALTER TABLE memories ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);

-- 4. Add user_id to tweets
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_tweets_user_id ON tweets(user_id);

-- 5. Add user_id to engagement_suggestions
ALTER TABLE engagement_suggestions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_engagement_suggestions_user_id ON engagement_suggestions(user_id);

-- 6. Add user_id to pending_events
ALTER TABLE pending_events ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_pending_events_user_id ON pending_events(user_id);

-- 7. Add user_id to job_approvals
ALTER TABLE job_approvals ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_job_approvals_user_id ON job_approvals(user_id);

-- 8. Add user_id to weekly_reports
ALTER TABLE weekly_reports ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_weekly_reports_user_id ON weekly_reports(user_id);

-- 9. Add user_id to sync_state (composite key)
ALTER TABLE sync_state ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
-- Drop old unique and add new composite
ALTER TABLE sync_state DROP CONSTRAINT IF EXISTS sync_state_table_name_key;
ALTER TABLE sync_state ADD CONSTRAINT sync_state_table_user_key UNIQUE (table_name, user_id);

-- 10. Update RLS on memories
DROP POLICY IF EXISTS "Users can manage their own memories" ON memories;
CREATE POLICY "users_own_memories" ON memories FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
CREATE POLICY "shared_project_memories" ON memories FOR SELECT
  USING (
    metadata->>'shared' = 'true'
    AND EXISTS (
      SELECT 1 FROM project_collaborators pc
      WHERE pc.user_id = auth.uid()
      AND pc.project_name = memories.entity_id
    )
  );

-- 11. Update RLS on tweets
DROP POLICY IF EXISTS "Users can manage their own tweets" ON tweets;
CREATE POLICY "users_own_tweets" ON tweets FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- 12. Update RLS on engagement_suggestions
DROP POLICY IF EXISTS "Users can manage engagement suggestions" ON engagement_suggestions;
CREATE POLICY "users_own_engagement" ON engagement_suggestions FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- 13. Update RLS on pending_events
DROP POLICY IF EXISTS "Users can manage their own pending events" ON pending_events;
CREATE POLICY "users_own_events" ON pending_events FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- 14. Update RLS on job_approvals
DROP POLICY IF EXISTS "Users can manage job approvals" ON job_approvals;
CREATE POLICY "users_own_approvals" ON job_approvals FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- 15. Update RLS on weekly_reports
DROP POLICY IF EXISTS "Users can manage weekly reports" ON weekly_reports;
CREATE POLICY "users_own_reports" ON weekly_reports FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- 16. is_project_collaborator helper function
CREATE OR REPLACE FUNCTION is_project_collaborator(p_user_id UUID, p_project TEXT)
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM project_collaborators
    WHERE user_id = p_user_id AND project_name = p_project
  );
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

-- 17. Onboarding status check function
CREATE OR REPLACE FUNCTION user_needs_onboarding(p_user_id UUID)
RETURNS BOOLEAN AS $$
  SELECT NOT EXISTS (
    SELECT 1 FROM user_profiles WHERE user_id = p_user_id
  );
$$ LANGUAGE SQL SECURITY DEFINER STABLE;
```

**Step 2: Apply the migration**

Run: `cd ~/Projects/omega && npx supabase migration up --linked` or apply via Supabase dashboard.

**Step 3: Seed owner into allowed_users**

Run this SQL in Supabase SQL editor after your first Google login (replace with your actual auth.users UUID):

```sql
INSERT INTO allowed_users (email, role)
VALUES ('your-email@gmail.com', 'owner');
```

**Step 4: Commit**

```bash
git add supabase/migrations/20260302100000_multi_user_auth.sql
git commit -m "feat: add multi-user auth migration (allowed_users, user_id columns, RLS)"
```

---

## Task 2: Install @supabase/ssr and Add User-Scoped Client

**Files:**
- Modify: `website/package.json`
- Modify: `website/lib/supabase.ts`

**Step 1: Install @supabase/ssr**

Run: `cd ~/Projects/omega/website && npm install @supabase/ssr`

**Step 2: Add createUserClient to supabase.ts**

Add after the existing `supabaseBrowser()` function (after line 36 in `website/lib/supabase.ts`):

```typescript
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

// User-scoped client (reads Supabase auth cookies, respects RLS)
export async function supabaseUser() {
  const jar = await cookies();
  return createServerClient(
    getEnv("NEXT_PUBLIC_SUPABASE_URL"),
    getEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY"),
    {
      cookies: {
        getAll() {
          return jar.getAll();
        },
        setAll(cookiesToSet) {
          for (const { name, value, options } of cookiesToSet) {
            jar.set(name, value, options);
          }
        },
      },
    },
  );
}

// Get current user from Supabase session (returns null if not authenticated)
export async function getCurrentUser() {
  const client = await supabaseUser();
  const { data: { user } } = await client.auth.getUser();
  return user;
}

// Get current user's role from allowed_users
export async function getCurrentUserRole(): Promise<"owner" | "contributor" | null> {
  const user = await getCurrentUser();
  if (!user?.email) return null;
  const db = supabaseServer();
  const { data } = await db
    .from("allowed_users")
    .select("role")
    .eq("email", user.email)
    .single();
  return (data?.role as "owner" | "contributor") ?? null;
}
```

Note: Keep the existing `createClient` import from `@supabase/supabase-js` on line 1. Add the new import for `createServerClient` from `@supabase/ssr`.

**Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 4: Commit**

```bash
git add website/package.json website/package-lock.json website/lib/supabase.ts
git commit -m "feat: add @supabase/ssr and user-scoped Supabase client"
```

---

## Task 3: OAuth Callback Route

**Files:**
- Create: `website/app/auth/callback/route.ts`

**Step 1: Write the callback route**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { supabaseServer } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/admin";

  if (!code) {
    return NextResponse.redirect(new URL("/admin/login?error=no_code", request.url));
  }

  const response = NextResponse.redirect(new URL(next, request.url));

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
        },
      },
    },
  );

  const { data, error } = await supabase.auth.exchangeCodeForSession(code);

  if (error || !data.user?.email) {
    return NextResponse.redirect(new URL("/admin/login?error=auth_failed", request.url));
  }

  // Check whitelist
  const db = supabaseServer();
  const { data: allowed } = await db
    .from("allowed_users")
    .select("role")
    .eq("email", data.user.email)
    .single();

  if (!allowed) {
    // Not whitelisted: sign them out and redirect
    await supabase.auth.signOut();
    return NextResponse.redirect(
      new URL("/admin/login?error=not_allowed", request.url),
    );
  }

  // Ensure user settings exist (idempotent)
  await db.rpc("ensure_user_settings", {
    p_user_id: data.user.id,
    p_name: data.user.user_metadata?.full_name ?? data.user.email.split("@")[0],
  });

  // Check if onboarding needed
  const { data: needsOnboarding } = await db.rpc("user_needs_onboarding", {
    p_user_id: data.user.id,
  });

  if (needsOnboarding) {
    return NextResponse.redirect(new URL("/admin/onboarding", request.url));
  }

  return response;
}
```

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 3: Commit**

```bash
git add website/app/auth/callback/route.ts
git commit -m "feat: add OAuth callback route with whitelist check and onboarding redirect"
```

---

## Task 4: Update proxy.ts for Supabase Session Verification

**Files:**
- Modify: `website/proxy.ts`

**Step 1: Add Supabase session verification**

Add the import at the top (after line 1):

```typescript
import { createServerClient } from "@supabase/ssr";
```

Add the `/auth/callback` path to the skip list. Modify line 106-113 to also skip:

```typescript
  if (
    pathname === "/admin/login" ||
    pathname === "/api/auth/login" ||
    pathname === "/api/auth/webauthn/auth-options" ||
    pathname === "/api/auth/webauthn/auth-verify" ||
    pathname === "/api/schedules/heartbeat" ||
    pathname === "/auth/callback"
  ) {
    return NextResponse.next();
  }
```

Replace the protected routes check block (lines 116-133) with:

```typescript
  // Check protected routes
  if (PROTECTED_PREFIXES.some((p) => pathname.startsWith(p))) {
    // Try Supabase auth first
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    if (supabaseUrl && supabaseAnonKey) {
      const response = NextResponse.next();
      const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet) {
            for (const { name, value, options } of cookiesToSet) {
              response.cookies.set(name, value, options);
            }
          },
        },
      });

      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        return response; // Valid Supabase session
      }
    }

    // Fallback: HMAC cookie (owner break-glass)
    const cookie = request.cookies.get(COOKIE_NAME);
    if (!cookie?.value) {
      return redirectToLogin(request);
    }
    const secret = process.env.AUTH_SECRET;
    if (!secret) {
      return redirectToLogin(request);
    }
    const valid = await verifyToken(cookie.value, secret);
    if (!valid) {
      return redirectToLogin(request);
    }
  }
```

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 3: Commit**

```bash
git add website/proxy.ts
git commit -m "feat: add Supabase session verification to proxy middleware with HMAC fallback"
```

---

## Task 5: Update Login Page with Google Sign-In

**Files:**
- Modify: `website/app/admin/login/page.tsx`

**Step 1: Add Google Sign-In button**

Add a Supabase browser client import and Google login handler. Insert after the existing imports (line 5):

```typescript
import { createBrowserClient } from "@supabase/ssr";
```

Add inside the `LoginPage` component, after the `handlePasswordLogin` function (after line 89):

```typescript
  async function handleGoogleLogin() {
    setError("");
    setLoading(true);
    try {
      const supabase = createBrowserClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      );
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      });
      if (error) {
        setError(error.message);
        setLoading(false);
      }
      // Browser will redirect to Google
    } catch {
      setError("Failed to start Google login");
      setLoading(false);
    }
  }
```

Add the Google button in the JSX. Insert before the card div (after line 126, the top edge highlight div), as the first element in the card when state !== "loading":

```tsx
          {/* Google Sign In -- always visible */}
          {state !== "loading" && (
            <div className="flex flex-col items-center gap-4 mb-5">
              <button
                onClick={handleGoogleLogin}
                disabled={loading}
                className="w-full py-3 px-4 rounded-xl text-[14px] font-medium flex items-center justify-center gap-3 transition-all border border-edge hover:border-gold/30 hover:bg-gold/[0.04] disabled:opacity-50 text-ink"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                </svg>
                Sign in with Google
              </button>

              <div className="flex items-center gap-3 w-full">
                <div className="flex-1 h-px bg-edge" />
                <span className="text-[11px] text-ink-faint uppercase tracking-wider">or</span>
                <div className="flex-1 h-px bg-edge" />
              </div>
            </div>
          )}
```

Also add an error message for the `not_allowed` case. Add inside the component, after the `mounted` useEffect (after line 21):

```typescript
  // Check for auth errors in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authError = params.get("error");
    if (authError === "not_allowed") {
      setError("Your account is not authorized. Contact the admin for access.");
    } else if (authError === "auth_failed") {
      setError("Authentication failed. Please try again.");
    }
  }, []);
```

**Step 2: Install @supabase/ssr in website if not already done in Task 2**

Run: `cd ~/Projects/omega/website && npm ls @supabase/ssr` (verify installed)

**Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 4: Commit**

```bash
git add website/app/admin/login/page.tsx
git commit -m "feat: add Google Sign-In button to admin login page"
```

---

## Task 6: User Management API Routes

**Files:**
- Create: `website/app/api/admin/users/route.ts`

**Step 1: Write the users API route**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer, getCurrentUser, getCurrentUserRole } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// GET: List allowed users (owner only)
export async function GET() {
  const role = await getCurrentUserRole();
  if (role !== "owner") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const db = supabaseServer();
  const { data, error } = await db
    .from("allowed_users")
    .select("id, email, role, created_at")
    .order("created_at", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

// POST: Add a user to whitelist (owner only)
export async function POST(request: NextRequest) {
  const role = await getCurrentUserRole();
  if (role !== "owner") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const user = await getCurrentUser();
  const { email, userRole } = await request.json();

  if (!email || !email.includes("@")) {
    return NextResponse.json({ error: "Valid email required" }, { status: 400 });
  }

  const db = supabaseServer();
  const { data, error } = await db
    .from("allowed_users")
    .insert({
      email: email.toLowerCase().trim(),
      role: userRole || "contributor",
      invited_by: user?.id,
    })
    .select("id, email, role, created_at")
    .single();

  if (error) {
    if (error.code === "23505") {
      return NextResponse.json({ error: "User already exists" }, { status: 409 });
    }
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data, { status: 201 });
}

// DELETE: Remove a user from whitelist (owner only)
export async function DELETE(request: NextRequest) {
  const role = await getCurrentUserRole();
  if (role !== "owner") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { id } = await request.json();
  const db = supabaseServer();

  // Prevent owner from removing themselves
  const { data: target } = await db
    .from("allowed_users")
    .select("role")
    .eq("id", id)
    .single();

  if (target?.role === "owner") {
    return NextResponse.json({ error: "Cannot remove owner" }, { status: 400 });
  }

  const { error } = await db.from("allowed_users").delete().eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ ok: true });
}
```

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 3: Commit**

```bash
git add website/app/api/admin/users/route.ts
git commit -m "feat: add user management API route (owner-only whitelist CRUD)"
```

---

## Task 7: Update Settings Routes to Use auth.uid()

**Files:**
- Modify: `website/app/api/settings/profile/route.ts`
- Modify: `website/app/api/settings/agent/route.ts`
- Modify: `website/app/api/settings/memory/route.ts`
- Modify: `website/app/api/settings/projects/route.ts`
- Modify: `website/app/api/settings/integrations/route.ts`

**Step 1: Update profile route**

In `website/app/api/settings/profile/route.ts`, replace the import on line 2:

```typescript
// OLD:
import { ADMIN_USER_ID, supabaseServer } from "@/lib/supabase";
// NEW:
import { supabaseServer, getCurrentUser } from "@/lib/supabase";
```

Update the GET handler to scope by user:

```typescript
export async function GET() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const db = supabaseServer();
  const { data, error } = await db
    .from("user_profiles")
    .select("*")
    .eq("user_id", user.id)
    .single();

  if (error && error.code !== "PGRST116") {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data || DEFAULTS);
}
```

Update the PATCH handler to use `user.id` instead of `ADMIN_USER_ID`:

Replace `.insert({ ...updates, user_id: ADMIN_USER_ID })` on line 53 with:
```typescript
.insert({ ...updates, user_id: user.id })
```

And add the user check at the start of PATCH:
```typescript
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
```

And scope the existing row lookup:
```typescript
  const { data: existing } = await db
    .from("user_profiles")
    .select("id")
    .eq("user_id", user.id)
    .single();
```

**Step 2: Apply the same pattern to the other 4 settings routes**

Each route follows the same pattern:
1. Replace `ADMIN_USER_ID` import with `getCurrentUser`
2. Add `const user = await getCurrentUser()` + 401 guard
3. Replace `ADMIN_USER_ID` with `user.id`
4. Add `.eq("user_id", user.id)` to GET queries

**Step 3: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 4: Commit**

```bash
git add website/app/api/settings/
git commit -m "feat: replace ADMIN_USER_ID with auth user in all settings routes"
```

---

## Task 8: Update Admin API Routes for Per-User Data

This task covers the admin routes that query user-scoped data (memories, tweets, approvals, etc.). Routes that show global system data (coordination, diagnostic) stay on `supabaseServer()`.

**Files:**
- Modify: `website/app/api/admin/memories/graph/route.ts`
- Modify: `website/app/api/admin/memories/[id]/route.ts`
- Modify: `website/app/api/admin/approvals/route.ts`
- Modify: `website/app/api/admin/events/route.ts`
- Modify: `website/app/api/admin/reports/route.ts`
- Modify: `website/app/api/admin/dashboard/route.ts`
- Modify: `website/app/api/admin/insights/route.ts`
- Modify: `website/app/api/admin/search/route.ts`

**Step 1: Update memories graph route**

In `website/app/api/admin/memories/graph/route.ts`, add user scoping. After the existing query builder, add a user_id filter:

```typescript
import { getCurrentUser } from "@/lib/supabase";

// Inside the GET handler, after building the base query:
const user = await getCurrentUser();
if (user) {
  // Show own memories + shared project memories
  query = query.or(`user_id.eq.${user.id},and(metadata->>shared.eq.true)`);
}
```

**Step 2: Apply user scoping to other data routes**

For each route that queries `tweets`, `engagement_suggestions`, `pending_events`, `job_approvals`, `weekly_reports`:
1. Import `getCurrentUser`
2. Get the current user
3. Add `.eq("user_id", user.id)` to queries

For routes that are purely system-level (coordination, diagnostic, llm-usage): leave unchanged on `supabaseServer()`.

**Step 3: Update the approvals route**

In `website/app/api/admin/approvals/route.ts`, replace the hardcoded `decidedBy: "admin"` (line 61) with the actual user identity:

```typescript
const user = await getCurrentUser();
const decidedBy = user?.email ?? "admin";
```

**Step 4: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 5: Commit**

```bash
git add website/app/api/admin/
git commit -m "feat: add per-user data scoping to admin API routes"
```

---

## Task 9: Admin Page Role-Based Tab Visibility

**Files:**
- Modify: `website/app/admin/page.tsx`
- Create: `website/app/admin/hooks/useCurrentUser.ts`

**Step 1: Create a client-side user hook**

```typescript
"use client";

import { createBrowserClient } from "@supabase/ssr";
import { useState, useEffect } from "react";
import type { User } from "@supabase/supabase-js";

interface UserInfo {
  user: User | null;
  role: "owner" | "contributor" | null;
  loading: boolean;
}

export function useCurrentUser(): UserInfo {
  const [info, setInfo] = useState<UserInfo>({ user: null, role: null, loading: true });

  useEffect(() => {
    const supabase = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    );

    (async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) {
        setInfo({ user: null, role: null, loading: false });
        return;
      }

      // Fetch role
      const res = await fetch("/api/admin/me");
      const data = await res.ok ? res.json() : null;
      setInfo({ user, role: data?.role ?? "contributor", loading: false });
    })();
  }, []);

  return info;
}
```

**Step 2: Create the /api/admin/me route**

Create `website/app/api/admin/me/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { getCurrentUser, getCurrentUserRole } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const role = await getCurrentUserRole();
  return NextResponse.json({
    id: user.id,
    email: user.email,
    name: user.user_metadata?.full_name,
    avatar: user.user_metadata?.avatar_url,
    role,
  });
}
```

**Step 3: Update admin page.tsx**

Import and use the hook. Add a logout handler. Conditionally render tabs:

```typescript
import { useCurrentUser } from "./hooks/useCurrentUser";

// Inside AdminDashboard component:
const { user, role } = useCurrentUser();

// Filter tabs based on role -- owner sees all, contributors see all but can only
// interact with their own data (data isolation happens at the API/RLS level)
```

Add a logout button in the sidebar or top bar:

```typescript
async function handleLogout() {
  const supabase = createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
  await supabase.auth.signOut();
  // Also clear HMAC cookie if present
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/admin/login";
}
```

**Step 4: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 5: Commit**

```bash
git add website/app/admin/hooks/useCurrentUser.ts website/app/api/admin/me/route.ts website/app/admin/page.tsx
git commit -m "feat: add role-based tab visibility and logout to admin dashboard"
```

---

## Task 10: Onboarding Wizard

**Files:**
- Create: `website/app/admin/onboarding/page.tsx`

**Step 1: Write the onboarding wizard**

Create a multi-step wizard with: Profile (pre-filled from Google), Connect X (optional), Connect Email (optional), Link Local OMEGA (optional).

The wizard page should:
1. Fetch user info from `/api/admin/me`
2. Pre-fill name and avatar from Google profile
3. Allow skipping optional steps
4. On completion: POST to `/api/settings/profile` to create profile, then redirect to `/admin`

This is a client component with step-based state. Implementation details depend on the existing design patterns in the admin dashboard -- follow the same styling conventions (`btn-primary`, `text-ink`, `bg-surface`, etc.).

**Step 2: Verify build**

Run: `cd ~/Projects/omega/website && npx tsc --noEmit`

**Step 3: Commit**

```bash
git add website/app/admin/onboarding/page.tsx
git commit -m "feat: add self-service onboarding wizard for new admin users"
```

---

## Task 11: Backfill Migration for Existing Data

**Files:**
- Create: `supabase/migrations/20260302200000_backfill_owner_user_id.sql`

**Step 1: Write the backfill migration**

This runs AFTER the owner has signed in via Google and their `auth.users` row exists. It should be run manually via Supabase SQL editor:

```sql
-- Backfill existing data with owner's user_id
-- Run this AFTER the owner has logged in via Google Auth
-- Replace the UUID below with the owner's actual auth.users.id

DO $$
DECLARE
  owner_uid UUID;
BEGIN
  -- Get owner's auth user ID from allowed_users + auth.users
  SELECT au.id INTO owner_uid
  FROM auth.users au
  JOIN allowed_users aw ON aw.email = au.email
  WHERE aw.role = 'owner'
  LIMIT 1;

  IF owner_uid IS NULL THEN
    RAISE EXCEPTION 'Owner not found. Ensure owner has logged in via Google and is in allowed_users.';
  END IF;

  -- Backfill all tables
  UPDATE memories SET user_id = owner_uid WHERE user_id IS NULL;
  UPDATE tweets SET user_id = owner_uid WHERE user_id IS NULL;
  UPDATE engagement_suggestions SET user_id = owner_uid WHERE user_id IS NULL;
  UPDATE pending_events SET user_id = owner_uid WHERE user_id IS NULL;
  UPDATE job_approvals SET user_id = owner_uid WHERE user_id IS NULL;
  UPDATE weekly_reports SET user_id = owner_uid WHERE user_id IS NULL;
  UPDATE sync_state SET user_id = owner_uid WHERE user_id IS NULL;

  -- Update user_profiles and user_agent_settings from ADMIN_USER_ID to real ID
  UPDATE user_profiles SET user_id = owner_uid
    WHERE user_id = '00000000-0000-0000-0000-000000000001';
  UPDATE user_agent_settings SET user_id = owner_uid
    WHERE user_id = '00000000-0000-0000-0000-000000000001';
  UPDATE user_memory_settings SET user_id = owner_uid
    WHERE user_id = '00000000-0000-0000-0000-000000000001';

  RAISE NOTICE 'Backfilled all data to owner %', owner_uid;
END $$;
```

**Step 2: Commit**

```bash
git add supabase/migrations/20260302200000_backfill_owner_user_id.sql
git commit -m "feat: add owner data backfill migration (run after first Google login)"
```

---

## Task 12: Update Cloud Sync to Include user_id

**Files:**
- Modify: `src/omega/cloud/sync.py`

**Step 1: Add user_id to sync_memories records**

In `src/omega/cloud/sync.py`, modify the records dict (lines 156-170) to include `user_id`:

```python
# Add at the top of the CloudSync class or __init__:
self._user_id = self._load_user_id()

def _load_user_id(self) -> Optional[str]:
    """Load user_id from ~/.omega/config.json for cloud sync attribution."""
    config_path = Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega"))) / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            return config.get("user_id")
        except Exception:
            pass
    return None
```

Then in `sync_memories()`, add `user_id` to the records dict (after line 169):

```python
records.append({
    "local_id": row["id"],
    "content": row["content"],
    "event_type": row["event_type"],
    "priority": row["priority"],
    "session_id": row["session_id"],
    "project": row["project"],
    "tags": tags,
    "metadata": meta,
    "created_at": row["created_at"],
    "entity_id": row["entity_id"],
    "memory_type": row["memory_type"],
    "access_count": row["access_count"] or 0,
    "user_id": self._user_id,  # NEW: attribute to user
    "synced_at": datetime.now(timezone.utc).isoformat(),
})
```

Also update the `sync_state` upsert (lines 180-185) to include `user_id`:

```python
client.table("sync_state").upsert({
    "table_name": "memories",
    "user_id": self._user_id,  # NEW: per-user sync cursor
    "last_local_id": max_id,
    "last_sync_at": datetime.now(timezone.utc).isoformat(),
    "sync_count": len(records),
}, on_conflict="table_name,user_id").execute()
```

**Step 2: Add user_id to ~/.omega/config.json schema**

Users set this during onboarding (Task 10, Step 5 of the wizard):

```bash
# The onboarding wizard will tell users to run:
omega config set user-id <their-supabase-uuid>
```

Or manually add to `~/.omega/config.json`:

```json
{
  "user_id": "supabase-auth-user-uuid-here",
  "storage_path": "~/.omega",
  ...
}
```

**Step 3: Run tests**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cloud_sync.py -x -v` (if test file exists)
Run: `cd ~/Projects/omega && python3.11 -m pytest -x` (full suite)

**Step 4: Commit**

```bash
git add src/omega/cloud/sync.py
git commit -m "feat: include user_id in cloud sync push for multi-user isolation"
```

---

## Task 13: Supabase Dashboard Configuration

This is a manual step, not code.

**Step 1: Enable Google provider in Supabase**

1. Go to Supabase Dashboard > Authentication > Providers
2. Enable Google
3. Set Client ID and Client Secret from Google Cloud Console
4. Set redirect URL: `https://omegamax.co/auth/callback`

**Step 2: Create Google OAuth credentials**

1. Go to Google Cloud Console > APIs & Services > Credentials
2. Create OAuth 2.0 Client ID (Web application)
3. Add authorized JavaScript origin: `https://omegamax.co`
4. Add authorized redirect URI: `https://<your-supabase-project>.supabase.co/auth/v1/callback`
5. Copy Client ID and Client Secret to Supabase

**Step 3: Seed owner in allowed_users**

Run in Supabase SQL Editor:
```sql
INSERT INTO allowed_users (email, role)
VALUES ('your-email@gmail.com', 'owner');
```

**Step 4: Run backfill after first login**

After you've signed in with Google for the first time, run the backfill migration from Task 11 in the Supabase SQL Editor.

---

## Execution Order

Tasks 1-5 are the critical path (auth works end-to-end).
Tasks 6-9 add multi-user features.
Tasks 10-11 handle onboarding and data migration.
Task 12 extends the Python backend.
Task 13 is manual Supabase/Google configuration.

```
Task 1 (migration) ──→ Task 2 (client) ──→ Task 3 (callback) ──→ Task 4 (proxy) ──→ Task 5 (login page)
                                                                                          │
                                                           Task 6 (user mgmt API) ←──────┤
                                                           Task 7 (settings routes) ←─────┤
                                                           Task 8 (admin routes) ←────────┤
                                                           Task 9 (role-based UI) ←───────┘
                                                                     │
                                                           Task 10 (onboarding) ←─────────┘
                                                           Task 11 (backfill) ← after first login
                                                           Task 12 (sync.py) ← independent
                                                           Task 13 (Supabase config) ← before first login
```
