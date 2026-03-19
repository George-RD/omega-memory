# LLM Provider Abstraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Abstract OMEGA's 2 direct Anthropic SDK call sites behind a provider-agnostic `llm_complete()` function, enabling swappable LLM backends (Anthropic, OpenAI, OpenAI-compatible/vLLM).

**Architecture:** Single `src/omega/llm.py` module with one public function `llm_complete()`. Provider dispatch via `OMEGA_LLM_PROVIDER` env var. Model selection via `model_tier` parameter ("fast"/"standard") mapped to provider-specific model names. Lazy imports for non-default providers.

**Tech Stack:** Python 3.11+, anthropic SDK (existing), openai SDK (lazy import), pytest + unittest.mock

---

### Task 1: Create `src/omega/llm.py` with tests

**Files:**
- Create: `src/omega/llm.py`
- Create: `tests/test_llm.py`

**Step 1: Write the failing tests**

Create `tests/test_llm.py`:

```python
"""Tests for omega.llm provider abstraction."""

import json
import os
import pytest
from unittest.mock import MagicMock, patch


class TestLlmComplete:
    """Test llm_complete() with mocked providers."""

    def test_anthropic_default_provider(self, monkeypatch):
        """Default provider is anthropic."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)

        mock_content = MagicMock()
        mock_content.text = "extracted summary"

        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            from omega.llm import llm_complete
            result = llm_complete("hello", "system prompt", max_tokens=100)

        assert result == "extracted summary"
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"
        assert call_kwargs.kwargs["max_tokens"] == 100

    def test_openai_provider(self, monkeypatch):
        """OpenAI provider uses openai SDK."""
        monkeypatch.setenv("OMEGA_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_choice = MagicMock()
        mock_choice.message.content = "openai response"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            from omega.llm import llm_complete
            result = llm_complete("hello", "system prompt", max_tokens=100)

        assert result == "openai response"

    def test_openai_compat_provider(self, monkeypatch):
        """openai_compat provider uses openai SDK with custom base_url."""
        monkeypatch.setenv("OMEGA_LLM_PROVIDER", "openai_compat")
        monkeypatch.setenv("OMEGA_LLM_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("OMEGA_LLM_API_KEY", "local-key")

        mock_choice = MagicMock()
        mock_choice.message.content = "vllm response"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            from omega.llm import llm_complete
            result = llm_complete("hello", "system prompt")

        assert result == "vllm response"
        # Verify base_url was passed
        mock_openai.OpenAI.assert_called_once()
        call_kwargs = mock_openai.OpenAI.call_args
        assert call_kwargs.kwargs["base_url"] == "http://localhost:8000/v1"

    def test_returns_empty_on_missing_api_key(self, monkeypatch):
        """Returns empty string when API key is missing."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)

        from omega.llm import llm_complete
        result = llm_complete("hello", "system prompt")
        assert result == ""

    def test_returns_empty_on_api_error(self, monkeypatch):
        """Returns empty string on API error."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.side_effect = Exception("timeout")

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            from omega.llm import llm_complete
            result = llm_complete("hello", "system prompt")

        assert result == ""

    def test_model_tier_standard(self, monkeypatch):
        """model_tier='standard' maps to Sonnet."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)

        mock_content = MagicMock()
        mock_content.text = "sonnet response"

        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            from omega.llm import llm_complete
            llm_complete("hello", "system prompt", model_tier="standard")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"

    def test_unknown_provider_returns_empty(self, monkeypatch):
        """Unknown provider returns empty string."""
        monkeypatch.setenv("OMEGA_LLM_PROVIDER", "unknown_provider")

        from omega.llm import llm_complete
        result = llm_complete("hello", "system prompt")
        assert result == ""


class TestGetApiKey:
    """Test API key resolution."""

    def test_anthropic_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-123")
        from omega.llm import _get_api_key
        assert _get_api_key("anthropic") == "ak-123"

    def test_openai_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-123")
        from omega.llm import _get_api_key
        assert _get_api_key("openai") == "sk-123"

    def test_compat_key(self, monkeypatch):
        monkeypatch.setenv("OMEGA_LLM_API_KEY", "local-key")
        from omega.llm import _get_api_key
        assert _get_api_key("openai_compat") == "local-key"

    def test_compat_defaults_to_none_string(self, monkeypatch):
        monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)
        from omega.llm import _get_api_key
        assert _get_api_key("openai_compat") == "none"

    def test_missing_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from omega.llm import _get_api_key
        assert _get_api_key("anthropic") == ""
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/singularityjason/Projects/omega && python3.11 -m pytest tests/test_llm.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'omega.llm'"

**Step 3: Write the implementation**

Create `src/omega/llm.py`:

```python
"""OMEGA LLM Provider Abstraction.

Thin wrapper over LLM APIs for text completion. Supports swappable
providers via OMEGA_LLM_PROVIDER env var.

Providers:
  - anthropic (default): Uses anthropic SDK
  - openai: Uses openai SDK
  - openai_compat: Uses openai SDK with custom base_url (for vLLM, MiniMax, etc.)
"""

import logging
import os

logger = logging.getLogger("omega.llm")

# Model tier -> provider-specific model name
_MODEL_MAP: dict[str, dict[str, str]] = {
    "anthropic": {
        "fast": "claude-haiku-4-5-20251001",
        "standard": "claude-sonnet-4-6",
    },
    "openai": {
        "fast": "gpt-4o-mini",
        "standard": "gpt-4o",
    },
    "openai_compat": {
        "fast": os.environ.get("OMEGA_LLM_MODEL_FAST", "default"),
        "standard": os.environ.get("OMEGA_LLM_MODEL_STANDARD", "default"),
    },
}


def _get_api_key(provider: str) -> str:
    """Resolve API key for the given provider."""
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY", "")
    if provider == "openai":
        return os.environ.get("OPENAI_API_KEY", "")
    if provider == "openai_compat":
        return os.environ.get("OMEGA_LLM_API_KEY", "none")
    return ""


def _complete_anthropic(
    prompt: str, system: str, *, model: str, max_tokens: int,
    temperature: float, timeout: float,
) -> str:
    """Complete via Anthropic SDK."""
    import anthropic

    api_key = _get_api_key("anthropic")
    if not api_key:
        return ""

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _complete_openai(
    prompt: str, system: str, *, model: str, max_tokens: int,
    temperature: float, timeout: float, base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Complete via OpenAI SDK (also used for openai_compat)."""
    import openai

    key = api_key or _get_api_key("openai")
    if not key:
        return ""

    kwargs: dict = {"api_key": key, "timeout": timeout}
    if base_url:
        kwargs["base_url"] = base_url

    client = openai.OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or ""


def llm_complete(
    prompt: str,
    system: str,
    *,
    max_tokens: int = 512,
    temperature: float = 0.0,
    timeout: float = 5.0,
    model_tier: str = "fast",
) -> str:
    """Send a prompt to the configured LLM provider. Returns text response.

    Args:
        prompt: User message content.
        system: System prompt.
        max_tokens: Maximum tokens in response.
        temperature: Sampling temperature (0.0 = deterministic).
        timeout: Request timeout in seconds.
        model_tier: "fast" (cheap/quick) or "standard" (capable).

    Returns:
        Response text, or empty string on any failure.
    """
    provider = os.environ.get("OMEGA_LLM_PROVIDER", "anthropic")

    models = _MODEL_MAP.get(provider)
    if not models:
        logger.warning("Unknown LLM provider: %s", provider)
        return ""

    model = models.get(model_tier, models["fast"])

    try:
        if provider == "anthropic":
            return _complete_anthropic(
                prompt, system, model=model, max_tokens=max_tokens,
                temperature=temperature, timeout=timeout,
            )

        if provider == "openai":
            return _complete_openai(
                prompt, system, model=model, max_tokens=max_tokens,
                temperature=temperature, timeout=timeout,
            )

        if provider == "openai_compat":
            base_url = os.environ.get("OMEGA_LLM_BASE_URL", "")
            api_key = _get_api_key("openai_compat")
            return _complete_openai(
                prompt, system, model=model, max_tokens=max_tokens,
                temperature=temperature, timeout=timeout,
                base_url=base_url or None, api_key=api_key,
            )

    except Exception as e:
        logger.debug("LLM completion failed (%s): %s", provider, e)

    return ""
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/singularityjason/Projects/omega && python3.11 -m pytest tests/test_llm.py -v`
Expected: All 12 tests PASS

**Step 5: Commit**

```bash
cd /Users/singularityjason/Projects/omega
git add src/omega/llm.py tests/test_llm.py
git commit -m "feat: add LLM provider abstraction layer

New omega.llm module with llm_complete() that dispatches to
anthropic, openai, or openai_compat (vLLM/MiniMax) based on
OMEGA_LLM_PROVIDER env var. Model tier mapping keeps callers
provider-agnostic."
```

---

### Task 2: Migrate `entity/extraction.py` to use `llm_complete()`

**Files:**
- Modify: `src/omega/entity/extraction.py:51-54,106-128`
- Modify: `tests/test_entity_extraction.py` (update mocks)

**Step 1: Write a failing integration test**

Add to `tests/test_entity_extraction.py` in `TestExtractEntities`:

```python
    def test_uses_llm_complete(self, monkeypatch):
        """extract_entities uses omega.llm.llm_complete under the hood."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import omega.entity.extraction as ext_mod
        ext_mod._last_call_ts = 0.0

        haiku_response = json.dumps({
            "entities": [{"name": "Python", "type": "technology"}],
            "relationships": [],
        })

        with patch("omega.llm.llm_complete", return_value=haiku_response) as mock_llm:
            result = ext_mod.extract_entities(
                "We are using Python to build a data pipeline.",
                "user_message",
            )

        mock_llm.assert_called_once()
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "Python"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/singularityjason/Projects/omega && python3.11 -m pytest tests/test_entity_extraction.py::TestExtractEntities::test_uses_llm_complete -v`
Expected: FAIL (extraction.py still uses anthropic directly)

**Step 3: Modify `extraction.py`**

In `src/omega/entity/extraction.py`:

1. Remove `_get_anthropic_module()` function (lines 51-54)
2. Add import: `from omega.llm import llm_complete`
3. Replace lines 106-127 (the API key check + anthropic call) with:

```python
    # Throttle: max 1 call per 2 seconds
    with _throttle_lock:
        now = time.monotonic()
        if now - _last_call_ts < _THROTTLE_INTERVAL_S:
            return _EMPTY
        _last_call_ts = now

    try:
        raw_text = llm_complete(
            content[:1000],
            _NER_SYSTEM_PROMPT,
            max_tokens=512,
            timeout=3.0,
        )
        if not raw_text:
            return _EMPTY

        cleaned = _strip_code_fences(raw_text)
        parsed = json.loads(cleaned)

        if not isinstance(parsed, dict):
            return _EMPTY

        return _validate_extraction(parsed)

    except Exception as e:
        logger.debug("Entity extraction failed: %s", e)
        return _EMPTY
```

Also remove the `ANTHROPIC_API_KEY` check (lines 106-108) since `llm_complete` handles missing keys internally.

**Step 4: Update existing tests that mock `_get_anthropic_module`**

In `tests/test_entity_extraction.py`, update tests that patch `_get_anthropic_module` to patch `omega.llm.llm_complete` instead:

- `test_returns_parsed_entities_from_haiku`: patch `omega.llm.llm_complete` to return the JSON string directly
- `test_returns_empty_on_api_error`: patch `omega.llm.llm_complete` to return `""`
- `test_returns_empty_on_invalid_json`: patch `omega.llm.llm_complete` to return `"this is not valid json"`
- `test_strips_markdown_code_fences`: patch `omega.llm.llm_complete` to return the fenced JSON
- `test_filters_entries_missing_required_fields`: patch `omega.llm.llm_complete` to return the JSON with bad entries
- `test_returns_empty_when_no_api_key`: no mock change needed (llm_complete returns "" without key)

The key simplification: tests no longer need to construct mock Anthropic client/response/content objects. They just mock `llm_complete` to return a string.

**Step 5: Run full extraction test suite**

Run: `cd /Users/singularityjason/Projects/omega && python3.11 -m pytest tests/test_entity_extraction.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
cd /Users/singularityjason/Projects/omega
git add src/omega/entity/extraction.py tests/test_entity_extraction.py
git commit -m "refactor: migrate entity extraction to llm_complete()

Replace direct anthropic SDK calls with omega.llm.llm_complete().
Simplify test mocks from multi-layer Anthropic client mocks to
single-function string return patches."
```

---

### Task 3: Migrate `task_utils.py` to use `llm_complete()`

**Files:**
- Modify: `src/omega/task_utils.py:109-136`
- Modify: `tests/test_task_utils.py` (add provider test)

**Step 1: Write a failing test**

Add to `tests/test_task_utils.py` in `TestSummarizeTaskText`:

```python
    def test_uses_llm_complete(self, monkeypatch):
        """summarize_task_text uses omega.llm.llm_complete under the hood."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with patch("omega.task_utils.llm_complete", return_value="fix auth token refresh") as mock_llm:
            result = summarize_task_text(
                "We need to fix the authentication token refresh bug that causes users to be logged out"
            )

        mock_llm.assert_called_once()
        assert result == "fix auth token refresh"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/singularityjason/Projects/omega && python3.11 -m pytest tests/test_task_utils.py::TestSummarizeTaskText::test_uses_llm_complete -v`
Expected: FAIL (task_utils still uses anthropic directly)

**Step 3: Modify `task_utils.py`**

In `src/omega/task_utils.py`:

1. Add import at top: `from omega.llm import llm_complete`
2. Replace lines 109-136 (API key check + anthropic call + fallback) with:

```python
    summary = llm_complete(
        full_text[:500],
        (
            "Summarize this developer task/question into a concise 3-8 word "
            "status bar title. Output ONLY the title, no quotes, no punctuation, "
            "lowercase. Focus on the ACTION and TARGET, not filler words. "
            "Examples: 'fix auth token refresh bug', 'add dark mode toggle', "
            "'refactor statusline task display', 'debug failing CI pipeline'."
        ),
        max_tokens=30,
        timeout=2.0,
    )
    summary = summary.strip().rstrip(".")
    if 5 <= len(summary) <= 60:
        return summary
    return clean_task_text(prompt)
```

Remove the `import anthropic` and the `os.environ.get("ANTHROPIC_API_KEY")` check since `llm_complete` handles this.

**Step 4: Run full task_utils test suite**

Run: `cd /Users/singularityjason/Projects/omega && python3.11 -m pytest tests/test_task_utils.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /Users/singularityjason/Projects/omega
git add src/omega/task_utils.py tests/test_task_utils.py
git commit -m "refactor: migrate task_utils to llm_complete()

Replace direct anthropic SDK import with omega.llm.llm_complete().
Removes anthropic dependency from task_utils entirely."
```

---

### Task 4: Verify no remaining direct anthropic imports in core

**Files:**
- No file changes (verification only)

**Step 1: Grep for remaining anthropic imports**

Run: `cd /Users/singularityjason/Projects/omega && grep -rn "import anthropic" src/omega/ --include="*.py" | grep -v __pycache__ | grep -v llm.py`
Expected: No results (all direct imports should now be in `llm.py` only)

**Step 2: Run full test suite**

Run: `cd /Users/singularityjason/Projects/omega && python3.11 -m pytest tests/test_llm.py tests/test_entity_extraction.py tests/test_task_utils.py -v`
Expected: All tests PASS

**Step 3: Verify extraction still works with API key check removed**

The `ANTHROPIC_API_KEY` check was in `extraction.py` lines 106-108. Now `llm_complete` handles this internally (returns ""). Confirm `test_returns_empty_when_no_api_key` still passes:

Run: `cd /Users/singularityjason/Projects/omega && python3.11 -m pytest tests/test_entity_extraction.py::TestExtractEntities::test_returns_empty_when_no_api_key -v`
Expected: PASS
