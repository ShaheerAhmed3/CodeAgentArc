from copy import deepcopy
from dataclasses import dataclass
from typing import Sequence

from code_agent.agent.models import Message, ModelResponse, ToolDefinition


@dataclass(frozen=True)
class RecordedRequest:
    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...]


class MockProvider:
    """Replay a finite script and record isolated requests for assertions."""

    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self._responses = deepcopy(tuple(responses))
        self.requests: list[RecordedRequest] = []

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolDefinition]
    ) -> ModelResponse:
        index = len(self.requests)
        if index >= len(self._responses):
            raise RuntimeError("MockProvider script exhausted")
        self.requests.append(deepcopy(RecordedRequest(tuple(messages), tuple(tools))))
        return deepcopy(self._responses[index])
