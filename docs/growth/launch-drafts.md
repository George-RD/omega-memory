# OMEGA Growth Campaign Drafts

> **IMPORTANT**: Review everything before posting. Do NOT post without explicit approval.
> Generated: 2026-02-15

---

## 1. Show HN Post

**Title:** `Show HN: OMEGA – Persistent memory for AI coding agents (MCP server)`

**Body:**

Hey HN, I built OMEGA because I got tired of re-explaining the same context to Claude Code every session. Every architectural decision, debugging insight, and code preference — gone the moment the session ends.

OMEGA is an MCP server that gives AI coding agents long-term memory. It runs locally (SQLite + CPU-only ONNX embeddings, no external services) and works with Claude Code, Cursor, and Windsurf.

How it works:

- **Auto-capture**: Hooks detect when decisions, lessons, or preferences are established during a coding session and store them automatically
- **Auto-surface**: When you edit a file or start a session, relevant memories from past sessions appear in context — without you asking
- **Checkpoint/resume**: Stop mid-task, pick up in a new session with full context of where you left off

The search pipeline uses vector similarity (bge-small-en-v1.5 via ONNX) + FTS5 + contextual re-ranking. Memories have a lifecycle: dedup, evolution (similar memories merge), TTL-based expiry, conflict detection, and decay for unaccessed content.

Setup is two commands:

    pip install omega-memory
    omega setup

On the LongMemEval benchmark (500 multi-session memory tasks), OMEGA scores 95.4% — currently #1 on the leaderboard.

Architecture: single SQLite database, 25 MCP tools, ~337 MB RSS after model load. Everything runs on your machine.

Code: https://github.com/omega-memory/omega-memory
PyPI: https://pypi.org/project/omega-memory/

I'd love feedback on the approach. The hardest problem has been corpus pollution at scale — as you accumulate hundreds of memories, signal-to-noise degrades. We recently added ingest-side contradiction detection (new decisions automatically supersede old conflicting ones) and atomic fact splitting to help with this.

---

## 2a. Reddit Post — r/ClaudeAI

**Title:** I built persistent memory for Claude Code — decisions, lessons, and context that survive across sessions

**Body:**

I've been using Claude Code daily for months, and the biggest friction point is context loss. Every new session starts from zero. I'd spend 10-20 minutes re-explaining architectural decisions, code preferences, and project context that Claude already knew yesterday.

So I built OMEGA — an MCP server that gives Claude Code long-term memory.

**What it does:**
- Auto-captures decisions, lessons, and preferences during your session (no manual tagging)
- Auto-surfaces relevant memories when you edit files or start new sessions
- Checkpoint mid-task, resume in a new session with full context
- Contradiction detection — when you change a decision, the old one is automatically superseded
- Runs 100% locally (SQLite + CPU-only embeddings, nothing leaves your machine)

**Setup:**
```
pip install omega-memory
omega setup
```

That's it. Two commands, works immediately. No API keys, no cloud services.

After setup, it works in the background. When Claude makes a decision or debugs something tricky, OMEGA stores it. Next session, it's there.

You can also explicitly tell Claude to remember things — "remember that we use JWT tokens, not session cookies" — but the real value is the automatic stuff.

On the LongMemEval benchmark (500 multi-session memory tasks), it scores 95.4% accuracy, which is #1 on the leaderboard.

**GitHub:** https://github.com/omega-memory/omega-memory
**PyPI:** `pip install omega-memory`

Also works with Cursor and Windsurf (`omega setup --client cursor`).

Happy to answer questions about the architecture or how it works under the hood.

---

## 2b. Reddit Post — r/mcp

**Title:** OMEGA — MCP memory server with 25 tools, auto-capture/surface, and #1 LongMemEval score

**Body:**

Sharing an MCP server I've been building: OMEGA gives AI coding agents persistent memory across sessions.

**25 MCP tools** including:
- `omega_store` / `omega_query` — typed memory storage + semantic search
- `omega_checkpoint` / `omega_resume_task` — cross-session task continuity
- `omega_lessons` — cross-session lessons ranked by access count
- `omega_similar` / `omega_traverse` — relationship graph navigation
- `omega_compact` / `omega_consolidate` — memory lifecycle management
- `omega_remind` — time-based reminders
- Plus auto-capture and auto-surface via hooks

**Search pipeline:**
1. Vector similarity (bge-small-en-v1.5 ONNX, 384-dim)
2. FTS5 keyword matching
3. Type-weighted scoring (decisions/lessons weighted 2x)
4. Contextual re-ranking (tags, project, content)
5. Dedup + time-decay

Everything runs locally — single SQLite database, CPU-only inference, ~337 MB after model load.

Scored 95.4% on LongMemEval (500 multi-session memory tasks) — #1 on the leaderboard.

```
pip install omega-memory
omega setup                    # auto-detects Claude Code
omega setup --client cursor    # or Cursor
omega setup --client windsurf  # or Windsurf
```

GitHub: https://github.com/omega-memory/omega-memory

Would appreciate feedback, especially from anyone building MCP memory solutions — curious how others approach the corpus pollution problem (signal-to-noise as memories scale).

---

## 3. X/Twitter Launch Thread (7 tweets)

**Tweet 1 (HOOK):**
I built persistent memory for AI coding agents.

95.4% accuracy on LongMemEval (#1 on the leaderboard). Runs 100% locally. Two commands to install.

Here's what it does and why I built it: 🧵

**Tweet 2 (PROBLEM):**
The problem: AI coding agents are stateless.

Every new session starts from zero. Decisions you made yesterday? Gone. That debugging insight from last week? Gone.

I was spending 10-20 minutes per session re-explaining context Claude Code already knew.

**Tweet 3 (SOLUTION):**
OMEGA is an MCP server that gives your agent long-term memory.

It auto-captures decisions, lessons, and preferences during your session — no manual tagging.

Next session, relevant memories surface automatically when you edit files or start working.

**Tweet 4 (DEMO):**
Setup is two commands:

pip install omega-memory
omega setup

That's it. Works with Claude Code, Cursor, and Windsurf.

Everything runs locally — SQLite + CPU-only embeddings. Nothing leaves your machine.

[ATTACH: demo.gif]

**Tweet 5 (TECHNICAL DEPTH):**
Under the hood:

- 25 MCP tools (search, checkpoint/resume, graph traversal, reminders)
- Vector similarity + FTS5 + contextual re-ranking
- Memory lifecycle: dedup, evolution, TTL, conflict detection, decay
- Contradiction detection: new decisions auto-supersede old ones
- ~337 MB RAM, zero external services

**Tweet 6 (PROOF):**
On LongMemEval (500 multi-session memory tasks):

OMEGA: 95.4% — #1 overall

The hardest part isn't storing memories — it's retrieving the right ones at scale without drowning in noise.

**Tweet 7 (CTA):**
OMEGA is open source (Apache-2.0):

https://github.com/omega-memory/omega-memory

Star it if this is useful. Issues and PRs welcome — there are good-first-issue labels for anyone who wants to contribute.

---

## 4. Social Preview Image Spec

**Dimensions:** 1280x640px (GitHub recommended)

**Layout:**
- Background: Dark (#0d1117 or similar dark gradient)
- Left side (60%):
  - OMEGA logo (if available, otherwise bold "OMEGA" text)
  - Tagline: "Persistent memory for AI coding agents"
  - Subtitle: "#1 on LongMemEval • 25 MCP tools • 100% local"
  - Badges row: "Claude Code" "Cursor" "Windsurf" in small pills
- Right side (40%):
  - Simplified terminal showing:
    ```
    $ omega setup
    ✓ Memory system ready

    > "What did we decide about auth?"
    → JWT tokens, not session cookies
      (decided 3 weeks ago)
    ```

**Colors:** Use GitHub-dark-friendly palette. White/light text on dark. Accent color: bright green or blue for the checkmark and key stats.

**Font:** Inter or SF Mono for the terminal section.

**Tool:** Can be created with Figma, Canva, or generated via HTML screenshot. Should be saved as `assets/social-preview.png` in the repo and set via GitHub repo Settings > Social preview.

---

## 5. Awesome-MCP PR Follow-up Comments

### For punkpeye/awesome-mcp-servers #1997:

> Hi @punkpeye — friendly follow-up on this. OMEGA is now published on the official MCP Registry (registry.modelcontextprotocol.io), v0.8.2 on PyPI with 650+ downloads, and scores #1 on LongMemEval (95.4%). Happy to adjust the listing format if needed. Thanks for maintaining this list!

### For appcypher/awesome-mcp-servers #314:

> Hi — just checking in on this PR. Since opening it, we've published to the MCP Registry and PyPI (650+ downloads). OMEGA scores 95.4% on LongMemEval (#1 overall). Let me know if any changes are needed for the listing format. Thanks!

---

## Posting Order (Recommended)

1. **Social preview image** — Create and set first, so all shared links look good
2. **Show HN** — Post Tuesday-Thursday, 8-10am ET. Be at keyboard for 4+ hours to respond to every comment
3. **X/Twitter thread** — Post same day as HN, 2-3 hours after (catch the HN traffic)
4. **Reddit r/ClaudeAI** — Post day after HN (different audience, won't cannibalize)
5. **Reddit r/mcp** — Same day as r/ClaudeAI or day after
6. **Awesome-MCP comments** — Post immediately (these are already open PRs)

## Timing Notes

- Best HN launch days: Tuesday, Wednesday, Thursday
- Best HN launch time: 8-10am ET (target ~9am)
- Avoid weekends and Mondays for launches
- Space Reddit posts 24h apart to avoid looking like a spam campaign
