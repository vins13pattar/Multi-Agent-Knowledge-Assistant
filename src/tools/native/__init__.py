from src.tools.registry import ToolDefinition, ToolRegistry


def register_default_tools(registry: ToolRegistry) -> None:
    from src.tools.native.support_ticket import create_support_ticket
    from src.tools.native.knowledge_search import search_knowledge_base

    registry.register(
        ToolDefinition(
            name="create_support_ticket",
            description="Create a support ticket for IT/HR/facilities follow-up.",
            risk_level="medium",
            input_schema={
                "subject": {"type": "string", "required": True},
                "description": {"type": "string", "required": False},
                "priority": {"type": "string", "enum": ["low", "medium", "high"], "required": False},
            },
        ),
        create_support_ticket,
    )

    registry.register(
        ToolDefinition(
            name="search_knowledge_base",
            description="Search the enterprise knowledge base for relevant document chunks.",
            risk_level="low",
            input_schema={
                "query": {"type": "string", "required": True},
                "k": {"type": "integer", "required": False},
            },
        ),
        search_knowledge_base,
    )
