# Wireframes & Layout: Pattern Insights (Narrative Scroll)

## Design Direction Recap

Direction C: Narrative Scroll. Text-first, single-column. Each section leads with a natural-language sentence. Gold accents are sparse and intentional. No D3 or visualization libraries.

---

## Master Layout

The Pattern Insights section replaces the `BehavioralAnalysis` stub inside `Insights.tsx`. It sits between Memory System and Content Pipeline, wrapped in the same `admin-divider` pattern. Internally, it is a single `admin-card` containing stacked narrative blocks.

```
┌─ Insights.tsx ──────────────────────────────────────────────┐
│  ... Summary Cards, Memory System ...                       │
│                                                             │
│  ── admin-divider ──────────────────────────────────────    │
│                                                             │
│  ┌─ PatternInsights (admin-card, p-4) ────────────────────┐ │
│  │                                                        │ │
│  │  WHAT OMEGA LEARNED              admin-section-label   │ │
│  │                                                        │ │
│  │  ┌─ A. Theme Overview ──────────────────────────────┐  │ │
│  │  │  narrative sentence + pill tags + summary line   │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │                                                        │ │
│  │  ┌─ B. What's Working ─────────────────────────────┐  │ │
│  │  │  narrative sentence + ranked bar list            │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │                                                        │ │
│  │  ┌─ C. Trends (conditional) ───────────────────────┐  │ │
│  │  │  1-3 narrative trend cards with sparklines      │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │                                                        │ │
│  │  ┌─ D. Synthesis (conditional) ────────────────────┐  │ │
│  │  │  blockquote summaries with evidence links       │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ── admin-divider ──────────────────────────────────────    │
│                                                             │
│  ... Content Pipeline, Project Breakdown ...                │
└─────────────────────────────────────────────────────────────┘
```

**Key layout decision**: One `admin-card` wrapping, not separate cards per section. This creates a cohesive reading experience (scroll one continuous document) rather than a grid of disconnected cards. Internal sections are separated by subtle `border-b border-edge` dividers, not `admin-divider`.

---

## Section A: Theme Overview

**Supports tasks**: #1 "What are my main knowledge themes?" and #4 "Show me details of a theme"

### Default View

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Your top theme is product strategy.                    18px │
│  47 memories across 12 sessions.                        16px │
│                                                              │
│  ┌───────────────┐ ┌────────────┐ ┌─────────┐ ┌─────────┐  │
│  │● product      │ │● threading │ │● testing│ │● git    │  │
│  │  strategy     │ │  & concurr │ │         │ │  style  │  │
│  └───────────────┘ └────────────┘ └─────────┘ └─────────┘  │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐                    │
│  │● database│ │● api      │ │● deploy  │                    │
│  └──────────┘ └───────────┘ └──────────┘                    │
│                                                              │
│  7 themes across 546 memories                           14px │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Element details:**

| Element | Font | Size | Color | Notes |
|---------|------|------|-------|-------|
| Lead sentence | Outfit | 18px, 400 | ink-primary | "Your top theme is **product strategy**." Bold the theme name. |
| Evidence line | Outfit | 16px, 400 | ink-secondary | "47 memories across 12 sessions." |
| Theme pills | JetBrains Mono | 14px, 400 | ink-secondary on surface-elevated | Horizontal wrap. Dot uses gold. |
| Summary count | Outfit | 14px, 400 | ink-faint | "7 themes across 546 memories" |

**Pill design:**
- Background: `surface-elevated` (#151620)
- Border: `border-edge` (1px)
- Border-radius: 9999px (full pill)
- Padding: 6px 14px
- Left dot: 6px circle, filled gold (#d4a843)
- Text: ink-secondary
- Hover: border-gold/30, background shifts slightly brighter
- Click: expands to cluster detail (see below)
- Min touch target: 44px height

### Expanded Cluster Detail (on pill click)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Your top theme is product strategy.                         │
│  47 memories across 12 sessions.                             │
│                                                              │
│  ┌───────────────┐ ┌────────────┐ ┌─────────┐ ┌─────────┐  │
│  │● product      │ │● threading │ │● testing│ │● git    │  │
│  │  strategy  ▼  │ │            │ │         │ │         │  │
│  └───────────────┘ └────────────┘ └─────────┘ └─────────┘  │
│                                                              │
│  ┌─ cluster detail (slides down) ─────────────────────────┐  │
│  │                                                        │  │
│  │  Product Strategy                               18px   │  │
│  │  Strong pattern · 47 memories · 12 sessions     14px   │  │
│  │                                                        │  │
│  │  ┌────────┐ ┌──────────────┐ ┌──────────────┐         │  │
│  │  │roadmap │ │prioritization│ │user research │         │  │
│  │  └────────┘ └──────────────┘ └──────────────┘         │  │
│  │  ┌────────┐ ┌──────────┐                               │  │
│  │  │market  │ │launch    │                               │  │
│  │  └────────┘ └──────────┘                               │  │
│  │                                                        │  │
│  │  Example memories:                              16px   │  │
│  │                                                        │  │
│  │  "Decided to prioritize mobile onboarding over         │  │
│  │   desktop dashboard for Q1 launch."            16px    │  │
│  │   decision · 2 days ago                        14px    │  │
│  │                                                        │  │
│  │  "User research shows 70% of users check the           │  │
│  │   app on their phone first."                   16px    │  │
│  │   lesson_learned · 5 days ago                  14px    │  │
│  │                                                        │  │
│  │  "Roadmap: ship pattern insights before entity          │  │
│  │   profiles. Patterns are more immediately useful."      │  │
│  │   decision · 1 week ago                        14px    │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  7 themes across 546 memories                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Cluster detail elements:**

| Element | Font | Size | Color | Notes |
|---------|------|------|-------|-------|
| Theme heading | Outfit | 18px, 500 | ink-primary | |
| Confidence + counts | JetBrains Mono | 14px, 400 | Confidence badge color (see IA mapping) | "Strong pattern" = green, "Emerging" = gold |
| Keyword tags | JetBrains Mono | 14px, 400 | ink-secondary on surface-elevated | Smaller pills, no dot |
| "Example memories" label | Outfit | 16px, 400 | ink-secondary | |
| Memory snippet | Outfit | 16px, 400 | ink-primary | Blockquote style, gold left border (2px) |
| Memory metadata | JetBrains Mono | 14px, 400 | ink-faint | "decision . 2 days ago" |

**Interaction**: Clicking an already-expanded pill collapses it. Only one cluster expanded at a time. Slide-down animation: 200ms ease.

---

## Section B: What's Working

**Supports task**: #2 "What's working best?"

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ── border-b border-edge ──────────────────────── (divider)  │
│                                                              │
│  Decisions are your most useful memory type.            18px │
│  Surfaced often and rated helpful 82% of the time.      16px │
│                                                              │
│  Decisions      Very helpful  ████████████████████████  47   │
│  Lessons        Helpful       ████████████████         32   │
│  Preferences    Mixed         ████████████             24   │
│  Errors         Mixed         ██████████               18   │
│  Summaries      Needs data    ████                      6   │
│                                                              │
│                                          Show details ▸ 14px │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Element details:**

| Element | Font | Size | Color | Notes |
|---------|------|------|-------|-------|
| Lead sentence | Outfit | 18px, 400 | ink-primary | "**Decisions** are your most useful memory type." Bold the type. |
| Evidence line | Outfit | 16px, 400 | ink-secondary | |
| Type label | Outfit | 16px, 400 | ink-secondary | Left-aligned, fixed 120px width |
| Effectiveness badge | JetBrains Mono | 14px, 400 | Badge color per IA mapping | Green/gold/secondary/faint |
| Bar fill | - | 20px height | Gold at varying opacity | Top bar = gold/100%, others proportional |
| Count | JetBrains Mono | 14px, 400 | ink-faint | Right-aligned |
| "Show details" link | Outfit | 14px, 400 | gold | Hover: underline. Toggles full Thompson table. |

**Bar design:**
- Background: surface-elevated, full-width, 20px, rounded-full
- Fill: gold (#d4a843) with opacity proportional to rank (1st=100%, 2nd=70%, 3rd=50%, 4th=35%, 5th=20%)
- Width: proportional to trial count (largest = 100%)

### Expanded "Show details" (Full Thompson Table)

```
│                                          Show details ▾      │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Type        Trials  Successes  Rate   Boost            │  │
│  │ ─────────── ─────── ───────── ────── ─────            │  │
│  │ decision       47       38    81.9%   1.12x            │  │
│  │ lesson         32       21    67.2%   1.06x            │  │
│  │ preference     24       10    43.5%   0.96x            │  │
│  │ error          18        7    40.2%   0.94x            │  │
│  │ summary         6        2    40.0%   ----             │  │
│  └────────────────────────────────────────────────────────┘  │
```

- Table font: JetBrains Mono, 14px, ink-secondary
- Table background: surface-elevated
- "----" for boost when trials < 5 (MIN_TRIALS_FOR_BOOST)
- Collapsed by default. 200ms slide-down.

---

## Section C: Trends (Conditional)

**Supports task**: #3 "Is anything shifting?"

This section is **hidden entirely** when no drift is detected. No empty state.

When 1-3 trends exist, each is a stacked narrative card:

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ── border-b border-edge ──────────────────────── (divider)  │
│                                                              │
│  ┌─ trend card ───────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Product strategy is growing.                    18px  │  │
│  │  +40% over 3 months. 28 memories last month,    16px  │  │
│  │  up from 20 the month before.                          │  │
│  │                                                        │  │
│  │  ╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱                 sparkline, 40px h  │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ trend card ───────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Threading is declining.                         18px  │  │
│  │  -30% over 3 months. Fewer memories about        16px  │  │
│  │  locks and concurrency recently.                       │  │
│  │                                                        │  │
│  │                  ╲╲╲╲╲╲╲╲╲╲╲╲╲╲╲    sparkline, 40px h  │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ trend card ───────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Sessions are 25% longer recently.               18px  │  │
│  │  48 min average vs 38 min historical.            16px  │  │
│  │                                                        │  │
│  │  ───────────────────────╱╱╱╱╱╱╱     sparkline, 40px h  │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Element details:**

| Element | Font | Size | Color | Notes |
|---------|------|------|-------|-------|
| Lead sentence | Outfit | 18px, 400 | ink-primary | Bold the subject. "**Product strategy** is growing." |
| Detail text | Outfit | 16px, 400 | ink-secondary | Supporting numbers and context. |
| Sparkline | inline SVG | 40px height | gold line, gold/15% fill-below | Same pattern as Memory System sparkline. |

**Trend card design:**
- Background: surface-elevated (#151620)
- Border: 1px border-edge
- Border-radius: 8px
- Padding: 16px
- Gap between cards: 12px
- No gold left border (not admin-card; these are inner cards)
- No hover lift (they're informational, not interactive)

**Sparkline**: Inline SVG, 100% width of card, 40px height. Gold stroke (2px), gold fill-below (15% opacity). Same `makePath()` utility already in Insights.tsx.

---

## Section D: Synthesis (Conditional)

**Supports task**: #5 "What did OMEGA synthesize?"

Hidden when no significant clusters (8+ members) exist.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ── border-b border-edge ──────────────────────── (divider)  │
│                                                              │
│  ┌─ synthesis card ───────────────────────────────────────┐  │
│  │  ╎                                                     │  │
│  │  ╎  "Recurring theme: product strategy. Based on       │  │
│  │  ╎   47 memories across 12 sessions. Key topics:       │  │
│  │  ╎   roadmap, prioritization, user research.           │  │
│  │  ╎   Representative: Decided to prioritize mobile      │  │
│  │  ╎   onboarding over desktop dashboard."               │  │
│  │  ╎                                                     │  │
│  │  ╎                               Based on 47 memories  │  │
│  │  ╎                                                     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ synthesis card ───────────────────────────────────────┐  │
│  │  ╎                                                     │  │
│  │  ╎  "Recurring theme: threading & concurrency.         │  │
│  │  ╎   Based on 23 memories across 8 sessions. Key       │  │
│  │  ╎   topics: lock, mutex, thread-safe. Representative: │  │
│  │  ╎   threading.Lock is non-reentrant, never nest."     │  │
│  │  ╎                                                     │  │
│  │  ╎                               Based on 23 memories  │  │
│  │  ╎                                                     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Element details:**

| Element | Font | Size | Color | Notes |
|---------|------|------|-------|-------|
| Quote text | Outfit | 16px, 400 italic | ink-primary | Wrapped in quotes. Italic for blockquote feel. |
| Left border | - | 2px | gold (#d4a843) | Blockquote style, matches memory snippet style in cluster detail |
| "Based on N memories" | JetBrains Mono | 14px, 400 | gold | Right-aligned. Clickable: scrolls to and expands that theme's pill. |

**Synthesis card design:**
- Background: transparent (inherits card background)
- Left border: 2px solid gold
- Padding-left: 16px
- Gap between synthesis cards: 16px
- Max 4 synthesis cards (only significant clusters: 8+ members)

---

## Empty State

When pattern learning has not run yet:

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  WHAT OMEGA LEARNED                    admin-section-label   │
│                                                              │
│  OMEGA is still learning your patterns.                 18px │
│  Themes will appear after the first analysis run        16px │
│  (requires 10+ memories with embeddings).                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

- Lead sentence: Outfit, 18px, ink-primary
- Detail text: Outfit, 16px, ink-secondary
- No loading spinner. This is a permanent state until the first pattern learning run completes.

---

## Responsive Strategy

**Desktop-first** (the admin dashboard is laptop-primary), with graceful mobile narrowing.

| Breakpoint | Width | Changes |
|-----------|-------|---------|
| Desktop (default) | >= 768px | Full layout as wireframed |
| Mobile | < 768px | Pills wrap to fill width. Bar chart labels stack vertically. Sparklines remain full-width. Trend cards stack (already stacked). |

**Why no mobile-specific layout**: Direction C (Narrative Scroll) is already single-column. The only elements that change are:
- **Theme pills**: They already wrap with `flex-wrap`. On narrow screens, they'll stack 2-3 per row instead of 4-5. No layout change needed.
- **Bar chart rows**: The type label (120px) + badge + bar + count may need the badge to move below the label on very narrow screens. Use `@media (max-width: 480px)` to stack label/badge vertically.
- **Everything else**: Text blocks, sparklines, synthesis quotes all naturally resize in a single column.

---

## Component Inventory

| Component | File | Complexity | Dependencies |
|-----------|------|------------|--------------|
| `PatternInsights` | `PatternInsights.tsx` | Medium | New API endpoint |
| `ThemePills` | inline in PatternInsights | Simple | None |
| `ClusterDetail` | inline in PatternInsights | Medium | Slide-down animation (CSS) |
| `EffectivenessRanking` | inline in PatternInsights | Simple | None |
| `ThompsonTable` | inline in PatternInsights | Simple | Expandable (CSS) |
| `TrendCard` | inline in PatternInsights | Simple | `makePath()` from Insights.tsx |
| `SynthesisCard` | inline in PatternInsights | Simple | None |
| `Sparkline` (shared) | Extract from Insights.tsx | Simple | Already exists inline |

**Decision: single file vs. multi-file**: All components are inline within `PatternInsights.tsx`. The section is self-contained and none of these sub-components are reused elsewhere. This avoids file proliferation while keeping the file well under 500 lines (estimated ~350 lines).

**Exception**: `makePath()` is currently defined in `Insights.tsx`. Either extract it to a shared util or duplicate it (it's 8 lines). Prefer extraction to `app/admin/lib/chartUtils.ts`.

---

## API Endpoint

**New**: `app/api/admin/pattern-insights/route.ts`

Queries three tables from the local SQLite database (via a new bridge function or direct Supabase if tables are synced):

```typescript
interface PatternInsightsResponse {
  clusters: {
    cluster_id: number;
    label: string;
    member_count: number;
    representative_keywords: string[];
    representative_memory_ids: string[];
    confidence: number;     // from the behavioral_pattern memory
    session_count: number;  // unique sessions among members
  }[];
  thompson: {
    arm_id: string;
    arm_type: string;
    total_trials: number;
    total_successes: number;
    expected_rate: number;  // alpha / (alpha + beta)
    boost_factor: number;   // from ThompsonBandit.get_boost_factor()
  }[];
  trends: {
    type: "topic_drift" | "behavioral_drift";
    headline: string;       // from the behavioral_pattern content
    direction: "up" | "down" | "stable";
    sparkline_data: number[];  // time series for sparkline
  }[];
  synthesis: {
    content: string;        // the meta-memory text
    cluster_label: string;
    evidence_count: number;
  }[];
  total_memories: number;
  total_clusters: number;
}
```

**Data flow**: The API route calls the OMEGA MCP server (via the existing bridge pattern used by other admin API routes) to query `memory_clusters`, `thompson_arms`, and `behavioral_pattern` memories. No direct SQLite access from the website.

---

## Build Sequence

| Step | What | Depends On | Est. Lines |
|------|------|-----------|------------|
| 1 | API endpoint (`pattern-insights/route.ts`) | OMEGA bridge/MCP for cluster + Thompson data | ~120 |
| 2 | TypeScript types (`PatternInsightsData` in types.ts) | Step 1 response shape | ~40 |
| 3 | Extract `makePath()` to `chartUtils.ts` | None | ~15 |
| 4 | `PatternInsights.tsx` scaffolding + data fetch + empty state | Steps 1-3 | ~60 |
| 5 | Section A: Theme Overview + ThemePills | Step 4 | ~80 |
| 6 | Section A: Cluster Detail (expandable) | Step 5 | ~70 |
| 7 | Section B: What's Working (bars + badges) | Step 4 | ~60 |
| 8 | Section B: Thompson Table (expandable) | Step 7 | ~40 |
| 9 | Section C: Trend Cards + sparklines | Steps 3-4 | ~50 |
| 10 | Section D: Synthesis Cards | Step 4 | ~30 |
| 11 | Wire into Insights.tsx (replace BehavioralAnalysis import) | Steps 4-10 | ~5 |
| 12 | Responsive polish | All steps | ~20 |

**Total estimated**: ~590 lines across all files. The main `PatternInsights.tsx` stays under 400 lines.

**Verification after each step**: Build (`npm run build`) to catch type errors. After step 11: deploy to Vercel and visually verify on omegamax.co/admin.
