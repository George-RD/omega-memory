"""OMEGA Entity Handlers -- MCP handlers for multi-entity corporate memory."""

import logging
from typing import Any, Dict

logger = logging.getLogger("omega.entity.handlers")


from omega.server.responses import mcp_response, mcp_error


async def handle_omega_entity_create(arguments: dict) -> dict:
    """Create a new entity."""
    entity_id = arguments.get("entity_id", "").strip()
    name = arguments.get("name", "").strip()
    entity_type = arguments.get("entity_type", "").strip()

    if not entity_id:
        return mcp_error("entity_id is required")
    if not name:
        return mcp_error("name is required")
    if not entity_type:
        return mcp_error("entity_type is required")

    jurisdiction = arguments.get("jurisdiction")
    metadata = arguments.get("metadata")

    try:
        from omega.entity.engine import entity_create

        result = entity_create(entity_id, name, entity_type, jurisdiction, metadata)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_entity_create failed: %s", e)
        return mcp_error(f"Failed to create entity: {e}")


async def handle_omega_entity_get(arguments: dict) -> dict:
    """Get entity details."""
    entity_id = arguments.get("entity_id", "").strip()
    if not entity_id:
        return mcp_error("entity_id is required")

    try:
        from omega.entity.engine import entity_get

        result = entity_get(entity_id)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_entity_get failed: %s", e)
        return mcp_error(f"Failed to get entity: {e}")


async def handle_omega_entity_list(arguments: dict) -> dict:
    """List entities."""
    entity_type = arguments.get("entity_type")
    status = arguments.get("status")

    try:
        from omega.entity.engine import entity_list

        result = entity_list(entity_type, status)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_entity_list failed: %s", e)
        return mcp_error(f"Failed to list entities: {e}")


async def handle_omega_entity_update(arguments: dict) -> dict:
    """Update entity fields."""
    entity_id = arguments.get("entity_id", "").strip()
    if not entity_id:
        return mcp_error("entity_id is required")

    name = arguments.get("name")
    status = arguments.get("status")
    jurisdiction = arguments.get("jurisdiction")
    metadata = arguments.get("metadata")

    try:
        from omega.entity.engine import entity_update

        result = entity_update(entity_id, name, status, jurisdiction, metadata)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_entity_update failed: %s", e)
        return mcp_error(f"Failed to update entity: {e}")


async def handle_omega_entity_delete(arguments: dict) -> dict:
    """Soft-delete an entity."""
    entity_id = arguments.get("entity_id", "").strip()
    if not entity_id:
        return mcp_error("entity_id is required")

    try:
        from omega.entity.engine import entity_delete

        result = entity_delete(entity_id)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_entity_delete failed: %s", e)
        return mcp_error(f"Failed to delete entity: {e}")


async def handle_omega_entity_add_relationship(arguments: dict) -> dict:
    """Add a relationship between entities."""
    source = arguments.get("source_entity_id", "").strip()
    target = arguments.get("target_entity_id", "").strip()
    rel_type = arguments.get("relationship_type", "").strip()

    if not source:
        return mcp_error("source_entity_id is required")
    if not target:
        return mcp_error("target_entity_id is required")
    if not rel_type:
        return mcp_error("relationship_type is required")

    metadata = arguments.get("metadata")

    try:
        from omega.entity.engine import entity_add_relationship

        result = entity_add_relationship(source, target, rel_type, metadata)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_entity_add_relationship failed: %s", e)
        return mcp_error(f"Failed to add relationship: {e}")


async def handle_omega_entity_relationships(arguments: dict) -> dict:
    """Get relationships for an entity."""
    entity_id = arguments.get("entity_id", "").strip()
    if not entity_id:
        return mcp_error("entity_id is required")

    direction = arguments.get("direction")
    relationship_type = arguments.get("relationship_type")

    try:
        from omega.entity.engine import entity_relationships

        result = entity_relationships(entity_id, direction, relationship_type)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_entity_relationships failed: %s", e)
        return mcp_error(f"Failed to get relationships: {e}")


async def handle_omega_entity_tree(arguments: dict) -> dict:
    """Get entity hierarchy tree."""
    entity_id = arguments.get("entity_id", "").strip()
    if not entity_id:
        return mcp_error("entity_id is required")

    try:
        from omega.entity.engine import entity_tree

        result = entity_tree(entity_id)
        return mcp_response(result)
    except Exception as e:
        logger.error("omega_entity_tree failed: %s", e)
        return mcp_error(f"Failed to get entity tree: {e}")


ENTITY_HANDLERS: Dict[str, Any] = {
    "omega_entity_create": handle_omega_entity_create,
    "omega_entity_get": handle_omega_entity_get,
    "omega_entity_list": handle_omega_entity_list,
    "omega_entity_update": handle_omega_entity_update,
    "omega_entity_delete": handle_omega_entity_delete,
    "omega_entity_add_relationship": handle_omega_entity_add_relationship,
    "omega_entity_relationships": handle_omega_entity_relationships,
    "omega_entity_tree": handle_omega_entity_tree,
}
