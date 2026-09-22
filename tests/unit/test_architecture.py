import json

import pytest

from code_agent.architecture.normalizer import normalize_architecture
from code_agent.architecture.parser import parse_documentation, parse_views


def test_sections_preserve_hierarchy_preamble_and_fenced_headings():
    text = "Preamble\n# Overview\nintro\n## API\n```markdown\n# not a heading\n```\n"
    sections = parse_documentation(text)
    assert [s.title for s in sections] == ["Preamble", "Overview", "API"]
    assert sections[-1].path == ("Overview", "API")
    assert sections[-1].line == 4
    assert "# not a heading" in sections[-1].content


def test_views_preserve_crlf_and_share_caption_without_merging_blocks():
    first = "@startuml A\r\n' comment\r\nA -> B\r\n@enduml\r\n"
    second = "@startuml B\r\n@enduml\r\n"
    text = "## ProcessView\r\n6. Sequence — Process View: Sequence Diagram\r\n"
    text += f"```plantuml\r\n{first}```\r\n```plantuml\r\n{second}```\r\n"
    views = parse_views(text)
    assert [v.plantuml_source for v in views] == [first, second]
    assert [v.diagram_name for v in views] == ["A", "B"]
    assert [v.diagram_number for v in views] == [6, 6]
    assert views[0].diagram_type == "Sequence"
    assert views[0].view_category == "ProcessView"
    assert views[0].line == 4


def test_view_metadata_does_not_leak_between_categories():
    text = "## LogicView\n2. Class — Logic View: Classes\n## UnknownView\n"
    text += "~~~PlantUML\n@startuml\n@enduml\n~~~\n"
    view, = parse_views(text)
    assert view.diagram_number is None
    assert view.diagram_type is None
    assert view.diagram_name is None
    assert view.view_category == "UnknownView"


@pytest.mark.parametrize("parser", [parse_documentation, parse_views])
def test_unclosed_fences_fail_explicitly(parser):
    with pytest.raises(ValueError, match="Unclosed"):
        parser("```plantuml\n@startuml Broken\n")


def test_unknown_input_remains_available_without_invented_facts(tmp_path):
    docs, views = tmp_path / "docs.md", tmp_path / "views.md"
    docs.write_bytes(b"\xef\xbb\xbf# Novel format\r\nUnclassified requirement.\r\n")
    views.write_text("```plantuml\nA -> B\n```\n", encoding="utf-8")
    architecture = normalize_architecture(docs, views)
    assert architecture.project_name is None
    assert architecture.architectural_style is None
    assert architecture.documentation_sections[0].content == "Unclassified requirement.\n"
    assert architecture.sources[0].text.encode("utf-8") == docs.read_bytes()
    assert any("missing a start/end" in warning for warning in architecture.warnings)
    assert architecture.agent_assumptions == ()
    assert architecture.implementation_decisions == ()
    assert json.loads(architecture.to_json())["project_name"] is None
