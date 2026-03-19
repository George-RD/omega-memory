# OMEGA Grant Pipeline

> Automated grant applications. Contact: jason@omegamax.co
> All drafts reuse content from `docs/pitch-narrative.md` and `docs/goose-grant-draft.md`.

## Pipeline Status

| # | Grant | Amount | Deadline | Format | Status |
|---|-------|--------|----------|--------|--------|
| 1 | Block Goose Grant | $100K/12mo | Rolling | Google Form | SUBMITTED (Feb 15, 2026) |
| 2 | NLnet NGI Zero Commons | Up to 50K EUR | Apr 1, 2026 | Web portal | SUBMITTED (Feb 15, 2026) |
| 3 | Sovereign Tech Fund | 50K+ EUR | Rolling | Web portal | SUBMITTED (Feb 15, 2026) |
| 4 | GitHub Secure OSS Fund | $10K ($6K+$2K+$2K) | Rolling | Google Form | SUBMITTED (Feb 15, 2026). Video pitch required separately. |
| 5 | RAAIS Foundation | $5K-$25K/3mo | Rolling | Typeform | SUBMITTED (Feb 15, 2026) |
| 6 | Mozilla Builders | Up to $100K | Next cohort TBD | Web portal | QUEUED |
| 7 | Prototype Fund | 95K EUR/6mo | Nov 30, 2025 | Web portal | QUEUED (check if open) |
| 8 | Zerodha FLOSS/fund | Variable | Rolling | funding.json in repo | QUEUED |

### Credits Programs (not cash, but free infrastructure)

| # | Program | Value | Format | Status |
|---|---------|-------|--------|--------|
| 9 | Microsoft for Startups | $150K Azure + $1K OpenAI | Web signup | QUEUED |
| 10 | Google Cloud for Startups | Up to $350K credits | Web portal | QUEUED |
| 11 | AWS Open Source Credits | Variable | Email | QUEUED |

---

## Automation Level Per Grant

### Tier 1: Fully Automatable (I fill + submit, you review)
These have simple web forms or email applications. I can draft everything from existing OMEGA materials.

- **Block Goose Grant** -- DONE
- **RAAIS Foundation** -- DONE (Typeform submitted Feb 15, 2026)
- **GitHub Secure OSS Fund** -- DONE (Google Form submitted Feb 15, 2026; 45-sec video pitch still needed)
- **Zerodha FLOSS/fund** -- Just add `funding.json` to the repo
- **AWS Open Source Credits** -- Email to awsopensourcecredits@amazon.com
- **Microsoft for Startups** -- Web signup, minimal info needed

### Tier 2: Mostly Automatable (I draft, you review, I submit)
These need slightly more tailored content or multi-step portals.

- **NLnet NGI Zero Commons** -- DONE (submitted Feb 15, 2026). Practical scope: accuracy sprint, docs, eval infra, packaging, MCP compliance. €50K requested.
- **Sovereign Tech Fund** -- DONE (Web portal submitted Feb 15, 2026)
- **Mozilla Builders** -- Accelerator application with more personal questions.
- **Google Cloud for Startups** -- Web portal, startup-focused questions.

### Tier 3: Needs Your Input (research framing or partnership)
- **Prototype Fund** -- May require German residency or partner.
- **Chan Zuckerberg EOSS** -- Needs scientific use case framing.
- **Open Technology Fund** -- Currently in litigation, status uncertain.

---

## Grant #2: NLnet NGI Zero Commons Fund (NEXT UP)

**Why**: Best fit. Dutch foundation (Kokyo) applying to Dutch funder (NLnet). EU digital infrastructure focus. Up to 50K EUR. Rolling deadlines every 2 months.

**URL**: https://nlnet.nl/propose/

**Key angles**:
- Local-first AI memory as digital commons infrastructure
- MCP standard integration (open protocol, not vendor lock-in)
- Foundation governance (Kokyo Keisho Zaidan Stichting)
- Privacy-preserving AI (no cloud dependency)
- Benchmarked and reproducible (LongMemEval, MemoryStress)

**What I need from you**: Nothing. I can draft the full proposal from existing materials.

**Deadline**: April 1, 2026 (next call)

---

## Reusable Content Blocks

All grants ask variations of the same questions. These blocks are pre-written:

### Project Summary (short)
OMEGA is an open-source, local-first persistent memory system for AI agents. Built as an MCP server, it scores 95.4% on LongMemEval (#1 on the public leaderboard). It provides semantic search, temporal reasoning, cross-session learning, and multi-agent coordination, all running locally with zero cloud dependencies. Apache 2.0 licensed, governed by Kokyo Keisho Zaidan Stichting.

### Project Summary (long)
See `docs/pitch-narrative.md`

### Open Source Commitment
Apache 2.0 licensed. Foundation governance through Kokyo Keisho Zaidan Stichting (Dutch foundation). All development public on GitHub (github.com/omega-memory/omega-memory). Benchmarks reproducible and published as open data.

### Privacy / Local-First
All data stays on the user's machine in SQLite. Embeddings run on CPU via ONNX. Profiles encrypted via system keyring. Zero cloud dependencies for core operation. Optional Supabase sync when user explicitly opts in.

### Verified Stats
- LongMemEval: 95.4% (466/500), #1 on public leaderboard
- Tests: 2,119 passing
- Source: ~19,000 lines code + ~20,000 lines tests
- PyPI: omega-memory v0.8.0
- License: Apache 2.0
- Funding to date: $0

### Team
Jason Sosa, independent developer. Foundation: Kokyō Keishō Zaidan Stichting (Netherlands).

### Location Policy
- EU-funded grants: Apply as the stichting, country = Netherlands
- Other grants: Match what they ask. "Organization country" = Netherlands. "Personal residence" = Singapore.
- Submitted inconsistencies: Goose says "United States" (needs correction), NLnet says "Singapore"

---

## Execution Order

1. ~~**Done**: Test jason@omegamax.co email delivery~~
2. ~~**Done**: Apply to Block Goose Grant (submitted Feb 15, 2026)~~
3. ~~**Done**: Apply to RAAIS Foundation (submitted Feb 15, 2026)~~
4. ~~**Done**: Apply to GitHub Secure OSS Fund (submitted Feb 15, 2026)~~ -- **TODO: Record 45-sec video pitch**
5. ~~**Done**: Apply to Sovereign Tech Fund (submitted Feb 15, 2026)~~
6. ~~**Done**: Apply to NLnet NGI Zero Commons (submitted Feb 15, 2026)~~
7. **This week**: Add funding.json to omega-memory/omega-memory repo (Zerodha FLOSS/fund)
8. **This week**: Sign up for Microsoft for Startups (free tier, instant)
9. **When cohort opens**: Apply to Mozilla Builders
10. **Monthly**: Email AWS Open Source Credits
11. **When ready**: Google Cloud for Startups application
