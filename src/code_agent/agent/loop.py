from copy import deepcopy
from typing import Callable, Sequence

from code_agent.agent.models import AgentResult, Message
from code_agent.providers.base import LLMProvider
from code_agent.tools.registry import ToolRegistry


class AgentLoop:
    def __init__(
        self, provider: LLMProvider, tools: ToolRegistry, *, max_turns: int = 20
    ) -> None:
        if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns < 1:
            raise ValueError("max_turns must be a positive integer")
        self.provider = provider
        self.tools = tools
        self.max_turns = max_turns

    def run(self, messages: Sequence[Message], *,
            observe: Callable[[int, Message], None] | None = None) -> AgentResult:
        history = list(deepcopy(messages))
        executed = 0
        used_ids = {call.id for message in history for call in message.tool_calls}
        for turn in range(1, self.max_turns + 1):
            response = self.provider.complete(
                deepcopy(tuple(history)), self.tools.definitions()
            )
            ids = [call.id for call in response.tool_calls]
            if any(not call_id for call_id in ids) or len(set(ids)) != len(ids):
                raise ValueError("Tool-call IDs must be nonempty and unique")
            if used_ids.intersection(ids):
                raise ValueError("Tool-call IDs must not be reused across turns")
            used_ids.update(ids)
            history.append(Message("assistant", response.content, response.tool_calls))
            if observe is not None:
                observe(turn, deepcopy(history[-1]))
            if not response.tool_calls:
                return AgentResult(response.content, tuple(history), turn, "final_response", executed)
            for call in response.tool_calls:
                result = self.tools.dispatch(call)
                executed += 1
                history.append(Message("tool", tool_result=result))
                if observe is not None:
                    observe(turn, deepcopy(history[-1]))
        return AgentResult(None, tuple(history), self.max_turns, "max_turns", executed)
