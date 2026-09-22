"""Bounded command observations, not an operating-system security sandbox."""

from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Mapping

from code_agent.agent.models import JSONValue, ToolOutput
from code_agent.tools.base import ToolInputError, check_keys, definition, string_list_argument
from code_agent.workspace.workspace import Workspace


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.error is None

    def metadata(self) -> dict[str, JSONValue]:
        return {
            "command": list(self.command), "exit_code": self.exit_code,
            "stdout": self.stdout, "stderr": self.stderr, "timed_out": self.timed_out,
            "stdout_truncated": self.stdout_truncated, "stderr_truncated": self.stderr_truncated,
            "error": self.error,
        }


class RunCommandTool:
    def __init__(self, workspace: Workspace, *, timeout: float = 30,
                 max_output_bytes: int = 16_000, environment: Mapping[str, str] | None = None) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number")
        if type(max_output_bytes) is not int or max_output_bytes < 1:
            raise ValueError("max_output_bytes must be a positive integer")
        self.workspace = workspace
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self.environment = dict(environment) if environment is not None else None
        self.definition = definition("run_command", "Execute an argument list in the workspace (not a security sandbox).", {
            "command": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "timeout": {"type": "number", "exclusiveMinimum": 0, "maximum": timeout},
            "verification": {"type": "boolean", "default": False,
                             "description": "Mark a final test/build check as validation evidence"},
        }, ["command"])

    def run(self, command: list[str], *, timeout: float | None = None) -> CommandResult:
        """Expose command evidence for callers performing post-run validation."""
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) or "\x00" in arg for arg in command):
            raise ToolInputError("command must be a nonempty list of strings without NUL characters")
        if not command[0].strip():
            raise ToolInputError("command executable must not be empty")
        seconds = self.timeout if timeout is None else timeout
        if (isinstance(seconds, bool) or not isinstance(seconds, (float, int))
                or not math.isfinite(seconds) or not 0 < seconds <= self.timeout):
            raise ToolInputError(f"timeout must be positive and no greater than {self.timeout} seconds")
        # Windows may implicitly invoke a shell for batch files even with shell=False.
        executable = shutil.which(command[0]) or command[0]
        if os.name == "nt" and Path(executable).suffix.lower() in {".bat", ".cmd"}:
            raise ToolInputError("Windows batch launchers are not supported; invoke an executable directly (for example node with a script path)")
        code: int | None = None
        timed_out = False
        error: str | None = None
        # File-backed capture bounds Python memory even when a command is noisy.
        # It does not impose a disk quota or contain descendants of the process.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                process = subprocess.run(
                    command, cwd=self.workspace.root, shell=False, stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr, timeout=seconds, check=False,
                    env=self.environment,
                )
                code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                error = f"Command timed out after {seconds} seconds; direct child terminated"
            except FileNotFoundError:
                error = f"Executable not found: {command[0]}"
            except OSError as exc:
                error = f"Could not start command: {exc}"
            stdout.seek(0)
            stderr.seek(0)
            out = stdout.read(self.max_output_bytes + 1)
            err = stderr.read(self.max_output_bytes + 1)
        return CommandResult(
            tuple(command), code, out[:self.max_output_bytes].decode("utf-8", errors="replace"),
            err[:self.max_output_bytes].decode("utf-8", errors="replace"), timed_out,
            len(out) > self.max_output_bytes, len(err) > self.max_output_bytes, error,
        )

    def execute(self, arguments: dict[str, JSONValue]) -> ToolOutput:
        check_keys(arguments, {"command", "timeout", "verification"})
        verification = arguments.get("verification", False)
        if not isinstance(verification, bool):
            raise ToolInputError("verification must be a boolean")
        command = string_list_argument(arguments, "command")
        timeout = arguments.get("timeout", self.timeout)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ToolInputError("timeout must be a positive number")
        result = self.run(command, timeout=timeout)
        status = result.error or f"Exit code: {result.exit_code}"
        text = (f"{status}\nstdout{' [truncated]' if result.stdout_truncated else ''}:\n{result.stdout}"
                f"\nstderr{' [truncated]' if result.stderr_truncated else ''}:\n{result.stderr}")
        metadata = result.metadata()
        if verification:
            metadata["verification"] = True
        return ToolOutput(text, not result.success, metadata)
