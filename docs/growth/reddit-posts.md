# Reddit Post Drafts

## Schedule

| When | Where | Why |
|------|-------|-----|
| Mon Feb 17, 9 AM PST | r/ClaudeAI | Current comment thread will be cold. Monday morning = peak dev browsing. Proven audience. |
| Wed Feb 19, 8 AM PST | r/LocalLLaMA | 2-day gap. Wednesday = highest engagement for tech subs. Morning catches US + Europe. |
| Fri Feb 21, 10 AM PST | r/MCP | 2-day gap. Friday = exploratory browsing. Niche sub so timing matters less. |

If ClaudeAI post breaks 50 upvotes, delay the other two by a day. Ride that momentum.

---

## Post 1: r/ClaudeAI

**Title:** I got tired of re-explaining my codebase every session, so I built a memory layer for Claude Code

**Body:**

Every time I opened a new Claude Code session, I had to re-explain the same things. "Use early returns in this project." "The deploy target is Vercel, not AWS." "We decided last week to use SQLite, not Postgres."

Claude is smart, but it has amnesia. So I built OMEGA to fix it.

**What it does:**

- At session start, a hook fires and loads a briefing: your recent decisions, preferences, lessons learned, and error patterns. Claude sees all of this before you type anything.
- During work, another hook fires after file edits and surfaces relevant memories. If you're editing auth.ts, Claude gets context from the last time you touched auth.
- When you say "remember this" or Claude makes a key decision, it calls `omega_store()` and that memory persists forever. Next session, next week, next month.

**What it is NOT:**

There's no background AI reading your conversations. OMEGA is an MCP server. Claude calls tools (`omega_store`, `omega_query`) like it calls any other MCP tool. Hooks fire on session events (start, end, prompt submit, file edit) and inject context. That's the whole trick.

**Setup is 2 minutes:**

```
pip install omega-memory
omega setup
omega doctor
```

That registers the MCP server, installs the hooks, and writes a small bootstrap into your CLAUDE.md that tells Claude to call `omega_welcome()` at session start.

Everything runs locally. SQLite database, ONNX embeddings on CPU (~337 MB RAM after first query), no cloud, no API keys.

Scored 95.4% on LongMemEval (an ICLR 2025 benchmark for long-term memory, 500 tasks). Currently #1 on the leaderboard. Open source, Apache 2.0.

Architecture walkthrough and setup guide: https://omegamax.co/quickstart

Happy to answer questions. Built this for myself and figured other Claude Code users might find it useful.

---

## Post 2: r/LocalLLaMA

**Title:** Built a persistent memory system for AI coding agents. Everything runs locally: SQLite, ONNX embeddings, zero cloud.

**Body:**

I wanted persistent memory for my AI coding agent (Claude Code) but every existing solution either required a cloud API, an external vector database, or both.

So I built one that runs entirely on your machine.

**Stack:**

- **Storage:** SQLite + sqlite-vec (vector extension). Single file at `~/.omega/omega.db`. Backs up trivially.
- **Embeddings:** bge-small-en-v1.5 via ONNX Runtime. 384-dim vectors, runs on CPU, no GPU needed. ~337 MB RSS after first query, ~31 MB at startup.
- **Encryption:** Optional AES-256-GCM with keys in macOS Keychain. At rest, not in transit (there is no transit, everything is local).
- **Protocol:** MCP (Model Context Protocol). Works with Claude Code, Cursor, Windsurf, or any MCP client.

**How it works:**

The agent calls 12 MCP tools to store and retrieve memories. Hooks fire on session events (start, end, file edits) to auto-capture decisions and surface relevant context. No background process scanning your conversations.

Memory types have different decay behaviors. Decisions and lessons persist forever. Session summaries expire after a day. Preferences and error patterns are exempt from decay. Contradictions are auto-detected via heuristic signals (negation, antonyms, temporal overrides), no LLM calls.

**Benchmark:**

95.4% on LongMemEval (ICLR 2025, 500-task memory evaluation). #1 on the leaderboard. Published results, reproducible.

```
pip install omega-memory
omega setup
omega doctor
```

Quickstart: https://omegamax.co/quickstart
Source: https://github.com/omega-memory/omega-memory

If you care about keeping your data local, this was built with that as a hard constraint from day one. No telemetry, no cloud sync, no external calls. Happy to answer questions about the architecture.

---

## Post 3: r/MCP

**Title:** I built a memory layer for the MCP ecosystem: 12 tools that give any agent persistent context

**Body:**

MCP gives agents access to tools, but there's no standard way for agents to remember what they learned yesterday. I built OMEGA to fill that gap.

**12 MCP tools across 4 areas:**

- **Session context:** `omega_welcome` (briefing at session start), `omega_protocol` (operating instructions)
- **Storage:** `omega_store` (persist decisions, lessons, preferences, error patterns), `omega_remember` (explicit user memories)
- **Retrieval:** `omega_query` (semantic search), `omega_lessons` (ranked lessons for a task), `omega_similar` (find related memories), `omega_traverse` (graph traversal)
- **Continuity:** `omega_checkpoint` (save task state), `omega_resume_task` (pick up where you left off), `omega_compact` (consolidate duplicates)

**How auto-capture works:**

Hooks fire on MCP client events. On session start, `omega_welcome()` returns a structured briefing (grouped by type: active constraints, preferences, decisions, lessons, error patterns). After file edits, `surface_memories` finds relevant context and injects it. On prompt submit, `auto_capture` detects decisions and lessons from the conversation.

The agent also explicitly calls `omega_store()` when it makes a decision or the user says "remember this." Memories auto-link via embedding similarity (creates graph edges to top-3 similar memories).

**Storage:**

SQLite + sqlite-vec for vectors. ONNX embeddings (bge-small-en-v1.5, CPU). Contradiction detection via heuristics (no LLM calls). Intelligent decay with type-based exemptions.

Works with Claude Code, Cursor, Windsurf, or any MCP-compatible client. `omega setup --client cursor` configures the right config file.

95.4% on LongMemEval (#1). Open source, Apache 2.0, on PyPI as `omega-memory`.

Quickstart: https://omegamax.co/quickstart
GitHub: https://github.com/omega-memory/omega-memory

Curious what memory patterns others in the MCP community are building. What does your agent need to remember?
