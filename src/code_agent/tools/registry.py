from copy import deepcopy

from code_agent.agent.models import ToolCall, ToolDefinition, ToolOutput, ToolResult
from code_agent.tools.base import Tool, ToolInputError
from code_agent.workspace.workspace import WorkspacePathError


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.definition.name
        if not name.strip():
            raise ValueError("Tool name must not be empty")
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(deepcopy(tool.definition) for tool in self._tools.values())

    def dispatch(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(call.id, call.name, f"Unknown tool: {call.name}", True)
        if not isinstance(call.arguments, dict):
            return ToolResult(call.id, call.name, "Arguments must be an object", True)
        try:
            content = tool.execute(deepcopy(call.arguments))
        except (ToolInputError, WorkspacePathError, OSError, UnicodeError) as exc:
            return ToolResult(call.id, call.name, str(exc), True)
        if isinstance(content, ToolOutput):
            return ToolResult(call.id, call.name, content.content, content.is_error,
                              deepcopy(content.metadata), content.completion)
        if not isinstance(content, str):
            raise TypeError(f"Tool {call.name} must return text or ToolOutput")
        return ToolResult(call.id, call.name, content)
