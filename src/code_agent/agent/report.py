from dataclasses import dataclass

from code_agent.agent.models import AgentResult
from code_agent.validation.validator import ValidationReport


@dataclass(frozen=True)
class GenerationReport:
    """Compose loop outcome and independent validation without changing the loop."""

    execution: AgentResult
    validation: ValidationReport
    provider: str = ""
    model: str = ""
    error: str | None = None
    error_status_code: int | None = None
    error_category: str | None = None
    error_retryable: bool = False

    @property
    def success(self) -> bool:
        return self.execution.stop_reason == "final_response" and self.validation.success

    @property
    def maximum_turns_reached(self) -> bool:
        return self.execution.stop_reason == "max_turns"
