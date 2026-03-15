# OMEGA vs Mem0 vs Claude MEMORY.md -- Which AI Memory Solution Should You Use?

AI coding agents have a fundamental flaw: they forget everything between sessions. The decision you explained yesterday, the debugging insight from last week, the project conventions you've repeated a dozen times -- all gone the moment you close the terminal.

Three solutions exist today, and they take radically different approaches. This is an honest comparison of OMEGA, Mem0, and Claude's built-in MEMORY.md to help you pick the right one for how you work.

## Quick Comparison

| Feature | OMEGA | Mem0 | MEMORY.md |
|---------|-------|------|-----------|
| **Architecture** | Local MCP server (SQLite + ONNX) | Cloud API or self-hosted (vector DB + LLM) | Flat markdown file |
| **Setup** | `pip install omega-memory && omega setup` | Cloud: API key signup. Self-hosted: vector DB + LLM config | Zero (built into Claude Code) |
| **Data location** | 100% local (~/.omega/) | Cloud by default; self-hosted possible | Local (~/.claude/projects/) |
| **Search** | Semantic (vector) + FTS5 + re-ranking | Semantic (vector) + graph traversal | None (full file loaded into context) |
| **Auto-capture** | Yes (hooks detect decisions, lessons, errors) | Yes (LLM-based extraction) | Partial (Claude writes to file, but you must prompt it) |
| **Memory types** | 8 typed (decision, lesson, preference, error, checkpoint, etc.) | 3 scopes (user, session, agent) + graph entities | Unstructured markdown |
| **Contradiction detection** | Yes (new decisions supersede old ones) | Yes (memory consolidation) | No |
| **Scalability** | Thousands of memories (SQLite + vector index) | Production-scale (dedicated vector DB) | ~200 lines before context truncation |
| **External dependencies** | None (CPU-only embeddings) | Requires LLM API (OpenAI, etc.) or local LLM | None |
| **Checkpoint/resume** | Built-in (`omega_checkpoint` / `omega_resume_task`) | Not built-in | Not built-in |
| **Agent support** | Claude Code, Cursor, Windsurf (MCP) | Multi-platform (Python SDK, REST API) | Claude Code only |
| **License** | Apache 2.0 | Apache 2.0 | Proprietary (part of Claude Code) |
| **Cost** | Free | Free tier + paid plans | Free (included with Claude Code) |
| **GitHub stars** | ~5 (new project) | ~47K | N/A |
| **Benchmark** | 95.4% LongMemEval (#1) | 66.9% LOCOMO | Not benchmarked |

## Architecture

### OMEGA: Local-first MCP server

OMEGA runs as a local process on your machine. Storage is a single SQLite database at `~/.omega/omega.db`. Semantic search uses a 90MB ONNX embedding model (bge-small-en-v1.5) that runs on your CPU -- no GPU required, no API calls, no network requests.

It communicates with your coding agent via [MCP](https://modelcontextprotocol.io) (Model Context Protocol), which means it works with any MCP-compatible client: Claude Code, Cursor, Windsurf, or anything else that speaks the protocol. The server exposes 27 MCP tools for storing, querying, traversing, and managing memories.

Hooks (small scripts that run on Claude Code events) handle auto-capture and auto-surfacing. When you edit a file, start a session, or finish a task, relevant memories appear automatically.

**Total footprint:** ~337 MB RAM after model load. One SQLite file. Zero external services.

### Mem0: Cloud-native memory layer

Mem0's architecture is fundamentally different. It's designed as an API-first memory service. The managed cloud version (app.mem0.ai) handles everything -- you get an API key, make calls, and memories are stored on Mem0's infrastructure.

The self-hosted option gives you more control, but requires assembling multiple components: a vector database (Qdrant, Chroma, Pinecone, pgvector, or one of 20+ supported options), an LLM provider for memory extraction (OpenAI, Anthropic, or a local model via Ollama), and optionally a graph database for relationship modeling.

This is both Mem0's strength and its complexity. The pluggable architecture means you can scale each component independently. Need faster search? Swap in a dedicated Qdrant cluster. Want richer relationships? Enable the graph layer. But you're managing distributed infrastructure rather than a single file.

Mem0's graph memory (Mem0g) is worth calling out specifically. It extracts entities and relationships from conversations, stores them as nodes and edges, and uses graph traversal alongside vector search during retrieval. This is genuinely powerful for applications that need to model complex relationships between concepts, people, or systems.

### MEMORY.md: A file you edit

Claude Code's built-in memory is the simplest approach possible: a markdown file at `~/.claude/projects/<project>/memory/MEMORY.md`. Claude reads the first 200 lines at the start of every turn. Claude can write to it during sessions. You can edit it manually with any text editor.

There's no database, no embeddings, no search index. The entire file is injected into the context window as raw text. This is both its greatest strength (zero moving parts) and its hard limitation (everything must fit in ~200 lines).

## Setup Complexity

**MEMORY.md: Zero effort.** It exists the moment you use Claude Code. Nothing to install, configure, or maintain. If you're already using Claude Code, you already have it.

**OMEGA: Two commands.** `pip install omega-memory && omega setup` downloads the embedding model, registers the MCP server, installs hooks, and updates your CLAUDE.md. Run `omega doctor` to verify. The entire process takes under a minute, and there's nothing else to configure. No API keys, no accounts, no external services.

**Mem0: Varies significantly.** The cloud API is straightforward -- sign up, get a key, `pip install mem0ai`, done. Self-hosted is a different story. You need to choose and run a vector database, configure an LLM provider (which typically means an OpenAI API key or a local Ollama setup), and wire everything together. The flexibility is real, but so is the setup time. Expect 30-60 minutes for a self-hosted deployment that includes graph memory.

## Memory Types and Structure

**OMEGA** uses typed memories. When something is stored, it's categorized: `decision`, `lesson_learned`, `user_preference`, `error_pattern`, `session_summary`, `task_completion`, `constraint`, or generic `memory`. Types affect retrieval scoring -- decisions and lessons are weighted higher than generic memories because they're typically more actionable. Memories also carry metadata: timestamps, project paths, session IDs, entity scopes, and tags.

**Mem0** organizes by scope rather than type: user memory (persists across all conversations with a person), session memory (single conversation), and agent memory (specific to an AI agent instance). The graph layer adds entity-relationship structure on top. This scope-based model is better suited for consumer-facing applications where you're personalizing across multiple users, each with distinct conversation histories.

**MEMORY.md** is unstructured. It's markdown. You can impose whatever structure you want with headings and bullet points, but the system has no awareness of what's a decision versus a preference versus a stale note. Everything has equal weight.

## Search Capabilities

This is where the differences matter most at scale.

**OMEGA** runs a multi-stage retrieval pipeline:
1. Vector similarity search against the embedded query (bge-small-en-v1.5, 384 dimensions)
2. FTS5 keyword matching for exact terms the vector model might miss
3. Type-weighted scoring (decisions and lessons rank higher)
4. Contextual re-ranking based on project, tags, recency, and access patterns
5. Deduplication and time-decay

On the LongMemEval benchmark (500 multi-session memory tasks testing temporal reasoning, relationship tracking, and factual recall), OMEGA scores 95.4% -- currently #1 on the leaderboard.

**Mem0** uses vector similarity search with an optional graph traversal layer. The graph component is where Mem0 differentiates: when you query, it doesn't just find similar memories -- it traverses relationships to surface connected context. On Mem0's own LOCOMO benchmark, it scores 66.9% accuracy with 1.4s latency, claiming 26% improvement over OpenAI's memory and 91% lower p95 latency than full-context approaches.

**MEMORY.md** has no search. The entire file is loaded into Claude's context window every turn. Claude's language model does the "retrieval" -- it reads the whole file and picks out what's relevant. This works well at 50 lines. At 200 lines, it's borderline. Beyond 200, the file is silently truncated and you lose memories without knowing it.

## Auto-Capture vs Manual

**OMEGA** is the most aggressive about auto-capture. Its hooks monitor conversation patterns and automatically store decisions ("let's go with PostgreSQL"), lessons learned ("the timeout was caused by connection pool exhaustion"), and session summaries. When you close a session, OMEGA records what was accomplished. When you edit a file, it surfaces relevant memories from prior sessions. You can also explicitly say "remember X" and it stores that too, but the real value is the automatic pipeline.

**Mem0** also auto-captures, using LLM-based extraction. When you add a conversation to Mem0, it uses an LLM to extract salient facts and relationships. This is powerful but has a cost implication: every memory extraction is an LLM call. If you're using the cloud API, that's included in your plan. Self-hosted, you're paying per extraction via your LLM provider.

**MEMORY.md** is mostly manual. Claude does write to it during sessions -- you'll see it add notes after significant decisions or when you explicitly ask -- but it's not systematic. There's no hook that fires on file edits or session boundaries. It's more like a shared notepad that Claude occasionally updates.

## Privacy and Data Locality

**OMEGA: Everything stays on your machine.** The SQLite database, the embedding model, the search index -- all local. No telemetry, no cloud sync, no network calls. If you're working on proprietary code or in a regulated environment, this matters. Your memories never leave your disk.

**Mem0 Cloud: Your data is on Mem0's servers.** That's the trade-off for a managed service. If you're building a consumer product and need to store user memories, this is fine -- it's what the platform is designed for. If you're storing memories about your employer's codebase, think carefully.

**Mem0 Self-hosted: You control the infrastructure.** But "self-hosted" still means running a vector database and potentially making API calls to an LLM provider for extraction. If you use OpenAI for extraction, conversation snippets leave your network. Using Ollama locally avoids this, but adds more infrastructure to manage.

**MEMORY.md: Local by definition.** It's a file on your disk. Anthropic doesn't collect it (Claude Code processes it locally). The simplest possible privacy story.

## Scalability: What Happens as Memories Grow

**At 100 memories:** All three solutions work fine. MEMORY.md starts getting verbose but is manageable. OMEGA and Mem0 both handle this trivially.

**At 1,000 memories:** MEMORY.md breaks down. You can't fit 1,000 memories in 200 lines. You'd need to aggressively prune and summarize, losing detail. OMEGA handles this well -- the vector index and FTS5 keep retrieval fast, and lifecycle tools (`omega_consolidate`, `omega_compact`) merge related memories and prune stale ones automatically. Mem0 handles this by design -- it's built for scale.

**At 10,000 memories:** MEMORY.md is not an option. OMEGA works but you need to be intentional about lifecycle management -- run consolidation regularly, use entity scoping to partition memories, and rely on the decay mechanism to surface recent/frequently-accessed memories over old noise. This is where the signal-to-noise problem gets real, and it's the hardest unsolved problem in AI memory. Mem0 with a dedicated vector database cluster handles this most gracefully from a pure infrastructure perspective -- it's what VC-backed infrastructure is built for.

## Best For: Honest Recommendations

### Use MEMORY.md if:

- You're just getting started with Claude Code and want zero friction
- Your project context fits in ~100 lines of markdown
- You want to manually curate exactly what Claude remembers
- You don't need cross-session search or auto-capture
- You're a single developer on a single project

MEMORY.md is genuinely great for small projects. Don't over-engineer memory if a text file solves your problem.

### Use OMEGA if:

- You use Claude Code (or Cursor/Windsurf) daily and lose context between sessions
- You want auto-capture without managing external infrastructure
- Privacy matters -- you need everything 100% local with zero network calls
- You want checkpoint/resume for long multi-session tasks
- You want typed, searchable memories with lifecycle management
- You're a developer who wants a `pip install` solution, not a platform to manage

OMEGA is purpose-built for the AI coding agent workflow. It's opinionated about what matters in that context: decisions, lessons, preferences, and task continuity.

### Use Mem0 if:

- You're building a product that needs to remember things about your users across conversations
- You need memory across multiple LLM providers or custom agent architectures
- You want graph-based relationship modeling between entities
- You need production-scale infrastructure with team-level access controls
- You're already using a vector database and want a memory layer on top of it
- You need the mature ecosystem (47K+ stars, VC-backed, extensive integrations)

Mem0 is a platform for building AI products with memory. It has REST APIs, SDKs in multiple languages, 20+ vector database integrations, and the organizational backing to support enterprise use cases. If you're building a customer-facing product, not a personal coding workflow, Mem0 is the more appropriate choice.

## The Honest Trade-offs

**OMEGA is new.** ~5 GitHub stars. Small community. If you hit an edge case, you might be the first person to encounter it. The benchmark results are strong, but the project is early. What you get in return is a focused tool that does one thing well: persistent memory for coding agents, with nothing to manage.

**Mem0 is mature but heavy.** 47K+ stars, $24M in funding, extensive documentation. But for the specific use case of "I just want my coding agent to remember things," it's over-architected. Self-hosted Mem0 means running a vector database, configuring an LLM provider, and managing infrastructure that exists to support use cases you don't have. The cloud API is simpler but sends your data off-machine.

**MEMORY.md is limited but honest.** It does exactly what it says: loads a file into context. No magic, no complexity, no failure modes beyond "file got too long." For many developers, this is enough. When it stops being enough, you'll know -- that's when you start looking at OMEGA or Mem0.

## Getting Started

**OMEGA:**
```bash
pip install omega-memory
omega setup
```
- [GitHub](https://github.com/omega-memory/omega-memory)
- [PyPI](https://pypi.org/project/omega-memory/)

**Mem0:**
```bash
pip install mem0ai
```
- [GitHub](https://github.com/mem0ai/mem0)
- [Docs](https://docs.mem0.ai)

**MEMORY.md:**
Already built into Claude Code. Type `/memory` in any session to open and edit it, or tell Claude to "remember" something and it writes to the file automatically.
