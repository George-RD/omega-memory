# Contextual Welcome Intelligence

## Problem

The session welcome is generic. Agents say "let me get oriented" (sounds like they don't know OMEGA), reference stale signals like 19-day streaks, and narrate boot-up tool calls. No perceived intelligence.

## Solution: Hybrid Context Nugget + Tier-Aware Tips

### Approach

1. Hook computes a **context nugget** — structured facts (peers, checkpoint, tasks) in 1-2 sentences
2. **Behavioral directive** suppresses boot-up narration
3. **User tier system** adapts welcome behavior based on journey stage
4. **Feature usage detection** queries `llm_usage.db` to suggest undiscovered tools

### User Tiers (by memory count)

| Tier | Count | Badge | Welcome Style |
|------|-------|-------|--------------|
| Newcomer | 0-10 | First Seed | Guided onboarding, celebrate captures |
| Explorer | 11-50 | Growing Graph | Feature discovery tips |
| Builder | 51-200 | Power Builder | Efficiency tips, power features |
| Veteran | 200+ | Veteran | Pure situational awareness |

Graduation milestone emitted once per tier transition via `~/.omega/tier-milestone` marker.

### Feature Discovery

Query `SELECT DISTINCT tool_name FROM llm_usage` to detect which tools user has called. Per-tier tip pools:

- **Explorer**: omega_query, omega_remind, omega_checkpoint
- **Builder**: omega_relate, omega_weekly_digest, omega_coord_status, omega_consult_claude
- **Veteran**: no tips unless new tool shipped

One tip per session, rotated from unused tools.

### Context Nugget Signals

| Signal | Source | Include when |
|--------|--------|-------------|
| Active peers | `ctx["active_peers"]` | count > 0 |
| Solo/team mode | peer count | always |
| Last checkpoint | `last_info["checkpoint_text"]` | exists |
| Time since last session | `last_info["ended_ago"]` | exists |
| Top pending task | `pending_tasks[0]` | exists |
| Git status | `git_status_str` | not "Clean" |
| Streak | `streak` dict | only at milestones |

### Changes

**File**: `src/omega/server/hook_server/session.py`

1. New `_get_user_tier(memory_count)` — returns (name, badge, is_graduation)
2. New `_get_unused_features(tier)` — queries llm_usage.db for undiscovered tools
3. New `_build_context_nugget(...)` — assembles situational facts
4. Replace `[GREET]` block (lines 757-764) with tier-aware output
5. Extend milestone check (line 167-169) for tier graduations

~80 lines added. No new files. No new dependencies.

### Token Budget

Old [GREET]: ~40 tokens. New: ~70-90 tokens (nugget + directive + optional tip). Net +30-50 tokens.
