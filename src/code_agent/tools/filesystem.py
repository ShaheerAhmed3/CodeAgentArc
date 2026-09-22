"""Small UTF-8 tools; all requested and discovered paths use Workspace."""

from fnmatch import fnmatchcase
from itertools import islice
from pathlib import Path

from code_agent.agent.models import JSONValue, ToolOutput
from code_agent.tools.base import (
    ToolInputError, bool_argument, check_keys, definition, positive_integer, text_argument,
)
from code_agent.workspace.workspace import Workspace


class FilesystemTool:
    def __init__(self, workspace: Workspace, *, max_file_bytes: int = 1_000_000,
                 max_output_chars: int = 16_000, max_results: int = 200) -> None:
        if any(type(value) is not int or value < 1 for value in
               (max_file_bytes, max_output_chars, max_results)):
            raise ValueError("Filesystem limits must be positive integers")
        self.workspace = workspace
        self.max_file_bytes = max_file_bytes
        self.max_output_chars = max_output_chars
        self.max_results = max_results

    def _read(self, path: str) -> tuple[Path, str]:
        target = self.workspace.resolve(path)
        if not target.exists():
            raise ToolInputError(f"File not found: {path}")
        if not target.is_file():
            raise ToolInputError(f"Not a regular file: {path}")
        with target.open("rb") as stream:
            data = stream.read(self.max_file_bytes + 1)
        if len(data) > self.max_file_bytes:
            raise ToolInputError(f"File exceeds {self.max_file_bytes} byte limit: {path}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolInputError(f"File is not UTF-8 text: {path}") from exc
        if "\x00" in text:
            raise ToolInputError(f"Binary file is not supported: {path}")
        return target, text

    def _encode(self, content: str) -> bytes:
        if "\x00" in content:
            raise ToolInputError("Binary content is not supported")
        data = content.encode("utf-8")
        if len(data) > self.max_file_bytes:
            raise ToolInputError(f"Content exceeds {self.max_file_bytes} byte limit")
        return data

    def _observation(self, content: str, *, truncated: bool = False) -> ToolOutput:
        truncated = truncated or len(content) > self.max_output_chars
        return ToolOutput(content[:self.max_output_chars] + ("\n[truncated]" if truncated else ""),
                          metadata={"truncated": truncated})


class ReadFileTool(FilesystemTool):
    definition = definition("read_file", "Read UTF-8 text, optionally selecting 1-based inclusive lines.", {
        "path": {"type": "string"}, "start_line": {"type": "integer", "minimum": 1},
        "end_line": {"type": "integer", "minimum": 1},
    }, ["path"])

    def execute(self, arguments: dict[str, JSONValue]) -> ToolOutput:
        check_keys(arguments, {"path", "start_line", "end_line"})
        path = text_argument(arguments, "path")
        start = positive_integer(arguments, "start_line", 1)
        _, content = self._read(path)
        lines = content.splitlines(keepends=True)
        end = positive_integer(arguments, "end_line", max(len(lines), 1))
        if end < start:
            raise ToolInputError("end_line must be greater than or equal to start_line")
        if start > max(len(lines), 1):
            raise ToolInputError(f"start_line exceeds file length ({len(lines)} lines)")
        end = min(end, len(lines))
        header = f"{path}: lines {start}-{end} of {len(lines)}" if lines else f"{path}: empty file"
        return self._observation(header + "\n" + "".join(lines[start - 1:end]))


class WriteFileTool(FilesystemTool):
    definition = definition("write_file", "Create UTF-8 text. Replacing a file requires overwrite=true.", {
        "path": {"type": "string"}, "content": {"type": "string"},
        "overwrite": {"type": "boolean", "default": False},
    }, ["path", "content"])

    def execute(self, arguments: dict[str, JSONValue]) -> ToolOutput:
        check_keys(arguments, {"path", "content", "overwrite"})
        path = text_argument(arguments, "path")
        data = self._encode(text_argument(arguments, "content"))
        overwrite = bool_argument(arguments, "overwrite")
        target = self.workspace.resolve(path)
        if target.exists() and not target.is_file():
            raise ToolInputError(f"Not a regular file: {path}")
        if target.exists() and not overwrite:
            raise ToolInputError(f"File exists: {path}; inspect/edit it or set overwrite=true")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb" if overwrite else "xb") as stream:
            stream.write(data)
        return ToolOutput(f"Wrote {path} ({len(data)} bytes)", metadata={"path": path, "bytes_written": len(data)})


class EditFileTool(FilesystemTool):
    definition = definition("edit_file", "Replace exact text in an existing file; ambiguous matches fail.", {
        "path": {"type": "string"}, "old_text": {"type": "string", "minLength": 1},
        "new_text": {"type": "string"}, "replace_all": {"type": "boolean", "default": False},
    }, ["path", "old_text", "new_text"])

    def execute(self, arguments: dict[str, JSONValue]) -> ToolOutput:
        check_keys(arguments, {"path", "old_text", "new_text", "replace_all"})
        path = text_argument(arguments, "path")
        old, new = text_argument(arguments, "old_text"), text_argument(arguments, "new_text")
        replace_all = bool_argument(arguments, "replace_all")
        if not old:
            raise ToolInputError("old_text must not be empty")
        target, content = self._read(path)
        count = content.count(old)
        if count == 0:
            raise ToolInputError("old_text was not found; no changes made")
        if count > 1 and not replace_all:
            raise ToolInputError(f"Ambiguous edit: {count} matches; use more context or replace_all=true")
        data = self._encode(content.replace(old, new))
        target.write_bytes(data)
        return ToolOutput(f"Edited {path}: {count} replacement(s)", metadata={"path": path, "replacements": count})


class ListFilesTool(FilesystemTool):
    definition = definition("list_files", "List sorted workspace entries. Links are omitted.", {
        "directory": {"type": "string", "default": "."},
        "recursive": {"type": "boolean", "default": False},
        "max_results": {"type": "integer", "minimum": 1},
    }, [])

    def execute(self, arguments: dict[str, JSONValue]) -> ToolOutput:
        check_keys(arguments, {"directory", "recursive", "max_results"})
        directory = text_argument(arguments, "directory", ".")
        recursive = bool_argument(arguments, "recursive")
        limit = min(positive_integer(arguments, "max_results", self.max_results), self.max_results)
        entries = list(islice(self.workspace.walk(directory, recursive=recursive), limit + 1))
        rows = [f"{'dir ' if path.is_dir() else 'file'} {path.relative_to(self.workspace.root).as_posix()}"
                for path in entries[:limit]]
        return self._observation("\n".join(rows) or "No entries found.", truncated=len(entries) > limit)


class SearchFilesTool(FilesystemTool):
    definition = definition("search_files", "Search UTF-8 files recursively by substring; skip binary/unreadable files and links.", {
        "query": {"type": "string", "minLength": 1}, "directory": {"type": "string", "default": "."},
        "pattern": {"type": "string", "default": "*"}, "case_sensitive": {"type": "boolean", "default": True},
        "max_results": {"type": "integer", "minimum": 1},
    }, ["query"])

    def execute(self, arguments: dict[str, JSONValue]) -> ToolOutput:
        check_keys(arguments, {"query", "directory", "pattern", "case_sensitive", "max_results"})
        query = text_argument(arguments, "query")
        if not query:
            raise ToolInputError("query must not be empty")
        pattern = text_argument(arguments, "pattern", "*")
        directory = text_argument(arguments, "directory", ".")
        sensitive = bool_argument(arguments, "case_sensitive", True)
        limit = min(positive_integer(arguments, "max_results", self.max_results), self.max_results)
        needle = query if sensitive else query.casefold()
        rows: list[str] = []
        skipped = 0
        for path in self.workspace.walk(directory):
            relative = path.relative_to(self.workspace.root).as_posix()
            if not path.is_file() or not (fnmatchcase(relative, pattern) or fnmatchcase(path.name, pattern)):
                continue
            try:
                _, content = self._read(relative)
            except (ToolInputError, OSError):
                skipped += 1
                continue
            for line_number, line in enumerate(content.splitlines(), 1):
                comparable = line if sensitive else line.casefold()
                if needle in comparable:
                    if len(rows) == limit:
                        return self._observation("\n".join(rows), truncated=True)
                    # Cap each matching line, in addition to the whole observation.
                    offset = comparable.find(needle)
                    if not sensitive:
                        match_offset = offset
                        folded_offset = 0
                        for offset, character in enumerate(line):
                            if folded_offset >= match_offset:
                                break
                            folded_offset += len(character.casefold())
                    start = max(0, offset - 80)
                    snippet = ("..." if start else "") + line[start:start + 300]
                    if len(line) > start + 300:
                        snippet += "..."
                    rows.append(f"{relative}:{line_number}: {snippet}")
        text = "\n".join(rows) or "No matches found."
        if skipped:
            text += f"\nSkipped {skipped} unreadable, binary, or oversized file(s)."
        return self._observation(text)
