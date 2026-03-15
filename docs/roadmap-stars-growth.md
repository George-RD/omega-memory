# OMEGA Stars Growth Roadmap

**Created**: 2026-03-14
**Goal**: 37 → 100 stars (30 days), 100 → 500 stars (90 days)
**Constraint**: $0 budget, solo founder, organic only

## Baseline Metrics (March 14, 2026)

| Metric | Value |
|--------|-------|
| GitHub stars | 37 |
| GitHub forks | 9 |
| GitHub watchers | 2 |
| Open issues | 9 (5 are Good First Issues) |
| PyPI downloads/day | 106 |
| PyPI downloads/week | 589 |
| PyPI downloads/month | 3,611 |
| X followers (@omega_memory) | 1,333 |
| X engagement rate | 10.1% |
| Pro customers | 1 |
| Comparison pages | 8 (Mastra, Letta, Supermemory, LangChain, Mem0, Zep, OpenMemory, MEMORY.md) |
| Awesome-list PRs (merged) | 4 (punkpeye, awesome-nostr, TensorBlock, awesome-L402) |
| Awesome-list PRs (open) | 11+ |
| MCP Registry | Listed (Official + 6 directories) |
| Blog posts | 3+ on omegamax.co |
| Integrations | 1 (CrewAI) |

## ICP

Senior/staff engineers (25-44) who use AI coding agents daily (Claude Code, Cursor).
Already spending on AI tools. Frustrated by context loss between sessions.
Discover tools via GitHub, r/ClaudeAI, MCP directories, X.

## Strategic Goals

| # | Goal | Metric | Target | Horizon |
|---|------|--------|--------|---------|
| G1 | Increase discovery | GitHub stars | 100 | 30 days |
| G2 | Build ecosystem presence | Integration count | 3 (CrewAI, LangGraph, AutoGen) | 60 days |
| G3 | Compound organic traffic | omegamax.co monthly visitors | 5K | 60 days |
| G4 | Scale community | GitHub contributors | 5 | 90 days |
| G5 | Reach escape velocity | GitHub stars | 500 | 90 days |

## NOW (Weeks 1-4: March 14 - April 14)

### 1. Content that converts (RICE: 9.0)
- [x] Blog: "Claude Code Memory vs OMEGA" (SEO + agent-optimized)
- [x] Blog: "Give Your CrewAI Agents Persistent Memory"
- [ ] Blog: "How OMEGA's Retrieval Pipeline Beats Mem0" (technical deep dive)
- [ ] Reddit post: r/ClaudeAI (draft ready at docs/internal/reddit-claudeai-draft.md)
- [ ] Reddit post: r/mcp
- [ ] X thread: @jasonsosa (draft ready at docs/internal/x-thread-jasonsosa-draft.md)
- **Success metric**: 30+ stars from content alone
- **Owner**: Jason

### 2. Integration co-marketing (RICE: 8.0)
- [x] CrewAI integration built + committed
- [ ] PR to CrewAI docs (in progress)
- [ ] X post tagging @craborai announcing integration
- [ ] LangGraph integration (week 2-3)
- [ ] AutoGen integration (week 3-4)
- **Success metric**: Partner retweet reaching 10K+ impressions
- **Owner**: Jason + Claude

### 3. GitHub discoverability (RICE: 7.5)
- [x] Social preview image created (needs manual upload)
- [x] 17 topics set on repo
- [x] 5 Good First Issues seeded (#26-#30)
- [x] "Listed On" social proof added to README
- [x] Official MCP Registry listing live
- [ ] Star history badge visibility
- [ ] Upload social preview image (manual: Settings → Social preview)
- **Success metric**: 2x star velocity (from ~1/week to ~2/week organic)
- **Owner**: Jason

### 4. Cold outreach to power users (RICE: 6.0)
- [ ] Identify 20 Claude Code power users from X/GitHub
- [ ] Personalized DM with specific value prop for their use case
- [ ] Track response rate and conversions
- **Success metric**: 5-10 real users from outreach
- **Owner**: Jason

## NEXT (Weeks 5-8: April 14 - May 14)

| Initiative | Goal | RICE | Effort |
|-----------|------|------|--------|
| Dev.to technical series (3 posts) | G3 | 5.5 | 2w |
| Newsletter sponsorship (Console.dev or TLDR) | G1 | 5.0 | 1d |
| "Ship Week" mini-launch (3-5 features in a week) | G1, G5 | 4.8 | 1w |
| Discord community setup | G4 | 4.0 | 1d |
| Conference talk proposal (AI Engineer, PyCon) | G1, G3 | 3.5 | 2d |

## LATER (Months 3-6)

- Flowise no-code integration (visual builder audience)
- GitHub Sponsors setup (legitimacy signal)
- "OMEGA Ambassador" program for power users
- Video tutorials / YouTube presence
- Enterprise case study (if pro customers grow)

## ICEBOX

- Paid ads (wait until 500+ stars for social proof)
- Product Hunt launch (declining value for dev tools)
- Hacker News (user cannot log in)

## Metrics Tracking (Weekly)

Run `scripts/growth-metrics.sh` every Monday to collect:

| Metric | Source | Frequency |
|--------|--------|-----------|
| Stars | GitHub API | Weekly |
| Forks | GitHub API | Weekly |
| PyPI downloads | pypistats.org | Weekly |
| X followers | X API | Weekly |
| X engagement rate | Admin dashboard | Weekly |
| omegamax.co visitors | Vercel Analytics | Weekly |
| Blog post views | Vercel Analytics | Weekly |
| Awesome-list PR merge rate | GitHub search | Weekly |
| New contributors | GitHub API | Weekly |

## Decision Log

- 2026-03-14: Chose organic-only strategy. No paid ads until 500+ stars.
- 2026-03-14: CrewAI integration prioritized over LangGraph (larger community, no existing memory integration).
- 2026-03-14: MEMORY.md comparison blog prioritized as #1 content piece (targets exact ICP pain point).
- 2026-03-14: Skipped TAAFT ($49 paid directory), DevHunt/AlternativeTo/Uneed (need account sign-up).
