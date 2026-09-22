from typing import Protocol

from code_agent.agent.models import JSONValue, ToolDefinition, ToolOutput


class ToolInputError(ValueError):
    """An expected argument error that the model may correct on its next turn."""


class Tool(Protocol):
    @property
    def definition(self) -> ToolDefinition: ...

    def execute(self, arguments: dict[str, JSONValue]) -> str | ToolOutput:
        """Validate arguments and execute; raise ToolInputError for bad input.

        The schema describes inputs to the model. Each implementation enforces
        its own constraints; the registry is not a general JSON Schema engine.
        """
        ...


def check_keys(arguments: dict[str, JSONValue], allowed: set[str]) -> None:
    unknown = arguments.keys() - allowed
    if unknown:
        raise ToolInputError(f"Unknown arguments: {', '.join(sorted(unknown))}")


def text_argument(arguments: dict[str, JSONValue], name: str, default: str | None = None) -> str:
    value = arguments.get(name, default)
    if not isinstance(value, str):
        raise ToolInputError(f"{name} must be a string")
    return value


def bool_argument(arguments: dict[str, JSONValue], name: str, default: bool = False) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise ToolInputError(f"{name} must be a boolean")
    return value


def string_list_argument(arguments: dict[str, JSONValue], name: str,
                         default: list[str] | None = None) -> list[str]:
    value = arguments.get(name, default)
    if not isinstance(value, list):
        raise ToolInputError(f"{name} must be a list of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ToolInputError(f"{name} must be a list of strings")
        result.append(item)
    return result


def positive_integer(arguments: dict[str, JSONValue], name: str, default: int) -> int:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolInputError(f"{name} must be a positive integer")
    return value


def definition(name: str, description: str, properties: dict[str, JSONValue], required: list[str]) -> ToolDefinition:
    return ToolDefinition(name, description, {
        "type": "object", "properties": properties,
        "required": required, "additionalProperties": False,
    })
