# NLnet NGI Zero Commons Fund -- Draft Proposal

> Review this, then I'll submit via their web portal.
> URL: https://nlnet.nl/propose/
> Deadline: April 1, 2026
> Contact: jason@omegamax.co

---

## Contact Information

- **Name:** Jason Sosa
- **Email:** jason@omegamax.co
- **Phone:** [NEED FROM YOU]
- **Organisation:** Kokyo Keisho Zaidan Stichting
- **Country:** Netherlands

---

## General Project Information

**Proposal name:** OMEGA: Open-Source Persistent Memory Infrastructure for AI Agents

**Website / wiki:** https://github.com/omega-memory/omega-memory

**Abstract:**

AI agents (coding assistants, development tools, autonomous workflows) lose all learned context when a session ends. Every new session starts from zero, forcing users to re-explain preferences, decisions, and project history. This wastes developer time and degrades trust in AI tools.

OMEGA solves this with a local-first persistent memory system, implemented as an MCP (Model Context Protocol) server. It stores, retrieves, and reasons over memories using semantic search, temporal indexing, and cross-session learning. All data stays on the user's machine in SQLite with ONNX embeddings on CPU. No cloud dependency. No data leaves the device.

OMEGA scores 95.4% on LongMemEval (ICLR 2025, 500-question standard benchmark), ranking #1 on the public leaderboard. It is published on PyPI as `omega-memory`, licensed Apache 2.0, and governed by a Dutch foundation (Kokyo Keisho Zaidan Stichting).

This proposal requests funding to:

1. Improve memory accuracy in weak areas: multi-session reasoning (65.4% to 80%+), preference extraction (50% to 75%+), and temporal reasoning (70.7% to 85%+).

2. Harden the system for broader adoption: encrypted exports, integrity checks, automatic backup, and capacity management (all recently implemented but need testing at scale).

3. Build ecosystem integrations: first-class plugins for AI agent frameworks (Goose, Claude Code, Cursor) so any MCP-compatible tool can gain persistent memory with a single install.

4. Publish open benchmarks: expand MemoryStress (a longitudinal memory benchmark, already on HuggingFace) and contribute improvements back to LongMemEval.

Expected outcome: a production-grade, privacy-respecting memory layer that any AI agent can use, available as free infrastructure for the open-source ecosystem.

**Prior involvement:**

OMEGA was developed as a successor to Gnosis, an earlier MCP-based memory system built in Swift. The current Python implementation has been in continuous development since mid-2025, with all code published under Apache 2.0 at github.com/omega-memory/omega-memory.

Related open-source contributions:
- omega-memory on PyPI (v0.8.0): pip-installable MCP server
- MemoryStress benchmark: published on GitHub (omega-memory/memorystress) and HuggingFace (singularityjason/memorystress), the first longitudinal memory benchmark for AI agents (583 facts, 1000 sessions, 300 questions)
- LongMemEval leaderboard contributions: publicly submitted and verified results

The applicant has experience building developer tools and infrastructure systems. The governing foundation (Kokyo Keisho Zaidan Stichting) is registered in the Netherlands.

---

## Requested Support

**Requested Amount:** 50,000 EUR

**Budget usage explanation:**

The budget covers 12 months of focused development across four workstreams. Work is performed by Kokyo Keisho Zaidan Stichting at 250 EUR/hr:

1. Memory accuracy improvements (40% / 20,000 EUR)
   - Cross-session linking and graph traversal enhancements: 40 hours
   - Preference extraction pipeline: 24 hours
   - Temporal reasoning improvements: 16 hours
   Deliverables: LongMemEval score improvement from 95.4% to target 97%+, published benchmark results

2. Security and robustness hardening (20% / 10,000 EUR)
   - Encrypted export/import with Fernet: 8 hours
   - Session ownership and access control: 12 hours
   - Startup integrity checks and automatic backup: 8 hours
   - Scale testing (50K+ memories, concurrent access): 12 hours
   Deliverables: Security audit report, stress test results, hardened release

3. Ecosystem integration (25% / 12,500 EUR)
   - MCP client plugins (Goose, Claude Code, Cursor, VS Code): 32 hours
   - Documentation, quickstart guides, and tutorials: 10 hours
   - CI/CD and release automation: 8 hours
   Deliverables: Published plugins, documentation site

4. Benchmark and research (15% / 7,500 EUR)
   - MemoryStress v2 (expanded question set, new categories): 16 hours
   - Universal-prompt LongMemEval baseline (fair scoring without category-specific tuning): 6 hours
   - Research write-up and open data publication: 8 hours
   Deliverables: MemoryStress v2 on HuggingFace, research report

Total: 200 hours at 250 EUR/hr = 50,000 EUR

**Other funding sources:**

No current or past funding. OMEGA has been developed entirely without external financial support. A grant application was submitted to the Block Goose Grant Program (February 2026) but no response has been received. If both grants are awarded, the work would be scoped to avoid overlap: the Goose Grant would focus specifically on Goose framework integration, while the NLnet grant would focus on core memory accuracy, security, and ecosystem breadth.

**Comparison to existing efforts:**

Existing AI memory systems fall into three categories:

Cloud-dependent memory services (Mem0, Supermemory): These store memories on remote servers. For developers working with proprietary code, this is a non-starter. Mem0 raised $24M but provides no local-first option. Supermemory focuses on personal knowledge management, not agent memory.

Graph-based systems (Zep/Graphiti): Requires Neo4j infrastructure, scores 71.2% on LongMemEval. No multi-agent support. Significant operational overhead.

Framework-locked solutions (Letta/MemGPT): Virtual memory paging approach, tied to a specific agent framework. No MCP integration. Cloud pricing model.

OMEGA is unique in combining:
- Local-first architecture (SQLite + ONNX, zero cloud dependencies)
- Standard protocol integration (MCP, works with any compatible client)
- Benchmark-verified accuracy (95.4% LongMemEval, #1 on leaderboard)
- Open-source with foundation governance (Apache 2.0, Dutch stichting)

No existing system provides all four. The closest competitor on accuracy (Hindsight, 91.4%) lacks multi-agent coordination and foundation governance. The closest on breadth (Letta) lacks benchmark verification and local-first operation.

**Technical challenges:**

1. Retrieval quality at scale: As the memory store grows beyond 10K memories, maintaining sub-second query latency while preserving semantic relevance requires careful index management, cache strategies, and query planning. The current BM25+vector hybrid pipeline (70/30 weighting) works well up to ~5K memories but needs optimization for larger stores.

2. Temporal reasoning: Determining which version of a fact is current when memories conflict across time periods. The current approach uses timestamp-based penalties, but more sophisticated approaches (contradiction detection, explicit supersession chains) are needed for the 85%+ accuracy target.

3. Cross-session context linking: Connecting related memories across sessions without explicit user tagging. Current semantic similarity works for obvious connections, but subtle relationships (e.g., a decision in session A that affects a constraint in session B) require graph-based traversal and inference.

4. Embedding model quality: OMEGA uses ONNX models on CPU to maintain the local-first constraint. When no model is available, it falls back to MD5 hash vectors, which produce valid-looking but semantically useless results. Improving the default model quality while maintaining CPU-only operation is an ongoing challenge.

5. Privacy-preserving export: Export files must be encrypted to prevent accidental exposure of sensitive development context. The recently implemented Fernet encryption needs testing across platforms and edge cases (large stores, partial exports, key rotation).

**Ecosystem and engagement:**

OMEGA operates within the MCP (Model Context Protocol) ecosystem, which has become the standard integration layer for AI tools:
- 10,000+ MCP servers in the ecosystem
- 97M monthly SDK downloads
- Adopted by Anthropic, OpenAI, Google, Microsoft, and others
- Linux Foundation governance

OMEGA is published on:
- PyPI as omega-memory (pip installable)
- GitHub at omega-memory/omega-memory
- Smithery MCP directory
- mcp.so directory (submitted)

Stakeholder engagement:
- MCP client developers (Goose, Claude Code, Cursor) benefit from a standard memory layer
- Individual developers benefit from persistent context across sessions
- Teams benefit from multi-agent coordination tools
- The research community benefits from open benchmarks (MemoryStress)

The project will engage stakeholders through:
- GitHub issues and discussions for feature requests and bug reports
- Published benchmarks with reproducible results
- Documentation and quickstart guides for each supported client
- Open roadmap with milestone tracking

---

## Generative AI Disclosure

**Did you use generative AI?** Yes, for drafting assistance

**Which model / what for:** Claude (Anthropic) was used to help draft and structure the proposal text. All technical claims, statistics, and architectural descriptions were verified against the actual codebase and benchmark results. The applicant reviewed and edited all generated text.

---

## Notes for Jason

Resolved:
1. Phone: +1 347-857-9454
2. Rate: 250 EUR/hr through Kokyo Keisho Zaidan Stichting (200 hours total)
3. Other funding: Goose Grant submitted (no response yet)

Still open:
- Any attachments you want to include (architecture diagrams, benchmark reports)?
