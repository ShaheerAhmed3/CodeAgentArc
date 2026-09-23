from dataclasses import dataclass
from fnmatch import fnmatchcase
from itertools import islice
from pathlib import Path
import re
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
    require_desktop_game: bool = False
    max_entries: int = 10_000

    def __post_init__(self) -> None:
        if type(self.max_entries) is not int or self.max_entries < 1:
            raise ValueError("max_entries must be a positive integer")


_DESKTOP_UI_PATTERNS = {
    "Tkinter": r"(?:from\s+tkinter\s+import|import\s+tkinter\b|\btkinter\.(?:Tk|Toplevel)\s*\(|\bTk\s*\()",
    "PySide": r"(?:from|import)\s+PySide[26]\b",
    "PyQt": r"(?:from|import)\s+PyQt[56]\b",
    "pygame": r"(?:import|from)\s+pygame\b",
    "wxPython": r"(?:import|from)\s+wx\b",
    "Kivy": r"(?:import|from)\s+kivy\b",
    "Electron": r"(?:require\(['\"]electron['\"]\)|from\s+['\"]electron['\"]).*\bBrowserWindow\b",
    "Java Swing": r"(?:import\s+javax\.swing|javax\.swing\.)",
    ".NET desktop UI": r"(?:System\.Windows\.(?:Forms|Application)|Microsoft\.UI\.Xaml)",
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _desktop_game_checks(*, workspace: Workspace, files: list[Path], sources: list[Path],
                         tests: list[Path], readmes: list[Path]) -> list[ValidationCheck]:
    """Plausibility checks for the evaluator's local desktop-game contract."""
    source_text = "\n".join(_read_text(path) for path in sources)
    readme_text = "\n".join(_read_text(path) for path in readmes)
    test_texts = [_read_text(path) for path in tests]

    frameworks = [name for name, pattern in _DESKTOP_UI_PATTERNS.items()
                  if re.search(pattern, source_text, re.IGNORECASE | re.DOTALL)]
    checks = [ValidationCheck(
        "desktop_ui", bool(frameworks),
        "Local desktop GUI framework found: " + ", ".join(frameworks) if frameworks else
        "Missing local desktop GUI framework; backend-only and browser-only applications are not accepted",
    )]

    python_launches = re.findall(
        r"(?im)^\s*(?:python(?:3(?:\.\d+)?)?|py(?:\s+-3(?:\.\d+)?)?)\s+"
        r"(-m\s+[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|[A-Za-z0-9_./\\-]+\.py)\s*$",
        readme_text,
    )
    has_main_guard = bool(re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:", source_text))
    other_launch = bool(re.search(r"(?im)^\s*(?:npm\s+start|java\s+-jar\s+\S+|dotnet\s+run)\s*$", readme_text))
    runnable = bool((python_launches and has_main_guard) or (other_launch and frameworks))
    checks.append(ValidationCheck(
        "desktop_entrypoint", runnable,
        "README documents a desktop launch command backed by an executable entry point" if runnable else
        "Missing a documented desktop launch command and executable application entry point",
    ))

    browser_dependency = bool(re.search(
        r"(?i)(?:https?://(?:localhost|127\.0\.0\.1)|open\s+(?:the\s+)?(?:url|browser)|"
        r"(?:browser|web\s+browser)\s+(?:at|to|and)\s+https?://)", readme_text
    ))
    checks.append(ValidationCheck(
        "no_browser_dependency", not browser_dependency,
        "README launch flow does not require localhost or a browser" if not browser_dependency else
        "README launch flow requires localhost or a web browser",
    ))

    behavior_patterns = {
        "game start": r"\b(?:start|begin|new)_?game\b",
        "questions": r"\bquestions?\b",
        "answer checking": r"\b(?:check|validate|submit)_?answer\b|\bis_correct\b",
        "score tracking": r"\bscore\b",
        "game completion": r"\bgame_?over\b|\b(?:finish|end|complete)_?game\b",
    }
    missing_behavior = [name for name, pattern in behavior_patterns.items()
                        if not re.search(pattern, source_text, re.IGNORECASE)]
    checks.append(ValidationCheck(
        "game_functionality", not missing_behavior,
        "Game start, question, answer, score, and completion flows found" if not missing_behavior else
        "Missing plausible game behavior: " + ", ".join(missing_behavior),
    ))

    has_test_command = bool(re.search(
        r"(?im)^\s*(?:python(?:3(?:\.\d+)?)?|py(?:\s+-3(?:\.\d+)?)?)\s+-m\s+"
        r"(?:pytest|unittest)(?:\s+.*)?$|^\s*(?:pytest|npm\s+test|cargo\s+test|go\s+test)(?:\s+.*)?$",
        readme_text,
    ))
    checks.append(ValidationCheck(
        "readme_commands", bool(python_launches or other_launch) and has_test_command,
        "README documents exact launch and test commands" if has_test_command and (python_launches or other_launch) else
        "README must document exact desktop launch and test commands",
    ))

    domain_test = any(
        len(re.findall(r"(?i)\b(?:question|answer|score|game)\b", text)) >= 2
        and not re.search(r"(?i)\b(?:mainloop|pyautogui|selenium)\b", text)
        for text in test_texts
    )
    checks.append(ValidationCheck(
        "domain_tests", domain_test,
        "Non-interactive game/domain tests found" if domain_test else
        "Missing non-interactive tests for game/domain logic",
    ))
    return checks


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
        if policy.require_desktop_game:
            checks.extend(_desktop_game_checks(workspace=workspace, files=files, sources=sources,
                                               tests=tests, readmes=readmes))
    except (OSError, WorkspacePathError) as exc:
        checks.append(ValidationCheck("inventory", False, f"Could not inspect repository: {exc}"))
    for index, result in enumerate(command_results, 1):
        detail = result.error or f"Command exit code: {result.exit_code}"
        checks.append(ValidationCheck(f"command:{index}", result.success, detail))
    if not command_results:
        warnings.append("No build/test command evidence supplied; only repository structure was checked.")
    return ValidationReport(tuple(checks), tuple(warnings))
