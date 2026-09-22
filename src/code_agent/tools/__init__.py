"""Tool contracts and explicit composition; no provider or plugin discovery."""

from code_agent.tools.command import RunCommandTool
from code_agent.tools.filesystem import EditFileTool, ListFilesTool, ReadFileTool, SearchFilesTool, WriteFileTool
from code_agent.tools.finish import FinishTool
from code_agent.tools.registry import ToolRegistry
from code_agent.workspace.workspace import Workspace
from typing import Mapping


def coding_tools(workspace: Workspace, *, command_timeout: float = 30,
                 command_environment: Mapping[str, str] | None = None) -> ToolRegistry:
    """Build a fresh registry; use only with a dedicated, trusted output workspace."""
    registry = ToolRegistry()
    for tool in (ReadFileTool(workspace), WriteFileTool(workspace), EditFileTool(workspace),
                 ListFilesTool(workspace), SearchFilesTool(workspace),
                 RunCommandTool(workspace, timeout=command_timeout, environment=command_environment), FinishTool()):
        registry.register(tool)
    return registry
