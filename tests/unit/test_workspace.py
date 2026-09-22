import os
import subprocess

import pytest

from code_agent.workspace.workspace import Workspace, WorkspacePathError


@pytest.mark.parametrize("path", [
    "../../outside", "a/../../outside", r"..\outside", "/tmp/outside",
    r"C:\outside", "C:outside", r"\\server\share\file", r"\rooted",
    "file:stream", "NUL", "CON.txt", "COM1", "trailing.", "trailing ", "bad\x00name", "",
])
def test_rejects_unsafe_paths(tmp_path, path):
    workspace = Workspace(tmp_path / "generated")
    with pytest.raises(WorkspacePathError):
        workspace.resolve(path)


def test_resolves_nested_paths_and_root(tmp_path):
    workspace = Workspace(tmp_path / "generated")
    assert workspace.resolve(r"src\app.py") == workspace.root / "src" / "app.py"
    assert workspace.resolve(".") == workspace.root
    assert workspace.resolve("src/./app.py").is_relative_to(workspace.root)


def test_existing_directory_link_cannot_escape(tmp_path):
    workspace = Workspace(tmp_path / "generated")
    outside = tmp_path / "generated-sibling"
    outside.mkdir()
    link = workspace.root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        # Windows junctions require no developer-mode symlink privilege.
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "New-Item -ItemType Junction -Path $env:CODE_AGENT_TEST_LINK "
             "-Target $env:CODE_AGENT_TEST_TARGET -ErrorAction Stop"],
            env={**os.environ, "CODE_AGENT_TEST_LINK": str(link), "CODE_AGENT_TEST_TARGET": str(outside)},
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
    try:
        with pytest.raises(WorkspacePathError):
            workspace.resolve("escape/new-file.txt")
    finally:
        # Unlink just the directory entry, never recurse through its target.
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()
    assert outside.is_dir()
