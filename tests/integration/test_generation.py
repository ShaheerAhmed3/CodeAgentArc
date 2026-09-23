from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from code_agent.agent.models import ModelResponse, ToolCall
from code_agent.agent.prompts import architecture_context
from code_agent.config import ConfigurationError, ProviderConfig
from code_agent.generation import generate, prepare_output
from code_agent.providers.base import ProviderError


@pytest.fixture
def generation_args(tmp_path):
    doc, view = tmp_path / "architecture.md", tmp_path / "views.md"
    doc.write_text("# A. Executive Summary\nThe Example system computes an answer.\n\nChosen architectural style: Modular\n", encoding="utf-8")
    view.write_text("## LogicView\n1. Class — Logic View: Example\n```plantuml\n@startuml Example\nclass Answer\n@enduml\n```", encoding="utf-8")
    return dict(architecture_doc=doc, architecture_view=view, output=tmp_path / "generated" / "example",
                config=ProviderConfig("mock", "scripted"), project_root=tmp_path)


def script():
    files = {
        "README.md": "# Example\n\nRun:\n```sh\npython main.py\n```\n\nTest:\n```sh\npython -m unittest discover -s tests\n```\n",
        "requirements.txt": "# standard library only\n",
        "main.py": "class Game:\n    def start_game(self): self.question = '1/2'\n    def check_answer(self, answer): self.score = int(answer == '1/2')\n    def finish_game(self): self.game_over = True\n\ndef main():\n    import tkinter as tk\n    root = tk.Tk()\n    root.title('Question Game')\n    root.mainloop()\n\nif __name__ == '__main__':\n    main()\n",
        "tests/test_game.py": "import unittest\nfrom main import Game\nclass TestGame(unittest.TestCase):\n    def test_answer_updates_score(self):\n        game = Game(); game.start_game(); game.check_answer('1/2'); self.assertEqual(game.score, 1)\n",
    }
    return [
        ModelResponse(tool_calls=tuple(ToolCall(f"write-{i}", "write_file", {"path": path, "content": content}) for i, (path, content) in enumerate(files.items()))),
        ModelResponse(tool_calls=(ToolCall("read", "read_file", {"path": "main.py"}),)),
        ModelResponse(tool_calls=(ToolCall("test", "run_command", {"command": [sys.executable, "-m", "unittest", "discover", "-s", "tests"], "verification": True}),)),
        ModelResponse(tool_calls=(ToolCall("finish", "finish", {"summary": "Example implemented", "tests_run": ["unittest discover -s tests"]}),)),
        ModelResponse("Example ready"),
    ]


def test_context_uses_normalized_sections_and_all_diagrams_without_raw_duplicates(architecture):
    text = architecture_context(architecture)
    data = json.loads(text)
    assert data["project_name"] == "Space Fractions"
    assert data["architectural_style"] == "Microservices"
    assert len(data["architectural_views"]) == 13
    assert data["architectural_views"][-1]["diagram_name"] == "ContainerDiagram"
    assert "text" not in data["sources"][0]
    assert all(isinstance(section_id, str) for section_id in data["assumptions"])
    assert "1000 users concurrently" in text
    assert len(text) < len(architecture.to_json())


def test_offline_generation_pipeline_reports_and_traces(generation_args, monkeypatch):
    from code_agent.providers.mock import MockProvider
    provider = MockProvider(script())
    monkeypatch.setattr("code_agent.generation.create_provider", lambda *args, **kwargs: provider)
    report = generate(**generation_args)
    assert report.success
    assert report.execution.turns == 5
    assert report.execution.tool_calls_executed == 7
    assert "@startuml Example" in provider.requests[0].messages[2].content
    assert "verification=true" in provider.requests[0].messages[0].content
    artifacts = generation_args["output"] / ".codeagent"
    data = json.loads((artifacts / "generation_report.json").read_text())
    assert data["provider"] == "mock" and data["success"]
    assert data["verification"][0]["exit_code"] == 0
    assert data["tool_counts"]["write_file"] == 4
    trace = (artifacts / "run.jsonl").read_text()
    events = [json.loads(line) for line in trace.splitlines()]
    assert events[-1]["event"] == "run_end"
    assert "start_game" not in trace
    assert "Example ready" not in trace
    assert any(event.get("content_characters") for event in events)
    assert any(event.get("exit_code") == 0 for event in events)


@pytest.mark.parametrize("suffix", [".", "generated", "../escape", "src/project"])
def test_output_must_be_dedicated_generated_subdirectory(tmp_path, suffix):
    with pytest.raises(ConfigurationError):
        prepare_output(tmp_path, tmp_path / suffix)


def test_nonempty_output_is_not_overwritten(generation_args):
    output = generation_args["output"]
    output.mkdir(parents=True)
    (output / "keep").write_text("original")
    with pytest.raises(ConfigurationError, match="empty"):
        generate(**generation_args, mock_responses=script())
    assert (output / "keep").read_text() == "original"


def test_empty_output_allowed_and_symlink_output_rejected(generation_args, directory_link):
    output = generation_args["output"]
    output.mkdir(parents=True)
    assert generate(**generation_args, mock_responses=script()).success
    target = generation_args["project_root"] / "elsewhere"
    target.mkdir()
    alias = output.parent / "alias"
    directory_link(alias, target)
    with pytest.raises(ConfigurationError, match="symlinks"):
        prepare_output(generation_args["project_root"], alias)
    assert not list(target.iterdir())


def test_final_response_without_repository_fails_validation(generation_args):
    report = generate(**generation_args, mock_responses=[ModelResponse("done")])
    assert not report.success
    assert "Missing README" in report.validation.errors
    assert any("No verification=true" in error for error in report.validation.errors)


def test_max_turns_and_provider_failure_preserve_outcome(generation_args, monkeypatch):
    report = generate(**generation_args, mock_responses=script(), max_turns=1)
    assert report.maximum_turns_reached and not report.success
    generation_args["output"] = generation_args["output"].parent / "failed"

    def fail(*args, **kwargs):
        raise ProviderError("Provider unavailable")

    monkeypatch.setattr("code_agent.generation.create_provider", fail)
    report = generate(**generation_args)
    assert report.execution.stop_reason == "provider_error"
    assert not report.success
    assert (generation_args["output"] / ".codeagent/generation_report.json").is_file()


def test_runtime_failure_has_generic_safe_error(generation_args):
    report = generate(**generation_args, mock_responses=[])
    assert report.execution.stop_reason == "runtime_error"
    assert "Tool/runtime failure" in report.error


def test_verification_before_last_edit_is_not_final_evidence(generation_args):
    responses = script()
    responses.insert(3, ModelResponse(tool_calls=(ToolCall("edit", "edit_file", {"path": "README.md", "old_text": "Example", "new_text": "Edited example"}),)))
    report = generate(**generation_args, mock_responses=responses)
    assert not report.success
    assert any("final file edits" in error for error in report.validation.errors)


def test_ordinary_command_invalidates_prior_verification(generation_args):
    responses = script()
    responses.insert(3, ModelResponse(tool_calls=(ToolCall("later", "run_command", {
        "command": [sys.executable, "-c", "print('ordinary command')"],
    }),)))
    report = generate(**generation_args, mock_responses=responses)
    assert not report.success


def test_final_failed_verification_is_a_validation_failure(generation_args):
    responses = script()
    responses[2] = ModelResponse(tool_calls=(ToolCall("test", "run_command", {
        "command": [sys.executable, "-c", "raise SystemExit(7)"], "verification": True,
    }),))
    report = generate(**generation_args, mock_responses=responses)
    assert not report.success
    assert "Command exit code: 7" in report.validation.errors


def test_failed_test_repair_and_rerun_can_pass(generation_args):
    responses = script()
    calls = list(responses[0].tool_calls)
    calls[2] = replace(calls[2], arguments={"path": "main.py", "content": "class Game:\n    def start_game(self): self.question = '1/2'\n    def check_answer(self, answer): self.score = 41\n    def finish_game(self): self.game_over = True\n\ndef main():\n    import tkinter as tk\n    root = tk.Tk(); root.mainloop()\n\nif __name__ == '__main__': main()\n"})
    responses[0] = ModelResponse(tool_calls=tuple(calls))
    responses.insert(3, ModelResponse(tool_calls=(ToolCall("repair", "edit_file", {"path": "main.py", "old_text": "41", "new_text": "1"}),)))
    responses.insert(4, ModelResponse(tool_calls=(replace(responses[2].tool_calls[0], id="retest"),)))
    report = generate(**generation_args, mock_responses=responses)
    assert report.success
    events = [json.loads(line) for line in (generation_args["output"] / ".codeagent/run.jsonl").read_text().splitlines()]
    assert [event["exit_code"] for event in events if "exit_code" in event] == [1, 0]


def test_known_secret_is_redacted_and_not_inherited(generation_args, monkeypatch):
    sentinel = "offline-private-sentinel"
    monkeypatch.setenv("GEMINI_API_KEY", sentinel)
    generation_args["config"] = ProviderConfig("mock", "scripted", sentinel)
    responses = script()
    # Verify only a boolean in the child; never print the environment itself.
    responses[2] = ModelResponse(tool_calls=(ToolCall("test", "run_command", {
        "command": [sys.executable, "-c", "import os; assert 'GEMINI_API_KEY' not in os.environ"], "verification": True,
    }),))
    responses[-1] = ModelResponse("Model echoed " + sentinel)
    report = generate(**generation_args, mock_responses=responses)
    assert report.success
    for path in (generation_args["output"] / ".codeagent").iterdir():
        assert sentinel not in path.read_text()


def test_reserved_metadata_directory_cannot_be_written_by_tools(generation_args):
    report = generate(**generation_args, mock_responses=[
        ModelResponse(tool_calls=(ToolCall("bad", "write_file", {"path": ".codeagent/generation_report.json", "content": "forged"}),)),
        ModelResponse("done"),
    ])
    assert report.execution.messages[-2].tool_result.is_error
    assert not report.success
