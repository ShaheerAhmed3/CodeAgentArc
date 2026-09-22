import json
from types import SimpleNamespace

import pytest
import httpx
from openai import APIStatusError

pytest.importorskip("openai")

from code_agent.agent.models import Message, ModelResponse, ToolDefinition, ToolResult
from code_agent.providers.base import ProviderError
from code_agent.providers.openai import OpenAIProvider


class Item(SimpleNamespace):
    def model_dump(self, **kwargs):
        return dict(self.wire)


def response(*items, status="completed"):
    return SimpleNamespace(status=status, output=list(items))


class FakeClient:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.requests = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.requests.append(kwargs)
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_text_tool_call_and_observation_round_trip():
    reasoning = Item(type="reasoning", wire={"type": "reasoning", "encrypted_content": "opaque"})
    call = Item(type="function_call", call_id="call-1", name="list_files", arguments="{}",
                wire={"type": "function_call", "call_id": "call-1", "name": "list_files", "arguments": "{}"})
    answer = Item(type="message", content=[SimpleNamespace(type="output_text", text="Done")],
                  wire={"type": "message", "content": [{"type": "output_text", "text": "Done"}]})
    client = FakeClient(response(reasoning, call), response(answer))
    adapter = OpenAIProvider(api_key="offline-credential", model="test-model", client=client)
    definition = ToolDefinition("list_files", "List files", {"type": "object", "properties": {}})
    initial = [Message("system", "rules"), Message("user", "inspect")]
    first = adapter.complete(initial, [definition])
    assert first.tool_calls[0].id == "call-1"
    assert first.tool_calls[0].arguments == {}
    assert client.requests[0]["instructions"] == "rules"
    assert client.requests[0]["tools"][0]["strict"] is False
    assert client.requests[0]["store"] is False
    assert client.requests[0]["include"] == ["reasoning.encrypted_content"]
    history = initial + [Message("assistant", first.content, first.tool_calls),
                         Message("tool", tool_result=ToolResult("call-1", "list_files", "empty"))]
    assert adapter.complete(history, []) == ModelResponse("Done")
    sent = client.requests[1]["input"]
    assert sent[1] == reasoning.wire
    assert sent[2] == call.wire
    assert sent[3]["type"] == "function_call_output"
    assert json.loads(sent[3]["output"]) == {"ok": True, "observation": "empty"}
    assert "opaque" not in repr(first)


@pytest.mark.parametrize("reply", [
    response(), response(status="incomplete"),
    response(Item(type="function_call", call_id="x", name="write_file", arguments="bad",
                  wire={})),
])
def test_bad_responses_fail_without_leaking_payload(reply):
    adapter = OpenAIProvider(api_key="offline-credential", model="m", client=FakeClient(reply))
    with pytest.raises(ProviderError, match="malformed or empty"):
        adapter.complete([Message("user", "test")], [])


def test_unmatched_observation_fails_before_request():
    client = FakeClient()
    adapter = OpenAIProvider(api_key="offline-credential", model="m", client=client)
    with pytest.raises(ProviderError, match="Unmatched"):
        adapter.complete([Message("tool", tool_result=ToolResult("wrong", "list_files", "x"))], [])
    assert not client.requests


def test_missing_key():
    with pytest.raises(ProviderError, match="Configure OPENAI_API_KEY"):
        OpenAIProvider(api_key=" ", model="m")


@pytest.mark.parametrize("status,retryable", [(400, False), (401, False), (429, True), (503, True)])
def test_status_errors_are_safe_and_classified(status, retryable):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    failure = APIStatusError("offline-secret", response=response, body={"secret": "offline-secret"})
    client = FakeClient(failure)
    adapter = OpenAIProvider(api_key="offline-credential", model="m", client=client)
    with pytest.raises(ProviderError) as caught:
        adapter.complete([Message("user", "task")], [])
    assert caught.value.status_code == status
    assert caught.value.retryable is retryable
    assert "offline-secret" not in str(caught.value)
    assert len(client.requests) == 1
