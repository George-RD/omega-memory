# Work Profile Redesign: Insights Tab "What OMEGA Learned" Section

**Date**: 2026-02-21
**Scope**: Replace PatternInsights component with Work Profile
**Audience**: Admin-only (Jason's dashboard)

## Problem

The current "What OMEGA Learned" section displays internal ML artifacts:
- HDBSCAN cluster labels as "themes" (e.g. "business communityfirst profitfirst rationale")
- Thompson bandit stats with tiny sample sizes (7 trials)
- Synthetic sparklines for drift detection
- Knowledge concentration synthesis quotes

None of this is actionable or meaningful to an admin user.

## Solution: Work Profile

Replace all 4 sub-sections with a behavioral profile view that surfaces data OMEGA already computes (via `habits_profile`) but doesn't display.

## Data Architecture

### New types (replace PatternInsightsData)

```typescript
interface WorkProfileData {
  summary: string;               // "High task completer, trunk-based, multi-project"
  patterns: WorkPattern[];       // behavioral patterns grouped by dimension
  recommendations: Recommendation[];
  recentDecisions: RecentDecision[];
  totalMemories: number;
  hasData: boolean;
}

interface WorkPattern {
  dimension: string;             // "git_workflow", "session_timing", etc.
  dimensionLabel: string;        // "Git", "Schedule", "Tasks"
  description: string;           // "Trunk-based: 100% of commits on main/master"
  confidence: number;            // 0-100
  evidenceCount: number;
  sessionCount: number;
}

interface Recommendation {
  category: string;              // "workflow", "git"
  text: string;
}

interface RecentDecision {
  content: string;
  project: string | null;
  createdAt: string;
}
```

### API changes

Rewrite `/api/admin/pattern-insights` route to return `WorkProfileData`:

1. Query `behavioral_pattern` rows from Supabase (same source as current)
2. Parse metadata to extract dimension, confidence, evidence counts
3. Filter to confidence >= 0.65
4. Sort by confidence descending
5. Derive summary from top 3 patterns
6. Derive recommendations from pattern gaps (missing handoffs, high commit size)
7. New query: `event_type = 'decision'`, `ORDER BY created_at DESC`, `LIMIT 10` for recent decisions

Dimension label mapping (server-side):
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
};
```

## UI Layout

### A. Summary Header

```
WORK PROFILE
High task completer, trunk-based, multi-project developer
15 patterns · avg 88% confidence
```

One-line synthesis from top 3 patterns. No interactivity.

### B. Behavioral Patterns (main content)

Compact rows, each:
- Dimension label (left, fixed width, muted text)
- Description (flex, primary text)
- Confidence bar (gold, opacity scaled) + percentage (right)

Sorted by confidence descending. Only patterns >= 65%.

### C. Recommendations

Below divider. 1-2 cards with category badge (pill) and text.

### D. Recent Decisions

Below divider. Last 5 decisions as compact single-line items:
- Truncated content
- Project tag (if scoped)
- Relative timestamp

## Files to modify

1. `website/app/admin/lib/types.ts` -- replace pattern types with work profile types
2. `website/app/api/admin/pattern-insights/route.ts` -- rewrite to return WorkProfileData
3. `website/app/admin/components/PatternInsights.tsx` -- full rewrite to render work profile

## Files NOT modified

- `website/app/admin/components/Insights.tsx` -- still imports and renders `<PatternInsights />`
- Backend `src/omega/pattern_learner.py` -- data source unchanged
