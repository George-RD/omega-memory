"""
OMEGA Intent Classifier -- Sub-millisecond task classification.

Uses OMEGA's ONNX embedding backend (bge-small-en-v1.5) with prototype-based
cosine similarity for <1ms intent classification.

Extracted from Gnosis gnosis_intent_classifier.py, adapted for OMEGA.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Cache prototypes in OMEGA's data directory
OMEGA_DIR = Path.home() / ".omega"
PROTOTYPE_CACHE_PATH = OMEGA_DIR / "intent-prototypes.json"

# Intent definitions with example phrases for prototype building
INTENT_DEFINITIONS = {
    "coding": {
        "description": "Writing, debugging, or modifying code",
        "examples": [
            "write a python function",
            "fix this bug",
            "implement the feature",
            "refactor this code",
            "debug the error",
            "create a class",
            "add error handling",
            "write unit tests",
            "optimize this algorithm",
            "parse the JSON",
        ],
    },
    "creative": {
        "description": "Creative writing, drafting, brainstorming",
        "examples": [
            "write a story",
            "draft an email",
            "brainstorm ideas",
            "write a poem",
            "create a marketing copy",
            "write documentation",
            "compose a message",
            "help me write",
            "creative writing",
            "write a blog post",
        ],
    },
    "logic": {
        "description": "Complex reasoning, architecture, analysis",
        "examples": [
            "analyze this problem",
            "design the architecture",
            "reason about this",
            "plan the implementation",
            "evaluate the tradeoffs",
            "strategic decision",
            "solve this puzzle",
            "compare these approaches",
            "think through this",
            "architectural decision",
        ],
    },
    "exploration": {
        "description": "Searching, finding, researching",
        "examples": [
            "search for files",
            "find where this is defined",
            "what is this function",
            "explain how this works",
            "research this topic",
            "look up documentation",
            "grep for usage",
            "explore the codebase",
            "list all files",
            "where is the config",
        ],
    },
    "simple_edit": {
        "description": "Trivial changes, typos, formatting",
        "examples": [
            "fix the typo",
            "rename this variable",
            "add a comment",
            "format this code",
            "update the import",
            "change the name",
            "remove unused code",
            "add a blank line",
            "fix indentation",
            "update the version",
        ],
    },
}


# ============================================================================
# Embedding Backend (uses OMEGA's ONNX model)
# ============================================================================


def _compute_embedding(text: str) -> list:
    """Compute embedding for a single text using OMEGA's ONNX backend."""
    from omega.embedding import generate_embedding

    return generate_embedding(text)


def _compute_embeddings(texts: List[str]) -> List[list]:
    """Compute embeddings for multiple texts."""
    return [_compute_embedding(t) for t in texts]


def _cosine_similarity(vec1: list, vec2: list) -> float:
    """Compute cosine similarity between two vectors."""
    v1, v2 = np.array(vec1), np.array(vec2)
    norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ClassificationResult:
    """Result of intent classification."""

    intent: str
    confidence: float
    all_scores: Dict[str, float]
    latency_ms: float


# ============================================================================
# Intent Classifier
# ============================================================================


class IntentClassifier:
    """
    Sub-millisecond intent classifier using embedding prototypes.

    How it works:
    1. Pre-compute prototype vectors for each intent (average of examples)
    2. At query time, embed the query and compute cosine similarity
    3. Return the intent with highest similarity

    Typical latency: 0.5-2ms (embedding) + <0.1ms (similarity)
    """

    def __init__(self, use_cache: bool = True):
        self.prototypes: Dict[str, list] = {}
        self.use_cache = use_cache
        self._loaded = False

    def _load_or_build_prototypes(self):
        """Load prototypes from cache or build them."""
        if self._loaded:
            return

        if self.use_cache and PROTOTYPE_CACHE_PATH.exists():
            try:
                cached = json.loads(PROTOTYPE_CACHE_PATH.read_text())
                if set(cached.keys()) == set(INTENT_DEFINITIONS.keys()):
                    self.prototypes = cached
                    self._loaded = True
                    return
            except Exception:
                pass

        self._build_prototypes()

        if self.use_cache:
            try:
                OMEGA_DIR.mkdir(parents=True, exist_ok=True)
                PROTOTYPE_CACHE_PATH.write_text(json.dumps(self.prototypes))
            except Exception:
                pass

        self._loaded = True

    def _build_prototypes(self):
        """Build prototype vectors for each intent."""
        for intent, definition in INTENT_DEFINITIONS.items():
            examples = definition["examples"]
            embeddings = _compute_embeddings(examples)
            prototype = np.mean(embeddings, axis=0).tolist()
            self.prototypes[intent] = prototype

    def classify(self, query: str) -> ClassificationResult:
        """Classify a query into an intent."""
        start = time.perf_counter()
        self._load_or_build_prototypes()

        query_vec = _compute_embedding(query)

        scores = {}
        for intent, prototype in self.prototypes.items():
            scores[intent] = _cosine_similarity(query_vec, prototype)

        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]
        latency_ms = (time.perf_counter() - start) * 1000

        return ClassificationResult(
            intent=best_intent,
            confidence=best_score,
            all_scores=scores,
            latency_ms=latency_ms,
        )

    def classify_batch(self, queries: List[str]) -> List[ClassificationResult]:
        """Classify multiple queries."""
        return [self.classify(q) for q in queries]

    def add_example(self, intent: str, example: str):
        """Add a new example to an intent (rebuilds prototype)."""
        if intent not in INTENT_DEFINITIONS:
            raise ValueError(f"Unknown intent: {intent}")
        INTENT_DEFINITIONS[intent]["examples"].append(example)
        self._loaded = False
        self._load_or_build_prototypes()


# ============================================================================
# Singleton & Convenience Functions
# ============================================================================

_classifier: Optional[IntentClassifier] = None
_classifier_lock = __import__("threading").Lock()


def get_classifier() -> IntentClassifier:
    """Get the singleton classifier instance (thread-safe)."""
    global _classifier
    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                _classifier = IntentClassifier()
    return _classifier


def classify_intent(query: str) -> Tuple[str, float]:
    """Convenience: classify a query, return (intent, confidence)."""
    result = get_classifier().classify(query)
    return result.intent, result.confidence


def classify_intent_detailed(query: str) -> Dict:
    """Classify with full details."""
    result = get_classifier().classify(query)
    return {
        "intent": result.intent,
        "confidence": result.confidence,
        "all_scores": result.all_scores,
        "latency_ms": result.latency_ms,
    }


def warm_up():
    """Pre-load the model and prototypes."""
    get_classifier()._load_or_build_prototypes()


# ============================================================================
# Keyword Fallback (No ML Dependencies)
# ============================================================================

KEYWORD_PATTERNS = {
    "coding": [
        "code",
        "function",
        "class",
        "bug",
        "fix",
        "implement",
        "debug",
        "test",
        "refactor",
        "algorithm",
        "parse",
        "compile",
        "error",
    ],
    "creative": [
        "write",
        "draft",
        "story",
        "email",
        "brainstorm",
        "creative",
        "poem",
        "blog",
        "article",
        "compose",
        "message",
    ],
    "logic": [
        "analyze",
        "design",
        "architect",
        "reason",
        "plan",
        "evaluate",
        "strategic",
        "compare",
        "tradeoff",
        "decision",
    ],
    "exploration": [
        "search",
        "find",
        "where",
        "what",
        "explain",
        "look up",
        "grep",
        "explore",
        "list",
        "documentation",
    ],
    "simple_edit": [
        "typo",
        "rename",
        "comment",
        "format",
        "indent",
        "import",
        "remove",
        "update",
        "change name",
        "blank line",
    ],
}


def classify_intent_keywords(query: str) -> Tuple[str, float]:
    """Fallback classifier using keywords (no ML dependencies)."""
    query_lower = query.lower()
    scores = {}

    for intent, keywords in KEYWORD_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        scores[intent] = score

    total = sum(scores.values())
    if total == 0:
        return "coding", 0.5

    best_intent = max(scores, key=scores.get)
    raw_confidence = scores[best_intent] / total
    # Scale to 0.4-0.85 range: keyword matching alone shouldn't claim high confidence.
    confidence = 0.4 + raw_confidence * 0.45
    return best_intent, confidence
