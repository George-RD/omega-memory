# Information Architecture: Pattern Insights

## Design Principle

The Pattern Insights section answers one meta-question: **"What has OMEGA learned about me?"** It is reflective, not operational. It complements the rest of the Insights page (which shows operational metrics like memory counts and content pipeline) by showing the *intelligence* layer: themes, effectiveness, and change.

No duplication with existing Insights sections. Memory counts stay in Summary Cards. Activity stays in Heatmap. Content pipeline stays in its section. Pattern Insights shows what the system *inferred* from all of that.

## Task-to-Content Mapping

| User Task | Content That Supports It |
|-----------|-------------------------|
| 1. "What are my main knowledge themes?" | Topic cluster bubbles: label, size, keywords |
| 2. "What's working best?" | Effectiveness ranking: memory types sorted by helpfulness |
| 3. "Is anything shifting?" | Drift cards: topic emergence/decline, session duration trend |
| 4. "Show me details of a theme" | Cluster detail: representative memories, keywords, session count |
| 5. "What did OMEGA synthesize?" | Synthesis cards: meta-memory summaries from significant clusters |

## Content Hierarchy

### Primary (always visible, answers at a glance)

**1. Knowledge Themes (bubble chart)**
Supports task #1: "What are my main knowledge themes?"

- Interactive bubble chart showing top clusters
- Each bubble: sized by member count, labeled with theme name
- 5-8 bubbles max (avoid clutter)
- Below bubbles: a one-line summary: "OMEGA found 7 themes across 546 memories"
- Mobile: degrades to a ranked list (theme name + count + bar)

**2. What's Working (ranked list)**
Supports task #2: "What's working best?"

- Ranked list of memory types by effectiveness (Thompson expected rate)
- Each row: type label, effectiveness badge ("Very helpful" / "Helpful" / "Mixed" / "Needs data"), evidence count
- Max 5-6 types shown
- The ranking tells Jason which memory types actually help when surfaced, and which don't

**3. Trends (compact cards)**
Supports task #3: "Is anything shifting?"

- 1-3 small trend cards, only shown when drift is detected
- Each card: plain-language headline + sparkline + direction arrow
- Examples:
  - "Product strategy is a growing theme (+40% over 3 months)"
  - "Sessions are 25% longer recently (48min avg vs 38min historical)"
  - "Threading topic is declining (15 -> 8 memories)"
- If no drift detected: section hidden entirely (no empty state noise)

### Secondary (one click away)

**4. Cluster Detail (expanded on bubble click)**
Supports task #4: "Show me details of a theme"

- Appears when a bubble is clicked (inline expansion, not modal)
- Shows: theme label, member count, session count, top keywords as tags
- Representative memories: 3-5 actual memory snippets with node_ids (citations)
- Confidence badge: "Strong pattern" / "Emerging" / "Developing"
- Close button returns to bubble view

**5. Synthesis Cards (below bubbles, scrollable)**
Supports task #5: "What did OMEGA synthesize?"

- 2-4 cards showing meta-memory summaries
- Each card: blockquote-style text of the synthesized insight
- Subtle link: "Based on N memories" (clickable to see the cluster)
- Only shown for clusters with 8+ members (significant themes)

### Tertiary (on demand, for the curious)

**6. Full Rankings Table**
- Expandable section below "What's Working"
- Shows all Thompson arms: arm_id, trials, successes, expected rate, boost factor
- Technical details for when Jason wants to verify the system's logic
- Collapsed by default with "Show details" toggle

**7. Cluster History**
- Available from cluster detail view
- Shows how this cluster's size changed over snapshots (if multiple exist)
- Simple sparkline or "First seen: date, Current: N memories"

### Removed (not shown)

| Content | Reason |
|---------|--------|
| Raw confidence scores (0.78) | Jargon. Replaced by verbal qualifiers. |
| Alpha/beta parameters | Thompson math. Replaced by effectiveness badges. |
| HDBSCAN noise ratio | Implementation detail. Not useful to user. |
| Cluster centroids | 384-dim vectors. Meaningless to display. |
| Pattern keys (theme:threading-concurrency) | Internal identifiers. Never shown. |
| CUSUM/EWMA values | Statistical details. Replaced by plain-language trend cards. |
| c-TF-IDF scores | Labeling internals. Keywords shown instead. |
| Embedding variance checks | Quality guard. Invisible to user. |

## Navigation Structure

The Pattern Insights section lives within the existing Insights tab, replacing the `BehavioralAnalysis` stub. No new tabs or pages needed.

```
Insights Tab
  |-- Summary Cards (existing)
  |-- Memory System (existing)
  |-- ** Pattern Insights ** (NEW, replaces BehavioralAnalysis stub)
  |      |-- Knowledge Themes (bubbles)
  |      |-- What's Working (ranked list)
  |      |-- Trends (drift cards, conditional)
  |      |-- Synthesis Cards
  |-- Content Pipeline (existing)
  |-- Project Breakdown (existing)
  |-- Activity Heatmap (existing)
```

Placement after "Memory System" and before "Content Pipeline" is intentional: it sits between "what OMEGA stored" (memory system metrics) and "what OMEGA published" (content pipeline), answering the middle question: "what OMEGA learned."

## Label Glossary

| Technical Term | User-Facing Label | Rationale |
|---------------|-------------------|-----------|
| memory_clusters | Knowledge Themes | "Clusters" is ML jargon. "Themes" is what they are. |
| thompson_arms | What's Working | Nobody needs to know about bandits. They want to know what works. |
| topic_drift | Trends | "Drift" sounds broken. "Trends" is neutral and clear. |
| behavioral_drift | Session Trends | Specific enough without being technical. |
| knowledge_concentration | Key Insight | "Concentration" is stats jargon. It's just an insight. |
| confidence: 0.78 | Strong pattern | Verbal qualifier (see mapping below). |
| confidence: 0.65 | Emerging pattern | |
| confidence: 0.50 | Developing | |
| evidence_count | Based on N memories | Plain attribution. |
| evidence_sessions | Across N sessions | Plain attribution. |
| expected_rate (Thompson) | Very helpful / Helpful / Mixed / Needs data | Verbal tier (see mapping below). |
| member_count | N memories | Just the count. |
| representative_memory_ids | Example memories | What they are. |
| pattern_type: memory_theme | Theme | Drop the prefix. |
| pattern_type: workflow_sequence_deep | Common workflow | Descriptive. |

### Confidence Verbal Mapping

| Raw Confidence | Verbal Label | Color |
|---------------|-------------|-------|
| >= 0.80 | Strong pattern | type-lesson (green) |
| >= 0.65 | Emerging pattern | gold |
| >= 0.50 | Developing | ink-secondary |
| < 0.50 | (not shown) | (filtered out) |

### Effectiveness Verbal Mapping (Thompson)

| Expected Rate | Verbal Label | Color |
|--------------|-------------|-------|
| >= 0.70 | Very helpful | type-lesson (green) |
| >= 0.50 | Helpful | gold |
| >= 0.30 | Mixed | ink-secondary |
| < 0.30 or < 5 trials | Needs more data | ink-faint |

## Progressive Disclosure Map

| Content Area | Default View | Expanded View | Deep Dive |
|-------------|-------------|---------------|-----------|
| Knowledge Themes | Bubble chart: 5-8 bubbles, labels, sizes | Click bubble: keywords, memory count, session count, 3 example memories | Full cluster history (sparkline of size over time) |
| What's Working | Ranked list: type label + effectiveness badge | (no expansion needed, list is already scannable) | "Show details" toggle: full Thompson table with trials/successes |
| Trends | 1-3 compact cards with headline + sparkline | Click card: before/after comparison, longer explanation | (no deeper level; trends are self-explanatory) |
| Synthesis Cards | Blockquote summary + "Based on N memories" | Click "Based on N": shows the cluster detail | Click individual memories: links to memory search |

## Empty States

Each section needs a graceful empty state for when pattern learning hasn't run yet:

| Section | Empty State |
|---------|-------------|
| Knowledge Themes | "OMEGA is still learning your patterns. Themes will appear after the first analysis run (requires 10+ memories with embeddings)." |
| What's Working | "Effectiveness tracking begins after memories are surfaced and receive feedback. Keep using OMEGA and themes will emerge." |
| Trends | (Section hidden entirely when no drift detected. No empty state needed.) |
| Synthesis Cards | (Section hidden when no significant clusters exist. No empty state needed.) |
