from dataclasses import dataclass
from fnmatch import fnmatchcase
from itertools import islice
from pathlib import Path
from typing import Sequence

from code_agent.tools.command import CommandResult
from code_agent.workspace.workspace import Workspace, WorkspacePathError


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    checks: tuple[ValidationCheck, ...]
    warnings: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(check.detail for check in self.checks if not check.passed)


@dataclass(frozen=True)
class ValidationPolicy:
    readmes: tuple[str, ...] = ("README.md", "README.rst", "README.txt", "README")
    manifests: tuple[str, ...] = ("pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod", "pom.xml")
    source_suffixes: tuple[str, ...] = (".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".cs", ".rb", ".php", ".html", ".vue", ".svelte")
    test_directories: tuple[str, ...] = ("tests", "test", "__tests__", "spec")
    test_patterns: tuple[str, ...] = ("test_*.py", "*_test.py", "*.test.*", "*.spec.*", "*_test.go", "*Test.java", "*Tests.cs")
    ignored_directories: frozenset[str] = frozenset({".git", ".codeagent", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "build", "dist"})
    required_files: tuple[str, ...] = ()
    max_entries: int = 10_000

    def __post_init__(self) -> None:
        if type(self.max_entries) is not int or self.max_entries < 1:
            raise ValueError("max_entries must be a positive integer")


def validate_repository(workspace: Workspace, *, policy: ValidationPolicy | None = None,
                        command_results: Sequence[CommandResult] = ()) -> ValidationReport:
    """Check artifacts and optional caller-supplied command evidence, not code quality."""
    policy = policy or ValidationPolicy()
    checks: list[ValidationCheck] = []
    warnings = ["Linked entries are excluded from repository inventory."]
    try:
        entries = list(islice(workspace.walk(ignored_directories=policy.ignored_directories), policy.max_entries + 1))
        if len(entries) > policy.max_entries:
            return ValidationReport((ValidationCheck("inventory", False, "Repository exceeds inventory limit; validation incomplete"),))
        files = [path for path in entries if path.is_file()]
        directories = [path for path in entries if path.is_dir()]
        checks.append(ValidationCheck("not_empty", bool(files), "Repository contains files" if files else "Repository has no files"))

        def named_files(names: tuple[str, ...]) -> list[Path]:
            # Only inventory members can satisfy requirements; links never count.
            found: list[Path] = []
            for name in names:
                workspace.resolve(name)
                literal = workspace.root / name.replace("\\", "/")
                if literal in files:
                    found.append(literal)
            return found

        readmes, manifests = named_files(policy.readmes), named_files(policy.manifests)
        checks.append(ValidationCheck("readme", bool(readmes), "README found" if readmes else "Missing README"))
        checks.append(ValidationCheck("dependencies", bool(manifests), "Dependency manifest found" if manifests else "Missing dependency manifest"))

        def is_test(path: Path) -> bool:
            relative = path.relative_to(workspace.root)
            return (any(part in policy.test_directories for part in relative.parts[:-1])
                    or any(fnmatchcase(path.name, pattern) for pattern in policy.test_patterns))

        code = [path for path in files if path.suffix.lower() in policy.source_suffixes
                and path.name not in {"__init__.py", "conftest.py", "setup.py"}]
        tests = [path for path in code if is_test(path)]
        sources = [path for path in code if not is_test(path) and path not in readmes + manifests]
        test_dirs = [path for path in directories if path.name in policy.test_directories]
        checks.append(ValidationCheck("source", bool(sources), "Application source found" if sources else "Missing application source files"))
        checks.append(ValidationCheck("tests", bool(tests or test_dirs), "Tests or test directory found" if tests or test_dirs else "Missing tests"))
        if test_dirs and not tests:
            warnings.append("Test directory exists but no recognized test files were found.")
        required = list(dict.fromkeys(readmes + manifests + sources + tests))
        for name in policy.required_files:
            found = named_files((name,))
            exists = bool(found)
            checks.append(ValidationCheck(f"required:{name}", exists, f"Required file {'found' if exists else 'missing'}: {name}"))
            if exists:
                required.extend(found)
        empty = [path.relative_to(workspace.root).as_posix() for path in required if path.stat().st_size == 0]
        checks.append(ValidationCheck("nonempty_files", not empty,
                                      "Required files have content" if not empty else "Empty required files: " + ", ".join(empty)))
    except (OSError, WorkspacePathError) as exc:
        checks.append(ValidationCheck("inventory", False, f"Could not inspect repository: {exc}"))
    for index, result in enumerate(command_results, 1):
        detail = result.error or f"Command exit code: {result.exit_code}"
        checks.append(ValidationCheck(f"command:{index}", result.success, detail))
    if not command_results:
        warnings.append("No build/test command evidence supplied; only repository structure was checked.")
    return ValidationReport(tuple(checks), tuple(warnings))
