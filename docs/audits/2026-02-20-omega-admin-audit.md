# Design Audit: OMEGA Admin Dashboard
**Date**: 2026-02-20
**Scope**: Full admin dashboard at `~/Projects/omega/website/app/admin/`
**Auditor**: Rowan (eae6dcec)

## Score: 3.5/10 (Grade D)

Major redesign warranted. Font sizes fail accessibility standards, heavy jargon, classic dashboard-trap layout, and 6 component files over 500 lines.

## Detailed Findings

### 1. Typography — Fail (0)

Body text is 13px throughout. This is the single biggest issue.

| Size | Usage | Files | Standard | Status |
|------|-------|-------|----------|--------|
| 10px | Badge numbers, action counts | page.tsx, Feed.tsx | 14px min (labels) | **FAIL** |
| 11px | Section labels, type badges | Dashboard.tsx:67, Feed.tsx | 14px min (labels) | **FAIL** |
| 12px | Secondary labels, helper text, buttons | Settings.tsx:126-279, multiple | 16px min (secondary) | **FAIL** |
| 13px | Primary body text (most common) | Feed.tsx, Settings.tsx, Inbox.tsx | 18px min (body) | **FAIL** |
| 14px | Item details, field values | Feed.tsx, KnowledgeBase.tsx | 18px min (body) | **FAIL** |
| 15px | Body paragraphs, status lines | Feed.tsx:200, login/page.tsx | 18px min (body) | **FAIL** |
| 18px | Feed type headers | Feed.tsx | 18px min (body) | PASS |
| 22px | Login title | login/page.tsx:111 | 24px min (h2) | **FAIL** |
| 32px | Growth pulse values | Dashboard.tsx:71 | 32px min (h1) | PASS |

Every body text size fails the 18px minimum. Line heights not verified but likely below 1.5 given the tight layouts.

### 2. Accessibility — Needs Work (0.5)

- **Contrast**: Custom semantic tokens (text-ink, text-ink-secondary, text-ink-faint) suggest hierarchy, but "faint" implies low contrast. Cannot verify ratios without computed colors.
- **Touch targets**: `touch-manipulation` class used, buttons have py-2.5 px-4 padding. Likely meets 44px on most elements.
- **Color-only indicators**: Type badges use color (text-type-error, text-type-decision) but also include text labels. Partial pass.
- **Text resize at 200%**: Not tested. Max-width constraints (1280px, 768px) may cause issues.

### 3. Jargon — Fail (0)

Extensive technical terminology visible to end users:

| Jargon Label | Where | Suggested Replacement |
|-------------|-------|----------------------|
| Decision | Feed filters, badges | What Was Remembered |
| Lesson Learned / Learned | Feed filters, badges | Insight |
| Error Pattern / Issues | Feed filters | Recent Problems |
| Entity Type | Feed details | Person / Thing |
| Event Type | Feed details | Category |
| Session Summary / Recap | Feed badges | What Happened |
| Stale checkpoints | Dashboard | Needs Attention |
| Engagement rate | Dashboard | Reach |
| Algorithmic value | Dashboard | Visibility Score |
| Value Add / Experience Share / Constructive Challenge | TweetReview.tsx | (reply type labels, opaque) |
| Reply-to-Reply | TweetReview.tsx | Thread Reply |

13+ jargon labels found. A non-technical user (e.g., Jiana) would not understand "Error Pattern" or "Entity Type."

### 4. Redundancy — Pass (1)

Feed (detailed list) vs. Dashboard (aggregated metrics) vs. Insights (analytics) are complementary, not redundant. Actions filters to actionable items only. No significant overlap detected.

### 5. Dashboard Trap — Fail (0)

Classic dashboard-trap pattern:
- Sidebar + metric cards + charts + tables
- Growth Pulse section opens with 3 metric cards in a row
- Insights has 4 summary cards in a row
- Content Performance section: metric cards + chart
- The layout organizes data by category, not by user task
- No clear answer to "what does Jason need to DO here?"

The dashboard shows data "because we have it" rather than helping the user accomplish specific tasks.

### 6. Layout — Needs Work (0.5)

- Standard SaaS dashboard layout (sidebar + content area with tabs)
- No unexpected or intentional layout choices
- Well-executed within the pattern, but the pattern itself is generic
- Max-width constraints provide reasonable reading widths
- Custom design tokens show intentionality in the color system

### 7. Information Architecture — Needs Work (0.5)

- 7 tabs is a lot of navigation
- Content organized by data type (Feed, Insights, Docs, Jobs) rather than user tasks
- No progressive disclosure: everything is one level deep
- Most common task ("is anything broken?") requires scanning multiple tabs
- Settings buried as a tab when it's rarely used (should be a modal or overlay)

### 8. Empty States — Needs Work (0.5)

- BehavioralAnalysis.tsx: 5-line stub component
- EngagementSummary.tsx: 20-line stub
- SocialAnalytics.tsx: 210 lines but possibly unused/legacy
- Empty state messages exist ("No performance data yet") but stubs are shipped to production
- Skeleton loaders present (good)

### 9. Component Size — Fail (0)

6 files over 500 lines:

| File | Lines | Status |
|------|-------|--------|
| contentUtils.tsx | 2,367 | **CRITICAL** |
| Feed.tsx | 1,606 | **FAIL** |
| KnowledgeBase.tsx | 1,258 | **FAIL** |
| Insights.tsx | 1,149 | **FAIL** |
| TweetReview.tsx | 913 | **FAIL** |
| Dashboard.tsx | 715 | **FAIL** |
| Inbox.tsx | 639 | **FAIL** |
| Schedules.tsx | 542 | **FAIL** |

contentUtils.tsx at 2,367 lines is a monolithic utility file handling rendering, parsing, and type definitions. Should be split into 3-4 focused modules.

### 10. Mobile/Responsive — Pass (1)

Excellent mobile support:
- MobileNav.tsx: dedicated bottom navigation
- Collapsible sidebar (hidden < lg, overlay on toggle)
- Responsive grids (1-col mobile, 3-col desktop)
- Touch-optimized interactions (touch-manipulation class)
- Proper breakpoints at lg (1024px) and sm (640px)
- Content width adapts (max-w-5xl / max-w-3xl)

## Score Summary

| # | Category | Rating | Score |
|---|----------|--------|-------|
| 1 | Typography | Fail | 0 |
| 2 | Accessibility | Needs Work | 0.5 |
| 3 | Jargon | Fail | 0 |
| 4 | Redundancy | Pass | 1 |
| 5 | Dashboard Trap | Fail | 0 |
| 6 | Layout | Needs Work | 0.5 |
| 7 | Information Architecture | Needs Work | 0.5 |
| 8 | Empty States | Needs Work | 0.5 |
| 9 | Component Size | Fail | 0 |
| 10 | Mobile/Responsive | Pass | 1 |
| | **Total** | | **3.5/10** |

## Top 3 Priorities

1. **Typography overhaul**: Increase all body text to 18px minimum, secondary to 16px, labels to 14px. This affects every single view and is the most impactful accessibility fix.
2. **Task-oriented redesign**: Replace the dashboard-trap layout with a "What needs my attention?" interface. The primary question is "is anything broken?" not "show me all the numbers."
3. **Jargon elimination**: Replace 13+ technical labels with plain language. This is a quick win that makes the interface immediately more approachable.

## Recommendation

This dashboard scores 3.5/10 (Grade D), warranting a full redesign through the `design-process` pipeline starting at Phase 1 (Discovery). The technical foundation is solid: custom design tokens, excellent mobile support, and no data redundancy. But the information architecture serves data categories rather than user tasks, the typography fails accessibility standards at every level, and the interface is built for a developer audience rather than its actual user. Start with Phase 1 discovery to redefine what Jason actually needs to DO in this interface, then let the IA and design direction flow from that.
