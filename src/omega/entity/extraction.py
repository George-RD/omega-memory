"""OMEGA Entity Extraction -- Automatic NER via Claude Haiku.

Extracts named entities (people, projects, technologies, etc.) and their
relationships from memory content using Claude Haiku, then resolves and
links them into the entity graph.

Internal module -- not exported from entity/__init__.py.
"""

import json
import logging
import os
import re
import threading
import time

from omega.entity.engine import ENTITY_TYPES, RELATIONSHIP_TYPES
from omega.llm import llm_complete

logger = logging.getLogger("omega.entity.extraction")

# Empty result constant
def _empty() -> dict:
    """Return a fresh empty extraction result dict."""
    return {"entities": [], "relationships": []}

# Event types to skip (high-volume, low-signal for NER)
_SKIP_EVENT_TYPES = frozenset({
    "file_summary",
    "code_chunk",
    "branch_switch",
    "session_respawn",
    "session_summary",
})

# Throttle: max 1 Haiku call per 2 seconds
_throttle_lock = threading.Lock()
_last_call_ts: float = 0.0
_THROTTLE_INTERVAL_S = 2.0

# NER system prompt
_NER_SYSTEM_PROMPT = (
    "Extract named entities and relationships from this developer memory/note. "
    "Return JSON with two arrays:\n"
    '- "entities": objects with "name" (string) and "type" (one of: person, project, '
    "tool, concept, technology, service, company)\n"
    '- "relationships": objects with "source" (entity name), "target" (entity name), '
    'and "type" (one of: uses, works_on, depends_on, mentions, created_by)\n\n'
    "Only extract clearly named entities. Output ONLY valid JSON, no explanation."
)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _validate_extraction(raw: dict) -> dict:
    """Filter extraction result to entries with required fields."""
    entities = []
    for e in raw.get("entities", []):
        if isinstance(e, dict) and "name" in e and "type" in e:
            entities.append({"name": e["name"], "type": e["type"]})

    relationships = []
    for r in raw.get("relationships", []):
        if isinstance(r, dict) and "source" in r and "target" in r and "type" in r:
            relationships.append({
                "source": r["source"],
                "target": r["target"],
                "type": r["type"],
            })

    return {"entities": entities, "relationships": relationships}


def extract_entities(content: str, event_type: str) -> dict:
    """Extract named entities from memory content using Claude Haiku.

    Returns:
        {"entities": [{"name": str, "type": str}],
         "relationships": [{"source": str, "target": str, "type": str}]}

    Returns empty result on any failure (API error, timeout, bad JSON, etc.).
    """
    global _last_call_ts

    # Skip conditions
    if os.environ.get("OMEGA_ENTITY_EXTRACTION") == "0":
        return _empty()

    if event_type in _SKIP_EVENT_TYPES:
        return _empty()

    if len(content) < 20:
        return _empty()

    # Throttle: max 1 call per 2 seconds
    with _throttle_lock:
        now = time.monotonic()
        if now - _last_call_ts < _THROTTLE_INTERVAL_S:
            return _empty()
        _last_call_ts = now

    try:
        raw_text = llm_complete(
            content[:1000],
            _NER_SYSTEM_PROMPT,
            max_tokens=512,
            timeout=3.0,
        )
        if not raw_text:
            return _empty()

        cleaned = _strip_code_fences(raw_text)
        parsed = json.loads(cleaned)

        if not isinstance(parsed, dict):
            return _empty()

        return _validate_extraction(parsed)

    except Exception as e:
        logger.debug("Entity extraction failed: %s", e)
        return _empty()


# ---------------------------------------------------------------------------
# Slugify helper
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert entity name to a lowercase URL-safe entity_id.

    Example: "React.js" -> "react-js", "Jason Sosa" -> "jason-sosa"
    """
    slug = name.lower().strip()
    # Replace non-alphanumeric chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return slug or "unnamed"


# ---------------------------------------------------------------------------
# resolve_and_link()
# ---------------------------------------------------------------------------

def resolve_and_link(
    store,
    em,
    node_id: str,
    extraction: dict,
) -> dict:
    """Resolve extracted entities, dedup against existing, and link to memory.

    Args:
        store: SQLiteStore instance (for updating memory entity_id)
        em: EntityManager instance
        node_id: The memory node_id to link
        extraction: Output from extract_entities()

    Returns:
        {"entities_created": int, "entities_linked": int, "relationships_created": int}
    """
    result = {
        "entities_created": 0,
        "entities_linked": 0,
        "relationships_created": 0,
    }

    entities = extraction.get("entities", [])
    relationships = extraction.get("relationships", [])

    if not entities and not relationships:
        return result

    # Build name -> entity_id mapping for existing entities
    existing_entities = em.list_entity_ids()  # list of (entity_id, name)
    name_to_id: dict[str, str] = {}
    for eid, ename in existing_entities:
        name_to_id[ename.lower()] = eid

    # Resolve each extracted entity: match existing or create new
    extracted_name_to_id: dict[str, str] = {}

    for ent in entities:
        name = ent.get("name", "").strip()
        etype = ent.get("type", "").strip().lower()

        if not name or etype not in ENTITY_TYPES:
            continue

        lower_name = name.lower()

        if lower_name in name_to_id:
            # Match existing entity
            extracted_name_to_id[lower_name] = name_to_id[lower_name]
        else:
            # Create new entity
            entity_id = _slugify(name)
            create_result = em.create_entity(entity_id, name, etype)
            if "Created entity" in create_result:
                extracted_name_to_id[lower_name] = entity_id
                name_to_id[lower_name] = entity_id
                result["entities_created"] += 1
            elif "already exists" in create_result:
                # Race condition or slug collision: check name match
                existing_entity = em.get_entity(entity_id)
                if existing_entity and name.lower() not in existing_entity.lower():
                    # Slug collision: different entity has this id — try numeric suffixes
                    for suffix in range(2, 10):
                        alt_id = f"{entity_id}-{suffix}"
                        alt_result = em.create_entity(alt_id, name, etype)
                        if "Created entity" in alt_result:
                            entity_id = alt_id
                            result["entities_created"] += 1
                            name_to_id[lower_name] = entity_id
                            break
                extracted_name_to_id[lower_name] = entity_id
            else:
                logger.debug("Failed to create entity %s: %s", entity_id, create_result)

    # Link memory to first extracted entity (if memory doesn't already have one)
    if extracted_name_to_id:
        first_entity_id = next(iter(extracted_name_to_id.values()))
        try:
            # Check if memory already has an entity_id
            row = store._exec(
                "SELECT entity_id FROM memories WHERE node_id = ?",
                (node_id,),
            ).fetchone()
            if row and not row[0]:
                store._exec(
                    "UPDATE memories SET entity_id = ? WHERE node_id = ? AND (entity_id IS NULL OR entity_id = '')",
                    (first_entity_id, node_id),
                )
                store._commit()
                result["entities_linked"] = 1
        except Exception as e:
            logger.debug("Failed to link entity to memory: %s", e)

    # Create relationships between resolved entity pairs
    for rel in relationships:
        source_name = rel.get("source", "").lower()
        target_name = rel.get("target", "").lower()
        rel_type = rel.get("type", "").strip().lower()

        source_id = extracted_name_to_id.get(source_name)
        target_id = extracted_name_to_id.get(target_name)

        if not source_id or not target_id:
            continue
        if source_id == target_id:
            continue
        if rel_type not in RELATIONSHIP_TYPES:
            continue

        add_result = em.add_relationship(source_id, target_id, rel_type)
        if "Added relationship" in add_result:
            result["relationships_created"] += 1

    return result
