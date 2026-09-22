import pytest

from code_agent.agent.loop import AgentLoop
from code_agent.agent.models import Message, ModelResponse, ToolCall, ToolDefinition
from code_agent.providers.mock import MockProvider
from code_agent.tools.base import ToolInputError
from code_agent.tools.registry import ToolRegistry


class EchoTool:
    definition = ToolDefinition("echo", "Test-only echo", {
        "type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
    })

    def execute(self, arguments):
        if not isinstance(arguments.get("text"), str):
            raise ToolInputError("text must be a string")
        return arguments["text"]


@pytest.fixture
def registry():
    registry = ToolRegistry()
    registry.register(EchoTool())
    return registry


def test_registration_definitions_and_duplicates(registry):
    assert registry.definitions() == (EchoTool.definition,)
    registry.definitions()[0].input_schema.clear()
    assert registry.definitions()[0].input_schema["type"] == "object"
    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoTool())


def test_unknown_tool_and_invalid_input_are_observations(registry):
    for call in [ToolCall("1", "missing", {}), ToolCall("2", "echo", {"text": 1})]:
        result = registry.dispatch(call)
        assert result.is_error
        assert result.call_id == call.id
        assert result.name == call.name
        assert result.content


def test_expected_io_error_returns_observation_but_bug_propagates():
    class BrokenTool(EchoTool):
        error = FileNotFoundError("missing file")

        def execute(self, arguments):
            raise self.error

    tool = BrokenTool()
    registry = ToolRegistry()
    registry.register(tool)
    call = ToolCall("1", "echo", {})
    assert registry.dispatch(call).is_error
    tool.error = RuntimeError("implementation bug")
    with pytest.raises(RuntimeError, match="implementation bug"):
        registry.dispatch(call)


def test_immediate_final_preserves_inputs(registry):
    messages = [Message("user", "hello")]
    result = AgentLoop(MockProvider([ModelResponse("done")]), registry).run(messages)
    assert result.final_answer == "done"
    assert result.turns == 1
    assert result.stop_reason == "final_response"
    assert len(messages) == 1


def test_multiple_calls_and_sequential_turns_feed_results_back(registry):
    script = [
        ModelResponse("working", (ToolCall("1", "echo", {"text": "a"}), ToolCall("2", "echo", {"text": "b"}))),
        ModelResponse(tool_calls=(ToolCall("3", "echo", {"text": "c"}),)),
        ModelResponse("done"),
    ]
    provider = MockProvider(script)
    result = AgentLoop(provider, registry).run([Message("user", "start")])
    assert result.turns == 3
    assert result.final_answer == "done"
    second_request = provider.requests[1].messages
    assert [m.role for m in second_request] == ["user", "assistant", "tool", "tool"]
    assert second_request[1].tool_calls == script[0].tool_calls
    assert [(m.tool_result.call_id, m.tool_result.content) for m in second_request[-2:]] == [("1", "a"), ("2", "b")]
    assert provider.requests[2].messages[-1].tool_result.content == "c"
    assert provider.requests[0].tools == registry.definitions()


def test_model_can_continue_after_error_observation(registry):
    provider = MockProvider([
        ModelResponse(tool_calls=(ToolCall("1", "unknown", {}),)),
        ModelResponse(tool_calls=(ToolCall("2", "echo", {"text": "recovered"}),)),
        ModelResponse("done"),
    ])
    assert AgentLoop(provider, registry).run([]).stop_reason == "final_response"
    assert provider.requests[1].messages[-1].tool_result.is_error
    assert provider.requests[2].messages[-1].tool_result.content == "recovered"


def test_max_turn_limit_is_not_success_and_keeps_last_observation(registry):
    provider = MockProvider([
        ModelResponse(tool_calls=(ToolCall(str(i), "echo", {"text": "again"}),)) for i in range(3)
    ])
    result = AgentLoop(provider, registry, max_turns=2).run([])
    assert result.stop_reason == "max_turns"
    assert result.final_answer is None
    assert result.turns == len(provider.requests) == 2
    assert result.messages[-1].tool_result.content == "again"


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_bad_turn_limit(limit, registry):
    with pytest.raises(ValueError, match="positive integer"):
        AgentLoop(MockProvider([]), registry, max_turns=limit)


def test_duplicate_call_ids_rejected_before_execution(registry):
    call = ToolCall("1", "echo", {})
    provider = MockProvider([ModelResponse(tool_calls=(call, call))])
    with pytest.raises(ValueError, match="unique"):
        AgentLoop(provider, registry).run([])


def test_mock_replay_is_deterministic_isolated_and_finite():
    call = ToolCall("1", "echo", {"text": "original"})
    script = [ModelResponse(tool_calls=(call,)), ModelResponse("done")]
    first, second = MockProvider(script), MockProvider(script)
    call.arguments["text"] = "changed after construction"
    assert first.complete([], []) == second.complete([], [])
    assert first.complete([], []) == second.complete([], []) == ModelResponse("done")
    assert first.requests == second.requests
    with pytest.raises(RuntimeError, match="exhausted"):
        first.complete([], [])
