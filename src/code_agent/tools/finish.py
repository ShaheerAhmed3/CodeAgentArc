from code_agent.agent.models import CompletionInfo, JSONValue, ToolOutput
from code_agent.tools.base import ToolInputError, check_keys, definition, string_list_argument, text_argument


class FinishTool:
    definition = definition("finish", "Record completion claims, then return a final response. This does not validate the repository.", {
        "summary": {"type": "string", "minLength": 1},
        "tests_run": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    }, ["summary"])

    def execute(self, arguments: dict[str, JSONValue]) -> ToolOutput:
        check_keys(arguments, {"summary", "tests_run", "assumptions", "warnings"})
        summary = text_argument(arguments, "summary")
        if not summary.strip():
            raise ToolInputError("summary must not be empty")
        fields: dict[str, tuple[str, ...]] = {}
        for name in ("tests_run", "assumptions", "warnings"):
            fields[name] = tuple(string_list_argument(arguments, name, []))
        completion = CompletionInfo(summary, **fields)
        return ToolOutput("Completion details recorded. Return your final response; validation runs separately.",
                          completion=completion)
