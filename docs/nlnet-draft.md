# NLnet NGI Zero Commons Fund — Application Draft

> Review this, then fill and submit the form at https://nlnet.nl/propose/
> Deadline: April 1, 2026, 12:00 CEST
> Edit anything you want changed.

---

## Contact Information

**Your name:** Jason Sosa

**Email address:** jason@omegamax.co

**Phone number:** [FILL]

**Organisation:** Kokyō Keishō Zaidan Stichting (KvK 96951559)

**Country:** Singapore

> Note: The stichting is registered in the Netherlands (Oldenzaal), but you as the developer are based in Singapore. Being upfront here. NLnet funds globally; the NGI Zero reviewers will decide if this fits.

---

## General Project Information

**Thematic fund:** NGI Zero Commons Fund

**Project name:** OMEGA: Open Memory Infrastructure for AI Agents

**Website / Homepage:** https://github.com/omega-memory/omega-memory

---

## Q1. Abstract

> "Can you explain the whole project and its expected outcome(s)?"

OMEGA is open-source infrastructure that gives AI agents persistent memory. It implements the Model Context Protocol (MCP), an open standard now governed by the Linux Foundation, providing tools for semantic memory, temporal reasoning, cross-session learning, and multi-agent coordination. Everything runs locally with zero cloud dependencies.

Today's AI agents are stateless: every session starts from zero. Users repeat themselves, agents forget past decisions, and debugging insights vanish between sessions. The proprietary alternatives (Mem0, commercial vector databases) route sensitive data through cloud services and create vendor lock-in.

OMEGA solves this with a local-first approach. All data stays on the user's device in SQLite with vector search (sqlite-vec) and full-text search (FTS5). Embeddings run on-CPU via ONNX Runtime. No API keys, no cloud accounts, no data exfiltration.

OMEGA currently scores 95.4% on LongMemEval, the ICLR 2025 standard benchmark for agent memory, ranking #1 on the public leaderboard. But there is room to improve: multi-session reasoning sits at 65%, and preference extraction at 50%. This grant funds the work to close those gaps, along with proper documentation, packaging, and evaluation infrastructure to make OMEGA accessible to the broader open-source community.

Expected outcomes: measurable accuracy improvements on public benchmarks, comprehensive documentation site, one-command installation across platforms, and a reproducible evaluation pipeline that any contributor can run.

Licensed Apache-2.0, developed by Kokyō Keishō Zaidan Stichting, a Dutch foundation for open AI infrastructure.

---

## Q2. Have you been involved with projects or organisations relevant to this project before?

I have been building AI systems for over 10 years. OMEGA is my current focus: a 19,000-line Python codebase with 2,150+ passing tests, published on PyPI as omega-memory (v0.9.3), and used as an MCP server by developers running Claude Code, Goose, and other agent clients.

I also created and published MemoryStress, the first longitudinal memory benchmark for AI agents (583 facts, 1,000 sessions, 300 questions, simulating 10 months of use). It is available as open data on HuggingFace and GitHub.

Kokyō Keishō Zaidan Stichting was established as a Dutch foundation specifically to steward open infrastructure for AI agent systems. The foundation's charter mandates open-source development under Apache-2.0 and prohibits profit distribution, ensuring OMEGA remains a public good.

---

## Q3. Requested amount (EUR)

50000

---

## Q4. Explain what the requested budget will be used for.

The budget covers 6 deliverable-based milestones. All funds go to development labor (single developer, no overhead). Milestones are output-based: each is complete when the deliverable ships, not tied to calendar months.

**M1: Memory Accuracy Sprint (€14,000)**
- Improve multi-session reasoning from 65% to 80%+ through enhanced cross-session linking and graph traversal
- Improve preference extraction from 50% to 75%+ via dedicated preference memory pipeline
- Improve temporal reasoning from 71% to 85%+ with temporal indexing improvements
- All improvements measured against LongMemEval (public, reproducible benchmark)

**M2: Documentation and Onboarding (€10,000)**
- Full documentation site with API reference for all public tools
- Quickstart guides for each supported agent client (Claude Code, Goose, Cursor)
- Architecture documentation and contributor guide
- Interactive tutorials for common workflows

**M3: Evaluation Infrastructure (€10,000)**
- Reproducible CI pipeline running LongMemEval and MemoryStress benchmarks on every release
- Public dashboard showing accuracy trends over time
- Contributor-friendly benchmark harness so anyone can test memory quality
- Published methodology and results for community verification

**M4: Packaging and Distribution (€6,000)**
- One-command installation across platforms (PyPI, Docker, Homebrew)
- Automated release pipeline with changelog generation
- Platform-specific packages (Debian/Ubuntu, macOS, Windows)
- Dependency minimization for easier adoption

**M5: MCP Standard Compliance (€6,000)**
- Track MCP specification as it evolves under the Linux Foundation
- Ensure OMEGA stays compatible with all major MCP clients
- Contribute upstream to the MCP specification where agent memory patterns are relevant
- Maintain interoperability test suite across client versions

**M6: Community and Dissemination (€4,000)**
- Published writeups documenting technical decisions and benchmark results
- Comparison with alternative approaches published alongside benchmark data
- Foundation board representative attends relevant events in the Netherlands (FOSDEM, NLnet community days) on behalf of the project
- Engagement with MCP ecosystem forums, AAIF community, and developer channels

Total: €50,000

---

## Q5. Does the project have other funding sources, both past and present?

No. OMEGA has been built entirely self-funded. This would be the project's first external funding. The stichting is applying to other open-source grant programs in parallel (Block Goose Grant, Sovereign Tech Fund, RAAIS Foundation, GitHub Secure OSS Fund), but no funding has been received from any source to date.

---

## Q6. Compare your own project with existing or historical efforts.

**Mem0** (proprietary, VC-funded $4.2M): Cloud-hosted agent memory API. Closed-source, data leaves the user's device, vendor lock-in. Targets enterprise SaaS revenue.

**LangChain Memory**: Tightly coupled to the LangChain framework. No standalone use, no multi-agent coordination, no MCP support. Deprecated in favor of LangGraph checkpointing.

**Commercial vector databases** (Pinecone, Weaviate, Qdrant): General-purpose, not agent-specific. Require cloud infrastructure and ongoing subscription costs. No built-in support for agent workflows (sessions, temporal reasoning, preference tracking).

**ChromaDB**: Open-source vector database. Good for retrieval, but no agent memory semantics, no coordination, no entity management. A building block, not a complete solution.

**OMEGA's differentiation:**
1. MCP-native: implements the open MCP standard, works with any MCP-compatible client
2. Local-first: all data on-device, encrypted at rest, no cloud dependency
3. Agent-specific: designed for agent workflows (sessions, lessons learned, temporal reasoning, preference tracking), not a generic vector database
4. Benchmarked: 95.4% on LongMemEval (#1 public leaderboard), with published reproducible methodology
5. Foundation-governed: Apache-2.0 under a Dutch stichting with charter-mandated open licensing

---

## Q7. What are significant technical challenges you expect to solve during the project?

**1. Multi-session reasoning accuracy.** When an agent needs to synthesize information stored across multiple past sessions, accuracy drops to 65%. The challenge is efficiently linking related memories across temporal boundaries without retrieving the entire history. Approach: build a cross-session reference graph that connects related memories at storage time, reducing retrieval to graph traversal rather than exhaustive search.

**2. Preference extraction and consistency.** Agents need to learn user preferences from natural conversation ("I prefer tabs over spaces") and apply them consistently. Current accuracy: 50%. Challenge: distinguishing stable preferences from one-time instructions, and handling preference conflicts over time. Approach: dedicated preference memory with confidence scoring and temporal decay for stale preferences.

**3. Embedding model portability.** Different users run different local embedding models with varying dimensions and quality. Challenge: ensuring vector search quality across heterogeneous embedding sources without requiring re-indexing. Approach: model-tagged embeddings with automatic re-embedding pipeline when models change.

**4. Scaling without cloud infrastructure.** SQLite is single-writer. Challenge: supporting heavy multi-agent workloads on a single local database. Approach: WAL mode, connection pooling, write batching, and carefully designed access patterns that minimize contention while preserving data integrity.

---

## Q8. Describe the ecosystem of the project, and how you will engage with relevant actors and promote the outcomes.

**Ecosystem:**
OMEGA operates in the Model Context Protocol (MCP) ecosystem, an open standard for AI agent communication now governed by the Agentic AI Foundation under the Linux Foundation. Members include Anthropic, Block, Google, Microsoft, OpenAI, and AWS. MCP is supported by major agent platforms: Claude Code, Goose, Cursor, Windsurf, and others.

The AI agent market is growing rapidly, but persistent memory infrastructure is missing. Every agent framework currently treats sessions as disposable. OMEGA fills this gap as open infrastructure that any MCP-compatible agent can use.

**Engagement plan:**
- All code published under Apache-2.0 on GitHub (github.com/omega-memory/omega-memory)
- Benchmark results published openly with reproducible methodology
- Technical writeups published with each milestone
- Published on PyPI for easy adoption by any Python developer
- Foundation board representative attends relevant European events (FOSDEM, NLnet community days) to present progress and gather feedback
- Active participation in MCP developer forums, AAIF community, and open-source AI channels

**Target users:**
1. AI agent developers building on the MCP standard
2. Open-source projects that need agent memory without cloud dependencies
3. Privacy-conscious organizations (EU public sector, healthcare, legal) where data must stay on-device
4. AI researchers studying agent memory quality and multi-agent coordination

**Sustainability beyond the grant:**
OMEGA is developed under a Dutch stichting whose charter mandates open-source licensing and prohibits profit distribution. The local-first architecture means there are no ongoing infrastructure costs to sustain: no servers, no cloud bills, no operational burden. Once built, the software runs indefinitely on user devices. The documentation and evaluation infrastructure funded by this grant directly enable community contributions beyond the grant period.

---

## Generative AI Disclosure

This application was drafted with assistance from Claude (Anthropic), used as a writing aid to structure and refine the applicant's own knowledge about the project. All technical claims, project details, and strategic decisions are the applicant's own. The applicant is the sole developer of OMEGA and wrote all project code.

---

## Pre-Submission Notes

**Transparency items for Jason to consider:**
1. Country is listed as Singapore (your location). The stichting is Dutch. NLnet may ask about this. Be prepared to explain the structure: Dutch foundation, Singapore-based developer, globally available open-source output.
2. The "other funding sources" answer mentions parallel applications. This is honest and NLnet expects it. If any of those come through before NLnet decides, you'd need to update them.
3. Budget is 100% labor, single developer. This is frugal and NLnet likes it, but reviewers may question whether one person can deliver all 6 milestones in 12 months. The answer is yes, because the core system already works; this is improvement and packaging, not greenfield development.
4. The 95.4% LongMemEval claim and #1 leaderboard ranking should be verifiable. Make sure the leaderboard entry is current before submitting.
