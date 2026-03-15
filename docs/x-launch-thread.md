# X Launch Thread — @omega_memory

**Status:** READY — post after updating X profile
**Date drafted:** February 13, 2026

---

## Profile Setup (do this first)

| Field | Value |
|-------|-------|
| Name | OMEGA |
| Bio | Persistent memory for AI agents. #1 on LongMemEval. 25 MCP tools. Local-first. Open source. |
| Website | omegamax.co |
| Location | Local-first |

---

## Thread

### Tweet 1/5

We just hit #1 on LongMemEval — the only standardized benchmark for AI agent memory.

95.4%. Beating Mastra ($13M, YC), Emergence ($97M), Supermemory (backed by Jeff Dean).

Zero funding. One developer. Everything runs on my MacBook.

OMEGA is open source today.

### Tweet 2/5

What OMEGA actually does:

Your AI coding agent forgets everything between sessions. Architecture decisions, debugging insights, your coding preferences — gone.

OMEGA gives it persistent memory. 25 MCP tools. Semantic search over every conversation you've ever had. Auto-capture, intelligent forgetting, temporal awareness.

One SQLite file. No cloud. No API keys.

### Tweet 3/5

The part nobody else has built: multi-agent coordination.

4 Claude Code agents working on the same codebase? OMEGA handles file locking, task handoff, intent broadcasting, and deadlock detection.

I built it because I kept running into it — agents overwriting each other's work. Now they negotiate. Through MCP.

### Tweet 4/5

The leaderboard:

1. OMEGA — 95.4% — $0 funding
2. Mastra — 94.87% — $13M (YC)
3. Hindsight — 91.4%
4. Emergence — 86.0% — $97M
5. Supermemory — 85.2% — $3M

Mastra needs gpt-5-mini to hit their score. We do it with GPT-4.1 and a retrieval pipeline that runs in 50ms on localhost.

### Tweet 5/5

pip install omega-memory

That's it. Works with Claude Code, Cursor, any MCP-compatible agent.

GitHub: github.com/omega-memory/omega-memory
Benchmarks: omegamax.co/benchmarks
How we built it: omegamax.co/blog/number-one-on-longmemeval

Apache 2.0. Ship it.
