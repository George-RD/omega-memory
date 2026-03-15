# Information Architecture: OMEGA Admin Dashboard (Dashboard Tab Only)

## Design Principle

The Dashboard is a **command center**, not a feed, not an action queue, not analytics. It answers three questions:
1. Is everything working?
2. What can be improved?
3. Where does each project stand?

No duplication with other tabs. Feed shows activity. Actions shows queues. Insights shows deep analytics. Jobs shows schedules. Dashboard shows the big picture.

## Content Hierarchy

### Primary: System Health

Big, unmissable, first thing you see. Traffic-light simplicity across all systems.

- OMEGA core: running/down, memory count, last capture
- Jobs: X of Y healthy, any failing
- Cloud sync: connected/disconnected, last sync
- Website: deployed, last deploy time
- APIs: X/Twitter connected, Supabase connected

One glance = "everything is fine" or "something needs attention." No charts, no numbers beyond what's needed for the yes/no answer.

### Primary: Project Overview Cards

**Configurable focus**: Cards can be reordered and pinned to reflect current priorities. The order represents what Jason is focused on right now, not a fixed layout.

Cards for each active project, showing real data. Each card contains:

- **Project name + category tag** (Open Source, SaaS, Foundation, Portfolio, Trading)
- **Key metrics** specific to the project type:
  - Open source: stars, downloads, forks, contributors
  - SaaS: users, MRR, churn
  - Foundation: grants submitted, grants won, pipeline value
  - Portfolio: traffic, deploys
- **ROI indicator**: What's this project returning? (engagement, revenue, learning, strategic value)
- **Shipping progress**: Recent commits, open PRs, version, last release
- **Launch readiness**: Progress bar or status (pre-launch, launched, growing, mature)

Projects to show:
| Project | Category | Key Metrics |
|---------|----------|-------------|
| OMEGA (open source) | Open Source | Stars, downloads, forks, PyPI version |
| OMEGA (website) | Marketing | Traffic, deploys, uptime |
| kokyo | Foundation | Grants in pipeline, grants submitted, success rate |
| app-o-matic | SaaS | Users, version, last deploy |
| memorystress | Benchmark | Downloads, citations, HuggingFace views |
| jason-sosa-website | Portfolio | Traffic, last deploy |
| orchestrator | Tool | Version, last commit |
| polymarket-omega | Trading | P&L, active positions |

### Secondary: What Can Be Improved

Actionable insights derived from data, not raw data itself.

- "PyPI downloads are flat. Consider a blog post or Reddit thread."
- "3 jobs haven't run in 48 hours. Check scheduler."
- "Engagement rate dropped from 4.2% to 2.1% this week."
- "memorystress has 0 stars. Consider promoting on X."

Short, specific, actionable. Max 3-5 suggestions. Not a feed of everything, just the highest-impact observations.

### Removed (from Dashboard)

| Content | Reason | Where It Lives |
|---------|--------|---------------|
| Recent Activity feed | Duplicates Feed tab | Feed |
| Needs Attention / action queue | Duplicates Actions tab | Actions |
| Content Performance charts | Deep analytics | Insights |
| Top Performer tweets | Deep analytics | Insights |
| Engagement rate details | Deep analytics | Insights |
| Tweet/content queue | Duplicates Actions tab | Actions |
| Outreach stats | Duplicates Actions tab | Actions |

## Label Glossary

| Current Label | New Label | Rationale |
|--------------|-----------|-----------|
| Command Center | Keep | Fits the purpose |
| Growth Pulse | (absorbed into project cards) | Not a separate section |
| Social Reach | (removed) | Lives in Insights |
| Content Performance | (removed) | Lives in Insights |
| Grant Pipeline | (absorbed into kokyo project card) | Not a separate section |

## Progressive Disclosure Map

| Content Area | Default View | Expanded View | Deep Dive |
|-------------|-------------|---------------|-----------|
| System Health | Traffic light row: all green or specific alerts | Click to see individual system details | Navigate to Jobs tab |
| Project Card | Name, category, 2-3 key metrics, launch status | Click to expand: full metrics, recent commits, ROI breakdown | Navigate to project (external link or tab) |
| Improvements | Top 3 suggestions as one-liners | Click for context and suggested action | Navigate to relevant tab/tool |
