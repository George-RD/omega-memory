# Retrieval Quality Overhaul: Cross-Encoder Reranking + Contradiction Detection

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve memory retrieval precision via cross-encoder reranking and auto-supersede outdated memories via contradiction detection at store time.

**Architecture:** Two independent features added to the existing retrieval/storage pipeline. Cross-encoder reranks top candidates after collection and basic filtering. Contradiction detection intercepts the store path when new content is similar (0.55-0.88) to existing memories and contains correction signals, auto-superseding the old version.

**Tech Stack:** ONNX Runtime (existing dep), `ms-marco-MiniLM-L-6-v2` cross-encoder model, `tokenizers` (existing dep), SQLite (existing).

---

## Task 1: Cross-Encoder Module — Model Loading & Scoring

**Files:**
- Create: `src/omega/reranker.py`
- Create: `tests/test_reranker.py`

### Step 1: Write failing tests for the reranker module

```python
# tests/test_reranker.py
"""Tests for OMEGA cross-encoder reranker."""
import pytest


class TestCrossEncoderScoring:
    """Cross-encoder should score (query, passage) pairs."""

    def test_score_single_pair(self):
        """Scoring a single (query, passage) pair returns a float."""
        from omega.reranker import cross_encoder_score
        scores = cross_encoder_score("What is Python?", ["Python is a programming language"])
        assert len(scores) == 1
        assert isinstance(scores[0], float)

    def test_score_multiple_pairs(self):
        """Scoring multiple passages returns one score per passage."""
        from omega.reranker import cross_encoder_score
        passages = [
            "Python is a programming language",
            "The weather is sunny today",
            "Python was created by Guido van Rossum",
        ]
        scores = cross_encoder_score("What is Python?", passages)
        assert len(scores) == 3
        # Relevant passages should score higher than irrelevant
        assert scores[0] > scores[1]  # "Python is..." > "weather is sunny"
        assert scores[2] > scores[1]  # "Python was created..." > "weather"

    def test_score_empty_passages(self):
        """Empty passage list returns empty scores."""
        from omega.reranker import cross_encoder_score
        scores = cross_encoder_score("test query", [])
        assert scores == []

    def test_score_empty_query(self):
        """Empty query still returns scores (no crash)."""
        from omega.reranker import cross_encoder_score
        scores = cross_encoder_score("", ["some passage"])
        assert len(scores) == 1
        assert isinstance(scores[0], float)


class TestCrossEncoderFallback:
    """When ONNX model is unavailable, reranker should fall back gracefully."""

    def test_fallback_returns_none_when_disabled(self, monkeypatch):
        """With OMEGA_CROSS_ENCODER=0, scoring returns None."""
        monkeypatch.setenv("OMEGA_CROSS_ENCODER", "0")
        # Reset module state
        import omega.reranker as mod
        mod._RERANKER_MODEL = None
        mod._LOAD_ATTEMPTED = False
        scores = mod.cross_encoder_score("query", ["passage"])
        assert scores is None

    def test_fallback_returns_none_when_no_model(self, monkeypatch):
        """When model files don't exist, scoring returns None."""
        monkeypatch.setenv("OMEGA_RERANKER_MODEL_DIR", "/nonexistent/path")
        import omega.reranker as mod
        mod._RERANKER_MODEL = None
        mod._LOAD_ATTEMPTED = False
        mod._RERANKER_MODEL_DIR = None
        scores = mod.cross_encoder_score("query", ["passage"])
        assert scores is None


class TestCrossEncoderModelLifecycle:
    """Model loading follows the same lazy-load pattern as graphs.py."""

    def test_model_info_returns_dict(self):
        """get_reranker_model_info returns model metadata."""
        from omega.reranker import get_reranker_model_info
        info = get_reranker_model_info()
        assert "model_name" in info
        assert "available" in info
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_reranker.py -v --no-header -q 2>&1 | head -20`
Expected: FAIL with `ModuleNotFoundError: No module named 'omega.reranker'`

### Step 3: Implement `src/omega/reranker.py`

The module mirrors `graphs.py` patterns: lazy model loading, circuit breaker, ONNX Runtime, env-var disable.

```python
# src/omega/reranker.py
"""
OMEGA Cross-Encoder Reranker — ONNX-based reranking for retrieval precision.

Provides:
- cross_encoder_score(query, passages) -> list[float] | None
- get_reranker_model_info() -> dict
- preload_reranker_model() -> bool

Uses ms-marco-MiniLM-L-6-v2 via ONNX Runtime (~22MB).
Falls back gracefully (returns None) when model unavailable.
"""

import logging
import os
import time as _time_module
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "cross_encoder_score",
    "get_reranker_model_info",
    "preload_reranker_model",
    "reset_reranker_state",
]

logger = logging.getLogger("omega.reranker")

# Model state (mirrors graphs.py pattern)
_RERANKER_MODEL = None  # (tokenizer, session) tuple when loaded
_LOAD_ATTEMPTED = False
_RERANKER_MODEL_DIR = None
_RERANKER_MODEL_NAME = "ms-marco-MiniLM-L-6-v2"

# Circuit breaker
_FIRST_FAILURE_TIME: float = 0.0
_CIRCUIT_BREAKER_COOLDOWN_S = 300  # 5 minutes

# Model paths
_ONNX_DEFAULT_DIR = "~/.cache/omega/models/ms-marco-MiniLM-L-6-v2-onnx"


def reset_reranker_state():
    """Reset all module state (for testing)."""
    global _RERANKER_MODEL, _LOAD_ATTEMPTED, _RERANKER_MODEL_DIR, _FIRST_FAILURE_TIME
    _RERANKER_MODEL = None
    _LOAD_ATTEMPTED = False
    _RERANKER_MODEL_DIR = None
    _FIRST_FAILURE_TIME = 0.0
    if hasattr(_get_reranker_model, "_attempt_count"):
        _get_reranker_model._attempt_count = 0


def get_reranker_model_info() -> Dict[str, Any]:
    """Return reranker model metadata."""
    return {
        "model_name": _RERANKER_MODEL_NAME,
        "available": _RERANKER_MODEL is not None,
        "model_dir": _RERANKER_MODEL_DIR,
    }


def _get_model_dir() -> Optional[str]:
    """Get ONNX model directory, checking if model exists."""
    global _RERANKER_MODEL_DIR
    if _RERANKER_MODEL_DIR is not None:
        return _RERANKER_MODEL_DIR

    # Environment override
    env_dir = os.environ.get("OMEGA_RERANKER_MODEL_DIR")
    if env_dir:
        if (Path(env_dir) / "model.onnx").exists():
            _RERANKER_MODEL_DIR = env_dir
            return _RERANKER_MODEL_DIR

    # Default location
    model_dir = Path(os.path.expanduser(_ONNX_DEFAULT_DIR))
    if (model_dir / "model.onnx").exists():
        _RERANKER_MODEL_DIR = str(model_dir)
        return _RERANKER_MODEL_DIR

    return None


def _get_reranker_model():
    """Lazy-load the cross-encoder model via ONNX Runtime."""
    global _RERANKER_MODEL, _LOAD_ATTEMPTED, _FIRST_FAILURE_TIME

    if _RERANKER_MODEL is not None:
        return _RERANKER_MODEL

    # Circuit breaker (3 attempts, 5-min cooldown)
    if not hasattr(_get_reranker_model, "_attempt_count"):
        _get_reranker_model._attempt_count = 0
    if _get_reranker_model._attempt_count >= 3:
        if _FIRST_FAILURE_TIME > 0 and (_time_module.monotonic() - _FIRST_FAILURE_TIME) >= _CIRCUIT_BREAKER_COOLDOWN_S:
            _get_reranker_model._attempt_count = 0
            _FIRST_FAILURE_TIME = 0.0
        else:
            return None
    _get_reranker_model._attempt_count += 1
    if _get_reranker_model._attempt_count == 1:
        _FIRST_FAILURE_TIME = _time_module.monotonic()

    _LOAD_ATTEMPTED = True

    if os.environ.get("OMEGA_CROSS_ENCODER", "1") == "0":
        logger.info("Cross-encoder disabled (OMEGA_CROSS_ENCODER=0)")
        return None

    model_dir = _get_model_dir()
    if not model_dir:
        logger.debug("Cross-encoder model not found at %s", _ONNX_DEFAULT_DIR)
        return None

    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer as FastTokenizer

        tokenizer = FastTokenizer.from_file(f"{model_dir}/tokenizer.json")
        tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        tokenizer.enable_truncation(max_length=512)

        sess_opts = ort.SessionOptions()
        sess_opts.log_severity_level = 4
        sess_opts.log_verbosity_level = 0
        sess_opts.enable_cpu_mem_arena = False

        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()):
            session = ort.InferenceSession(
                f"{model_dir}/model.onnx",
                sess_options=sess_opts,
                providers=["CPUExecutionProvider"],
            )

        _RERANKER_MODEL = (tokenizer, session)
        _get_reranker_model._attempt_count = 0
        _FIRST_FAILURE_TIME = 0.0
        logger.info("Loaded cross-encoder reranker model")
        return _RERANKER_MODEL
    except Exception as e:
        logger.warning("Failed to load cross-encoder model: %s", e)
        return None


def cross_encoder_score(query: str, passages: List[str]) -> Optional[List[float]]:
    """Score (query, passage) pairs using the cross-encoder.

    Returns list of relevance scores (higher = more relevant), or None if
    the model is unavailable (caller should skip reranking).
    """
    if not passages:
        return [] if os.environ.get("OMEGA_CROSS_ENCODER", "1") != "0" else None

    model = _get_reranker_model()
    if model is None:
        return None

    tokenizer, session = model
    import numpy as np

    # Tokenize as (query, passage) pairs
    encoded = tokenizer.encode_batch(
        [(query, p) for p in passages]
    )

    input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)

    # Handle token_type_ids: cross-encoders need them to distinguish query from passage
    token_type_ids = np.array([e.type_ids for e in encoded], dtype=np.int64)

    feeds = {"input_ids": input_ids, "attention_mask": attention_mask}

    # Some ONNX exports include token_type_ids, some don't
    input_names = [inp.name for inp in session.get_inputs()]
    if "token_type_ids" in input_names:
        feeds["token_type_ids"] = token_type_ids

    outputs = session.run(None, feeds)
    logits = outputs[0]  # shape: (batch_size, 1) or (batch_size,)

    # Flatten and convert to Python floats
    scores = logits.flatten().tolist()
    return scores


def preload_reranker_model() -> bool:
    """Pre-load the reranker model. Returns True if loaded successfully."""
    return _get_reranker_model() is not None
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_reranker.py -v --no-header -q`
Expected: Tests that need the model will pass if model is downloaded, or we need to handle the "model not present" case. The fallback tests should pass regardless.

Note: If the model isn't downloaded yet, `TestCrossEncoderScoring` tests will need the model. We handle this in Task 2 (model download). For now, mark model-dependent tests with `@pytest.mark.skipif` if model is absent.

### Step 5: Commit

```bash
git add src/omega/reranker.py tests/test_reranker.py
git commit -m "feat(reranker): add cross-encoder module with ONNX inference and tests"
```

---

## Task 2: Model Download Script

**Files:**
- Modify: `src/omega/reranker.py` (add `download_model` function)

### Step 1: Write failing test

Add to `tests/test_reranker.py`:

```python
class TestModelDownload:
    """Model download utility."""

    def test_download_returns_path(self, tmp_path, monkeypatch):
        """download_model writes model files to target dir."""
        from omega.reranker import download_model
        # Point to tmp dir so we don't pollute real cache
        target = str(tmp_path / "test-model")
        monkeypatch.setenv("OMEGA_RERANKER_MODEL_DIR", target)
        path = download_model(target_dir=target)
        assert path is not None
        assert (Path(path) / "model.onnx").exists()
        assert (Path(path) / "tokenizer.json").exists()
```

### Step 2: Run test to verify it fails

Run: `pytest tests/test_reranker.py::TestModelDownload -v`
Expected: FAIL with `cannot import name 'download_model'`

### Step 3: Implement download_model

Add to `src/omega/reranker.py`:

```python
def download_model(target_dir: Optional[str] = None) -> Optional[str]:
    """Download cross-encoder model from HuggingFace Hub.

    Downloads ms-marco-MiniLM-L-6-v2 ONNX files to target_dir
    (default: ~/.cache/omega/models/ms-marco-MiniLM-L-6-v2-onnx).
    Returns the directory path, or None on failure.
    """
    if target_dir is None:
        target_dir = os.path.expanduser(_ONNX_DEFAULT_DIR)

    target = Path(target_dir)
    if (target / "model.onnx").exists() and (target / "tokenizer.json").exists():
        logger.info("Cross-encoder model already exists at %s", target)
        return str(target)

    target.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download

        repo_id = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        for filename in ["model.onnx", "tokenizer.json", "config.json"]:
            try:
                downloaded = hf_hub_download(
                    repo_id=repo_id,
                    filename=f"onnx/{filename}" if filename == "model.onnx" else filename,
                    local_dir=str(target),
                    local_dir_use_symlinks=False,
                )
                # Move from subfolder to target root if needed
                src = Path(downloaded)
                dst = target / filename
                if src != dst and src.exists():
                    import shutil
                    shutil.move(str(src), str(dst))
            except Exception:
                # Try without onnx/ prefix
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=str(target),
                    local_dir_use_symlinks=False,
                )

        logger.info("Downloaded cross-encoder model to %s", target)
        return str(target)
    except ImportError:
        logger.warning("huggingface_hub not installed. Run: pip install huggingface-hub")
        return None
    except Exception as e:
        logger.warning("Failed to download cross-encoder model: %s", e)
        return None
```

### Step 4: Run test

Run: `pytest tests/test_reranker.py::TestModelDownload -v`
Expected: PASS (downloads ~22MB model to tmp dir)

### Step 5: Commit

```bash
git add src/omega/reranker.py tests/test_reranker.py
git commit -m "feat(reranker): add model download from HuggingFace Hub"
```

---

## Task 3: Integrate Cross-Encoder into SQLiteStore.query()

**Files:**
- Modify: `src/omega/sqlite_store.py` (add reranking after filters, before Phase 3)
- Modify: `tests/test_sqlite_store.py` (add integration test)

### Step 1: Write failing integration test

Add to `tests/test_sqlite_store.py`:

```python
class TestCrossEncoderReranking:
    """Cross-encoder reranking should improve result ordering."""

    def test_reranking_does_not_crash_when_disabled(self, store, monkeypatch):
        """With OMEGA_CROSS_ENCODER=0, query still works normally."""
        monkeypatch.setenv("OMEGA_CROSS_ENCODER", "0")
        store.store(content="Python is a great programming language", metadata={"event_type": "observation"})
        results = store.query("programming language", limit=5)
        assert len(results) >= 1

    def test_reranking_preserves_result_count(self, store):
        """Reranking should not change the number of results returned."""
        for i in range(5):
            store.store(content=f"Memory number {i} about different topics", metadata={"event_type": "observation"})
        results = store.query("memory topics", limit=5)
        # Should return results regardless of whether reranker is available
        assert len(results) >= 1

    def test_reranking_flag_respected(self, store, monkeypatch):
        """OMEGA_CROSS_ENCODER=0 disables reranking, =1 enables it."""
        store.store(content="The capital of France is Paris", metadata={"event_type": "observation"})
        monkeypatch.setenv("OMEGA_CROSS_ENCODER", "0")
        results_no_rerank = store.query("capital of France", limit=5)
        assert len(results_no_rerank) >= 1
```

### Step 2: Run test to verify it passes (baseline — no reranking integrated yet)

Run: `pytest tests/test_sqlite_store.py::TestCrossEncoderReranking -v`
Expected: Should fail since the class doesn't exist yet.

### Step 3: Implement reranking integration in `sqlite_store.py`

In `sqlite_store.py`, add after the project filter block (after line ~1336) and before Phase 3 (contextual re-ranking at line ~1338):

```python
        # Phase 2.7: Cross-encoder reranking (precision upgrade)
        # Rerank top candidates using (query, content) pair scoring.
        # Only runs when model is available; graceful skip otherwise.
        if node_scores and os.environ.get("OMEGA_CROSS_ENCODER", "1") != "0":
            try:
                from omega.reranker import cross_encoder_score
                # Sort by heuristic score, take top N for reranking
                _rerank_limit = 30
                sorted_for_rerank = sorted(node_scores, key=node_scores.get, reverse=True)[:_rerank_limit]
                passages = [all_results[nid].content for nid in sorted_for_rerank]
                ce_scores = cross_encoder_score(query_text, passages)
                if ce_scores is not None:
                    # Replace heuristic scores with cross-encoder scores for reranked set.
                    # Normalize CE scores to 0-1 range, then scale to preserve compatibility
                    # with downstream phases that multiply on top.
                    ce_min = min(ce_scores)
                    ce_max = max(ce_scores)
                    ce_range = ce_max - ce_min if ce_max > ce_min else 1.0
                    for nid, ce_score in zip(sorted_for_rerank, ce_scores):
                        normalized = (ce_score - ce_min) / ce_range  # 0 to 1
                        node_scores[nid] = 0.1 + normalized * 0.9  # floor at 0.1
            except Exception as e:
                logger.debug("Cross-encoder reranking skipped: %s", e)
```

Also add `import os` at the top of sqlite_store.py if not already present.

### Step 4: Run tests

Run: `pytest tests/test_sqlite_store.py::TestCrossEncoderReranking -v`
Expected: PASS

Run: `pytest tests/test_sqlite_store.py -v --no-header -q 2>&1 | tail -5`
Expected: All existing tests still pass (no regressions)

### Step 5: Commit

```bash
git add src/omega/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat(query): integrate cross-encoder reranking into retrieval pipeline"
```

---

## Task 4: Contradiction Detection — Pure Function

**Files:**
- Create: `tests/test_contradiction.py`
- Modify: `src/omega/sqlite_store.py` (add `_detect_correction` method)

### Step 1: Write failing tests

```python
# tests/test_contradiction.py
"""Tests for contradiction detection at store time."""
import pytest


class TestCorrectionSignalDetection:
    """Heuristic detection of correction/update signals in new content."""

    def test_explicit_switch_detected(self, store):
        """'I switched from X to Y' is detected as a correction."""
        from omega.sqlite_store import SQLiteStore
        assert store._detect_correction(
            new_content="I actually switched from React to Svelte for the frontend",
            old_content="I'm using React for the frontend project",
            new_meta={"event_type": "user_preference"},
            old_meta={"event_type": "user_preference"},
        ) is True

    def test_now_using_detected(self, store):
        """'now using X' is detected as a correction."""
        assert store._detect_correction(
            new_content="I'm now using VS Code instead of Sublime",
            old_content="My editor of choice is Sublime Text",
            new_meta={"event_type": "user_preference"},
            old_meta={"event_type": "user_preference"},
        ) is True

    def test_no_longer_detected(self, store):
        """'no longer' signals a correction."""
        assert store._detect_correction(
            new_content="I no longer use Docker for local development",
            old_content="I use Docker for all my local development work",
            new_meta={"event_type": "decision"},
            old_meta={"event_type": "decision"},
        ) is True

    def test_additive_not_detected(self, store):
        """'I also use X' is additive, not a correction."""
        assert store._detect_correction(
            new_content="I also use TypeScript for some backend services",
            old_content="I use Python for backend development",
            new_meta={"event_type": "observation"},
            old_meta={"event_type": "observation"},
        ) is False

    def test_unrelated_not_detected(self, store):
        """Unrelated content is not a correction."""
        assert store._detect_correction(
            new_content="Had a great meeting with the design team today",
            old_content="I prefer using dark mode in all my editors",
            new_meta={"event_type": "observation"},
            old_meta={"event_type": "user_preference"},
        ) is False

    def test_same_type_preference_with_signal(self, store):
        """Same event_type + correction signal = correction."""
        assert store._detect_correction(
            new_content="Updated my preference: use tabs instead of spaces",
            old_content="I prefer spaces over tabs in all code",
            new_meta={"event_type": "user_preference", "tags": ["coding-style"]},
            old_meta={"event_type": "user_preference", "tags": ["coding-style"]},
        ) is True

    def test_disabled_via_env(self, store, monkeypatch):
        """OMEGA_CONTRADICTION_DETECT=0 disables detection."""
        monkeypatch.setenv("OMEGA_CONTRADICTION_DETECT", "0")
        assert store._detect_correction(
            new_content="I actually switched to Vim",
            old_content="I use VS Code for everything",
            new_meta={"event_type": "user_preference"},
            old_meta={"event_type": "user_preference"},
        ) is False
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_contradiction.py -v`
Expected: FAIL with `AttributeError: 'SQLiteStore' object has no attribute '_detect_correction'`

### Step 3: Implement `_detect_correction` on SQLiteStore

Add to `src/omega/sqlite_store.py` (as a method on `SQLiteStore`, near other private methods):

```python
    # Contradiction detection signals
    _CORRECTION_SIGNALS = frozenset({
        "actually", "changed", "updated", "switched", "no longer",
        "instead", "corrected", "now using", "replaced", "moved to",
        "not anymore", "stopped using", "deprecated",
    })

    # Event types eligible for contradiction detection
    _CORRECTABLE_TYPES = frozenset({"user_preference", "decision", "lesson_learned"})

    def _detect_correction(
        self,
        new_content: str,
        old_content: str,
        new_meta: dict,
        old_meta: dict,
    ) -> bool:
        """Detect if new content is a correction/update of old content.

        Uses fast heuristics (no LLM). Returns True if the new content
        likely supersedes the old content.
        """
        if os.environ.get("OMEGA_CONTRADICTION_DETECT", "1") == "0":
            return False

        new_lower = new_content.lower()

        # Signal 1: Explicit correction language in new content
        has_signal = any(signal in new_lower for signal in self._CORRECTION_SIGNALS)
        if not has_signal:
            return False

        # Signal 2: Same correctable event type (preferences, decisions, lessons)
        new_type = new_meta.get("event_type", "")
        old_type = old_meta.get("event_type", "")
        if new_type in self._CORRECTABLE_TYPES and new_type == old_type:
            return True

        # Signal 3: Overlapping tags suggest same topic
        new_tags = set(new_meta.get("tags") or [])
        old_tags = set(old_meta.get("tags") or [])
        if new_tags and old_tags and new_tags & old_tags:
            return True

        # Signal 4: Same entity_id suggests same scope
        new_entity = new_meta.get("entity_id")
        old_entity = old_meta.get("entity_id")
        if new_entity and new_entity == old_entity and has_signal:
            return True

        return False
```

### Step 4: Run tests

Run: `pytest tests/test_contradiction.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/omega/sqlite_store.py tests/test_contradiction.py
git commit -m "feat(store): add contradiction detection heuristic (_detect_correction)"
```

---

## Task 5: Integrate Contradiction Detection into store()

**Files:**
- Modify: `src/omega/sqlite_store.py` (add contradiction check in store path)
- Add to: `tests/test_contradiction.py` (end-to-end integration tests)

### Step 1: Write failing integration tests

Add to `tests/test_contradiction.py`:

```python
class TestContradictionStoreIntegration:
    """End-to-end: storing a correction auto-supersedes the old memory."""

    def test_correction_supersedes_old_memory(self, store):
        """Storing a correction marks the old memory as superseded."""
        old_id = store.store(
            content="I use React for all my frontend projects",
            metadata={"event_type": "user_preference", "tags": ["frontend"]},
        )
        new_id = store.store(
            content="I actually switched from React to Svelte for frontend work",
            metadata={"event_type": "user_preference", "tags": ["frontend"]},
        )
        assert old_id != new_id  # Not deduped
        old_node = store.get_node(old_id)
        assert old_node.metadata.get("superseded") is True
        assert old_node.metadata.get("superseded_by") == new_id

    def test_correction_creates_supersedes_edge(self, store):
        """A 'supersedes' edge is created from new to old."""
        old_id = store.store(
            content="My preferred database is PostgreSQL",
            metadata={"event_type": "decision", "tags": ["database"]},
        )
        new_id = store.store(
            content="I've switched from PostgreSQL to SQLite for this project",
            metadata={"event_type": "decision", "tags": ["database"]},
        )
        edges = store._conn.execute(
            "SELECT source_id, target_id, edge_type FROM edges WHERE source_id = ? AND target_id = ?",
            (new_id, old_id),
        ).fetchall()
        assert len(edges) == 1
        assert edges[0][2] == "supersedes"

    def test_superseded_memory_excluded_from_query(self, store):
        """Superseded memories should not appear in query results."""
        old_id = store.store(
            content="I always deploy to AWS for production workloads",
            metadata={"event_type": "decision", "tags": ["infrastructure"]},
        )
        new_id = store.store(
            content="I've switched from AWS to Vercel for all deployments now",
            metadata={"event_type": "decision", "tags": ["infrastructure"]},
        )
        results = store.query("where do I deploy", limit=10)
        result_ids = [r.id for r in results]
        assert new_id in result_ids
        assert old_id not in result_ids

    def test_additive_does_not_supersede(self, store):
        """Non-correction similar content stores normally without superseding."""
        first_id = store.store(
            content="I enjoy hiking in the mountains on weekends",
            metadata={"event_type": "observation", "tags": ["hobbies"]},
        )
        second_id = store.store(
            content="I went hiking with friends this past weekend in the mountains",
            metadata={"event_type": "observation", "tags": ["hobbies"]},
        )
        # Neither should be superseded (additive, not correction)
        first_node = store.get_node(first_id)
        assert first_node.metadata.get("superseded") is not True

    def test_new_memory_has_supersedes_metadata(self, store):
        """The new memory records which memory it superseded."""
        old_id = store.store(
            content="I use vim as my primary editor",
            metadata={"event_type": "user_preference"},
        )
        new_id = store.store(
            content="I've now switched from vim to neovim as my editor",
            metadata={"event_type": "user_preference"},
        )
        new_node = store.get_node(new_id)
        assert new_node.metadata.get("supersedes") == old_id
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_contradiction.py::TestContradictionStoreIntegration -v`
Expected: FAIL (store doesn't do contradiction check yet)

### Step 3: Implement contradiction check in store()

In `src/omega/sqlite_store.py`, modify the `store()` method. After the embedding dedup check (line ~816) and before generating the node_id (line ~818), add the contradiction zone:

```python
            # Contradiction detection: similarity 0.55-0.88 zone
            # Check if new content corrects/updates an existing memory
            if (embedding and not skip_inference and self._vec_available
                    and os.environ.get("OMEGA_CONTRADICTION_DETECT", "1") != "0"):
                try:
                    similar = self._vec_query(embedding, limit=3)
                    for sim_rowid, sim_distance in similar:
                        sim_similarity = 1.0 - sim_distance
                        if sim_similarity < 0.55 or sim_similarity >= self.DEFAULT_EMBEDDING_DEDUP_THRESHOLD:
                            continue  # Outside contradiction zone
                        sim_row = self._conn.execute(
                            "SELECT node_id, content, metadata FROM memories WHERE id = ?",
                            (sim_rowid,),
                        ).fetchone()
                        if not sim_row:
                            continue
                        old_node_id = sim_row[0]
                        old_content = sim_row[1]
                        old_meta = json.loads(sim_row[2]) if sim_row[2] else {}
                        if old_meta.get("superseded"):
                            continue  # Already superseded
                        if self._detect_correction(content, old_content, meta, old_meta):
                            # Mark old memory as superseded (will be applied after INSERT below)
                            self._pending_supersede = (old_node_id, old_meta)
                            meta["supersedes"] = old_node_id
                            break  # Only supersede one memory per store
                except Exception as e:
                    logger.debug("Contradiction detection failed: %s", e)
```

Then, after the INSERT and edge creation (after line ~880, before `self._commit()`), add:

```python
            # Apply pending supersession from contradiction detection
            if hasattr(self, "_pending_supersede") and self._pending_supersede:
                old_nid, old_meta = self._pending_supersede
                old_meta["superseded"] = True
                old_meta["superseded_by"] = node_id
                self._conn.execute(
                    "UPDATE memories SET metadata = ? WHERE node_id = ?",
                    (json.dumps(old_meta), old_nid),
                )
                self._conn.execute(
                    """INSERT INTO edges (source_id, target_id, edge_type, created_at)
                       VALUES (?, ?, 'supersedes', ?)""",
                    (node_id, old_nid, now),
                )
                self._pending_supersede = None
                self.stats.setdefault("contradictions_detected", 0)
                self.stats["contradictions_detected"] += 1
```

### Step 4: Run tests

Run: `pytest tests/test_contradiction.py -v`
Expected: PASS

Run: `pytest tests/test_sqlite_store.py -v --no-header -q 2>&1 | tail -5`
Expected: All existing tests still pass

### Step 5: Commit

```bash
git add src/omega/sqlite_store.py tests/test_contradiction.py
git commit -m "feat(store): integrate contradiction detection into store pipeline"
```

---

## Task 6: Full Regression Test + Cleanup

**Files:**
- All modified files

### Step 1: Run full test suite

Run: `pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: All ~1984 tests pass, no regressions.

### Step 2: Run linter

Run: `ruff check src/omega/reranker.py src/omega/sqlite_store.py`
Expected: Clean (or fix any issues).

### Step 3: Verify the model download works

Run: `python3 -c "from omega.reranker import download_model; print(download_model())"`
Expected: Prints model path (downloads ~22MB on first run).

### Step 4: Quick manual smoke test

Run: `python3 -c "
from omega.reranker import cross_encoder_score
scores = cross_encoder_score('What programming language do you use?', [
    'I use Python for data science',
    'The weather is nice today',
    'JavaScript is used for web development',
])
print('Scores:', scores)
print('Best:', ['Python', 'weather', 'JavaScript'][scores.index(max(scores))])
"`
Expected: Python and JavaScript score higher than weather.

### Step 5: Final commit with all files

```bash
git add src/omega/reranker.py src/omega/sqlite_store.py tests/test_reranker.py tests/test_contradiction.py tests/test_sqlite_store.py
git commit -m "feat: cross-encoder reranking + contradiction detection for retrieval quality

Cross-encoder reranker (ms-marco-MiniLM-L-6-v2 via ONNX) reranks top 30
candidates after initial retrieval for better precision. Contradiction
detection at store time auto-supersedes outdated memories when correction
signals are detected in the 0.55-0.88 similarity zone.

Both features behind env-var flags (OMEGA_CROSS_ENCODER, OMEGA_CONTRADICTION_DETECT).
No schema migration required."
```

---

## Summary

| Task | Description | Files | Est. |
|------|-------------|-------|------|
| 1 | Cross-encoder module + tests | `reranker.py`, `test_reranker.py` | 15 min |
| 2 | Model download utility | `reranker.py`, `test_reranker.py` | 10 min |
| 3 | Integrate reranking into query() | `sqlite_store.py`, `test_sqlite_store.py` | 10 min |
| 4 | Contradiction detection function | `sqlite_store.py`, `test_contradiction.py` | 10 min |
| 5 | Integrate contradiction into store() | `sqlite_store.py`, `test_contradiction.py` | 15 min |
| 6 | Regression test + cleanup | All files | 10 min |
