"""OMEGA Entity Tool Schemas -- 8 tools for multi-entity corporate memory."""

ENTITY_TOOL_SCHEMAS = [
    {
        "name": "omega_entity_create",
        "description": (
            "Create a corporate entity in the registry. Supports companies, LLCs, foundations, "
            "startups, and more. Entity IDs are slugs (e.g., 'acme', 'acme-llc')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Unique slug identifier (e.g., 'acme', 'acme-llc')",
                },
                "name": {
                    "type": "string",
                    "description": "Display name (e.g., 'Acme Corp', 'Acme LLC')",
                },
                "entity_type": {
                    "type": "string",
                    "description": (
                        "Entity type: company, llc, s_corp, c_corp, foundation, startup, "
                        "trust, partnership, sole_proprietorship, nonprofit, other, "
                        "person, project, tool, concept, technology, service"
                    ),
                },
                "jurisdiction": {
                    "type": "string",
                    "description": "Jurisdiction code (e.g., 'US-DE', 'US-WY', 'NL')",
                },
                "metadata": {
                    "type": "object",
                    "description": "Additional metadata (e.g., {ein: '...', founded: '2023'})",
                },
            },
            "required": ["entity_id", "name", "entity_type"],
        },
    },
    {
        "name": "omega_entity_get",
        "description": "Get detailed information about a specific entity by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Entity ID to look up",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "omega_entity_list",
        "description": "List all registered entities with optional type and status filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "description": "Filter by entity type (e.g., 'llc', 'foundation')",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: active, acquired, dissolved, dormant, pending",
                },
            },
        },
    },
    {
        "name": "omega_entity_update",
        "description": "Update an entity's name, status, jurisdiction, or metadata. Only provided fields are changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Entity ID to update",
                },
                "name": {
                    "type": "string",
                    "description": "New display name",
                },
                "status": {
                    "type": "string",
                    "description": "New status: active, acquired, dissolved, dormant, pending",
                },
                "jurisdiction": {
                    "type": "string",
                    "description": "New jurisdiction code",
                },
                "metadata": {
                    "type": "object",
                    "description": "Metadata keys to merge (set a key to null to delete it)",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "omega_entity_delete",
        "description": "Soft-delete an entity by setting its status to 'dissolved'. Does not remove data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Entity ID to dissolve",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "omega_entity_add_relationship",
        "description": (
            "Add a directed relationship between two entities. "
            "Types: parent_of, subsidiary_of, owned_by, acquired_by, partner_of, investor_in, operated_by, "
            "uses, works_on, depends_on, mentions, created_by."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_entity_id": {
                    "type": "string",
                    "description": "Source entity ID",
                },
                "target_entity_id": {
                    "type": "string",
                    "description": "Target entity ID",
                },
                "relationship_type": {
                    "type": "string",
                    "description": (
                        "Relationship type: parent_of, subsidiary_of, owned_by, "
                        "acquired_by, partner_of, investor_in, operated_by, "
                        "uses, works_on, depends_on, mentions, created_by"
                    ),
                },
                "metadata": {
                    "type": "object",
                    "description": "Relationship metadata (e.g., {ownership_pct: 100, year: 2024})",
                },
            },
            "required": ["source_entity_id", "target_entity_id", "relationship_type"],
        },
    },
    {
        "name": "omega_entity_relationships",
        "description": "Get all relationships for an entity, optionally filtered by direction and type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Entity ID to query relationships for",
                },
                "direction": {
                    "type": "string",
                    "description": "Filter by direction: 'outgoing', 'incoming', or omit for both",
                },
                "relationship_type": {
                    "type": "string",
                    "description": "Filter by relationship type",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "omega_entity_tree",
        "description": (
            "Get a recursive hierarchy view of an entity and its children "
            "(follows parent_of relationships). Useful for visualizing corporate structure."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Root entity ID to build tree from",
                },
            },
            "required": ["entity_id"],
        },
    },
]
