# How a Solo Dev Built the #1-Ranked Memory System for AI Agents

**95.4% on LongMemEval. Local-first. Zero funding. Here's what I learned.**

---

## The Problem (You Already Know This One)

Your AI coding agent has amnesia. Every session starts from zero. Yesterday's architecture decisions, last week's debugging insights, the coding conventions you've established over months — gone when the session ends.

You've felt this. The 200 hours per year you spend re-explaining context. The 66% of developers who cite "almost right but not quite" as their top AI frustration. The declining trust — 43% to 33% year-over-year — even as adoption accelerates. Developers are using AI more and trusting it less.

The industry has noticed. Over $180 million has flowed into AI memory startups: Mem0 ($24M, 44K stars, AWS partnership), Mastra ($13M, YC-backed, PayPal and Adobe customers), Letta ($10M, $70M valuation), Emergence ($97M Series C), Supermemory ($3M, backed by Jeff Dean). OpenClaw hit 180K GitHub stars in 60 days without even trying to solve memory well — its markdown-based system is functional but limited, and three separate companies (Mem0, MemOS, Cognee) have built memory plugins for it.

The problem is real, funded, and unsolved.

I built OMEGA to solve it for myself. It scores 95.4% on LongMemEval — first on the leaderboard, ahead of Mastra's 94.87% ($13M funded) and every other system. It runs entirely on my laptop. No cloud, no API keys, no external databases. One SQLite file.

This is what I learned.

---

## The Retrieval Pipeline: From 76.8% to 95.4%

### What LongMemEval Tests

LongMemEval (Wang et al., ICLR 2025) is the standard benchmark for long-term memory in AI assistants. Five hundred manually created questions across five dimensions: single-session recall, preference application, multi-session reasoning, knowledge updates, and temporal reasoning. Sessions drawn from ~115K tokens of conversation history. Scored by GPT-4.1 as judge.

It's become a competitive battleground. In early 2026, Mastra, Supermemory, Emergence, and Hindsight have all published research claiming state-of-the-art. Scores are self-reported and model-dependent — the same system can score 84% with gpt-4o and 95% with gpt-5-mini. Worth keeping in mind when reading leaderboard claims, including mine. The score reported here (95.4%) is the unweighted mean of six category scores, which is the standard leaderboard methodology. Raw accuracy is 466/500 (93.2%).

### The Architecture

OMEGA uses a five-stage retrieval pipeline. This is architecturally different from Mastra's approach — they compress conversations into dense observation logs and keep them in the context window, eliminating retrieval entirely. OMEGA retrieves from an external store:

```
Query
  │
  ▼
┌─────────────────────────┐
│ Stage 1: Vector Search  │  bge-small-en-v1.5 (384-dim), sqlite-vec
│                         │  cosine distance, K nearest neighbors
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Stage 2: Full-Text      │  FTS5 with BM25 scoring
│                         │  catches terms distant in embedding space
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Stage 3: Blended Rank   │  70% vector + 30% text score
│                         │  dual-source candidates get blended score
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Stage 4: Type Weighting │  decisions/lessons weighted 2x
│                         │  priority field (1-5) further adjusts
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Stage 5: Re-Ranking     │  tag/project overlap boost
│                         │  word overlap (Jaccard, capped 50%)
│                         │  feedback dampening
│                         │  temporal hard penalty (0.05x for stale)
│                         │  abstention floor (0.35 vec / 0.5 text)
└─────────────────────────┘
```

Everything runs on SQLite with two extensions: `sqlite-vec` for vector similarity and FTS5 for full-text search. Embeddings from bge-small-en-v1.5 via ONNX on CPU. No external services.

The abstention floor matters more than you'd expect. When no memory meets the minimum relevance threshold, the system returns nothing rather than surfacing low-quality matches. Hallucination from irrelevant context destroys trust faster than no result at all.

### The Optimization Journey

The headline number didn't come from one clever idea. It came from seven iterations, most of which made things worse before they made them better:

| Version | Score | What Changed |
|---------|-------|-------------|
| Baseline | 76.8% (384/500) | Initial BM25 + vector blend |
| v2 | 82.0% (410/500) | Added MS-MARCO cross-encoder reranking |
| v3 | 89.2% (446/500) | **Removed** cross-encoder, better prompts |
| v6 | 90.8% (454/500) | Cherry-picked best prompts per category, K=25 |
| v7b | 95.4% (466/500) | Temporal prompt chain, query augmentation |

Each iteration taught something transferable:

**1. Cross-encoders trained on web search hurt conversational memory.**

I added an MS-MARCO cross-encoder expecting a big win. It dropped the score by 7 points. Web search relevance ("does this document answer this query?") and memory relevance ("does this past conversation contain this fact?") are different distributions. The cross-encoder confidently promoted irrelevant memories that happened to share vocabulary with the query.

**2. Session compression destroys retrieval quality.**

Compressing conversation sessions into summaries strips the exact details that questions ask about. "What restaurant did the user mention on Tuesday?" requires the raw session, not a summary that says "discussed dining preferences."

Interestingly, Mastra's compression-based Observational Memory scores 94.87% — but through continuous compression that maintains details, not retrieve-from-compressed. Different mechanism, different trade-offs. OMEGA's retrieval-based approach ultimately overtook it.

**3. K=25 is the sweet spot. K=35 makes counting worse.**

More context seems like it should help. For counting questions ("How many times did the user mention Python?"), K=35 retrieves more relevant memories but also more near-duplicates. The LLM naturally deduplicates similar notes, causing it to under-count. K=25 gives enough signal without the noise.

**4. Aggressive dedup instructions backfire.**

I tried telling the model to "VERIFY each item and REMOVE duplicates before counting." This caused 9 regressions in one run — the model got so focused on deduplication that it started removing valid distinct entries. Simple "list all relevant items" prompts with soft dedup consistently outperform aggressive filtering.

**5. Query expansion is free accuracy.**

Extracting temporal dates ("last Tuesday" → "2026-02-11") and entity names from queries before retrieval adds ~2 points with essentially zero downside. The retrieval pipeline finds better matches when the query contains the same tokens as the stored memories.

### Where I Am on the Leaderboard

| Rank | System | Score | Model | Notes |
|------|--------|-------|-------|-------|
| **1** | **OMEGA** | **95.4%** | **GPT-4.1** | **Retrieval-based, fully local, $0 funded** |
| 2 | Mastra OM | 94.87% | gpt-5-mini | Compression-based, $13M funded; 84.23% on gpt-4o |
| 3 | Mastra OM | 93.27% | gemini-3-pro | Same system, different model |
| 4 | Hindsight | 91.4% | gemini-3-pro | Local-first, memory-only |
| 5 | Emergence | 86.0% | Internal | $97M funded; score "not publicly reproducible" |
| 6 | Supermemory | 85.2% | gemini-3-pro | Cloud-hosted, $3M funded |

Category breakdown for OMEGA:

| Category | Score | Notes |
|----------|-------|-------|
| Single-Session Recall | 99% (126 questions) | Near-ceiling |
| Preference Application | 100% (30 questions) | Dedicated preference prompts |
| Knowledge Updates | 96% (78 questions) | Temporal state tracking |
| Temporal Reasoning | 94% (133 questions) | 4-step prompt chain |
| Multi-Session Reasoning | 83% (133 questions) | Counting errors; primary improvement target |

OMEGA leads by 0.53 points over the next system (Mastra at 94.87%). Worth noting: Mastra's top score uses gpt-5-mini ($13M in funding). On the standard gpt-4o model, they score 84.23%. OMEGA achieves #1 with GPT-4.1 on a laptop. Benchmark scores are inseparable from the generation model, and the competitive marketing around LongMemEval often obscures this.

### The Academic Connection: Orthogonal Decomposition

MAGMA (Jiang et al., January 2026) independently validated the idea that orthogonal decomposition improves memory retrieval. They decompose memory into four orthogonal semantic subspaces — semantic, temporal, causal, and entity graphs — showing that disentangled representations outperform monolithic approaches.

OMEGA applies the same principle at the system architecture level rather than the retrieval level. The name stands for **O**rthogonal **M**ulti-Agent **E**ngine for **G**eneralized **A**gents. Five independent modules that compose without coupling:

| Module | Tools | What It Does |
|--------|-------|-------------|
| Core Memory | 26 | Store, query, traverse, checkpoint, resume, compact |
| Coordination | 28 | File claims, branch guards, task DAG, peer messaging, deadlock detection |
| Router | 10 | Multi-LLM routing, intent classification |
| Entity | 8 | Entity registry, relationship graphs |
| Knowledge | ~5 | Document ingestion (PDF, web, markdown) |

Each module is independently adoptable. Start with memory. Add coordination when you have multiple agents. Enable routing when you need it. No forced bundle.

---

## What OMEGA Does That Memory-Only Systems Don't

### Multi-Agent Coordination

This is the part nobody else builds. Mem0 doesn't do it. Mastra doesn't do it. Supermemory doesn't do it. Hindsight doesn't do it.

When you run multiple Claude Code sessions on the same repo — which 29% of developers now do — they will step on each other. Edit the same file simultaneously. Push to the same branch. Make contradictory architecture decisions. Fewer than 10% of multi-agent deployments reach production, and coordination is the primary failure mode.

OMEGA provides 28 coordination tools:

| Primitive | What It Prevents |
|-----------|-----------------|
| File Claims | Two agents editing the same file |
| Branch Guards | Two agents pushing to the same branch |
| Task DAG | Duplicated work; dependency violations |
| Peer Messaging | Agents working without awareness of each other |
| Intent Broadcasting | Overlapping work plans |
| Deadlock Detection | Circular waits across claims |

All backed by the same SQLite database. No message broker, no distributed consensus, no external service. Agents coordinate through database reads and writes with heartbeat-based liveness detection.

Letta's "Context Repositories" (February 2026) is the first competitive move toward coordination — git-based memory with version control. But that's coordination through version control, not real-time coordination. OMEGA provides live coordination: agents claim, communicate, and resolve conflicts during concurrent execution.

### Zero-Configuration Memory Capture

Most memory systems require manual saves or cloud accounts. OMEGA hooks into Claude Code's lifecycle events and captures memories automatically:

```
Claude Code event → fast_hook.py → (~5ms UDS) → hook_server.py → memory + coordination
```

Seven hooks, 12 handlers. Session start/end, user prompts, edits, reads, git pushes. Fail-open — if the daemon is down, work continues unblocked. The developer never manually saves anything.

### Intelligent Forgetting

Memory systems that never forget become noise generators. OMEGA implements structured forgetting:

- **TTL**: Session summaries expire after 1 day. Checkpoints after 7 days. Lessons and decisions are permanent.
- **Three-layer dedup**: Exact hash, semantic similarity (>= 0.85), and per-type Jaccard similarity.
- **Memory evolution**: Similar content (55–95% match) gets appended to existing memories rather than creating duplicates.
- **Compaction**: Clusters related memories, creates summaries, marks originals as superseded.
- **Audit trail**: Every deletion is logged with its reason. Deterministic, auditable, reversible.

### Local-First, Actually

Everything runs on your machine. SQLite for storage. ONNX on CPU for embeddings. FTS5 for text search. macOS Keychain for encrypted profiles. ~31MB startup, ~337MB after first query. No cloud account needed. Optional Supabase sync if you choose.

This matters because 77% of enterprise leaders cite data privacy as their #1 concern with AI adoption. Your architecture decisions, debugging history, and credential patterns never leave your machine.

---

## Try It

```bash
pip install omega-memory
```

Open source. Apache 2.0. One command. Works with any MCP client.

The retrieval pipeline, coordination system, hook architecture, and all 73 tools are in the repo. The benchmark is reproducible — `benchmarks/longmemeval/scripts/longmemeval_official.py` runs the full 500-question evaluation.

If you're tired of re-explaining your project to your AI every morning, this is what I built to fix it.

---

## References

1. Wang, Y., et al. "LongMemEval: Benchmarking Long-Term Memory in AI Assistants." *ICLR 2025*. arxiv.org/abs/2410.10813

2. Jiang, D., et al. "MAGMA: A Multi-Graph based Agentic Memory Architecture for AI Agents." arXiv:2601.03236, January 2026.

3. Mastra. "Observational Memory: A New Architecture for Long-Term Agent Memory." mastra.ai/research, February 2026.

4. Letta. "Context Repositories: Git-Based Memory for Coding Agents." letta.com/blog, February 2026.

5. Anthropic. "Donating the Model Context Protocol and Establishing the Agentic AI Foundation." anthropic.com, December 2025.

6. Stack Overflow. "2025 Developer Survey." stackoverflow.com, 2025.

7. Zep. "A Temporal Knowledge Graph Architecture for Agent Memory." arxiv.org/abs/2501.13956, January 2025.
