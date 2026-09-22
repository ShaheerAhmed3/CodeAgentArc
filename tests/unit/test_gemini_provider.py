from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai")
from google.genai import errors, types
import httpx

from code_agent.agent.models import Message, ModelResponse, ToolCall, ToolDefinition, ToolResult
from code_agent.providers.base import ProviderError
from code_agent.providers.gemini import GeminiProvider


class FakeClient:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []
        self.models = SimpleNamespace(generate_content=self.generate)

    def generate(self, **kwargs):
        self.requests.append(kwargs)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


def response(*parts, finish_reason="STOP"):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=list(parts)), finish_reason=finish_reason,
    )])


def provider(client):
    return GeminiProvider(api_key="offline-test-credential", client=client)


def test_system_user_tools_and_text_translation():
    client = FakeClient(response(types.Part(text="Done")))
    tool = ToolDefinition("read_file", "Read text", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]})
    result = provider(client).complete([Message("system", "rules"), Message("user", "task")], [tool])
    assert result == ModelResponse("Done")
    request = client.requests[0]
    assert request["model"] == "gemini-3.8-flash"
    assert request["config"].system_instruction == "rules"
    assert request["config"].automatic_function_calling.disable is True
    assert request["config"].thinking_config.include_thoughts is False
    assert request["contents"][0].role == "user"
    assert request["contents"][0].parts[0].text == "task"
    declaration = request["config"].tools[0].function_declarations[0]
    assert declaration.name == "read_file"
    assert declaration.parameters_json_schema == tool.input_schema
    assert json.loads(json.dumps(asdict(result))) == {"content": "Done", "tool_calls": []}


def test_multiple_calls_signatures_ids_and_observations_round_trip():
    first = response(
        types.Part(text="Inspecting"),
        types.Part(function_call=types.FunctionCall(id="remote-1", name="read_file", args={"path": "a"}), thought_signature=b"opaque-signature"),
        types.Part(function_call=types.FunctionCall(id="remote-2", name="list_files", args={})),
    )
    client = FakeClient(first, response(types.Part(text="Finished")))
    adapter = provider(client)
    initial = [Message("system", "rules"), Message("user", "task")]
    result = adapter.complete(initial, [])
    assert [call.id for call in result.tool_calls] == ["remote-1", "remote-2"]
    assert result.tool_calls[0].arguments == {"path": "a"}
    history = initial + [Message("assistant", result.content, result.tool_calls)] + [
        Message("tool", tool_result=ToolResult("remote-1", "read_file", "Missing", True)),
        Message("tool", tool_result=ToolResult("remote-2", "list_files", "file a")),
    ]
    adapter.complete(history, [])
    contents = client.requests[1]["contents"]
    assert contents[-2] == first.candidates[0].content
    assert contents[-2].parts[1].thought_signature == b"opaque-signature"
    observations = contents[-1].parts
    assert len(observations) == 2
    assert observations[0].function_response.id == "remote-1"
    assert observations[0].function_response.response == {"ok": False, "observation": "Missing"}
    assert observations[1].function_response.name == "list_files"
    assert "opaque-signature" not in repr(result)
    json.dumps(asdict(result), allow_nan=False)


def test_missing_call_id_gets_local_id_but_original_wire_shape_is_preserved():
    client = FakeClient(response(types.Part(function_call=types.FunctionCall(name="list_files", args={}))), response(types.Part(text="done")))
    adapter = provider(client)
    result = adapter.complete([Message("user", "task")], [])
    call, = result.tool_calls
    assert call.id
    adapter.complete([Message("user", "task"), Message("assistant", tool_calls=(call,)),
                      Message("tool", tool_result=ToolResult(call.id, call.name, "empty"))], [])
    assert client.requests[1]["contents"][-1].parts[0].function_response.id is None


def test_hidden_thought_text_is_not_public_content():
    result = provider(FakeClient(response(types.Part(text="hidden", thought=True), types.Part(text="public")))).complete([], [])
    assert result.content == "public"


@pytest.mark.parametrize("bad", [
    types.GenerateContentResponse(), response(), response(types.Part(text="   ")),
    response(types.Part(function_call=types.FunctionCall(name="bad"))),
    response(types.Part(function_call=types.FunctionCall(name="a", args={}, id="same")),
             types.Part(function_call=types.FunctionCall(name="b", args={}, id="same"))),
    response(types.Part(text="incomplete"), finish_reason="MAX_TOKENS"), object(),
])
def test_bad_responses_fail_cleanly(bad):
    with pytest.raises(ProviderError, match="response"):
        provider(FakeClient(bad)).complete([], [])


def test_missing_key_fails_before_client_initialization(monkeypatch):
    monkeypatch.setattr("code_agent.providers.gemini.genai.Client", lambda **kwargs: pytest.fail("client must not be created"))
    with pytest.raises(ProviderError, match="Configure GEMINI_API_KEY"):
        GeminiProvider(api_key=" ")


@pytest.mark.parametrize("status,fragment", [(400, "rejected"), (401, "authentication"), (403, "permission"), (404, "availability"), (429, "quota"), (503, "API request failed")])
def test_api_errors_are_safe_and_not_retried(status, fragment):
    sentinel = "offline-error-secret"
    error = errors.APIError(status, {"error": {"message": sentinel}})
    client = FakeClient(error)
    with pytest.raises(ProviderError, match=fragment) as caught:
        provider(client).complete([], [])
    assert sentinel not in str(caught.value)
    assert len(client.requests) == 1


def test_network_and_sdk_errors_do_not_expose_original_message():
    for failure in (httpx.ConnectError("offline-secret"), ValueError("offline-secret")):
        with pytest.raises(ProviderError) as caught:
            provider(FakeClient(failure)).complete([], [])
        assert "offline-secret" not in str(caught.value)


def test_client_options_and_cleanup_without_network(monkeypatch):
    options = {}
    client = SimpleNamespace(close=lambda: options.update(closed=True))

    def create(**kwargs):
        options.update(kwargs)
        return client

    monkeypatch.setattr("code_agent.providers.gemini.genai.Client", create)
    adapter = GeminiProvider(api_key="offline-test-credential")
    assert options["http_options"].retry_options.attempts == 1
    assert options["http_options"].timeout == 120_000
    adapter.close()
    assert options["closed"]


def test_unmatched_tool_result_fails_before_request():
    client = FakeClient()
    with pytest.raises(ProviderError, match="Unmatched"):
        provider(client).complete([Message("tool", tool_result=ToolResult("bad", "read_file", "x"))], [])
    assert not client.requests
