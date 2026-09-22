import hashlib
import json
import re

from code_agent.agent.loop import AgentLoop
from code_agent.agent.models import ModelResponse, ToolCall, ToolDefinition
from code_agent.agent.prompts import build_messages
from code_agent.architecture.normalizer import normalize_architecture
from code_agent.cli import main
from code_agent.providers.mock import MockProvider
from code_agent.tools.registry import ToolRegistry
from code_agent.workspace.workspace import Workspace


SOURCE_HASHES = {
    "Architecture_Documentation.md": "111282df7817bca771e53c82ebb053707a3217cb8f11733a2c25b631ca81db55",
    "Architecture_View.md": "77dac057e13f122ddc6fc19294490c6a961f00429b72f15df81a81adc91bdbc8",
}


def test_reference_inputs_are_byte_identical(project_root):
    for filename, expected in SOURCE_HASHES.items():
        assert hashlib.sha256((project_root / filename).read_bytes()).hexdigest() == expected


def test_supplied_documentation_is_preserved_and_categorized(architecture):
    assert architecture.project_name == "Space Fractions"
    assert architecture.architectural_style == "Microservices"
    assert "sixth-grade students" in architecture.description
    assert {c.name for c in architecture.components} == {"GameComponent", "QuestionComponent", "UserComponent"}
    expected = {
        "technologies": ["Node.js 18-20", "Elasticsearch 7-8", "Terraform 1"],
        "interfaces": ["/play:", "rpc Play(PlayRequest) returns (PlayResponse)"],
        "data_models": ["CREATE TABLE games", "game_state JSONB NOT NULL"],
        "deployment": ["replicas: 3", "PostgreSQL replication"],
        "security": ["OAuth2", "Hashicorp's Vault", "Istio"],
        "testing": ["Chaos testing", "TestRail"],
        "assumptions": ["1000 users concurrently", "1 hour per session"],
        "open_questions": ["expected user growth rate"],
    }
    for field, fragments in expected.items():
        extracted = "\n".join(item.text for item in getattr(architecture, field))
        for fragment in fragments:
            assert fragment in extracted, (field, fragment)
    # Preserve inconsistent SLO/error-budget statements without correcting either.
    all_sections = "".join(s.content for s in architecture.documentation_sections)
    assert "99.99% uptime" in all_sections
    assert "Error budget: 1%" in all_sections
    assert "sql/question_ddl.sql" in all_sections
    assert "sql/game_ddl.sql" in all_sections


def test_all_supplied_plantuml_blocks_are_exact(project_root, architecture):
    source = (project_root / "Architecture_View.md").read_bytes().decode("utf-8")
    expected = re.findall(r"```plantuml\r?\n(.*?)```", source, re.DOTALL)
    assert len(expected) == len(architecture.architectural_views) == 13
    assert [v.plantuml_source for v in architecture.architectural_views] == expected
    assert {v.diagram_number for v in architecture.architectural_views} == set(range(1, 12))
    assert {v.view_category for v in architecture.architectural_views} == {
        "ScenarioView", "LogicView", "ProcessView", "DevelopmentView", "PhysicalView",
    }
    assert [v.diagram_name for v in architecture.architectural_views if v.diagram_number == 6] == ["SequenceDiagram1", "SequenceDiagram2"]
    assert any("AdminComponent" in v.plantuml_source for v in architecture.architectural_views)


def test_json_is_repeatable_and_contains_source_provenance(project_root, architecture):
    repeated = normalize_architecture(project_root / "Architecture_Documentation.md", project_root / "Architecture_View.md")
    assert architecture.to_json() == repeated.to_json()
    decoded = json.loads(architecture.to_json())
    assert decoded["schema_version"] == "1.0"
    for source in decoded["sources"]:
        assert source["text"].encode("utf-8") == (project_root / source["filename"]).read_bytes()
        assert source["sha256"] == SOURCE_HASHES[source["filename"]]


def test_cli_writes_json_and_refuses_source_overwrite(project_root, tmp_path, capsys):
    inputs = ["normalize", "--documentation", str(project_root / "Architecture_Documentation.md"), "--views", str(project_root / "Architecture_View.md")]
    target = tmp_path / "architecture.json"
    assert main(inputs + ["--output", str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["project_name"] == "Space Fractions"
    for original in SOURCE_HASHES:
        assert main(inputs + ["--output", str(project_root / original)]) == 1
    assert "code-agent:" in capsys.readouterr().err


def test_normalization_prompt_loop_and_workspace_work_together(architecture, tmp_path):
    workspace = Workspace(tmp_path / "project")
    workspace.resolve("README.md").write_text("Test-only fixture", encoding="utf-8")

    class ReadFixture:
        definition = ToolDefinition("read_file", "Read the integration fixture", {
            "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"],
        })

        def execute(self, arguments):
            return workspace.resolve(arguments["path"]).read_text(encoding="utf-8")

    registry = ToolRegistry()
    registry.register(ReadFixture())
    provider = MockProvider([
        ModelResponse(tool_calls=(ToolCall("read-1", "read_file", {"path": "README.md"}),)),
        ModelResponse("Fixture inspected; generation is deferred."),
    ])
    result = AgentLoop(provider, registry).run(build_messages(architecture, "Inspect the fixture."))
    assert result.stop_reason == "final_response"
    assert provider.requests[1].messages[-1].tool_result.content == "Test-only fixture"
    assert "Space Fractions" in provider.requests[0].messages[2].content
    assert not list(workspace.root.glob("*.py"))
