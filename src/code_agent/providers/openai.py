"""OpenAI Responses adapter; the AgentLoop remains the sole tool executor."""

from copy import deepcopy
from dataclasses import asdict
import json
from typing import Any, Sequence

from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, APIStatusError

from code_agent.agent.models import Message, ModelResponse, ToolCall, ToolDefinition
from code_agent.providers.base import ProviderError


class OpenAIProvider:
    def __init__(self, *, api_key: str, model: str, client: Any = None) -> None:
        if not api_key.strip():
            raise ProviderError("Configure OPENAI_API_KEY in your environment or local .env")
        self.model = model
        self._owns_client = client is None
        try:
            self._client = client if client is not None else OpenAI(
                api_key=api_key, timeout=120.0, max_retries=0,
            )
        except Exception:
            raise ProviderError("Could not initialize OpenAI client; check configuration") from None
        # Reasoning and tool-call continuation items stay private to this adapter.
        self._turns: dict[tuple[str, ...], list[dict[str, Any]]] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
        self._turns.clear()

    def _input(self, messages: Sequence[Message]) -> tuple[str, list[dict[str, Any]]]:
        instructions: list[str] = []
        items: list[dict[str, Any]] = []
        pending: dict[str, str] = {}
        for message in messages:
            if message.role == "system":
                instructions.append(message.content)
            elif message.role == "tool":
                result = message.tool_result
                if result is None or pending.pop(result.call_id, None) != result.name:
                    raise ProviderError("Unmatched tool observation in conversation")
                payload: dict[str, Any] = {"ok": not result.is_error, "observation": result.content}
                if result.completion is not None:
                    payload["completion"] = asdict(result.completion)
                items.append({"type": "function_call_output", "call_id": result.call_id,
                              "output": json.dumps(payload, ensure_ascii=False)})
            elif message.role == "assistant":
                if pending:
                    raise ProviderError("Missing tool observations in conversation")
                if message.tool_calls:
                    ids = tuple(call.id for call in message.tool_calls)
                    if ids not in self._turns:
                        raise ProviderError("Missing OpenAI continuation state for tool calls")
                    items.extend(deepcopy(self._turns[ids]))
                    pending.update({call.id: call.name for call in message.tool_calls})
                elif message.content:
                    items.append({"role": "assistant", "content": message.content})
            else:
                if pending:
                    raise ProviderError("Missing tool observations in conversation")
                items.append({"role": "user", "content": message.content})
        if pending:
            raise ProviderError("Missing tool observations in conversation")
        return "\n\n".join(instructions), items

    def complete(self, messages: Sequence[Message], tools: Sequence[ToolDefinition]) -> ModelResponse:
        instructions, items = self._input(messages)
        declarations = [
            {"type": "function", "name": tool.name, "description": tool.description,
             "parameters": deepcopy(tool.input_schema), "strict": False}
            for tool in tools
        ]
        try:
            response = self._client.responses.create(
                model=self.model, instructions=instructions or None, input=items,
                tools=declarations, store=False, include=["reasoning.encrypted_content"],
            )
        except APIStatusError as exc:
            status = exc.status_code
            if status in {401, 403}:
                message, category = "OpenAI authentication/permission failure; check OPENAI_API_KEY and access", "authentication"
            elif status == 429:
                message, category = "OpenAI rate limit or quota exceeded; wait or check your quota", "rate_limit"
            elif status in {400, 404}:
                message, category = "OpenAI rejected the request; check model availability and request compatibility", "invalid_request"
            else:
                message, category = "OpenAI API request failed; try again later", "service_error"
            raise ProviderError(message, provider="openai", status_code=status,
                                category=category, retryable=status in {429, 500, 502, 503, 504}) from None
        except (APIConnectionError, APITimeoutError):
            raise ProviderError("OpenAI network request failed; check connectivity and try again",
                                provider="openai", category="network", retryable=True) from None
        except APIError:
            raise ProviderError("OpenAI API request failed", provider="openai", category="api_error") from None
        except Exception:
            raise ProviderError("OpenAI request could not be processed") from None
        try:
            if response.status != "completed":
                raise ValueError("Incomplete response")
            texts: list[str] = []
            calls: list[ToolCall] = []
            output: list[dict[str, Any]] = []
            for item in response.output:
                output.append(item.model_dump(mode="json", exclude_none=True))
                if item.type == "message":
                    for part in item.content:
                        if part.type == "output_text" and part.text:
                            texts.append(part.text)
                elif item.type == "function_call":
                    arguments = json.loads(item.arguments)
                    if not item.call_id or not item.name or not isinstance(arguments, dict):
                        raise ValueError("Malformed function call")
                    calls.append(ToolCall(item.call_id, item.name, arguments))
            if len({call.id for call in calls}) != len(calls):
                raise ValueError("Duplicate function call ID")
            content = "\n".join(texts)
            if not content.strip() and not calls:
                raise ValueError("No usable content")
            if calls:
                self._turns[tuple(call.id for call in calls)] = output
            return ModelResponse(content, tuple(calls))
        except Exception:
            raise ProviderError("OpenAI returned a malformed or empty response") from None
