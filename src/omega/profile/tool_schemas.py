"""OMEGA Secure Profile Tool Schemas -- 4 tools for encrypted personal data."""

PROFILE_TOOL_SCHEMAS = [
    {
        "name": "omega_profile_set",
        "description": (
            "Store an encrypted personal profile field. Data is AES-256 encrypted before storage "
            "with the key in macOS Keychain. Categories: identity, medical, financial, personal, "
            "professional, contacts, legal."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category: identity, medical, financial, personal, professional, contacts, legal",
                },
                "field_name": {
                    "type": "string",
                    "description": "Field name (e.g., 'full_name', 'blood_type', 'ssn')",
                },
                "value": {
                    "type": "string",
                    "description": "The sensitive value to encrypt and store",
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional unencrypted metadata (e.g., {'source': 'passport', 'expires': '2030-01'})",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Entity to scope this field to (e.g., 'acme'). Omit for personal profile.",
                },
            },
            "required": ["category", "field_name", "value"],
        },
    },
    {
        "name": "omega_profile_get",
        "description": (
            "Decrypt and retrieve personal profile field(s). If field_name is omitted, "
            "returns all fields in the category. Decryption uses the local Keychain key."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category to retrieve from",
                },
                "field_name": {
                    "type": "string",
                    "description": "Specific field name (optional -- omit to get all fields in category)",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Entity to retrieve from (e.g., 'acme'). Omit for personal profile.",
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "omega_profile_search",
        "description": (
            "Search profile metadata and field names (not encrypted values). "
            "Returns matching fields with categories. Use omega_profile_get to decrypt values."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term to match against field names, categories, and metadata",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Filter search to a specific entity. Omit to search all entities.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "omega_profile_list",
        "description": (
            "List all stored profile categories with field counts. "
            "Shows what's stored without decrypting values. "
            "Use omega_profile_get to decrypt and view specific fields."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Filter to a specific entity (e.g., 'acme'). Omit for personal profile.",
                },
            },
            "required": [],
        },
    },
]
