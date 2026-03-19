# LLM Provider Abstraction (Phase 1)

**Date**: 2026-02-27
**Scope**: Python core only (2 files)
**Approach**: Thin function wrapper

## Problem

OMEGA has direct Anthropic SDK calls in 2 Python files (`entity/extraction.py`, `task_utils.py`). This couples the core to a single LLM provider, blocking evaluation of OpenAI GPT-5.3 Codex or self-hosted models like MiniMax M2.5.

## Design

### New module: `src/omega/llm.py`

Single public function:

```python
def llm_complete(
    prompt: str,
    system: str,
    *,
    max_tokens: int = 512,
    temperature: float = 0.0,
    timeout: float = 5.0,
    model_tier: str = "fast",
) -> str:
```

### Provider dispatch

`OMEGA_LLM_PROVIDER` env var selects backend: `anthropic` (default), `openai`, `openai_compat`.

### Model tier mapping

| Provider | `fast` | `standard` |
|----------|--------|------------|
| anthropic | claude-haiku-4-5-20251001 | claude-sonnet-4-6 |
| openai | gpt-5.3-codex-spark | gpt-5.3-codex |
| openai_compat | (from OMEGA_LLM_MODEL_FAST) | (from OMEGA_LLM_MODEL_STANDARD) |

### API key resolution

- `anthropic`: `ANTHROPIC_API_KEY`
- `openai`: `OPENAI_API_KEY`
- `openai_compat`: `OMEGA_LLM_API_KEY` + `OMEGA_LLM_BASE_URL`

### Error handling

Returns empty string on any error (matches current caller behavior).

### No new hard dependencies

`openai` SDK is lazy-imported only when selected.

## Files changed

1. **New**: `src/omega/llm.py` (~80 lines)
2. **Edit**: `src/omega/entity/extraction.py` (swap SDK calls for `llm_complete`)
3. **Edit**: `src/omega/task_utils.py` (swap SDK calls for `llm_complete`)
4. **New**: `tests/test_llm.py` (unit tests for provider dispatch)

## Out of scope

- Streaming (neither caller needs it)
- Tool use / function calling (stays in MCP layer)
- TypeScript website changes (deferred to Phase 1b)
- New pip dependencies
