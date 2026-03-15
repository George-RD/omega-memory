# OMEGA Outreach Pitches

Ready-to-send pitches for newsletters, listicle authors, and directories.

---

## 1. Console.dev - Developer Tool of the Week

**To:** david@console.dev
**Subject:** OMEGA - local-first memory for AI coding agents

Hi David,

I built OMEGA, an open-source memory system for AI coding agents (Claude Code, Cursor, Windsurf). It's local-first, runs on SQLite + ONNX embeddings, and scores #1 on LongMemEval (95.4%), the ICLR 2025 benchmark for long-term memory.

The pitch: AI coding agents are stateless. Every session starts from zero. OMEGA auto-captures decisions and lessons, surfaces them when relevant, and handles contradiction detection and intelligent forgetting. Three commands to install, zero API keys.

- GitHub: https://github.com/omega-memory/omega-memory
- PyPI: 3,600+ monthly downloads
- License: Apache-2.0

Would love to be considered for Developer Tool of the Week.

Best,
Jason

---

## 2. PulseMCP Newsletter

**To:** hello@pulsemcp.com
**Subject:** OMEGA for PulseMCP Weekly Pulse

Hi,

OMEGA is a persistent memory MCP server for AI coding agents. It provides 12 MCP tools for semantic search, auto-capture, checkpoints, and cross-session learning. Local-first (SQLite + ONNX), no API keys required.

What makes it different from other memory servers:
- #1 on LongMemEval (95.4%) - the ICLR 2025 benchmark
- Intelligent forgetting (dedup, contradiction detection, time decay)
- Auto-capture hooks that detect decisions without "remember this" commands
- Works with Claude Code, Cursor, Windsurf, Zed, Codex, Antigravity

GitHub: https://github.com/omega-memory/omega-memory
Listed on: MCP Registry, awesome-mcp-servers, mcp.so, mcpservers.org

Would love to be featured in the Weekly Pulse.

Thanks,
Jason

---

## 3. MCP Newsletter (mcpnewsletter.com)

**To:** (use contact form on mcpnewsletter.com)
**Subject:** OMEGA - #1 ranked memory MCP server

OMEGA is the #1 ranked memory system on LongMemEval (95.4%). It's an MCP server that gives AI coding agents persistent memory with semantic search, auto-capture, and intelligent forgetting. Fully local, no cloud.

12 MCP tools, works with every MCP client. Apache-2.0.

GitHub: https://github.com/omega-memory/omega-memory

---

## 4. Listicle Author Template

**For:** Authors of "Best MCP Servers" or "Top AI Dev Tools" posts

**Subject:** Adding OMEGA to your MCP server roundup

Hi [Name],

I saw your [article title] and noticed the memory/knowledge category could use OMEGA. It's the #1 ranked memory system on LongMemEval (95.4%, ICLR 2025 benchmark), fully open source, and local-first.

Quick facts:
- 12 MCP tools (store, query, checkpoint, resume, consolidate, etc.)
- Semantic search via bge-small-en-v1.5 + sqlite-vec
- Auto-captures decisions and lessons without explicit commands
- Works with Claude Code, Cursor, Windsurf, Zed
- Apache-2.0, 3,600+ PyPI downloads/month

GitHub: https://github.com/omega-memory/omega-memory

Happy to provide any additional details.

Best,
Jason

---

## 5. Specific Listicle Targets

| Article | Author | Platform | Contact |
|---------|--------|----------|---------|
| Top 10 Most Popular MCP Servers | FastMCP team | fastmcp.me/blog | Site contact form |
| Best MCP Servers for 2025 | Various | dev.to | Comment + DM |
| What Makes an MCP Server Successful | Hands-On Architects | handsonarchitects.com | Blog comments |
| 5 Proven Strategies for MCP Server Usage | Shubham Palriwala | Medium | @shubhampalriwala |
| MCP Servers roundup | Firecrawl | firecrawl.dev/blog | Site contact |
| MCP Servers roundup | Builder.io | builder.io/blog | Site contact |

---

## 6. Reddit Posts (for Phase 2, after Mar 29 warm-up)

### r/ClaudeCode post draft

**Title:** I built a persistent memory system for Claude Code that auto-captures your decisions

I got tired of re-explaining my codebase every session. "We use early returns." "The auth middleware was refactored." "Don't touch legacy billing."

So I built OMEGA -- it runs locally, auto-captures decisions and lessons, and surfaces them when relevant. No API keys, no cloud. Three commands:

```
pip3 install omega-memory[server]
omega setup
omega doctor
```

After 6 weeks: 800+ memories stored, 130K queries served across 107 sessions. Scores #1 on LongMemEval (95.4%).

It also works with Cursor, Windsurf, Zed, and any MCP client.

Apache-2.0: https://github.com/omega-memory/omega-memory

Happy to answer questions about the architecture.

### r/LocalLLaMA post draft

**Title:** Local-first memory for AI coding agents - no cloud, no API keys, SQLite + ONNX

Built a persistent memory system that gives AI coding agents (Claude Code, Cursor, etc.) long-term memory across sessions. Everything runs on your machine:

- SQLite for storage
- bge-small-en-v1.5 ONNX embeddings (384-dim, ~90MB model)
- sqlite-vec for vector search
- ~337MB RAM after first query, no GPU

It auto-captures decisions, detects contradictions, deduplicates, and decays stale memories. #1 on LongMemEval (95.4%).

Works as an MCP server with any compatible client. Apache-2.0.

https://github.com/omega-memory/omega-memory
