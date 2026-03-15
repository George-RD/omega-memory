# How to Use OMEGA with Claude Code — Persistent Memory in 2 Minutes

Every Claude Code session starts from zero. You open a new terminal, start coding, and immediately spend the first 10 minutes re-explaining decisions you already made. "We use PostgreSQL, not MySQL." "The auth tokens are RS256." "Don't run `git add .` — it picks up generated files."

This is the fundamental problem with AI coding agents: they're stateless. There's no continuity between sessions. Your agent doesn't remember what it learned yesterday, what mistakes it made last week, or what architectural decisions you settled three sessions ago. It's like working with a brilliant colleague who has amnesia.

OMEGA fixes this. It's an MCP memory server that gives Claude Code (and other AI coding agents) persistent, semantic memory across every session. Decisions, lessons, preferences, context — all stored locally, all surfaced automatically when relevant. No cloud. No API keys. Just `pip install` and go.

## Install & Setup

Two commands. That's it.

```bash
pip install omega-memory
omega setup
```

`omega setup` does five things:

1. **Creates `~/.omega/`** — local storage for your SQLite database, profile, and logs.
2. **Downloads the embedding model** — fetches `bge-small-en-v1.5` (~90MB ONNX model) for local semantic search. No API calls, everything runs on your CPU.
3. **Registers the MCP server** — adds `omega-memory` to your Claude Code config so it can spawn OMEGA on demand.
4. **Installs hooks** — adds 7 hooks to `~/.claude/settings.json` for automatic memory capture, surfacing, and coordination.
5. **Updates CLAUDE.md** — injects an `<!-- OMEGA:BEGIN -->` block into `~/.claude/CLAUDE.md` that teaches Claude how to use memory tools.

Setup is idempotent — run it again after upgrades without worrying about duplicates.

Verify everything works:

```bash
omega doctor
```

```
OMEGA Doctor — v1.0.0
─────────────────────
[OK] Python 3.12.4
[OK] Database: ~/.omega/omega.db (0 memories)
[OK] Embedding model: bge-small-en-v1.5-onnx
[OK] MCP server registered in ~/.claude.json
[OK] 7 hooks installed in ~/.claude/settings.json
[OK] CLAUDE.md has OMEGA block

All checks passed.
```

## Your First Memory

Open Claude Code and tell it something:

> "Remember that we use PostgreSQL, not MySQL for this project."

Claude stores this via OMEGA as a decision. Close the session.

Open a new session. Ask:

> "What database do we use?"

OMEGA performs a semantic search, finds the match, and Claude responds:

> "Based on a previous decision, you use PostgreSQL, not MySQL."

You didn't re-explain anything. The memory persisted. And because OMEGA uses semantic search (not keyword matching), asking "which DB engine" or "what's our database choice" would surface the same result.

You can also store and query from the CLI directly:

```bash
omega store "API rate limit is 100 req/min per user" --type decision
omega query "rate limiting"
```

## Auto-Capture

You don't have to say "remember" every time. OMEGA's hooks watch your conversation and auto-capture:

- **Decisions** — When Claude detects language like "let's go with X" or "the approach is Y," it stores that as a decision.
- **Lessons learned** — When a debugging session resolves with an insight, it captures the lesson.
- **Session summaries** — When you close a session, OMEGA records what was accomplished.

When you edit or open files, OMEGA surfaces relevant memories from prior sessions:

```
[MEMORY] (2 days ago) Decision: webhook payloads use HMAC-SHA256 signatures
[MEMORY] (5 days ago) Lesson: retry logic needs exponential backoff with jitter
```

OMEGA also handles **contradiction detection**. If you previously decided "use REST for the API" and later say "let's switch to GraphQL," OMEGA supersedes the old decision. No stale context floating around.

## Checkpoint & Resume

This is where OMEGA saves you from the context window wall.

You're deep into a refactor — 30 files touched, a clear plan in your head, halfway through. Then Claude's context window fills up. In a vanilla setup, you'd start a new session and spend 20 minutes reconstructing where you were.

With OMEGA, Claude calls `omega_checkpoint` before the context runs out:

```
Checkpoint saved:
  Task: "Migrate auth module from JWT to session tokens"
  Progress: 18/30 files converted
  Files: src/auth/*.ts, src/middleware/auth.ts, ...
  Decisions: "Keep backward compat for 2 releases"
  Next: "Convert src/api/routes.ts, then update tests"
```

New session. Claude calls `omega_resume_task`:

```
Resuming: "Migrate auth module from JWT to session tokens"
  Progress: 18/30 files converted
  Next step: Convert src/api/routes.ts, then update tests
  Key decision: Keep backward compat for 2 releases
```

It picks up exactly where it left off. No re-explanation. No lost context.

## Power Features

Once you're comfortable with the basics, OMEGA has deeper tools:

- **`omega_lessons`** — Retrieves cross-session lessons ranked by how often they've been verified. Ask "what lessons have we learned about deployments?" and get battle-tested answers.
- **`omega_similar`** — Given a memory, finds related knowledge clusters. Useful for discovering connections you didn't know existed.
- **`omega_traverse`** — Walks the relationship graph between memories. When you need to understand *why* a decision was made, traverse from the decision to the context that led to it.
- **`omega_remind`** — Set time-based reminders. "Remind me in 2 hours to check the deployment." OMEGA surfaces it at the right time.

### Works Beyond Claude Code

OMEGA speaks MCP (Model Context Protocol), so it works with any MCP-compatible agent:

- **Cursor** — Add OMEGA as an MCP server in Cursor's settings.
- **Windsurf** — Same MCP integration path.
- **Any MCP client** — OMEGA uses stdio transport. Point your client at `python -m omega` and you're connected.

The hooks are Claude Code-specific, but the core memory tools work everywhere.

## Get Started

OMEGA is open source (Apache 2.0) and runs entirely on your machine.

```bash
pip install omega-memory
omega setup
```

- **GitHub**: [github.com/omega-memory/omega-memory](https://github.com/omega-memory/omega-memory)
- **PyPI**: [pypi.org/project/omega-memory](https://pypi.org/project/omega-memory/)
- **Docs**: [omegamax.co](https://omegamax.co)

If OMEGA saves you from re-explaining your codebase one more time, consider giving the repo a star. It helps others find it.
