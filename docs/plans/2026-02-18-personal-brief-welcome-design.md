# Personal Brief Welcome Design

**Date:** 2026-02-18
**Goal:** Restructure the session start welcome so users *feel* OMEGA's memory working. Shift from system diagnostic to warm personal briefing.
**Target file:** `src/omega/server/hook_server.py` :: `handle_session_start()` (lines 625-1070)
**Audience:** The end user (human reading the terminal), with agent context preserved below.

## Approach

**"Personal Brief"**: Natural-language greeting at the top, structured agent context in the middle, compact system footer at the bottom. The first 3 lines prove memory is working.

## Output Structure

### Layer 1: Personal Greeting (always, 2-3 lines)

```
Good afternoon, Jason. 9-day streak.

Last session ended 8m ago - Aspen was reviewing the insights report.
You left off at: Magic moments plan done. Next: open-core launch checklist.
```

Data sources:
- Name: OMEGA profile (`display_name` or `name` field)
- Time of day: local hour (morning/afternoon/evening), timezone from profile
- Streak: `get_streak()` (existing)
- Last session: coord handoff data
- Left off: most recent checkpoint content

Fallbacks:
- No name: "Good afternoon." (no name)
- No streak or < 3 days: omit streak
- No last session: "Starting fresh."
- No checkpoint: omit "left off" line

### Layer 2: What's Ahead (conditional, 1-3 lines)

```
5 tasks pending - top: SEO Monday checklist (P5).
26 unread messages. 1 reminder due.
Alder is active, reviewing the insights report.
```

Data sources: existing task query, coord inbox count, reminder query, coord_sessions.
Omit any line with zero items.

### Layer 3: Agent Context (conditional)

```
[CONTEXT]
  DECISION: Implemented insights report recommendations...
  LESSON: Same rule as all outbound actions...
  PREF: Jason is currently in Bangkok...
```

Unchanged from current implementation. This is what Claude uses.

### Layer 4: Nudges (conditional, max 2)

Natural sentences, no `[NUDGE]` prefix:
```
You typically work on the website in the afternoons.
```

### Layer 5: System Footer (always, 1 line)

```
OMEGA: 730 memories | ok | capture: 12m ago | backup ok, doctor ok, cloud ok
```

All system diagnostics compressed into one line.

## What Gets Removed/Demoted

- `## Welcome back! OMEGA ready - 730 memories | Project: ... | Branch: ...` header -> replaced by personal greeting + footer
- `**Health:**`, `**Graph:**`, `**Profile:**` lines -> folded into footer or dropped
- `[ACTION]` maintenance line -> dropped (agent discovers via `omega_stats`)
- `[WEEKLY]` digest -> stays, rate-limited
- Bracket prefixes `[NUDGE]`, `[TASKS]`, `[REMINDER]` -> natural language

## What Stays Unchanged

- `[CONTEXT]` block (agent needs it)
- First-time user onboarding (memory_count == 0)
- Early user encouragement (memory_count <= 10)
- Alert lines `[!]` for degraded subsystems
- All existing data queries (no new DB calls needed, just reformatting)

## Scope

- Single file change: `src/omega/server/hook_server.py`
- Fallback script `hooks/session_start.py` is secondary (daemon path is what runs)
- No schema changes, no new tools, no new dependencies
