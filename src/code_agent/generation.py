"""One generation workflow composed from the existing provider-neutral runtime."""

from dataclasses import asdict, replace
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
from code_agent.tools.command import RunCommandTool
from code_agent.validation.validator import ValidationCheck, ValidationPolicy, ValidationReport, validate_repository
from code_agent.workspace.workspace import Workspace


def _resolve_output(project_root: Path, output: Path) -> Path:
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
    return resolved


def prepare_output(project_root: Path, output: Path) -> Workspace:
    resolved = _resolve_output(project_root, output)
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise ConfigurationError("Output must be absent or empty; choose a new directory")
    return Workspace(resolved, reserved_names=frozenset({".codeagent"}))


def verify_existing(*, project_root: Path, output: Path,
                    command: list[str]) -> bool:
    """Independently verify the final files of a completed run, preserving its first result."""
    resolved = _resolve_output(project_root, output)
    if (resolved / ".codeagent").is_symlink() or (resolved / ".codeagent").is_junction():
        raise ConfigurationError("Run artifact directory must not be linked")
    report_path = resolved / ".codeagent" / "generation_report.json"
    if not report_path.is_file() or report_path.is_symlink():
        raise ConfigurationError("Output has no regular generation report")
    trace_path = resolved / ".codeagent" / "run.jsonl"
    if not trace_path.is_file() or trace_path.is_symlink() or trace_path.is_junction():
        raise ConfigurationError("Output has no regular run trace")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("stop_reason") != "final_response" or report.get("error"):
        raise ConfigurationError("Only a completed, error-free agent run can be verified")
    workspace = Workspace(resolved, reserved_names=frozenset({".codeagent"}))
    environment = {name: value for name, value in os.environ.items()
                   if not re.search(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", name, re.IGNORECASE)}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = RunCommandTool(workspace, timeout=120, environment=environment).run(command)
    validation = validate_repository(
        workspace, policy=ValidationPolicy(require_desktop_game=True), command_results=[result]
    )
    validation = ValidationReport(validation.checks + (
        ValidationCheck("final_verification", result.success,
                        "Independent post-run verification passed" if result.success else
                        "Independent post-run verification failed"),
    ), validation.warnings)
    if "initial_validation" not in report:
        report["initial_validation"] = report["validation"]
        report["initial_success"] = report["success"]
    report["validation"] = {
        "success": validation.success,
        "checks": [asdict(check) for check in validation.checks],
        "errors": validation.errors, "warnings": validation.warnings,
    }
    report["verification"] = [{"executable": Path(result.command[0]).name,
                               "argument_count": len(result.command) - 1,
                               "exit_code": result.exit_code, "timed_out": result.timed_out,
                               "success": result.success,
                               "stdout_truncated": result.stdout_truncated,
                               "stderr_truncated": result.stderr_truncated}]
    report["post_run_verification"] = True
    report["success"] = validation.success
    temporary = report_path.with_suffix(".json.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(report_path)
    with trace_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"event": "post_run_verification", "executable": Path(command[0]).name,
                                 "argument_count": len(command) - 1, "exit_code": result.exit_code,
                                 "validation_passed": validation.success}) + "\n")
    return validation.success


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
        "Generate the architecture-described game in this empty workspace as a local desktop "
        "application with a graphical UI. Prefer Python and Tkinter. It must run without a browser "
        "or hosted server; adapt conflicting web/deployment guidance while preserving functional behavior. "
        f"Host OS: {sys.platform}. Python executable available: {sys.executable}. "
        "On Windows invoke executables directly, not .cmd/.bat launchers."
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
    provider_failure: ProviderError | None = None
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
            provider_failure = exc
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
        validation = validate_repository(
            workspace, policy=ValidationPolicy(require_desktop_game=True), command_results=evidence
        )
        validation = ValidationReport(validation.checks + (
            ValidationCheck("final_verification", bool(evidence),
                            "Final verification evidence recorded" if evidence else
                            "No verification=true command executed after the final file edits"),
        ), validation.warnings)
        report = GenerationReport(
            execution, validation, config.provider, config.model, error,
            provider_failure.status_code if provider_failure else None,
            provider_failure.category if provider_failure else None,
            provider_failure.retryable if provider_failure else False,
        )
        trace.write(json.dumps({"event": "run_end", "stop_reason": execution.stop_reason,
                                "validation_passed": validation.success}) + "\n")
    payload = report_payload(report, evidence, config.api_key)
    with (_artifact_directory(workspace) / "generation_report.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return report
