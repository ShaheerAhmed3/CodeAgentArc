import os

import pytest

from code_agent.agent.models import ModelResponse
from code_agent.config import ConfigurationError, ProviderConfig, load_config
from code_agent.providers.factory import create_provider
from code_agent.providers.mock import MockProvider


def test_dotenv_precedence_and_no_environment_mutation(tmp_path):
    path = tmp_path / ".env"
    path.write_text("CODE_AGENT_PROVIDER=gemini\nCODE_AGENT_MODEL=from-file\nGEMINI_API_KEY=offline-file-credential\n", encoding="utf-8")
    before = dict(os.environ)
    original = path.read_bytes()
    config = load_config(env_file=path, environ={})
    assert config.model == "from-file"
    assert config.api_key == "offline-file-credential"
    assert config.api_key not in repr(config)
    config = load_config(env_file=path, environ={"CODE_AGENT_MODEL": "from-env"}, model="from-cli")
    assert config.model == "from-cli"
    assert dict(os.environ) == before
    assert path.read_bytes() == original


def test_blank_environment_key_overrides_dotenv(tmp_path):
    path = tmp_path / ".env"
    path.write_text("GEMINI_API_KEY=offline-file-credential\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Configure GEMINI_API_KEY"):
        load_config(env_file=path, environ={"GEMINI_API_KEY": ""})


def test_default_model_and_mock_selection(tmp_path):
    config = load_config(env_file=tmp_path / "absent", environ={"GEMINI_API_KEY": "offline-credential"})
    assert config.model == "gemini-3.8-flash"
    mock = load_config(env_file=tmp_path / "absent", environ={}, provider="mock")
    adapter = create_provider(mock, mock_responses=[ModelResponse("done")])
    assert isinstance(adapter, MockProvider)
    assert adapter.complete([], []) == ModelResponse("done")


def test_unknown_provider_does_not_echo_configuration():
    with pytest.raises(ConfigurationError) as caught:
        create_provider(ProviderConfig("private-sentinel", "m", "secret-sentinel"))
    assert "private-sentinel" not in str(caught.value)
    assert "secret-sentinel" not in str(caught.value)


def test_gemini_selection_uses_adapter_only_at_factory(monkeypatch):
    pytest.importorskip("google.genai")
    captured = {}
    sentinel = object()

    def adapter(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("code_agent.providers.gemini.GeminiProvider", adapter)
    assert create_provider(ProviderConfig("gemini", "selected-model", "offline-credential")) is sentinel
    assert captured["model"] == "selected-model"


def test_example_is_secret_free_and_env_ignore_rule_is_present(project_root):
    from dotenv import dotenv_values
    assert dotenv_values(project_root / ".env.example")["GEMINI_API_KEY"] == ""
    rules = (project_root / ".gitignore").read_text().splitlines()
    assert ".env" in rules
    assert "!.env" not in rules
