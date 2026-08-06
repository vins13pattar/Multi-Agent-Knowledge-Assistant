from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel


class ToolDefinition(BaseModel):
    name: str
    description: str
    risk_level: str  # low | medium | high | critical
    input_schema: Dict[str, Any]


class ToolRegistry:
    """In-memory registry of native tools available to the agent graph."""

    def __init__(self):
        self._tools: Dict[str, Tuple[ToolDefinition, Callable]] = {}

    def register(self, definition: ToolDefinition, func: Callable) -> None:
        self._tools[definition.name] = (definition, func)

    def get(self, name: str) -> Optional[Tuple[ToolDefinition, Callable]]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return [definition for definition, _ in self._tools.values()]

    def execute(self, name: str, **kwargs) -> Any:
        entry = self.get(name)
        if not entry:
            raise ValueError(f"Unknown tool: {name}")
        _definition, func = entry
        from src.tools.executor import execute_tool
        return execute_tool(name, func, **kwargs)


_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    from src.tools.native import register_default_tools
    if not _registry.list_tools():
        register_default_tools(_registry)
    return _registry
