# OMEGA Directory Listing Copy

> Use this copy when submitting OMEGA to software directories.
> Adapt length/format per platform requirements.

## Core Info

- **Name**: OMEGA
- **Tagline**: Persistent memory for AI coding agents
- **Website**: https://omegamax.co
- **GitHub**: https://github.com/omega-memory/omega-memory
- **PyPI**: https://pypi.org/project/omega-memory/
- **License**: Apache-2.0 (Core), Commercial (Pro/Team)
- **Pricing**: Free (Core), $19/mo (Pro), $39/user/mo (Team)
- **Category**: Developer Tools / AI / MCP Tools
- **Platform**: Python 3.11+, macOS, Linux, Windows

## Short Description (1-2 sentences)

Persistent memory for AI coding agents. Decisions, lessons, and context carry forward across every session with 15 MCP tools, semantic search, and zero cloud dependency.

## Medium Description (paragraph)

OMEGA gives AI coding agents persistent memory that survives across sessions. Instead of starting from zero every conversation, your agent remembers decisions, lessons learned, error patterns, and user preferences. Built on SQLite with ONNX embeddings, it runs entirely local with no cloud dependency. 15 MCP tools cover semantic search, auto-capture, contradiction detection, provenance tracking, and intelligent forgetting. #1 on LongMemEval benchmark (95.4%). Works with Claude Code, Cursor, Windsurf, and any MCP-compatible client.

## Long Description (full listing)

OMEGA is a persistent memory system for AI coding agents, built as an MCP (Model Context Protocol) server. It solves the fundamental problem that AI agents forget everything between sessions.

**What it does:**
Your agent remembers decisions made, lessons learned, error patterns encountered, and user preferences across every session. When a new session starts, OMEGA surfaces relevant context automatically so your agent picks up where it left off.

**Key features:**
- 15 MCP tools for memory management, search, and maintenance
- Semantic search with ONNX embeddings (384-dim, local inference)
- Auto-capture via Claude Code hooks (no manual saves needed)
- Contradiction detection and temporal supersession
- Provenance tracking with source URIs and lineage chains
- Active connection discovery between related memories
- Bi-temporal queries (what did we know at time X?)
- Multi-agent coordination (file claims, task management)
- Intelligent forgetting with strength decay curves
- Zero cloud dependency, runs entirely on your machine

**Architecture:**
SQLite + FTS5 full-text search + sqlite-vec vector search. ~5-10 MB RAM footprint vs. 372 MB for in-memory graph alternatives. Sub-200ms query latency.

**Benchmark:**
#1 on LongMemEval with 95.4% score, the standard benchmark for evaluating AI agent memory systems.

**Install:**
```
pip install omega-memory
```

**Works with:** Claude Code, Cursor, Windsurf, OpenCode, and any MCP-compatible AI client.

## Tags/Keywords

MCP server, AI agent memory, persistent memory, Claude Code, semantic search, knowledge graph, local-first, developer tools, coding assistant, Mem0 alternative, Zep alternative, MCP tools, auto-capture, cross-session learning

## Submission Checklist

### High Priority (developer/AI focused)
- [ ] OpenAlternative (open-source alternatives) — https://openalternative.co/submit
- [ ] SaaSHub — https://www.saashub.com/submit
- [ ] DevHunt — https://devhunt.org
- [ ] "There's an AI for that" — https://theresanaiforthat.com/submit
- [ ] AlternativeTo — https://alternativeto.net/how-to-add/
- [ ] G2 — https://www.g2.com/products/new
- [ ] Capterra — https://www.capterra.com/vendors/sign-up
- [ ] LibHunt — https://www.libhunt.com
- [ ] SourceForge — https://sourceforge.net/create/
- [ ] Toolfolio
- [ ] SaaS Genius

### Already Listed (don't re-submit)
- Official MCP Registry (registry.modelcontextprotocol.io)
- awesome-mcp-servers (80K+ stars)
- mcp.so
- mcpservers.org
- awesome-nostr
- awesome-L402
- PyPI (omega-memory)

### "Alternative to" positioning
When platforms ask "alternative to what?":
- Mem0 (cloud-based agent memory)
- Zep (conversation memory)
- OpenAI memory (built-in, limited)
- Letta (formerly MemGPT)
- Mastra (agent framework with memory)

## Competitive Comparison (for platforms that support it)

| Feature | OMEGA | Mem0 | Zep | Mastra | OpenAI |
|---------|:-----:|:----:|:---:|:------:|:------:|
| Local-first | Yes | No | No | Yes | No |
| Free tier | Full | Limited (10K) | Limited | Yes | No |
| Cloud required | No | Yes | Partial | No | Yes |
| Semantic search | Yes | Yes | Yes | Yes | No |
| Auto-capture | Yes | Cloud only | No | Yes | No |
| Checkpoint/resume | Yes | No | No | No | No |
| Graph relationships | Yes | No | Yes | Yes | No |
| Multi-agent coordination | Pro | No | No | Limited | No |
| LongMemEval score | 95.4% (#1) | Not published | 71.2% | 94.87% | Not published |

## Social Proof

- #1 on LongMemEval (ICLR 2025), 95.4% accuracy on 500-question benchmark
- 77 test files, ~41K lines of tests
- Apache-2.0 open-source core, governed by Kokyo Keisho Zaidan Stichting
- Active development since 2025
