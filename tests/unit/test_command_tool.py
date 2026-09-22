import os
from pathlib import Path
import sys

import pytest

from code_agent.agent.models import ToolCall
from code_agent.tools.command import RunCommandTool
from code_agent.tools.registry import ToolRegistry
from code_agent.workspace.workspace import Workspace


@pytest.fixture
def runner(tmp_path):
    return RunCommandTool(Workspace(tmp_path / "repo"), timeout=3, max_output_bytes=1024)


def dispatch(runner, arguments):
    registry = ToolRegistry()
    registry.register(runner)
    return registry.dispatch(ToolCall("command-1", "run_command", arguments))


def test_success_stdout_stderr_and_cwd(runner):
    result = runner.run([sys.executable, "-c", "import os,sys; print(os.getcwd()); print('diagnostic', file=sys.stderr)"])
    assert result.success
    assert Path(result.stdout.strip()) == runner.workspace.root
    assert result.stderr.strip() == "diagnostic"
    assert result.exit_code == 0


def test_nonzero_exit_is_a_correlated_error_observation(runner):
    result = dispatch(runner, {"command": [sys.executable, "-c", "import sys; print('failed'); sys.exit(7)"]})
    assert result.is_error
    assert result.call_id == "command-1"
    assert result.metadata["exit_code"] == 7
    assert "failed" in result.content


def test_timeout_returns_partial_output(runner):
    result = dispatch(runner, {"command": [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(10)"], "timeout": 0.5})
    assert result.is_error
    assert result.metadata["timed_out"]
    assert result.metadata["exit_code"] is None
    assert "timed out" in result.content
    assert "started" in result.metadata["stdout"]


def test_executable_not_found(runner):
    result = dispatch(runner, {"command": [str(runner.workspace.root / "missing-command-4839.exe")]})
    assert result.is_error
    assert "Executable not found" in result.content


def test_output_truncation_is_per_stream(runner):
    runner = RunCommandTool(runner.workspace, max_output_bytes=100)
    result = runner.run([sys.executable, "-c", "import sys; print('a'*200); print('b'*200, file=sys.stderr)"])
    assert result.success
    assert result.stdout == "a" * 100 and result.stderr == "b" * 100
    assert result.stdout_truncated and result.stderr_truncated


def test_arguments_are_passed_literally_without_shell(runner):
    literal = "hello && echo wrong; $PATH"
    result = runner.run([sys.executable, "-c", "import sys; print(sys.argv[1])", literal])
    assert result.stdout.strip() == literal


@pytest.mark.parametrize("arguments", [
    {"command": "python --version"}, {"command": []}, {"command": [""]},
    {"command": ["python", 1]}, {"command": ["python\x00"]},
    {"command": ["python"], "timeout": 0}, {"command": ["python"], "timeout": True},
    {"command": ["python"], "timeout": 999}, {"command": ["python"], "timeout": None},
    {"command": ["python"], "timeout": float("nan")},
])
def test_bad_command_inputs_become_observations(runner, arguments):
    assert dispatch(runner, arguments).is_error


@pytest.mark.skipif(os.name != "nt", reason="Windows implicit batch shell behavior")
def test_windows_batch_launchers_are_rejected(runner):
    result = dispatch(runner, {"command": ["build.cmd"]})
    assert result.is_error and "batch launchers" in result.content
