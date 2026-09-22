import argparse
from pathlib import Path
import sys
from typing import NoReturn

from code_agent.architecture.normalizer import normalize_architecture
from code_agent.config import ConfigurationError, load_config
from code_agent.generation import generate, verify_existing


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse normally echoes unknown/invalid argument values, possibly secrets.
        self.print_usage(sys.stderr)
        self.exit(2, "code-agent: Invalid arguments; use --help for options and value types.\n")


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(description="Iterative architecture-to-code agent")
    commands = parser.add_subparsers(dest="command", required=True)
    normalize = commands.add_parser("normalize", help="Extract source-preserving architecture JSON")
    normalize.add_argument("--documentation", type=Path, default=Path("Architecture_Documentation.md"))
    normalize.add_argument("--views", type=Path, default=Path("Architecture_View.md"))
    normalize.add_argument("--output", type=Path, help="New output file; existing files are never overwritten")
    generation = commands.add_parser("generate", help="Generate into a new or empty directory under generated/")
    generation.add_argument("--architecture-doc", type=Path, default=Path("Architecture_Documentation.md"))
    generation.add_argument("--architecture-view", type=Path, default=Path("Architecture_View.md"))
    generation.add_argument("--output", type=Path, required=True)
    generation.add_argument("--provider", help="gemini, openai, or mock (default from environment/.env)")
    generation.add_argument("--model", help="Model override (no key argument is accepted)")
    generation.add_argument("--max-turns", type=int, default=20)
    verification = commands.add_parser("verify", help="Recheck final files of a completed generation")
    verification.add_argument("--output", type=Path, required=True)
    verification.add_argument("--command", dest="verify_command", nargs=argparse.REMAINDER, required=True,
                              help="Test/build command and arguments, for example npm test")
    args = parser.parse_args(argv)
    if args.command == "verify":
        try:
            passed = verify_existing(project_root=Path.cwd(), output=args.output, command=args.verify_command)
        except (ConfigurationError, OSError, ValueError):
            print("code-agent: Could not verify output; check the generated path and command", file=sys.stderr)
            return 5
        print("Final generated repository validation passed." if passed else
              "Final generated repository validation failed. See .codeagent/generation_report.json.")
        return 0 if passed else 1
    if args.command == "generate":
        try:
            config = load_config(provider=args.provider, model=args.model)
            report = generate(architecture_doc=args.architecture_doc, architecture_view=args.architecture_view,
                              output=args.output, config=config, project_root=Path.cwd(), max_turns=args.max_turns)
        except ConfigurationError as exc:
            print(f"code-agent: {exc}", file=sys.stderr)
            return 2
        except (OSError, ValueError):
            print("code-agent: Input/output failure; check architecture files and output permissions", file=sys.stderr)
            return 5
        if report.execution.stop_reason == "provider_error":
            print(f"code-agent: {report.error}", file=sys.stderr)
            return 4
        if report.execution.stop_reason == "runtime_error":
            print(f"code-agent: {report.error}", file=sys.stderr)
            return 5
        if report.maximum_turns_reached:
            print("Agent reached maximum turns; generation incomplete.")
            return 3
        if not report.validation.success:
            print("Agent completed, but deterministic validation failed. See .codeagent/generation_report.json.")
            return 1
        print("Agent completed and deterministic validation passed. See .codeagent/generation_report.json.")
        return 0
    try:
        architecture = normalize_architecture(args.documentation, args.views)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(architecture.to_json())
        else:
            sys.stdout.write(architecture.to_json())
    except (OSError, ValueError) as exc:
        print(f"code-agent: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
