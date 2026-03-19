# NLnet Form Fields — Ready to Paste

> Open https://nlnet.nl/propose/ and paste each field below.
> Character limits noted. All fields verified under limits.

---

## Call: NGI Zero Commons Fund (already default)

## Name
```
Jason Sosa
```

## Email
```
jason@omegamax.co
```

## Phone
```
(leave blank)
```

## Organisation
```
Kokyō Keishō Zaidan Stichting (KvK 96951559)
```

## Country
```
Singapore
```

## Proposal name
```
OMEGA: Open Memory Infrastructure for AI Agents
```

## Website
```
https://github.com/omega-memory/omega-memory
```

---

## Abstract (1200 char limit)

```
OMEGA is open-source infrastructure giving AI agents persistent memory. It implements the Model Context Protocol (MCP), an open standard governed by the Linux Foundation, providing tools for semantic memory, temporal reasoning, cross-session learning, and multi-agent coordination. Everything runs locally with zero cloud dependencies.

Today's AI agents are stateless: every session starts from zero. Proprietary alternatives (Mem0, commercial vector DBs) route sensitive data through cloud services and create vendor lock-in.

OMEGA uses SQLite with vector search (sqlite-vec) and full-text search (FTS5), with ONNX Runtime embeddings for fully offline operation. It scores 95.4% on LongMemEval (ICLR 2025 agent memory benchmark), #1 on the public leaderboard. But multi-session reasoning is at 65% and preference extraction at 50%.

This grant funds: (1) accuracy improvements measured on public benchmarks, (2) documentation site and onboarding, (3) reproducible evaluation infrastructure, (4) one-command installation packaging, (5) MCP standard compliance as the spec evolves.

Apache-2.0, developed by Kokyō Keishō Zaidan Stichting (Dutch foundation, KvK 96951559).
```

---

## Previous experience (2500 char limit)

```
I have been building AI systems for over 10 years. OMEGA is my current focus: a 19,000-line Python codebase with 2,150+ passing tests, published on PyPI as omega-memory (v0.9.3), and used as an MCP server by developers running Claude Code, Goose, and other agent clients.

I also created and published MemoryStress, the first longitudinal memory benchmark for AI agents (583 facts, 1,000 sessions, 300 questions, simulating 10 months of use). Available as open data on HuggingFace and GitHub.

Kokyō Keishō Zaidan Stichting was established as a Dutch foundation to steward open infrastructure for AI agent systems. The foundation's charter mandates open-source development under Apache-2.0 and prohibits profit distribution, ensuring OMEGA remains a public good.
```

---

## Amount
```
50000
```

---

## Budget explanation (2500 char limit)

```
6 deliverable-based milestones. All funds: development labor, single developer, no overhead. Rate: ~42 EUR/hour (est. 1,200 hours).

M1: Memory Accuracy Sprint (14,000 EUR)
- Multi-session reasoning 65% -> 80%+ (cross-session linking, graph traversal)
- Preference extraction 50% -> 75%+ (dedicated preference pipeline)
- Temporal reasoning 71% -> 85%+ (temporal indexing)
- All measured on LongMemEval (public, reproducible)

M2: Documentation and Onboarding (10,000 EUR)
- Documentation site, API reference, quickstart guides per agent client
- Architecture docs, contributor guide, tutorials

M3: Evaluation Infrastructure (10,000 EUR)
- CI pipeline: LongMemEval + MemoryStress benchmarks per release
- Public accuracy dashboard, contributor-friendly benchmark harness

M4: Packaging and Distribution (6,000 EUR)
- One-command install: PyPI, Docker, Homebrew, platform packages
- Automated release pipeline with changelog

M5: MCP Standard Compliance (6,000 EUR)
- Track evolving MCP spec under Linux Foundation
- Interoperability test suite across client versions

M6: Community and Dissemination (4,000 EUR)
- Technical writeups per milestone, benchmark comparisons
- Board representative attends European events (FOSDEM, NLnet community days)
- Engagement with MCP ecosystem and developer communities

Total: 50,000 EUR

Other funding: None. Self-funded to date. Applying to other programs in parallel (Block Goose Grant, Sovereign Tech Fund, RAAIS, GitHub Secure OSS Fund) but no funding received.
```

---

## Compare with existing efforts (4000 char limit)

```
Mem0 (proprietary, VC-funded $4.2M): Cloud-hosted agent memory API. Closed-source, data leaves user's device, vendor lock-in. Targets enterprise SaaS revenue.

LangChain Memory: Tightly coupled to LangChain framework. No standalone use, no multi-agent coordination, no MCP support. Deprecated in favor of LangGraph checkpointing.

Commercial vector databases (Pinecone, Weaviate, Qdrant): General-purpose, not agent-specific. Require cloud infrastructure and subscriptions. No built-in agent workflow support (sessions, temporal reasoning, preference tracking).

ChromaDB: Open-source vector database. Good for retrieval, but no agent memory semantics, no coordination, no entity management. A building block, not a complete solution.

OMEGA's differentiation:
1. MCP-native: implements the open MCP standard, works with any MCP-compatible client
2. Local-first: all data on-device, encrypted at rest, no cloud dependency
3. Agent-specific: designed for agent workflows (sessions, lessons learned, temporal reasoning, preference tracking), not a generic vector database
4. Benchmarked: 95.4% on LongMemEval (#1 public leaderboard), reproducible methodology
5. Foundation-governed: Apache-2.0 under Dutch stichting with charter-mandated open licensing
```

---

## Technical challenges (5000 char limit)

```
1. Multi-session reasoning accuracy. When an agent synthesizes information across multiple past sessions, accuracy drops to 65%. The challenge: efficiently linking related memories across temporal boundaries without retrieving entire history. Approach: cross-session reference graph connecting related memories at storage time, reducing retrieval to graph traversal.

2. Preference extraction and consistency. Agents must learn preferences from natural conversation ("I prefer tabs over spaces") and apply them consistently. Current accuracy: 50%. Challenge: distinguishing stable preferences from one-time instructions, handling conflicts over time. Approach: dedicated preference memory with confidence scoring and temporal decay.

3. Embedding model portability. Different users run different local embedding models with varying dimensions and quality. Challenge: vector search quality across heterogeneous sources without re-indexing. Approach: model-tagged embeddings with automatic re-embedding when models change.

4. Scaling without cloud. SQLite is single-writer. Challenge: heavy multi-agent workloads on a single local database. Approach: WAL mode, connection pooling, write batching, carefully designed access patterns minimizing contention while preserving integrity.
```

---

## Ecosystem (2500 char limit)

```
OMEGA operates in the Model Context Protocol (MCP) ecosystem, an open standard for AI agent communication governed by the Agentic AI Foundation under the Linux Foundation. Members: Anthropic, Block, Google, Microsoft, OpenAI, AWS. Supported by major agent platforms: Claude Code, Goose, Cursor, Windsurf.

Persistent memory infrastructure is the missing layer. Every agent framework treats sessions as disposable. OMEGA fills this gap as open infrastructure any MCP client can use.

Engagement:
- All code Apache-2.0 on GitHub (github.com/omega-memory/omega-memory)
- Benchmark results published with reproducible methodology
- Technical writeups with each milestone
- Published on PyPI for easy adoption
- Board representative attends European events (FOSDEM, NLnet community days)
- Active in MCP developer forums and communities

Target users:
1. AI agent developers building on MCP
2. Open-source projects needing agent memory without cloud dependencies
3. Privacy-conscious organizations (EU public sector, healthcare, legal)
4. AI researchers studying agent memory and coordination

Sustainability:
Developed under a Dutch stichting with charter-mandated open licensing and no profit distribution. Local-first architecture means zero ongoing infrastructure costs: no servers, no cloud bills. Once built, the software runs indefinitely on user devices. Documentation and evaluation infrastructure funded here directly enable community contributions beyond the grant.
```

---

## Generative AI: Select "I have used generative AI in writing this proposal"

(Additional fields will appear after selecting this option. Enter:)

**Model:** Claude (Anthropic)

**Usage:** Used as a writing aid to structure and refine the applicant's own project knowledge. All technical claims, project details, and strategic decisions are the applicant's own. The applicant is the sole developer of OMEGA and wrote all project code.

---

## Privacy checkbox: Check it

## Send copy: Already checked by default

## Then click "Send request"
