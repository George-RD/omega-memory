# Intelligence Cards for OMEGA Pro

> Date: 2026-02-23
> Status: Approved
> Scope: Pro-only in-session intelligence visibility

## Problem

OMEGA already runs a sophisticated intelligence stack (retrieval biasing, perspective differentiation, auto-capture, contextual injection, lessons learned). But all of it happens silently in hook outputs injected as system reminders. The user never sees it working. Pro adds 74+ tools over core's 12, but the value proposition is "more buttons," not "smarter behavior."

## Solution: Intelligence Cards

Structured, compact blocks (`[OMEGA]` prefix) that make OMEGA's intelligence visible to the user during their session. Same engine, different visibility.

**Value proposition**: "Core OMEGA remembers. Pro OMEGA shows you how it thinks."

## Card Types

### 1. Memory Card
Surfaces when Claude uses a retrieved memory in its response.

```
[OMEGA] Used: "Always validate test fixtures before running"
  verified 4x | last used 2d ago | project: omega
```

### 2. Decision Trail Card
Surfaces before Claude makes a decision on a topic with prior decisions.

```
[OMEGA] Prior decisions on "sync policy":
  -> Feb 15: Coordination is PRO-ONLY (active)
  -> Feb 13: Hide pro until 100+ stars (active)
  ! New decision should be consistent with these.
```

### 3. Learning Card
Surfaces when OMEGA auto-captures a lesson, decision, or pattern from Claude's response.

```
[OMEGA] Learned: "threading.Lock is non-reentrant -- never nest"
  auto-captured | will verify in future sessions
```

### 4. Warning Card
Surfaces proactively when Claude is about to edit a file or area with known issues.

```
[OMEGA] Warning: Known issues in coordination.py:
  3 prior errors related to "lock nesting"
  Last fix: session abc123, Feb 20
```

### 5. Session Summary Card
Surfaces at session end with intelligence metrics.

```
[OMEGA] Session intelligence:
  12 memories surfaced | 8 used | 3 new lessons captured
  1 contradiction detected | 0 repeated mistakes
  Learning rate: +2 verified lessons this week
```

## Architecture

### Data Flow

```
Current:  Hook fires -> queries OMEGA -> injects [MEMORY]/[TIP] text -> Claude absorbs silently
Proposed: Hook fires -> queries OMEGA -> generates [OMEGA] card  -> Claude surfaces to user
```

The change is in formatting (structured cards vs free text) and protocol instruction (surface to user vs absorb silently).

### Implementation Layers

1. **Hook layer** (`hook_server/*.py`): Modify existing hooks to emit structured `[OMEGA]` cards instead of free-text `[MEMORY]`/`[TIP]` blocks when `_pro_licensed` is True.

2. **Protocol layer** (`protocol.py`): Add pro-only protocol section instructing Claude to relay `[OMEGA]` blocks to the user. Keep them compact. Do not editorialize.

3. **Capture layer** (`hook_server/assistant.py`): Existing auto-capture becomes the source for Learning Cards. Add outcome tracking by comparing surfaced memories vs referenced memories in Claude's response.

4. **Summary layer** (new): Session-end hook aggregates card stats and emits Session Summary Card.

### Pro Gating

```python
# In hook handler
if self._pro_licensed:
    card = format_intelligence_card(card_type, data)
    inject(card)  # [OMEGA] block
else:
    inject(legacy_format)  # existing [MEMORY]/[TIP] blocks
```

Core users: no change, existing behavior preserved.
Pro users: structured `[OMEGA]` cards that Claude is instructed to surface.

## Outcome Tracking (Aggressive Learning)

### Signal Types

| Signal | When | Effect |
|---|---|---|
| **Used** | Claude references card content in response | Immediate priority +1 (cap 5) |
| **Acknowledged** | Claude surfaces card to user | Neutral |
| **Ignored** | Card injected but never mentioned | Weak negative |
| **Contradicted** | Claude's response contradicts card | Auto-store `contradiction_detected` memory |

### Aggressive Learning Parameters

- **Graduation threshold**: 2 sessions. A lesson used in 2 distinct sessions is verified and injected into protocol.
- **Decay acceleration**: Ignored 2x consecutively triggers 3x decay lambda. OMEGA forgets fast.
- **Contradiction handling**: Immediate `contradiction_detected` memory stored; surfaces as Warning Card next time topic comes up.
- **First-session capture**: New auto-captures start at `capture_confidence: "medium"`. If used in same session, immediately promoted to "high".
- **Philosophy**: Strong opinions, loosely held. Capture aggressively, promote fast, forget fast.

## Scope

### Files Modified

| File | Change |
|---|---|
| `hook_server/memory.py` | Reformat advisory output as [OMEGA] cards |
| `hook_server/assistant.py` | Add outcome tracking (used/ignored/contradicted) |
| `hook_server/session.py` | Session Summary Card at session end |
| `protocol.py` | Pro-only section: "surface [OMEGA] blocks to user" |
| `sqlite_store.py` or `bridge.py` | Aggressive decay/graduation parameters |

### Not Touched

- No new MCP tools
- No schema changes
- No new database tables
- No frontend/web changes
- No pyproject.toml changes

## Success Criteria

1. Pro users see [OMEGA] cards in Claude's responses when OMEGA is actively working
2. Core users see no change
3. Memories that prove useful graduate faster (2 sessions)
4. Memories that are ignored decay faster (2 consecutive ignores)
5. Users report feeling like OMEGA is "thinking alongside them"
