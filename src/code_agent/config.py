"""Explicit provider configuration without changing the process environment."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_OPENAI_MODEL = "gpt-5"


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "gemini"
    model: str = DEFAULT_GEMINI_MODEL
    api_key: str = field(default="", repr=False)

    def validate(self) -> None:
        if self.provider not in {"mock", "gemini", "openai"}:
            raise ConfigurationError("Unknown provider; choose mock, gemini, or openai")
        if not self.model.strip():
            raise ConfigurationError("Configure CODE_AGENT_MODEL or --model")
        if self.provider == "gemini" and not self.api_key.strip():
            raise ConfigurationError("Configure GEMINI_API_KEY in your environment or local .env")
        if self.provider == "openai" and not self.api_key.strip():
            raise ConfigurationError("Configure OPENAI_API_KEY in your environment or local .env")


def load_config(*, env_file: Path = Path(".env"), environ: Mapping[str, str] | None = None,
                provider: str | None = None, model: str | None = None) -> ProviderConfig:
    # Keep .env credentials out of os.environ and therefore out of child commands.
    values = dict(dotenv_values(env_file, interpolate=False)) if env_file.is_file() else {}
    values.update(os.environ if environ is None else environ)
    configured_provider = (values.get("CODE_AGENT_PROVIDER") or "gemini").strip().lower()
    selected = (provider if provider is not None else configured_provider).strip().lower()
    default_model = {"gemini": DEFAULT_GEMINI_MODEL, "openai": DEFAULT_OPENAI_MODEL}.get(selected, "scripted")
    # A CLI provider switch should not inherit the configured provider's model name.
    inherited_model = None if provider is not None and selected != configured_provider else values.get("CODE_AGENT_MODEL")
    selected_model = model if model is not None else inherited_model or default_model
    key_name = "OPENAI_API_KEY" if selected == "openai" else "GEMINI_API_KEY"
    config = ProviderConfig(selected, selected_model.strip(), (values.get(key_name) or "").strip())
    config.validate()
    return config
