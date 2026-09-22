"""Explicit provider configuration without changing the process environment."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "gemini"
    model: str = DEFAULT_GEMINI_MODEL
    api_key: str = field(default="", repr=False)

    def validate(self) -> None:
        if self.provider not in {"mock", "gemini"}:
            raise ConfigurationError("Unknown provider; choose mock or gemini")
        if not self.model.strip():
            raise ConfigurationError("Configure CODE_AGENT_MODEL or --model")
        if self.provider == "gemini" and not self.api_key.strip():
            raise ConfigurationError("Configure GEMINI_API_KEY in your environment or local .env")


def load_config(*, env_file: Path = Path(".env"), environ: Mapping[str, str] | None = None,
                provider: str | None = None, model: str | None = None) -> ProviderConfig:
    # Keep .env credentials out of os.environ and therefore out of child commands.
    values = dict(dotenv_values(env_file, interpolate=False)) if env_file.is_file() else {}
    values.update(os.environ if environ is None else environ)
    selected = (provider if provider is not None else values.get("CODE_AGENT_PROVIDER") or "gemini").strip().lower()
    selected_model = model if model is not None else values.get("CODE_AGENT_MODEL") or (
        DEFAULT_GEMINI_MODEL if selected == "gemini" else "scripted"
    )
    config = ProviderConfig(selected, selected_model.strip(), (values.get("GEMINI_API_KEY") or "").strip())
    config.validate()
    return config
