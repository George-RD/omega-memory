# Work Profile Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the "What OMEGA Learned" insights section with a Work Profile that surfaces behavioral patterns, recommendations, and recent decisions.

**Architecture:** Rewrite the existing `/api/admin/pattern-insights` API route to return `WorkProfileData` instead of `PatternInsightsData`. Rewrite the `PatternInsights.tsx` component to render work profile sections. Same data source (behavioral_pattern rows in Supabase), different interpretation. Add a second query for recent decisions.

**Tech Stack:** Next.js 15 (App Router), TypeScript, Tailwind CSS, Supabase

---

### Task 1: Update TypeScript types

**Files:**
- Modify: `website/app/admin/lib/types.ts`

**Step 1: Replace pattern insight types with work profile types**

Remove these interfaces (they will no longer be used):
- `PatternCluster`
- `EffectivenessArm`
- `PatternTrend`
- `PatternSynthesis`
- `PatternInsightsData`

Add these new interfaces:

```typescript
// ─── Work Profile ────────────────────────────────────────

export interface WorkPattern {
  dimension: string;
  dimensionLabel: string;
  description: string;
  confidence: number;
  evidenceCount: number;
  sessionCount: number;
}

export interface WorkRecommendation {
  category: string;
  text: string;
}

export interface RecentDecision {
  content: string;
  project: string | null;
  createdAt: string;
}

export interface WorkProfileData {
  summary: string;
  patterns: WorkPattern[];
  recommendations: WorkRecommendation[];
  recentDecisions: RecentDecision[];
  totalMemories: number;
  patternCount: number;
  avgConfidence: number;
  hasData: boolean;
}
```

**Step 2: Verify no other files import removed types**

Run: `grep -r "PatternCluster\|EffectivenessArm\|PatternTrend\|PatternSynthesis\|PatternInsightsData" website/app/ --include="*.ts" --include="*.tsx" -l`

Expected: Only `types.ts`, `PatternInsights.tsx`, and `pattern-insights/route.ts`. These are all files we're rewriting.

**Step 3: Commit**

```bash
git add website/app/admin/lib/types.ts
git commit -m "refactor(website): replace PatternInsightsData types with WorkProfileData"
```

---

### Task 2: Rewrite API route

**Files:**
- Modify: `website/app/api/admin/pattern-insights/route.ts`

**Step 1: Rewrite the route handler**

Replace the entire file contents. The new route:

1. Queries `behavioral_pattern` rows from Supabase (same table, same `event_type` filter)
2. Parses metadata to extract `pattern_type`, `pattern_key`, `confidence`, `evidence_count`, `evidence_sessions`
3. Filters to confidence >= 0.65, skips patterns where `user_confirmed === false` (denied)
4. Picks the highest-confidence pattern per `pattern_type` (dimension)
5. Builds summary from top 3 dimensions using `DIMENSION_PHRASES` mapping
6. Evaluates `RECOMMENDATION_RULES` against the active patterns
7. Queries recent decisions: `event_type = 'decision'`, `ORDER BY created_at DESC`, `LIMIT 5`
8. Returns `WorkProfileData`

Key constants to port from `behavioral.py`:

```typescript
const DIMENSION_LABELS: Record<string, string> = {
  git_workflow: "Git",
  session_timing: "Schedule",
  task_management: "Tasks",
  handoff_quality: "Handoffs",
  project_focus: "Projects",
  workflow_sequence: "Workflow",
  tool_preference: "Tools",
  memory_theme: "Themes",
  effectiveness_ranking: "Effectiveness",
  co_edit_cluster: "Files",
};

// Maps pattern_type to a summary phrase builder
// Input: the pattern content string
// Output: a short phrase for the summary line
const DIMENSION_PHRASES: Record<string, (content: string) => string> = {
  session_timing: (c) =>
    c.includes("morning") ? "morning worker" :
    c.includes("afternoon") ? "afternoon worker" :
    c.includes("evening") ? "evening worker" : "night owl",
  git_workflow: (c) =>
    c.includes("frequently") ? "atomic committer" :
    c.includes("sparingly") ? "batch committer" :
    c.includes("Trunk") ? "trunk-based" : "steady committer",
  project_focus: (c) => {
    const m = c.match(/Primary project: (\S+)/);
    return m ? `focused on ${m[1]}` : "multi-project developer";
  },
  handoff_quality: (c) =>
    c.includes("Thorough") ? "thorough handoff writer" : "concise handoff writer",
  task_management: (c) =>
    c.includes("High") ? "high task completer" :
    c.includes("Moderate") ? "steady task manager" : "exploratory worker",
  workflow_sequence: (c) =>
    c.toLowerCase().includes("handoff") ? "disciplined workflow" : "consistent workflow",
  tool_preference: (c) => c.split("(")[0].trim().slice(0, 40),
};

// Recommendation rules: each has a condition function and output text
interface RecommendationRule {
  condition: (patterns: ParsedPattern[]) => boolean;
  recommendation: string;
  category: string;
}
```

Recommendation rules to port (from `behavioral.py` lines 1254-1338):
- `no_handoff_discipline`: no pattern with key `workflow_handoff_discipline` but has session_timing patterns
- `large_commits`: pattern key `git_message_length` with "detailed" in content
- `low_completion_rate`: pattern key `task_completion_rate` with "Low" in content
- `high_blocker_rate`: pattern key `handoff_blocker_rate` exists

For recent decisions query:
```typescript
const { data: decisions } = await db
  .from("memories")
  .select("content, project, created_at")
  .eq("event_type", "decision")
  .order("created_at", { ascending: false })
  .limit(5);
```

**Step 2: Verify the route builds**

Run: `cd /Users/singularityjason/Projects/omega/website && npx tsc --noEmit`
Expected: No errors in pattern-insights route or types

**Step 3: Commit**

```bash
git add website/app/api/admin/pattern-insights/route.ts
git commit -m "refactor(website): rewrite pattern-insights API to return work profile data"
```

---

### Task 3: Rewrite PatternInsights component

**Files:**
- Modify: `website/app/admin/components/PatternInsights.tsx`

**Step 1: Rewrite the component**

Replace entire file. New structure:

```
PatternInsights (main)
  ├── ProfileHeader        -- summary line + stats
  ├── PatternRows          -- behavioral pattern list
  ├── Recommendations      -- 1-2 recommendation cards
  └── RecentDecisions      -- last 5 decisions
```

**ProfileHeader:**
- Section label: "WORK PROFILE" (using `admin-section-label` class)
- Summary text: `data.summary` in `text-[18px] text-ink-primary`
- Stats: `{patternCount} patterns · avg {avgConfidence}% confidence` in `text-[14px] text-ink-faint`

**PatternRows:**
Each pattern is a flex row:
- Left: `dimensionLabel` in `text-[14px] text-ink-faint w-20 shrink-0 uppercase tracking-wider font-mono`
- Center: `description` in `text-[16px] text-ink-primary flex-1`
- Right: confidence bar (gold, width proportional to confidence) + `{confidence}%` in `text-[14px] font-mono text-ink-faint`

Confidence bar: `h-5 bg-surface-elevated rounded-full` container, inner `bg-gold` div with opacity scaled (100% at 95+, 70% at 80+, 50% at 65+). Width = confidence%.

**Recommendations:**
Below `border-t border-edge` divider. Each recommendation:
- Category pill: `px-2 py-0.5 text-[12px] font-mono rounded bg-gold/[0.08] text-gold border border-gold/20`
- Text: `text-[16px] text-ink-secondary leading-relaxed`

**RecentDecisions:**
Below another `border-t border-edge` divider.
- Sub-label: "RECENT DECISIONS" in `admin-section-label` style
- Each decision is a flex row:
  - Content (truncated to ~120 chars): `text-[14px] text-ink-primary flex-1 truncate`
  - Project tag (if present): `text-[12px] font-mono text-ink-faint bg-surface-elevated px-1.5 py-0.5 rounded`
  - Relative time: `text-[13px] text-ink-faint tabular-nums shrink-0`

**EmptyState:** Same as current but updated text:
- "OMEGA is still learning your work patterns."
- "Behavioral patterns will appear after a few sessions with coordination enabled."

**Step 2: Verify the build**

Run: `cd /Users/singularityjason/Projects/omega/website && npx tsc --noEmit && npm run build`
Expected: Build succeeds with no errors

**Step 3: Commit**

```bash
git add website/app/admin/components/PatternInsights.tsx
git commit -m "feat(website): replace pattern insights with work profile view

Replaces ML artifact display (HDBSCAN clusters, Thompson bandit stats,
synthetic sparklines) with actionable behavioral profile showing work
patterns, recommendations, and recent decisions."
```

---

### Task 4: Clean up unused imports and verify

**Files:**
- Modify: `website/app/admin/components/PatternInsights.tsx` (if needed)
- Check: `website/app/admin/lib/types.ts`

**Step 1: Verify no dead imports remain**

Run: `grep -r "PatternCluster\|EffectivenessArm\|PatternTrend\|PatternSynthesis\|makePathFromValues" website/app/ --include="*.ts" --include="*.tsx"`
Expected: No matches (all old types removed, `makePathFromValues` no longer imported since sparklines are gone)

**Step 2: Check `chartUtils` is still needed by other components**

Run: `grep -r "makePathFromValues\|chartUtils" website/app/ --include="*.ts" --include="*.tsx" -l`
If only `PatternInsights.tsx` used it, the import is already removed. If other files use it, leave `chartUtils` alone.

**Step 3: Full build check**

Run: `cd /Users/singularityjason/Projects/omega/website && npm run build`
Expected: Build succeeds, no warnings about unused exports

**Step 4: Commit (if any cleanup was needed)**

```bash
git add -A website/app/
git commit -m "chore(website): clean up unused pattern insight imports"
```
