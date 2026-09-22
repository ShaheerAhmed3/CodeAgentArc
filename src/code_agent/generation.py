"""One generation workflow composed from the existing provider-neutral runtime."""

from dataclasses import replace
import json
import os
from pathlib import Path
import re
import sys
from typing import Sequence

from code_agent.agent.loop import AgentLoop
from code_agent.agent.models import AgentResult, Message, ModelResponse
from code_agent.agent.prompts import build_messages
from code_agent.agent.report import GenerationReport
from code_agent.architecture.normalizer import normalize_architecture
from code_agent.config import ConfigurationError, ProviderConfig
from code_agent.providers.base import ProviderError
from code_agent.providers.factory import create_provider
from code_agent.reporting import redact, report_payload, trace_message
from code_agent.tools import coding_tools
from code_agent.tools.command import CommandResult
from code_agent.validation.validator import ValidationCheck, ValidationReport, validate_repository
from code_agent.workspace.workspace import Workspace


def prepare_output(project_root: Path, output: Path) -> Workspace:
    project_root = project_root.resolve()
    generated = project_root / "generated"
    target = output.absolute()
    if not target.is_relative_to(generated) or target == generated:
        raise ConfigurationError("Output must be a project subdirectory under generated/")
    for path in (target, *target.parents):
        if path == project_root:
            break
        if path.is_symlink() or path.is_junction():
            raise ConfigurationError("Output paths must not contain symlinks or junctions")
    resolved = target.resolve()
    if not resolved.is_relative_to(generated) or resolved == generated:
        raise ConfigurationError("Output must stay inside generated/")
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise ConfigurationError("Output must be absent or empty; choose a new directory")
    return Workspace(resolved, reserved_names=frozenset({".codeagent"}))


def _artifact_directory(workspace: Workspace) -> Path:
    directory = workspace.root / ".codeagent"
    if directory.is_symlink() or directory.is_junction():
        raise OSError("Run artifact directory was replaced with a link")
    return directory


def generate(*, architecture_doc: Path, architecture_view: Path, output: Path,
             config: ProviderConfig, project_root: Path, max_turns: int = 20,
             mock_responses: Sequence[ModelResponse] | None = None) -> GenerationReport:
    config.validate()
    if type(max_turns) is not int or max_turns < 1:
        raise ConfigurationError("max_turns must be a positive integer")
    architecture = normalize_architecture(architecture_doc, architecture_view)
    workspace = prepare_output(project_root, output)
    directory = _artifact_directory(workspace)
    directory.mkdir()
    initial = build_messages(architecture, (
        "Generate the architecture-described application in this empty workspace. "
        f"Host OS: {sys.platform}. Python executable available: {sys.executable}. "
        "Use the architecture's stack. On Windows invoke executables directly, not .cmd/.bat launchers."
    ))
    # Defense in depth if a source file accidentally contains the configured key.
    initial = tuple(replace(message, content=redact(message.content, config.api_key, limit=None)) for message in initial)
    history = list(initial)
    turns = 0
    executed = 0
    verification: dict[tuple[str, ...], CommandResult] = {}
    environment = {name: value for name, value in os.environ.items()
                   if not re.search(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", name, re.IGNORECASE)
                   and (not config.api_key or config.api_key not in value)}
    # Rapid same-size edits can otherwise reuse Python's timestamp-based bytecode.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    tools = coding_tools(workspace, command_timeout=120, command_environment=environment)
    provider = None
    error = None
    with (directory / "run.jsonl").open("x", encoding="utf-8", newline="\n") as trace:
        def observe(turn: int, message: Message) -> None:
            nonlocal turns, executed
            turns = turn
            history.append(message)
            trace_message(trace, turn, message, config.api_key)
            result = message.tool_result
            if result is None:
                return
            executed += 1
            if result.name in {"write_file", "edit_file"} or (
                result.name == "run_command" and not result.metadata.get("verification")
            ):
                verification.clear()
            if result.name == "run_command" and result.metadata.get("verification"):
                data = dict(result.metadata)
                data.pop("verification")
                data["command"] = tuple(data["command"])
                evidence = CommandResult(**data)
                verification[evidence.command] = evidence

        try:
            provider = create_provider(config, mock_responses=mock_responses)
            execution = AgentLoop(provider, tools, max_turns=max_turns).run(initial, observe=observe)
        except ProviderError as exc:
            error = redact(str(exc), config.api_key)
            execution = AgentResult(None, tuple(history), turns, "provider_error", executed)
        except Exception:
            error = "Tool/runtime failure; inspect the execution trace and generated files"
            execution = AgentResult(None, tuple(history), turns, "runtime_error", executed)
        finally:
            if provider is not None and callable(getattr(provider, "close", None)):
                try:
                    provider.close()
                except Exception:
                    pass  # Cleanup must not hide the original outcome or reveal SDK data.
        evidence = list(verification.values())
        validation = validate_repository(workspace, command_results=evidence)
        validation = ValidationReport(validation.checks + (
            ValidationCheck("final_verification", bool(evidence),
                            "Final verification evidence recorded" if evidence else
                            "No verification=true command executed after the final file edits"),
        ), validation.warnings)
        report = GenerationReport(execution, validation, config.provider, config.model, error)
        trace.write(json.dumps({"event": "run_end", "stop_reason": execution.stop_reason,
                                "validation_passed": validation.success}) + "\n")
    payload = report_payload(report, evidence, config.api_key)
    with (_artifact_directory(workspace) / "generation_report.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return report
