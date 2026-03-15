# Coordination File Claim Gap -- Root Cause Analysis & Fixes

**Date**: 2026-03-01
**Incident**: Agent "Cedar" (session `855a6768`) was working on Growth Tab files (`GrowthTab.tsx`, `page.tsx`, `growth/route.ts`). A separate agent session committed and pushed those same files without realizing Cedar had active work on them.

## Root Cause Analysis

### What failed

Four coordination mechanisms failed simultaneously, creating a compounding gap:

**1. Missing task registration (FIXED in 5381dff)**
`handle_coord_session_start` was not passing `payload.get("task")` to `register_session()`. Cedar's session was registered with `task=None`, making it invisible in the roster. Other agents saw Cedar as "idle" rather than "working on Growth Tab."

**2. Empty structured handoffs (FIXED in 5381dff)**
`handle_session_stop` in `session.py` was not writing to the `coord_handoffs` table. When Cedar's predecessor session ended, no structured handoff was recorded, so the admin timeline showed empty rows and no context about Growth Tab work.

**3. No file claims on Growth Tab files (NOT FIXED -- this is the core gap)**
Cedar never called `omega_file_check` or `omega_file_claim` on the Growth Tab files. The auto-claim mechanism (`handle_auto_claim_file` in `guards.py`) only fires on `PostToolUse` for `Edit|Write|NotebookEdit` tools. If Cedar was:
- Reading files via `Read` tool (no auto-claim triggered)
- Running dev server via `Bash` (no auto-claim triggered)
- Planning changes without editing yet (no auto-claim triggered)
- Or if the hook daemon was temporarily unavailable (fail-open skip)

...then zero file claims would exist. The Growth Tab files appeared unclaimed to any other agent.

**4. The other agent committed files it didn't create**
The committing agent found uncommitted Growth Tab changes in the working tree (left by Cedar or a predecessor). It staged and committed them as part of its own work. The `pre_commit_guard` hook, while active, only blocks commits when the staged files are **explicitly claimed by another session** in `coord_file_claims`. Since Cedar had NO claims, the guard saw these as unclaimed files and issued only a non-blocking warning ("staged files not in your claim list").

### Why the existing guardrails didn't catch it

| Guardrail | Why it failed |
|-----------|--------------|
| `auto_claim_file` (PostToolUse) | Only fires on Edit/Write/NotebookEdit. Read/Bash don't trigger it. Cedar may not have edited yet. |
| `pre_file_guard` (PreToolUse) | Protects files claimed by OTHER agents. Cedar had no claims, so nothing to protect. |
| `pre_commit_guard` (PreToolUse) | Checks if staged files are claimed by peers. Cedar had no claims, so overlap check found nothing. The "unclaimed_by_self" warning is non-blocking. |
| Session start uncommitted file check | Only warns about uncommitted files that are **peer-claimed** (`f_sid != session_id and f_path in uncommitted`). Uncommitted files with NO claims are silently ignored. |
| `[COORD-PROTOCOL]` instructions | Tells agent to "check `omega_file_check` before editing shared files." This is advisory -- agents can and do skip it, especially when they believe they're the only one working on those files. |

### The fundamental gap

The system relies on agents proactively claiming files via edits or explicit tool calls. But there's a window between "agent starts working on files" (reading, planning, running dev server) and "agent first edits a file" (triggering auto-claim) where the files are invisible to coordination. An agent that only reads files, or whose edits haven't triggered the hook yet, has zero coordination footprint for those files.

## Proposed Fixes (ranked by impact/effort)

### Fix 1: Auto-claim on Read in multi-agent mode (HIGH impact, MEDIUM effort)

**What**: Extend `handle_auto_claim_file` to also fire on `Read` tool use when peers are active, using a softer "read-interest" claim that doesn't block but provides visibility.

**Why**: Reading a file is the strongest signal of intent to work on it. In the Cedar incident, Cedar almost certainly Read the Growth Tab files before (or instead of) editing them. This would have made Cedar's interest visible.

**How**:
- Add `Read` to the `auto_claim_file` PostToolUse matcher in `hooks.json`
- In `handle_auto_claim_file`, when `tool_name == "Read"` and multi-agent mode, call `mgr.record_file_read()` (already exists) instead of `claim_file()`
- Modify `pre_commit_guard` to also check `coord_file_reads` -- if a staged file has recent reads from another session, issue a WARNING (not block)

**Files to modify**:
- `src/omega/data/hooks.json` -- add Read to auto_claim_file matcher
- `src/omega/server/hook_server/guards.py` -- `handle_auto_claim_file()`: add Read path using `record_file_read()`
- `src/omega/server/hook_server/guards.py` -- `handle_pre_commit_guard()`: check file reads from peers, warn

### Fix 2: Escalate "unclaimed staged files" warning to BLOCK in multi-agent mode (HIGH impact, LOW effort)

**What**: In `handle_pre_commit_guard`, when an agent stages files that are NOT in its own claim list AND peers are active, escalate from non-blocking warning to BLOCK (exit_code=2).

**Why**: This directly prevents the "commit someone else's work" pattern. The committing agent staged Growth Tab files it never edited (and thus never auto-claimed). The current warning "staged files not in your claim list" is too soft -- agents ignore non-blocking warnings.

**How**:
- In `handle_pre_commit_guard`, after computing `unclaimed_by_self`, check if `len(peers) > 0 and len(unclaimed_by_self) > 0`
- If so, return `exit_code=2` with a message like:
  `[COMMIT-GUARD] BLOCKED: N staged file(s) not in your claim list while peers are active. Only commit files YOU edited.`
- Add an override env var `OMEGA_SKIP_UNCLAIMED_CHECK=1` for legitimate cases

**Files to modify**:
- `src/omega/server/hook_server/guards.py` -- `handle_pre_commit_guard()`: ~15 lines changed

### Fix 3: Session-start uncommitted file warning without claims (MEDIUM impact, LOW effort)

**What**: When `handle_coord_session_start` detects uncommitted files in the working tree, warn about ALL uncommitted files (not just peer-claimed ones), with a note about authorship uncertainty.

**Why**: The current check at lines 52-87 of `coordination.py` only warns about uncommitted files that match `status.get("files")` (i.e., files with active claims). If nobody has claims, all uncommitted files are silently ignored. A new agent inheriting a dirty working tree gets no warning.

**How**:
- After the existing peer-owned check (line 78-85), add a fallback: if there are uncommitted files that are NOT peer-owned (because nobody claimed them), emit a softer warning:
  `[!] N uncommitted file(s) with no coordination claims: X, Y, Z -- verify you authored these before committing`
- Only emit when `peer_count > 0` (single-agent mode doesn't need this)

**Files to modify**:
- `src/omega/server/hook_server/coordination.py` -- `handle_coord_session_start()`: ~10 lines added after line 85

### Fix 4: Auto-claim from git diff at session start (MEDIUM impact, MEDIUM effort)

**What**: When a session starts and finds uncommitted changes in tracked files, auto-claim those files for the PREVIOUS session (if still registered) or mark them with a "ghost claim" attribute so the next agent knows they belong to someone.

**Why**: This retroactively creates claims for files that were modified but never claimed -- exactly the Cedar scenario. It closes the gap between "file was modified" and "file has a coordination claim."

**How**:
- In `handle_coord_session_start`, after detecting uncommitted files, check if any can be attributed to the predecessor session (via `recover_session()` or `get_latest_handoff()`)
- For each unattributed modified file, create a synthetic "ghost claim" with `session_id="unknown"` and `task="uncommitted-orphan"`
- `pre_commit_guard` already checks for peer-claimed files -- ghost claims would trigger this block

**Files to modify**:
- `src/omega/server/hook_server/coordination.py` -- `handle_coord_session_start()`: ~25 lines
- `src/omega/coordination.py` -- may need a `claim_file_ghost()` variant or a flag on `claim_file()`

### Fix 5: Intent-based soft claims from task description (LOW impact, HIGH effort)

**What**: When an agent's task description mentions specific files or components (e.g., "Growth Tab"), automatically create soft claims on likely files via pattern matching or LLM classification.

**Why**: Even before any file is touched, the task description "work on Growth Tab" maps to a predictable set of files. This provides the earliest possible coordination signal.

**How**:
- Build a project-specific file map (component name -> file paths) or use the existing `_DOMAIN_MAP` in guards.py
- At session registration time, if `task` is set, extract component/file references and create soft claims
- Soft claims wouldn't block but would surface as `[INTENT-OVERLAP]` warnings

**Files to modify**:
- `src/omega/server/hook_server/coordination.py` -- `handle_coord_session_start()`: ~30 lines
- New utility function for task-to-file mapping
- Coordination DB may need a `claim_type` column (hard vs soft)

## Recommended Implementation Order

1. **Fix 2** (escalate unclaimed staging to BLOCK) -- immediate, low-effort, prevents recurrence
2. **Fix 3** (warn about all uncommitted files) -- low-effort, catches the "inherited dirty tree" case
3. **Fix 1** (auto-claim on Read) -- medium effort, closes the biggest gap (Read without Edit)
4. **Fix 4** (ghost claims from git diff) -- medium effort, handles the "predecessor left files" case
5. **Fix 5** (intent-based claims) -- future enhancement, requires more infrastructure

Fixes 2 and 3 together would have prevented the Cedar incident with minimal code changes (~25 lines total). Fix 1 would prevent the broader class of "working on files without editing" gaps.

## Key Insight

The coordination system was designed around an assumption that **editing a file is the primary signal of working on it**. In practice, agents spend significant time reading, planning, and running commands before their first edit. The file claim system is blind during this entire pre-edit phase. The fixes above progressively close this blind spot, from blocking at commit time (reactive) to claiming at read time (proactive) to claiming at task assignment time (predictive).
