# Launch Day Copy

## Reddit Posts

### r/ClaudeAI

**Title:** I built a persistent memory system for Claude Code (open source, local-first)

**Body:**

Claude Code forgets everything between sessions. You debug something, close the session, and next time the same mistake happens from scratch.

I built OMEGA to fix this. It's an MCP server that runs locally and gives Claude Code persistent memory across sessions.

What it does:

- **Auto-captures** decisions and debugging outcomes (through Claude Code hooks)
- **Auto-surfaces** relevant context when you start working on a file
- **Checkpoint/resume** so you can stop mid-refactor and pick up later
- **Semantic search** over all your past sessions (bge-small-en-v1.5 + sqlite-vec)

Everything runs on your machine. SQLite database, ONNX embeddings on CPU. No cloud, no API keys.

It scores 95.4% on LongMemEval (ICLR 2025 benchmark for long-term memory systems), #1 on the leaderboard.

```bash
pip install omega-memory[server]
omega setup
```

Also works with Cursor, Windsurf, and Zed.

Apache-2.0 licensed. GitHub: https://github.com/omega-memory/omega-memory

---

### r/selfhosted

**Title:** OMEGA: Self-hosted persistent memory for AI coding agents (SQLite, no cloud, Apache-2.0)

**Body:**

For anyone running Claude Code, Cursor, or similar AI coding tools: I built a self-hosted memory system that keeps your agent's context across sessions.

Why self-hosted matters here: your agent sees your code, your architecture decisions, your debugging sessions. That context shouldn't leave your machine.

Stack:

- SQLite (single file database, easy to backup)
- ONNX embeddings (bge-small-en-v1.5, runs on CPU, ~90MB model)
- MCP protocol (standard protocol for AI tool integrations)
- ~31MB RAM at startup, ~337MB after first query

No Docker needed. No external services. Install with pip, run `omega setup`, done.

```bash
pip install omega-memory[server]
omega setup
omega doctor
```

Works great on any Linux VPS too. SSH in, install, every future session has full memory of past sessions. Survives disconnects.

Apache-2.0 core. GitHub: https://github.com/omega-memory/omega-memory

---

### r/LocalLLaMA

**Title:** Built an open source, local-first memory layer for AI agents (ONNX embeddings, SQLite, no API keys)

**Body:**

I've been running Claude Code as my daily driver and the biggest pain point was context loss between sessions. Every session starts from zero.

I built OMEGA to fix it. It's a local-first memory system that uses:

- **bge-small-en-v1.5** for embeddings (ONNX runtime, CPU-only, ~90MB)
- **sqlite-vec** for vector search (inside SQLite, no external vector DB)
- **FTS5** for full-text search (hybrid retrieval, not just vectors)
- **Contextual reranking** to surface the right memory at the right time

The retrieval pipeline is vector similarity + FTS5 + type-weighted scoring + reranking + dedup. A recent paper from UCSD/CMU (Yuan et al., 2026) found that retrieval method is the dominant factor in memory accuracy, spanning 20 points across methods but only 3-8 across write strategies. OMEGA's hybrid approach aligns with their findings.

Everything is local. No OpenAI API calls for embeddings. No cloud services. SQLite database you can copy or delete.

Scored 95.4% on LongMemEval (ICLR 2025), #1 on the leaderboard.

Works with any MCP client (Claude Code, Cursor, Windsurf, Zed).

GitHub: https://github.com/omega-memory/omega-memory

---

### r/ChatGPTCoding

**Title:** Open source memory for AI coding agents - stops your agent from forgetting between sessions

**Body:**

If you use Claude Code, Cursor, or similar tools, you've hit this: you teach your agent something, close the session, and it's gone.

OMEGA is an MCP server that gives your agent persistent memory. Install, run setup, forget about it. It auto-captures your decisions and surfaces them in future sessions.

Quick example: You spend 30 minutes debugging a Docker issue. Agent figures it out. OMEGA stores the fix automatically. Next time the same issue comes up, your agent already knows the answer.

```bash
pip install omega-memory[server]
omega setup
```

Local-first (SQLite + ONNX embeddings), no cloud, Apache-2.0.

GitHub: https://github.com/omega-memory/omega-memory

---

## Tweets

### @jasonsosa (launch day)

I've been running the same AI coding agent every day for months. And every morning it wakes up with amnesia.

So I built a memory system for it. Local-first, SQLite, runs on CPU. No cloud APIs.

95.4% on the LongMemEval benchmark, #1 overall.

Open source, Apache-2.0.

(reply with link: https://github.com/omega-memory/omega-memory)

### @omega_memory (launch day)

v1.1.0 shipped.

95.4% on LongMemEval. 12 MCP tools. Auto-capture. Semantic search. Checkpoint/resume.

SQLite + ONNX. No cloud. No API keys.

pip install omega-memory[server]

---

## LinkedIn Post (Jason Sosa)

AI coding agents have a memory problem. Every session starts from zero. Your agent forgets architectural decisions, debugging lessons, and code style preferences the moment you close the terminal.

I've been working on OMEGA, a local-first memory system for AI agents. It runs as an MCP server alongside Claude Code, Cursor, Windsurf, or Zed.

Instead of cloud APIs and external databases, it uses SQLite and local ONNX embeddings. Your data stays on your machine. It auto-captures decisions and surfaces relevant context in future sessions.

We scored #1 on LongMemEval, the ICLR 2025 benchmark for long-term memory systems (95.4%, 500 questions).

The core is open source under Apache-2.0. If you're running AI coding agents daily and frustrated by the context loss, give it a look: github.com/omega-memory/omega-memory
