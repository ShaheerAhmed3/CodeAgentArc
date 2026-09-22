import pytest

from code_agent.agent.models import ToolCall
from code_agent.tools import coding_tools
from code_agent.tools.filesystem import ReadFileTool, SearchFilesTool
from code_agent.tools.registry import ToolRegistry
from code_agent.workspace.workspace import Workspace


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "repo")


@pytest.fixture
def dispatch(workspace):
    registry = coding_tools(workspace)
    return lambda name, **args: registry.dispatch(ToolCall("call-1", name, args))


def test_read_utf8_ranges_missing_directory_and_binary(workspace, dispatch):
    workspace.resolve("text.txt").write_bytes("hello\r\n世界\r\nlast".encode("utf-8"))
    result = dispatch("read_file", path="text.txt", start_line=2, end_line=2)
    assert not result.is_error
    assert "lines 2-2 of 3\n世界\r\n" in result.content
    assert "File not found" in dispatch("read_file", path="missing").content
    assert dispatch("read_file", path=".").is_error
    for data in (b"\xff", b"a\x00b"):
        workspace.resolve("binary").write_bytes(data)
        assert dispatch("read_file", path="binary").is_error


@pytest.mark.parametrize("ranges", [{"start_line": 0}, {"start_line": True}, {"start_line": 2, "end_line": 1}, {"end_line": "2"}, {"start_line": 10}])
def test_read_invalid_ranges(workspace, dispatch, ranges):
    workspace.resolve("text").write_text("one\ntwo", encoding="utf-8")
    assert dispatch("read_file", path="text", **ranges).is_error


def test_file_and_observation_size_limits(workspace):
    workspace.resolve("text").write_text("0123456789\n" * 10, encoding="utf-8")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace, max_file_bytes=200, max_output_chars=25))
    result = registry.dispatch(ToolCall("1", "read_file", {"path": "text"}))
    assert result.metadata["truncated"]
    assert len(result.content) <= 25 + len("\n[truncated]")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace, max_file_bytes=10))
    result = registry.dispatch(ToolCall("1", "read_file", {"path": "text"}))
    assert result.is_error and "byte limit" in result.content


def test_write_parents_overwrite_and_byte_count(workspace, dispatch):
    result = dispatch("write_file", path="src/app.txt", content="héllo\r\n")
    assert not result.is_error
    assert result.metadata["bytes_written"] == len("héllo\r\n".encode("utf-8"))
    assert workspace.resolve("src/app.txt").read_bytes() == "héllo\r\n".encode("utf-8")
    assert dispatch("write_file", path="src/app.txt", content="lost").is_error
    assert workspace.resolve("src/app.txt").read_bytes() == "héllo\r\n".encode("utf-8")
    assert not dispatch("write_file", path="src/app.txt", content="new", overwrite=True).is_error
    assert workspace.resolve("src/app.txt").read_text() == "new"
    assert dispatch("write_file", path="src", content="bad", overwrite=True).is_error


def test_edit_preserves_bytes_outside_exact_match(workspace, dispatch):
    path = workspace.resolve("file")
    path.write_bytes(b"\xef\xbb\xbfone\r\ntwo\nthree\r\n")
    result = dispatch("edit_file", path="file", old_text="two", new_text="TWO")
    assert not result.is_error
    assert path.read_bytes() == b"\xef\xbb\xbfone\r\nTWO\nthree\r\n"


def test_edit_missing_ambiguous_and_replace_all(workspace, dispatch):
    path = workspace.resolve("file")
    path.write_text("same same", encoding="utf-8")
    for old, message in [("", "must not be empty"), ("missing", "not found"), ("same", "Ambiguous")]:
        result = dispatch("edit_file", path="file", old_text=old, new_text="new")
        assert result.is_error and message in result.content
        assert path.read_text() == "same same"
    result = dispatch("edit_file", path="file", old_text="same", new_text="new", replace_all=True)
    assert result.metadata["replacements"] == 2
    assert path.read_text() == "new new"
    assert dispatch("edit_file", path="missing", old_text="x", new_text="y").is_error


@pytest.mark.parametrize("name,args", [
    ("read_file", {"path": "../outside"}),
    ("write_file", {"path": "../outside", "content": "bad"}),
    ("edit_file", {"path": "../outside", "old_text": "original", "new_text": "bad"}),
    ("list_files", {"directory": "..", "recursive": True}),
    ("search_files", {"directory": "..", "query": "original"}),
])
def test_every_filesystem_tool_enforces_boundary(workspace, dispatch, name, args):
    outside = workspace.root.parent / "outside"
    outside.write_text("original", encoding="utf-8")
    assert dispatch(name, **args).is_error
    assert outside.read_text() == "original"


@pytest.mark.parametrize("name,args", [
    ("read_file", {"path": 2}),
    ("write_file", {"path": "file", "content": "x", "overwrite": "false"}),
    ("edit_file", {"path": "file", "old_text": "x", "new_text": "y", "replace_all": 1}),
    ("list_files", {"recursive": "true"}),
    ("search_files", {"query": ""}),
    ("search_files", {"query": "x", "max_results": False}),
])
def test_invalid_inputs_are_error_observations(dispatch, name, args):
    assert dispatch(name, **args).is_error


def test_listing_order_recursion_and_limit(workspace, dispatch):
    for path in ("z.txt", "folder/b.txt", "folder/a.txt", "a.txt"):
        dispatch("write_file", path=path, content="content")
    result = dispatch("list_files")
    assert result.content.splitlines() == ["file a.txt", "dir  folder", "file z.txt"]
    recursive = dispatch("list_files", recursive=True)
    assert recursive.content.splitlines()[-2:] == ["file folder/a.txt", "file folder/b.txt"]
    assert dispatch("list_files", recursive=True).content == recursive.content
    assert dispatch("list_files", max_results=1).metadata["truncated"]
    assert not dispatch("list_files", directory="folder", max_results=2).metadata["truncated"]


def test_search_paths_lines_globs_directory_case_and_limit(workspace, dispatch):
    dispatch("write_file", path="src/a.py", content="one\nNeedle\nneedle\n")
    dispatch("write_file", path="other.py", content="needle")
    workspace.resolve("src/binary.py").write_bytes(b"\xff\x00needle")
    result = dispatch("search_files", query="needle", directory="src", pattern="*.py")
    assert "src/a.py:3: needle" in result.content
    assert "other.py" not in result.content
    assert "binary.py:" not in result.content
    assert "Skipped 1" in result.content
    result = dispatch("search_files", query="needle", directory="src", case_sensitive=False, max_results=1)
    assert "src/a.py:2: Needle" in result.content
    assert result.metadata["truncated"]
    assert "No matches" in dispatch("search_files", query="needle", pattern="*.js").content


def test_search_skips_unreadable_file_without_hiding_other_matches(workspace, monkeypatch):
    workspace.resolve("a.py").write_text("needle", encoding="utf-8")
    workspace.resolve("b.py").write_text("needle", encoding="utf-8")
    tool = SearchFilesTool(workspace)
    read = tool._read

    def unreadable(path):
        if path == "a.py":
            raise PermissionError("unreadable fixture")
        return read(path)

    monkeypatch.setattr(tool, "_read", unreadable)
    result = tool.execute({"query": "needle"})
    assert "b.py:1: needle" in result.content
    assert "Skipped 1" in result.content


def test_long_search_snippet_includes_match_after_unicode_casefold(workspace, dispatch):
    dispatch("write_file", path="long.txt", content="ß" * 400 + "Needle" + "x" * 400)
    result = dispatch("search_files", query="needle", case_sensitive=False)
    assert "long.txt:1:" in result.content
    assert "Needle" in result.content
    assert len(result.content) < 350


def test_tools_do_not_follow_directory_links(workspace, directory_link, dispatch):
    outside = workspace.root.parent / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("needle", encoding="utf-8")
    directory_link(workspace.root / "escape", outside)
    directory_link(workspace.root / "cycle", workspace.root)
    assert "secret" not in dispatch("list_files", recursive=True).content
    assert "No matches" in dispatch("search_files", query="needle").content
    assert dispatch("read_file", path="escape/secret.txt").is_error
    assert dispatch("write_file", path="escape/new", content="bad").is_error
    assert dispatch("edit_file", path="escape/secret.txt", old_text="needle", new_text="bad").is_error
    assert dispatch("search_files", query="needle", directory="escape").is_error
    assert not (outside / "new").exists()
