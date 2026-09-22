"""Persist observable metadata, never full transcripts or provider state."""

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, TextIO

from code_agent.agent.models import Message
from code_agent.agent.report import GenerationReport
from code_agent.tools.command import CommandResult


def redact(value: Any, secret: str, *, limit: int | None = 4000) -> Any:
    if isinstance(value, str):
        text = value.replace(secret, "[REDACTED]") if secret else value
        return text[:limit] if limit is not None else text
    if isinstance(value, dict):
        return {redact(key, secret, limit=limit): redact(item, secret, limit=limit) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact(item, secret, limit=limit) for item in value]
    return value


def trace_message(stream: TextIO, turn: int, message: Message, secret: str) -> None:
    events: list[dict[str, Any]] = []
    if message.role == "assistant":
        events.append({"event": "model_response", "turn": turn, "tool_calls": len(message.tool_calls)})
        for call in message.tool_calls:
            event: dict[str, Any] = {"event": "tool_call", "turn": turn, "id": call.id, "name": call.name}
            for name in ("path", "directory"):
                if isinstance(call.arguments.get(name), str):
                    event[name] = call.arguments[name]
            for name in ("content", "old_text", "new_text"):
                if isinstance(call.arguments.get(name), str):
                    event[name + "_characters"] = len(call.arguments[name])
            command = call.arguments.get("command")
            if isinstance(command, list) and command and isinstance(command[0], str):
                event["executable"] = Path(command[0]).name
                event["argument_count"] = len(command) - 1
            events.append(event)
    elif message.tool_result is not None:
        result = message.tool_result
        event = {"event": "tool_result", "turn": turn, "id": result.call_id,
                 "name": result.name, "success": not result.is_error}
        for name in ("exit_code", "timed_out", "stdout_truncated", "stderr_truncated", "verification"):
            if name in result.metadata:
                event[name] = result.metadata[name]
        events.append(event)
    for event in events:
        stream.write(json.dumps(redact(event, secret), ensure_ascii=False) + "\n")
    stream.flush()


def report_payload(report: GenerationReport, commands: list[CommandResult], secret: str) -> dict[str, Any]:
    execution = report.execution
    counts = Counter(message.tool_result.name for message in execution.messages if message.tool_result is not None)
    payload = {
        "provider": report.provider, "model": report.model, "success": report.success,
        "stop_reason": execution.stop_reason, "turns": execution.turns,
        "tool_calls_executed": execution.tool_calls_executed, "tool_counts": dict(counts),
        "final_summary": execution.final_answer,
        "completion": asdict(execution.completion) if execution.completion else None,
        "error": report.error,
        "error_status_code": report.error_status_code,
        "error_category": report.error_category,
        "error_retryable": report.error_retryable,
        "validation": {"success": report.validation.success,
                       "checks": [asdict(check) for check in report.validation.checks],
                       "errors": report.validation.errors, "warnings": report.validation.warnings},
        "verification": [{"executable": Path(result.command[0]).name,
                          "argument_count": len(result.command) - 1,
                          "exit_code": result.exit_code, "timed_out": result.timed_out,
                          "success": result.success, "stdout_truncated": result.stdout_truncated,
                          "stderr_truncated": result.stderr_truncated} for result in commands],
    }
    return redact(payload, secret)
