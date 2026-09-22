import json
import pytest

from code_agent.cli import main


def setup_inputs(tmp_path):
    (tmp_path / "Architecture_Documentation.md").write_text("# Summary\nExample", encoding="utf-8")
    (tmp_path / "Architecture_View.md").write_text("", encoding="utf-8")


def test_generate_requires_output_and_positive_turn_count(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(["generate"])
    assert caught.value.code == 2
    assert main(["generate", "--output", "generated/x", "--provider", "mock", "--max-turns", "0"]) == 2
    assert not (tmp_path / "generated/x").exists()


def test_missing_key_fails_without_creating_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert main(["generate", "--output", "generated/x", "--provider", "gemini"]) == 2
    assert "Configure GEMINI_API_KEY" in capsys.readouterr().err
    assert not (tmp_path / "generated/x").exists()


def test_cli_mock_and_model_override_offline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    setup_inputs(tmp_path)
    assert main(["generate", "--provider", "mock", "--model", "fixture", "--output", "generated/demo"]) == 1
    report = json.loads((tmp_path / "generated/demo/.codeagent/generation_report.json").read_text())
    assert report["provider"] == "mock" and report["model"] == "fixture"
    assert report["stop_reason"] == "final_response"


def test_cli_provider_failure_never_prints_key(tmp_path, monkeypatch, capsys):
    from code_agent.providers.base import ProviderError
    monkeypatch.chdir(tmp_path)
    setup_inputs(tmp_path)
    sentinel = "offline-secret-for-cli"
    monkeypatch.setenv("GEMINI_API_KEY", sentinel)

    def fail(*args, **kwargs):
        raise ProviderError("failed " + sentinel)

    monkeypatch.setattr("code_agent.generation.create_provider", fail)
    assert main(["generate", "--provider", "gemini", "--output", "generated/demo"]) == 4
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err


def test_help_and_key_not_accepted_as_cli_option(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["generate", "--help"])
    assert caught.value.code == 0
    assert "--architecture-doc" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        main(["generate", "--output", "generated/demo", "--api-key", "offline-argument-secret"])
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert "offline-argument-secret" not in captured.out + captured.err


@pytest.mark.parametrize("stop,valid,code", [("final_response", True, 0), ("final_response", False, 1), ("max_turns", True, 3), ("runtime_error", False, 5)])
def test_cli_exit_codes(tmp_path, monkeypatch, stop, valid, code):
    from code_agent.agent.models import AgentResult
    from code_agent.agent.report import GenerationReport
    from code_agent.validation.validator import ValidationCheck, ValidationReport
    monkeypatch.chdir(tmp_path)
    result = GenerationReport(AgentResult("done", (), 1, stop),
                              ValidationReport((ValidationCheck("fixture", valid, "fixture"),)), error="Safe runtime error")
    monkeypatch.setattr("code_agent.cli.generate", lambda **kwargs: result)
    assert main(["generate", "--provider", "mock", "--output", "generated/example"]) == code
