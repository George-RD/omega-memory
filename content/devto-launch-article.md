---
title: "I Built a Local-First Memory System for AI Agents. Here's What I Learned."
published: false
description: "AI agents forget everything between sessions. Mem0 fixes it with cloud APIs. I wanted something that stays on my machine."
tags: ai, opensource, python, productivity
---

Every AI coding agent I use has the same problem: it forgets everything the moment I close the session.

I tell Claude Code to use early returns. It follows the rule perfectly. Next session, it's back to nested conditionals. I spend 30 minutes debugging a Docker volume mount issue. Claude figures it out. Next session, same mistake from scratch. I make an architectural decision about PostgreSQL over MongoDB. Two weeks later, Claude suggests MongoDB.

This isn't a prompt engineering problem. It's an infrastructure problem. And I got tired of it.

## What Already Exists (and Why I Didn't Use It)

I looked at what's out there. Mem0, Zep, Letta (the MemGPT people). They all tackle the same problem, but they make tradeoffs I wasn't willing to accept.

**Mem0** is the biggest name. Tens of thousands of GitHub stars, $24M in YC funding. It works well if you're okay with cloud APIs. I wasn't. My code, my decisions, my debugging context. I don't want that on someone else's server. Mem0 does have a self-hosted option, but their primary path is cloud.

**Zep/Graphiti** requires Neo4j. That's a graph database I now have to run, maintain, and back up. For agent memory? Too heavy.

**Letta** (formerly MemGPT) takes an interesting approach with memory management through LLM calls. But it's a full agent framework. I don't want a framework. I want a memory layer I can plug into the tools I already use.

**CLAUDE.md files** are Claude Code's built-in option. A flat markdown file. Works for 10 lines of preferences. Falls apart at 200 lines when you're searching for a decision you made three weeks ago about whether to use JWTs or session cookies.

So I built OMEGA.

## What OMEGA Actually Does

OMEGA is an MCP server. You install it with `pip install omega-memory[server]`, run `omega setup`, and it configures itself for whatever editor you use. Claude Code, Cursor, Windsurf, Zed.

After setup, it runs in the background. No commands to learn. Two things happen automatically:

**Auto-capture.** When you make a decision or debug an issue, OMEGA detects it through Claude Code hooks and stores it. You don't have to say "remember this." It picks up patterns like "We chose X because Y" and debugging resolutions.

**Auto-surface.** When you start a session or edit a file, OMEGA surfaces relevant memories. If you're working on the auth module and you made a JWT decision three weeks ago, it shows up without you asking.

You can also tell it things explicitly:

> "Remember that we use PostgreSQL for the orders service because we need ACID transactions for payment processing."

But the real value is what it does without being asked.

## The Architecture Choices I'm Most Opinionated About

**SQLite, not Postgres/Neo4j/Redis.** Your agent's memory should be a single file you can copy, back up, or delete. SQLite gives you that. No server to run, no ports to open, no credentials to manage. I use sqlite-vec for vector search inside the same database. One file.

**Local ONNX embeddings, not API calls.** OMEGA uses bge-small-en-v1.5, a 90MB model that runs on CPU. No OpenAI API key needed. No network calls during retrieval. First query loads the model (bumps memory from 31MB to 337MB), then every search after that takes about 50ms.

**Hybrid retrieval, not just vectors.** This one matters more than people realize. A paper from UCSD/CMU researchers (Yuan, Su & Yao, 2026) ran a 3x3 factorial study on memory retrieval methods. Their finding: retrieval method is the dominant factor in accuracy. It spans 20 points across methods but only 3-8 across write strategies. OMEGA uses vector similarity + FTS5 full-text search + type-weighted scoring + contextual reranking. It's the same architecture the paper identified as optimal.

**Forgetting is a feature.** Most memory systems only add. OMEGA also removes. Session summaries expire after a day. Unaccessed memories decay in ranking over time. But preferences and error lessons are exempt from decay, because "always use early returns" should persist forever and "this Docker fix worked" should persist until you need it again.

## Benchmark Results

I ran OMEGA against LongMemEval, an academic benchmark from ICLR 2025. 500 questions testing extraction, reasoning, temporal understanding, and preference tracking.

| System | Score |
|--------|------:|
| **OMEGA** | **95.4%** |
| Mastra | 94.87% |
| Emergence | 86.0% |
| Zep/Graphiti | 71.2% |

#1 overall. The benchmark is open and reproducible. You can verify it yourself.

## What Surprised Me

**More test lines than source lines.** The codebase has about 11,000 lines of source and 21,000 lines of tests. That ratio happened organically. When you're building a system that agents depend on for context, correctness isn't optional. A wrong memory surfaced at the wrong time can send an agent down a completely wrong path.

**Contradiction detection matters more than I expected.** If you tell an agent "use JWTs" in January and "use session cookies" in March, what should happen? OMEGA detects contradictions on store. For decisions, the newer one wins automatically. For lessons, it flags the conflict and lets you resolve it.

**The checkpoint/resume feature gets used constantly.** I built it because I kept stopping mid-refactor when I had to leave my desk. Now it's one of the most-used features. `omega_checkpoint` saves task state. Next session, `omega_resume_task` picks up exactly where you left off. No "where was I?" No re-explaining context.

## Try It

```bash
pip install omega-memory[server]
omega setup
omega doctor
```

Three commands. Works with Claude Code, Cursor, Windsurf, and Zed. Your data stays on your machine.

{% github omega-memory/omega-memory %}

The core is Apache-2.0 and will stay that way. There's a Pro tier for multi-agent coordination (file claims, branch guards, deadlock detection), but the memory system itself is free and complete.

If you're building something similar or have opinions about how agent memory should work, I'd like to hear about it. The hardest open problem I'm working on is cross-project learning: when should a lesson from Project A apply to Project B? I don't have a good answer yet.
