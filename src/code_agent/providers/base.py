from typing import Protocol, Sequence

from code_agent.agent.models import Message, ModelResponse, ToolDefinition


class ProviderError(RuntimeError):
    """Safe application-level failure; never contains SDK error bodies or keys."""


class LLMProvider(Protocol):
    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolDefinition]
    ) -> ModelResponse:
        """Return a neutral response; translate SDK values inside the adapter.

        Adapters must preserve tool-call IDs and reject malformed API responses.
        Provider/network failures propagate to the caller, not as final answers.
        Model choice and credentials belong in adapter configuration.
        """
        ...
