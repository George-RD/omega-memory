# Design: Wire Intelligence Cards

**Date**: 2026-02-24
**Status**: Approved
**Approach**: A (Transparency-driven upgrade)

## Problem

The Intelligence Cards system (`cards.py`, `card_tracker.py`) was built with 11 card formatters and an adaptive transparency engine. Only 6 of 11 formatters are wired. The 4 dead cards are the ones that would make OMEGA Pro feel noticeably smarter: full structured memory context, decision trails, confidence-scored learnings, and prior-decision awareness on file edits.

## Dead Cards

| Card | Formatter | Purpose |
|------|-----------|---------|
| Full Memory | `format_memory_card` | Multi-line `[OMEGA MEMORY]` with transparency-scaled depth + linked memories |
| Decision Trail | `format_decision_trail_card` | Surfaces prior decisions before new ones on the same topic |
| Full Decision | `format_decision_card` | `[OMEGA DECISIONS]` showing decision history for files being edited |
| Full Learning | `format_learning_card` | `[OMEGA LEARNED]` with confidence score from pattern match density |

## Approach: Transparency-Driven Upgrade

Use the existing `compute_transparency()` system. Compact cards stay for simple sessions (MINIMAL); full structured cards activate as session complexity rises (NORMAL, VERBOSE).

| Transparency | Memory | Decision | Learning |
|---|---|---|---|
| MINIMAL | Compact (current behavior) | Suppressed | Suppressed |
| NORMAL | Full card (top 3 memories) | Latest decision only | One-liner + confidence |
| VERBOSE | Full card + linked memories | Full trail (up to 5) | Full detail + confidence |

Decision trail card fires independently on `omega_store(type="decision")`, regardless of transparency level.

## Integration Points

### 1. Memory Cards: `memory.py:_surface_for_edit`

After results are enriched with age/is_remembered flags, check transparency level. If NORMAL+, use `format_memory_card()` with linked memories. If MINIMAL, keep existing `_format_results_as_cards()`.

### 2. Decision Trail: `handlers.py:handle_omega_store`

After storing a `decision` type memory, query for prior decisions matching the content. If found, format with `format_decision_trail_card()` and append to response. Exclude the just-stored memory.

### 3. Learning Cards: `assistant.py:handle_assistant_capture`

Get transparency from session tracker. If NORMAL+, use `format_learning_card()` with computed confidence. If MINIMAL, keep existing `format_compact_learning_card()`.

### 4. Decision Cards on Edit: `memory.py:_surface_for_edit`

When transparency is NORMAL+, query for decisions about the file being edited. Format with `format_decision_card()`. Call `tracker.record_decisions_seen()` to escalate complexity (decisions beget more decisions).

## Files Modified

- `src/omega/server/hook_server/memory.py` -- wire `format_memory_card` + `format_decision_card`
- `src/omega/server/hook_server/assistant.py` -- wire `format_learning_card`
- `src/omega/server/handlers.py` -- wire `format_decision_trail_card` in `omega_store`
- Test files for each integration point

## Files Not Modified

- `cards.py` -- formatters are already complete
- `card_tracker.py` -- tracking is already wired
- `session.py` -- session cards are already wired
