from pathlib import Path, PureWindowsPath
from collections.abc import Iterator


class WorkspacePathError(ValueError):
    """A requested path violates the workspace boundary."""


class Workspace:
    def __init__(self, root: str | Path, *, reserved_names: frozenset[str] = frozenset()) -> None:
        self.root = Path(root).resolve()
        self.reserved_names = reserved_names
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str | Path) -> Path:
        """Resolve a portable relative path and reject existing escaping links.

        This is a filesystem boundary for trusted local use, not protection
        against another process racing to replace directories or hard links.
        """
        raw = str(relative_path)
        windows = PureWindowsPath(raw)
        if not raw or "\x00" in raw or windows.drive or windows.root:
            raise WorkspacePathError("Expected a nonempty relative workspace path")
        parts = raw.replace("\\", "/").split("/")
        if any(part.casefold() in self.reserved_names for part in parts):
            raise WorkspacePathError("Path is reserved for agent run artifacts")
        reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
        reserved.update(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10))
        for part in parts:
            if part == "..":
                raise WorkspacePathError("Parent traversal is not allowed")
            if part in {"", "."}:
                continue
            if (
                any(char in part for char in ':<>"|?*')
                or any(ord(char) < 32 for char in part)
                or part.endswith((" ", "."))
                or part.split(".")[0].upper() in reserved
            ):
                raise WorkspacePathError(f"Unsafe path component: {part!r}")
        try:
            candidate = self.root.joinpath(*parts).resolve()
        except (OSError, RuntimeError) as exc:
            raise WorkspacePathError("Could not safely resolve workspace path") from exc
        if not candidate.is_relative_to(self.root):
            raise WorkspacePathError("Path resolves outside the workspace")
        if any(part.casefold() in self.reserved_names for part in candidate.relative_to(self.root).parts):
            raise WorkspacePathError("Path is reserved for agent run artifacts")
        return candidate

    def walk(self, directory: str = ".", *, recursive: bool = True,
             ignored_directories: frozenset[str] = frozenset()) -> Iterator[Path]:
        """Yield sorted entries without following symlinks or Windows junctions.

        Resolve every visited entry through the same boundary. Linked entries
        are omitted altogether, preventing cycles and scans beyond the root.
        """
        start = self.resolve(directory)
        if not start.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")
        pending = [start]
        while pending:
            current = pending.pop()
            descend: list[Path] = []
            for entry in sorted(current.iterdir(), key=lambda item: item.name):
                if entry.name.casefold() in self.reserved_names:
                    continue
                if entry.is_symlink() or entry.is_junction():
                    continue
                safe = self.resolve(entry.relative_to(self.root))
                if safe.is_dir() and safe.name in ignored_directories:
                    continue
                if safe.is_file() or safe.is_dir():
                    yield safe
                if recursive and safe.is_dir():
                    descend.append(safe)
            pending.extend(reversed(descend))
