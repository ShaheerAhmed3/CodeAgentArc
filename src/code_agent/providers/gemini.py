"""The only Google SDK boundary. Tool execution remains entirely in AgentLoop."""

from copy import deepcopy
from dataclasses import asdict
import json
from typing import Any, Sequence
from uuid import uuid4

from google import genai
from google.genai import errors, types
import httpx

from code_agent.agent.models import Message, ModelResponse, ToolCall, ToolDefinition
from code_agent.config import DEFAULT_GEMINI_MODEL
from code_agent.providers.base import ProviderError


class GeminiProvider:
    def __init__(self, *, api_key: str, model: str = DEFAULT_GEMINI_MODEL,
                 client: Any = None) -> None:
        if not api_key.strip():
            raise ProviderError("Configure GEMINI_API_KEY in your environment or local .env")
        self.model = model
        self._owns_client = client is None
        try:
            self._client = client if client is not None else genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=120_000, retry_options=types.HttpRetryOptions(attempts=1)),
            )
        except Exception:
            raise ProviderError("Could not initialize Gemini client; check configuration") from None
        # Exact ordered parts/signatures live only in adapter memory as JSON values.
        self._turns: dict[tuple[str, ...], dict[str, Any]] = {}
        self._wire_ids: dict[str, str | None] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
        self._turns.clear()
        self._wire_ids.clear()

    def _contents(self, messages: Sequence[Message]) -> tuple[str, list[types.Content]]:
        system: list[str] = []
        contents: list[types.Content] = []
        pending: dict[str, str] = {}
        for message in messages:
            if message.role == "system":
                system.append(message.content)
                continue
            if message.role == "tool":
                result = message.tool_result
                if result is None or pending.pop(result.call_id, None) != result.name:
                    raise ProviderError("Unmatched tool observation in conversation")
                payload: dict[str, Any] = {"ok": not result.is_error, "observation": result.content}
                if result.completion is not None:
                    payload["completion"] = asdict(result.completion)
                part = types.Part(function_response=types.FunctionResponse(
                    id=self._wire_ids.get(result.call_id, result.call_id), name=result.name, response=payload,
                ))
                if contents and contents[-1].role == "user":
                    contents[-1].parts.append(part)
                else:
                    contents.append(types.Content(role="user", parts=[part]))
                continue
            if pending:
                raise ProviderError("Missing tool observations in conversation")
            if message.role == "assistant":
                ids = tuple(call.id for call in message.tool_calls)
                if ids in self._turns:
                    content = types.Content.model_validate(deepcopy(self._turns[ids]))
                else:
                    parts = [types.Part(text=message.content)] if message.content else []
                    parts.extend(types.Part(function_call=types.FunctionCall(
                        id=call.id, name=call.name, args=call.arguments,
                    )) for call in message.tool_calls)
                    content = types.Content(role="model", parts=parts)
                pending.update({call.id: call.name for call in message.tool_calls})
                contents.append(content)
            else:
                if contents and contents[-1].role == "user":
                    contents[-1].parts.append(types.Part(text=message.content))
                else:
                    contents.append(types.Content(role="user", parts=[types.Part(text=message.content)]))
        if pending:
            raise ProviderError("Missing tool observations in conversation")
        return "\n\n".join(system), contents

    def complete(self, messages: Sequence[Message], tools: Sequence[ToolDefinition]) -> ModelResponse:
        try:
            system, contents = self._contents(messages)
            declarations = [types.FunctionDeclaration(
                name=tool.name, description=tool.description,
                parameters_json_schema=deepcopy(tool.input_schema),
            ) for tool in tools]
            config = types.GenerateContentConfig(
                system_instruction=system or None,
                tools=[types.Tool(function_declarations=declarations)] if declarations else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                thinking_config=types.ThinkingConfig(include_thoughts=False), candidate_count=1,
            )
            response = self._client.models.generate_content(model=self.model, contents=contents, config=config)
        except ProviderError:
            raise
        except errors.APIError as exc:
            if exc.code in {401, 403}:
                message = "Gemini authentication/permission failure; check GEMINI_API_KEY and access"
            elif exc.code == 429:
                message = "Gemini rate limit or quota exceeded; wait or check your quota"
            elif exc.code in {400, 404}:
                message = "Gemini rejected the request; check model availability and request compatibility"
            else:
                message = "Gemini API request failed; try again later"
            raise ProviderError(message) from None
        except (httpx.HTTPError, OSError):
            raise ProviderError("Gemini network request failed; check connectivity and try again") from None
        except Exception:
            raise ProviderError("Gemini request could not be processed") from None
        try:
            candidates = response.candidates
            if not candidates or len(candidates) != 1:
                raise ValueError("Expected one candidate")
            candidate = candidates[0]
            if candidate.finish_reason not in {None, types.FinishReason.STOP}:
                raise ProviderError("Gemini response was blocked, truncated, or incomplete; no tools were executed")
            content = candidate.content
            if content is None or not content.parts:
                raise ValueError("No content")
            texts: list[str] = []
            calls: list[ToolCall] = []
            wire_ids: dict[str, str | None] = {}
            for part in content.parts:
                if part.thought:
                    continue
                if part.text:
                    texts.append(part.text)
                function = part.function_call
                if function is not None:
                    if not function.name or not isinstance(function.args, dict):
                        raise ValueError("Invalid function call")
                    args = json.loads(json.dumps(function.args, allow_nan=False))
                    call_id = function.id or f"call-{uuid4().hex}"
                    if call_id in wire_ids or call_id in self._wire_ids:
                        raise ValueError("Duplicate function call ID")
                    calls.append(ToolCall(call_id, function.name, args))
                    wire_ids[call_id] = function.id
            text = "\n".join(texts)
            if not text.strip() and not calls:
                raise ValueError("No usable content")
            if calls:
                self._turns[tuple(call.id for call in calls)] = content.model_dump(mode="json", exclude_none=True)
                self._wire_ids.update(wire_ids)
            return ModelResponse(text, tuple(calls))
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("Gemini returned a malformed or empty response") from None
