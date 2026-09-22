import json
import sys

from code_agent.agent.loop import AgentLoop
from code_agent.agent.models import Message, ModelResponse, ToolCall
from code_agent.agent.report import GenerationReport
from code_agent.providers.mock import MockProvider
from code_agent.tools import coding_tools
from code_agent.tools.command import CommandResult
from code_agent.validation.validator import validate_repository
from code_agent.workspace.workspace import Workspace


def test_concrete_registry_definitions_and_dispatch(tmp_path):
    registry = coding_tools(Workspace(tmp_path))
    assert {tool.name for tool in registry.definitions()} == {
        "read_file", "write_file", "edit_file", "list_files", "search_files", "run_command", "finish",
    }
    for definition in registry.definitions():
        assert json.loads(json.dumps(definition.input_schema))["type"] == "object"
    assert registry.dispatch(ToolCall("1", "missing", {})).is_error
    assert registry.dispatch(ToolCall("2", "finish", {"summary": ""})).is_error
    assert registry.dispatch(ToolCall("3", "finish", {"summary": "done", "tests_run": "claimed"})).is_error


def test_mock_writes_reads_verifies_and_records_completion(tmp_path):
    workspace = Workspace(tmp_path / "generated")
    registry = coding_tools(workspace)
    files = {
        "README.md": "Minimal generated fixture\n",
        "requirements.txt": "# No third-party dependencies\n",
        "app.py": "def answer():\n    return 42\n",
        "tests/test_app.py": "import unittest\nfrom app import answer\n\nclass TestAnswer(unittest.TestCase):\n    def test_answer(self):\n        self.assertEqual(answer(), 42)\n",
    }
    provider = MockProvider([
        ModelResponse(tool_calls=tuple(ToolCall(f"write-{i}", "write_file", {"path": path, "content": content})
                                       for i, (path, content) in enumerate(files.items()))),
        ModelResponse(tool_calls=(ToolCall("read", "read_file", {"path": "app.py"}),)),
        ModelResponse(tool_calls=(ToolCall("test", "run_command", {"command": [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]}),)),
        ModelResponse(tool_calls=(ToolCall("finish", "finish", {"summary": "Created a minimal repository", "tests_run": ["unittest discover -s tests -v"], "assumptions": ["Standard library only"]}),)),
        ModelResponse("Repository created; one test passed."),
    ])
    result = AgentLoop(provider, registry).run([Message("user", "Create a small fixture and verify it.")])
    assert result.turns == 5
    assert result.tool_calls_executed == 7
    assert "return 42" in provider.requests[2].messages[-1].tool_result.content
    command_observation = provider.requests[3].messages[-1].tool_result
    assert not command_observation.is_error
    assert command_observation.metadata["exit_code"] == 0
    assert "Ran 1 test" in command_observation.metadata["stderr"]
    assert result.completion.summary == "Created a minimal repository"
    assert result.completion.assumptions == ("Standard library only",)
    assert provider.requests[4].messages[-1].tool_result.completion == result.completion
    command = CommandResult(**{**command_observation.metadata, "command": tuple(command_observation.metadata["command"])})
    report = GenerationReport(result, validate_repository(workspace, command_results=[command]))
    assert report.success and not report.maximum_turns_reached


def test_finish_claims_do_not_override_validation_or_turn_limit(tmp_path):
    workspace = Workspace(tmp_path)
    provider = MockProvider([
        ModelResponse(tool_calls=(ToolCall("finish", "finish", {"summary": "Everything passed", "tests_run": ["claimed tests"]}),)),
    ])
    result = AgentLoop(provider, coding_tools(workspace), max_turns=1).run([])
    report = GenerationReport(result, validate_repository(workspace))
    assert result.completion.summary == "Everything passed"
    assert result.final_answer is None
    assert report.maximum_turns_reached and not report.success
    assert not report.validation.success


def test_command_failure_is_observed_before_model_retries(tmp_path):
    workspace = Workspace(tmp_path)
    provider = MockProvider([
        ModelResponse(tool_calls=(ToolCall("fail", "run_command", {"command": [sys.executable, "-c", "raise SystemExit(3)"]}),)),
        ModelResponse(tool_calls=(ToolCall("retry", "run_command", {"command": [sys.executable, "-c", "print('ok')"]}),)),
        ModelResponse("Retried successfully"),
    ])
    result = AgentLoop(provider, coding_tools(workspace)).run([])
    assert provider.requests[1].messages[-1].tool_result.is_error
    assert provider.requests[2].messages[-1].tool_result.metadata["stdout"].strip() == "ok"
    assert result.tool_calls_executed == 2
