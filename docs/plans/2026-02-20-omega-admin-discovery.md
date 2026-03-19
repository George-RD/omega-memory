# Discovery Brief: OMEGA Admin Dashboard

## Problem Statement

This helps Jason check if his AI memory system is healthy and approve outbound actions (tweets, emails) without wading through developer dashboards full of numbers he doesn't need.

## Target User

- **Name/persona**: Jason, the sole user
- **Age/context**: 46, founder, based in Bangkok. Wears reading glasses. Needs large, readable text.
- **Primary goal**: Know if anything needs attention, approve/reject queued actions, and move on. Not studying analytics.
- **Environment**: Laptop (primary) and phone (quick checks). Often checks briefly between other work. Frequency: multiple times daily, sessions under 2 minutes.

## User Tasks (ranked by frequency)

1. **"Is anything broken?"** - Glance at system health. Are there errors? Is OMEGA running? Quick yes/no.
2. **"What needs my approval?"** - Review queued tweets, email drafts, and reminders. Approve, edit, or reject.
3. **"What happened while I was away?"** - Scan recent memories/events. See what OMEGA remembered, flagged, or acted on.
4. **"Find something OMEGA remembers"** - Search for a specific memory, document, or past decision.
5. **"Change a setting"** - Adjust notification preferences, job schedules, or system config. Rare (weekly or less).

## Competitive Analysis

| Site/App | What Works | What Doesn't | Key Insight |
|----------|-----------|--------------|-------------|
| **Linear** | Ultra-clean, task-focused. Dark theme with high contrast. No metric cards. Keyboard-first. Content is the interface, not chrome around content. | Marketing page only captured; actual app is behind login. | Task-oriented layout proves you don't need dashboards to manage complex systems. |
| **Vercel Dashboard** | Project-centric, not metric-centric. Each project shows status inline. Progressive disclosure: summary -> deploy details. Clean typography. | Redirected to login; public view limited. | Status-first design: green/red indicators with drill-down, not charts. |
| **Better Stack (Uptime)** | Status-board approach: is it up or down? Green/red clarity. Large, confident typography. Minimal UI chrome. | Marketing page only. The monitoring dashboard itself wasn't accessible. | Monitoring is about yes/no answers, not graphs. The best status pages are the simplest. |
| **Notion** | Content-first. The document IS the interface. Minimal navigation. Progressive disclosure through toggle blocks. Large body text. | Can feel overwhelming for simple tasks. | When content is the product, get the chrome out of the way. |
| **Things 3** (reference, not scraped) | Task-focused, not data-focused. "Today" view answers the primary question. Beautiful typography. Generous whitespace. 18px+ body text. | iOS/Mac only. | The best task manager shows you what to do NOW, not everything you could do. |
| **Arc Browser** (reference) | Command bar as primary navigation (like Cmd+K). Minimal persistent UI. Focus on the content you're looking at. | Learning curve for new users. | Command palette > sidebar for power users who know what they want. |

## Pain Points (from design audit)

- **13px body text everywhere**: Hard to read, especially on mobile or with glasses. Audit found every body size below 18px minimum.
- **7 tabs is too many**: Dashboard, Feed, Actions, Insights, Docs, Jobs, Settings. Forces users to remember where things live.
- **Jargon labels**: "Error Pattern", "Decision", "Lesson Learned", "Entity Type", "Algorithmic value" are developer terms, not user terms.
- **Dashboard tab shows data without purpose**: Growth Pulse, Social Reach, Content Performance, Grant Pipeline. None answer "is anything broken?"
- **Insights tab overlaps with Dashboard**: Both show analytics/metrics.
- **6 components over 500 lines**: contentUtils.tsx at 2,367 lines. Maintenance burden.
- **Stub components**: BehavioralAnalysis.tsx (5 lines), EngagementSummary.tsx (20 lines) shipped to production.

## Design Trends Observed

- **Task-oriented over data-oriented**: Linear, Things, Todoist all lead with "what needs doing" not "here are your numbers."
- **Status-board simplicity**: Better Stack, Instatus, and similar monitoring tools use green/yellow/red with drill-down, not charts by default.
- **Command palette as primary nav**: Arc, Linear, Raycast, Notion all rely heavily on Cmd+K for navigation rather than extensive sidebar/tab structures.
- **Large typography is standard**: Modern tools use 16-20px body text. 13px is a relic of 2015 design.
- **Dark themes with high contrast**: Linear, Vercel, and others use dark backgrounds with bright, high-contrast text. Reduces eye strain for frequent use.
- **Content-first layouts**: The trend is away from dashboards toward showing the actual content (tasks, documents, messages) as the primary interface.

## Constraints

- **Technical**: Next.js (App Router), Tailwind CSS, deployed on Vercel (Hobby plan, one deploy per day)
- **Accessibility**: 18px body minimum, 4.5:1 contrast, 44px touch targets (see standards)
- **Brand**: OmegaMax existing color system (gold accent, semantic tokens). Custom design tokens already in place.
- **Scope**: Single user (Jason). No multi-tenant concerns. No onboarding flow needed.
- **Mobile**: Must work on phone for quick checks. Existing MobileNav.tsx is solid.
