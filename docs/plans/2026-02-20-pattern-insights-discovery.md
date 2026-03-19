# Discovery Brief: Pattern Insights (Insights Page)

## Problem Statement

This helps Jason understand what OMEGA has learned about his knowledge patterns, which memory types are most useful, and whether his interests are shifting, without needing to read ML terminology or raw statistics.

## Target User

- **Name/persona**: Jason, the sole user
- **Age/context**: 46, founder, Bangkok. Wears reading glasses. Needs large, readable text.
- **Primary goal**: Glance at what OMEGA has figured out about his memory patterns. "What themes keep coming up? What's working? What's changing?" Then move on.
- **Environment**: Laptop (primary), phone (quick checks). The Insights tab is visited less frequently than Dashboard: maybe weekly, sessions under 3 minutes. This is reflective, not urgent.

## User Tasks (ranked by frequency)

1. **"What are my main knowledge themes?"** See the topics OMEGA has clustered from 546+ memories. "Am I mostly storing decisions about threading, or about product strategy?"
2. **"What's working best?"** Which memory types actually help when surfaced? Are decisions more useful than lessons? (Thompson Sampling results, translated to plain language.)
3. **"Is anything shifting?"** Has a topic been growing or declining? Are sessions getting longer or shorter? (Drift detection, presented as trends.)
4. **"Show me the details of a theme"** Drill into a specific cluster: see representative memories, keywords, how many sessions contributed. Verification, not analytics.
5. **"What did OMEGA synthesize?"** See the meta-memory summaries OMEGA generated from clusters. "What recurring patterns did it find?"

## Competitive Analysis

| Site/App | What Works | What Doesn't | Key Insight |
|----------|-----------|--------------|-------------|
| **Spotify Wrapped** | Transforms raw data into identity-affirming narratives. Superlatives ("Your #1 topic"), temporal animations, sharable cards. Bold type, minimal chart complexity. | Only annual; methodology opaque. | **Turn data into narratives, not dashboards.** Frame metrics as stories. |
| **Notion AI** | Insights appear inline where you work (database autofill, search). Zero context-switching. | No dedicated insight overview; must ask for insights. | **Contextual delivery beats separate analytics.** But we need an overview page too. |
| **Obsidian Graph View** | Visually striking force-directed graph. Local Graph (1-2 hop neighborhood) is useful. Spots orphan notes. | Global graph is "a pretty hairball." Not navigational at scale. Positions change every load. | **Spatial graphs are motivational, not navigational.** Local > global. Bubble charts more practical. |
| **Elicit** | Structured tables with sentence-level citations. Every AI claim links to source papers. "More than chat." | Homepage feature-dense. No visual clustering. | **Structure AI output as verifiable tables, not prose.** Citations build trust. |
| **PostHog** | Click any funnel data point to see the actual session recording. Correlation analysis auto-surfaces "X is 3x more likely." | Developer-first; non-technical users may find SQL editor intimidating. | **Link insights to raw evidence.** Click a cluster to see the actual memories. |
| **Amplitude** | Root cause analysis: when a metric spikes, it automatically identifies *why*. Proactive insight delivery. | Heavy on jargon ("complex distributed joins"). | **Explain anomalies, don't just detect them.** "Why" matters more than "what." |
| **Mixpanel Metric Trees** | Hierarchical KPI decomposition. Shows how metrics causally relate. Templates lower barrier. | Visually busy homepage. AI claims vague. | **Show how insights relate to each other**, not just flat cards. |
| **Apple Health** | Card-based summaries. Plain-language health insights. Calendar heatmaps universally understood. Trend arrows. | Limited customization. | **Cards with natural language + trend arrows** are the most accessible format for non-technical users. |

## Pain Points (from current state)

- **BehavioralAnalysis.tsx is a 5-line stub returning null**: The "Behavioral Analysis" section was planned but never built. This is a blank canvas.
- **No pattern visibility**: OMEGA discovers clusters, Thompson rankings, and drift internally, but Jason has zero visibility into what it learned.
- **Trust gap**: Without seeing what OMEGA has learned, the system feels like a black box. "Is it actually getting smarter?"
- **Existing Insights page is operational metrics only**: Memory counts, session counts, content pipeline. No "what did the AI learn?" section.
- **1,150-line monolith**: Current Insights.tsx needs the new section to be a clean, separate component (not more code in the monolith).

## Design Trends Observed

- **Natural language over numbers**: Lead with human-readable sentences ("Your top theme is product strategy"), not raw percentages. Reserve numbers for drill-down.
- **Insight cards as the atomic unit**: Self-contained cards with headline + mini-visual + confidence badge + action link. The dominant pattern across all modern analytics products.
- **Bento grid layout**: Mixed card sizes, most important insights get largest cards. Apple, Notion, most modern SaaS products use this.
- **Bubble charts for topic clusters**: Intuitive for non-technical users. Size = importance. Color = category. Click to explore. No training needed.
- **Verbal confidence qualifiers**: "Strong pattern" / "Emerging" / "Needs more data" instead of "0.78 confidence." Only show numbers on drill-down.
- **Progressive disclosure**: Headline > mini sparkline > full detail on click. Three layers, not one dump.
- **Show outcomes, not mechanisms**: "Decisions are your most useful memory type" not "Beta(47, 12) posterior with E[p]=0.80." Never expose Thompson Sampling math.
- **Citations**: Every insight links to the source memories. Click to verify. Builds trust.

## Constraints

- **Technical**: Next.js App Router, Tailwind CSS, existing design tokens (gold accent, dark canvas). Deploy on Vercel Hobby plan.
- **Integration point**: Replace `BehavioralAnalysis.tsx` stub. New component imported by existing `Insights.tsx`.
- **Data source**: New API endpoint (`/api/admin/pattern-insights`) that queries `memory_clusters`, `thompson_arms`, and `memories` tables from Supabase or direct SQLite.
- **Accessibility**: 18px body minimum, 4.5:1 contrast, 44px touch targets. Existing design system enforces this.
- **Scope**: Single user (Jason). No multi-tenant. No onboarding. The component lives within the existing Insights tab.
- **Mobile**: Must degrade gracefully. Bubble chart becomes a ranked list on small screens.

## Data Available for Visualization

From the pattern learning system (just implemented):

| Data Source | What It Contains | Visual Potential |
|-------------|-----------------|------------------|
| `memory_clusters` table | cluster_id, label, member_count, centroid, keywords, representative_memory_ids | Bubble chart (size=count, label=theme), keyword tags |
| `thompson_arms` table | arm_id, arm_type, alpha, beta, total_trials, total_successes | "What's working" ranking, boost factors |
| `PatternLearner.detect_topic_drift()` | cluster growth/decline over snapshots | Sparkline trends, "growing"/"declining" badges |
| `PatternLearner.detect_behavioral_drift()` | session duration z-scores | Trend card: "Sessions are 30% longer recently" |
| `PatternLearner.synthesize_meta_memories()` | template summaries of cluster themes | Quote-style cards with cluster context |
| `behavioral_pattern` memories | pattern_type, confidence, evidence_count, pattern_key | Insight cards with evidence counts |
