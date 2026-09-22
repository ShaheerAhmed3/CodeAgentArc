from typing import Sequence

from code_agent.agent.models import ModelResponse
from code_agent.config import ProviderConfig
from code_agent.providers.base import LLMProvider, ProviderError
from code_agent.providers.mock import MockProvider


def create_provider(config: ProviderConfig, *, mock_responses: Sequence[ModelResponse] | None = None) -> LLMProvider:
    config.validate()
    if config.provider == "mock":
        return MockProvider(mock_responses if mock_responses is not None else [
            ModelResponse("Mock has no generation script; no repository was generated.")
        ])
    try:
        from code_agent.providers.gemini import GeminiProvider
    except ImportError:
        raise ProviderError("Install the Gemini extra: pip install -e '.[gemini]'") from None
    return GeminiProvider(api_key=config.api_key, model=config.model)
