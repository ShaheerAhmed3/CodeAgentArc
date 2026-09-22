from dataclasses import replace
import sys

import pytest

from code_agent.tools.command import RunCommandTool
from code_agent.validation.validator import ValidationPolicy, validate_repository
from code_agent.workspace.workspace import Workspace


@pytest.fixture
def repository(tmp_path):
    workspace = Workspace(tmp_path / "repo")
    for path, text in {"README.md": "Example", "pyproject.toml": "[project]\nname='example'\n",
                       "src/app.py": "answer = 42\n", "tests/test_app.py": "def test_answer(): assert 42 == 42\n"}.items():
        target = workspace.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return workspace


def test_valid_repository_passes_structure_with_unverified_warning(repository):
    report = validate_repository(repository)
    assert report.success and not report.errors
    assert any("No build/test command evidence" in message for message in report.warnings)
    assert not repository.resolve("Dockerfile").exists()


@pytest.mark.parametrize("path,check", [
    ("README.md", "readme"), ("pyproject.toml", "dependencies"), ("src/app.py", "source"),
])
def test_missing_required_category_fails(repository, path, check):
    repository.resolve(path).unlink()
    report = validate_repository(repository)
    assert not report.success
    assert not next(item for item in report.checks if item.name == check).passed


def test_missing_tests_fails_but_empty_test_directory_is_reported(repository):
    repository.resolve("tests/test_app.py").unlink()
    report = validate_repository(repository)
    assert report.success
    assert any("no recognized test files" in warning for warning in report.warnings)
    repository.resolve("tests").rmdir()
    report = validate_repository(repository)
    assert not report.success and "Missing tests" in report.errors


@pytest.mark.parametrize("path", ["README.md", "pyproject.toml", "src/app.py", "tests/test_app.py"])
def test_empty_required_files_fail(repository, path):
    repository.resolve(path).write_bytes(b"")
    report = validate_repository(repository)
    assert not report.success
    assert any("Empty required files" in error and path in error for error in report.errors)


def test_empty_package_initializers_are_allowed(repository):
    repository.resolve("src/__init__.py").write_bytes(b"")
    repository.resolve("tests/__init__.py").write_bytes(b"")
    assert validate_repository(repository).success


def test_empty_repository_and_dependency_artifacts_do_not_pass(tmp_path):
    workspace = Workspace(tmp_path / "repo")
    assert not validate_repository(workspace).success
    target = workspace.resolve("node_modules/library/index.js")
    target.parent.mkdir(parents=True)
    target.write_text("export default 1", encoding="utf-8")
    assert not next(c for c in validate_repository(workspace).checks if c.name == "source").passed


def test_node_repository_and_custom_policy(tmp_path):
    workspace = Workspace(tmp_path)
    for path, content in {"README.md": "Example", "package.json": "{}", "app.js": "export default 1;", "app.test.js": "test('a', () => {});"}.items():
        workspace.resolve(path).write_text(content, encoding="utf-8")
    assert validate_repository(workspace).success
    workspace.resolve("app.js").rename(workspace.resolve("app.custom"))
    policy = replace(ValidationPolicy(), source_suffixes=(".custom", ".js"), required_files=("LICENSE",))
    assert not validate_repository(workspace, policy=policy).success
    workspace.resolve("LICENSE").write_text("Example license", encoding="utf-8")
    assert validate_repository(workspace, policy=policy).success


def test_command_evidence_is_checked_independently(repository):
    runner = RunCommandTool(repository)
    success = runner.run([sys.executable, "-c", "print('checked')"])
    failure = runner.run([sys.executable, "-c", "raise SystemExit(2)"])
    assert validate_repository(repository, command_results=[success]).success
    report = validate_repository(repository, command_results=[success, failure])
    assert not report.success
    assert "Command exit code: 2" in report.errors


def test_limits_and_unsafe_required_paths_fail_closed(repository):
    report = validate_repository(repository, policy=replace(ValidationPolicy(), max_entries=1))
    assert not report.success
    assert "validation incomplete" in report.errors[0]
    report = validate_repository(repository, policy=replace(ValidationPolicy(), required_files=("../secret",)))
    assert not report.success


def test_external_link_cannot_supply_source(repository, directory_link):
    repository.resolve("src/app.py").unlink()
    outside = repository.root.parent / "outside"
    outside.mkdir()
    (outside / "app.py").write_text("answer = 42", encoding="utf-8")
    directory_link(repository.root / "linked", outside)
    report = validate_repository(repository)
    assert not next(c for c in report.checks if c.name == "source").passed


def test_internal_link_alias_cannot_satisfy_required_path(repository, directory_link):
    actual = repository.resolve("actual")
    actual.mkdir()
    (actual / "README.md").write_text("Real document", encoding="utf-8")
    directory_link(repository.root / "linked", actual)
    policy = replace(ValidationPolicy(), readmes=("linked/README.md",), required_files=("linked/README.md",))
    report = validate_repository(repository, policy=policy)
    assert not report.success
    assert not next(c for c in report.checks if c.name == "readme").passed
    assert not next(c for c in report.checks if c.name == "required:linked/README.md").passed
