"""Small API-neutral values shared by providers, tools, and the runtime."""

from dataclasses import dataclass, field
from typing import Literal

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, JSONValue]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, JSONValue]


@dataclass(frozen=True)
class CompletionInfo:
    summary: str
    tests_run: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolOutput:
    """Execution payload; the registry adds call identity to form ToolResult."""

    content: str
    is_error: bool = False
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    completion: CompletionInfo | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    content: str
    is_error: bool = False
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    completion: CompletionInfo | None = None


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_result: ToolResult | None = None

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"Invalid message role: {self.role}")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("Only assistant messages can contain tool calls")
        if (self.role == "tool") != (self.tool_result is not None):
            raise ValueError("Tool messages must contain exactly one tool result")


@dataclass(frozen=True)
class ModelResponse:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class AgentResult:
    final_answer: str | None
    messages: tuple[Message, ...]
    turns: int
    stop_reason: Literal["final_response", "max_turns", "provider_error", "runtime_error"]
    tool_calls_executed: int = 0

    @property
    def completion(self) -> CompletionInfo | None:
        for message in reversed(self.messages):
            result = message.tool_result
            if result and not result.is_error and result.completion is not None:
                return result.completion
        return None
