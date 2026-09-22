from pathlib import Path
import os
import subprocess
import socket

import pytest

from code_agent.architecture.normalizer import normalize_architecture


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("Network access is forbidden in the offline test suite")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def architecture(project_root):
    inputs = project_root / "architecture" / "inputs"
    return normalize_architecture(
        inputs / "Architecture_Documentation.md",
        inputs / "Architecture_View.md",
    )


@pytest.fixture
def directory_link():
    """Exercise real links on Unix and privilege-free junctions on Windows."""
    links: list[Path] = []

    def create(link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 "New-Item -ItemType Junction -Path $env:CODE_AGENT_TEST_LINK "
                 "-Target $env:CODE_AGENT_TEST_TARGET -ErrorAction Stop"],
                env={**os.environ, "CODE_AGENT_TEST_LINK": str(link), "CODE_AGENT_TEST_TARGET": str(target)},
                capture_output=True, check=True,
            )
        links.append(link)

    yield create
    for link in reversed(links):
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()
