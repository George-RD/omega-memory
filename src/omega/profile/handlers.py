"""OMEGA Secure Profile Handlers -- MCP handlers for encrypted personal data."""

import logging
from typing import Any, Dict

logger = logging.getLogger("omega.profile.handlers")


from omega.server.responses import mcp_response, mcp_error


async def handle_omega_profile_set(arguments: dict) -> dict:
    """Encrypt and store a profile field."""
    category = arguments.get("category", "").strip()
    field_name = arguments.get("field_name", "").strip()
    value = arguments.get("value", "").strip()
    metadata = arguments.get("metadata")
    entity_id = arguments.get("entity_id", "__personal__")

    if not category:
        return mcp_error("category is required")
    if not field_name:
        return mcp_error("field_name is required")
    if not value:
        return mcp_error("value is required")

    try:
        from omega.profile.engine import profile_set

        result = profile_set(category, field_name, value, metadata, entity_id)
        return mcp_response(result)
    except ImportError:
        return mcp_error("cryptography package not installed. Run: pip install 'omega-memory[encrypt]'")
    except Exception as e:
        logger.error("omega_profile_set failed: %s", e)
        return mcp_error(f"Failed to store profile field: {e}")


async def handle_omega_profile_get(arguments: dict) -> dict:
    """Decrypt and retrieve profile field(s)."""
    category = arguments.get("category", "").strip()
    field_name = arguments.get("field_name", "").strip() or None
    entity_id = arguments.get("entity_id", "__personal__")

    if not category:
        return mcp_error("category is required")

    try:
        from omega.profile.engine import profile_get

        result = profile_get(category, field_name, entity_id)
        return mcp_response(result)
    except ImportError:
        return mcp_error("cryptography package not installed. Run: pip install 'omega-memory[encrypt]'")
    except Exception as e:
        logger.error("omega_profile_get failed: %s", e)
        return mcp_error(f"Failed to retrieve profile field: {e}")


async def handle_omega_profile_search(arguments: dict) -> dict:
    """Search profile by field name/category/metadata."""
    query = arguments.get("query", "").strip()
    entity_id = arguments.get("entity_id")

    if not query:
        return mcp_error("query is required")

    try:
        from omega.profile.engine import profile_search

        result = profile_search(query, entity_id)
        return mcp_response(result)
    except ImportError:
        return mcp_error("cryptography package not installed. Run: pip install 'omega-memory[encrypt]'")
    except Exception as e:
        logger.error("omega_profile_search failed: %s", e)
        return mcp_error(f"Failed to search profile: {e}")


async def handle_omega_profile_list(arguments: dict) -> dict:
    """List all profile categories with field counts."""
    entity_id = arguments.get("entity_id")

    try:
        from omega.profile.engine import profile_list_categories

        result = profile_list_categories(entity_id=entity_id)
        return mcp_response(result)
    except ImportError:
        return mcp_error("cryptography package not installed. Run: pip install 'omega-memory[encrypt]'")
    except Exception as e:
        logger.error("omega_profile_list failed: %s", e)
        return mcp_error(f"Failed to list profile categories: {e}")


PROFILE_HANDLERS: Dict[str, Any] = {
    "omega_profile_set": handle_omega_profile_set,
    "omega_profile_get": handle_omega_profile_get,
    "omega_profile_search": handle_omega_profile_search,
    "omega_profile_list": handle_omega_profile_list,
}
