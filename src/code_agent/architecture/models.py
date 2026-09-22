from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    level: int
    path: tuple[str, ...]
    line: int
    content: str


@dataclass(frozen=True)
class SourceExcerpt:
    section_id: str
    heading_path: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class Component:
    name: str
    description: str
    section_id: str


@dataclass(frozen=True)
class ArchitecturalView:
    view_category: str | None
    diagram_number: int | None
    diagram_type: str | None
    diagram_name: str | None
    caption: str | None
    line: int
    plantuml_source: str


@dataclass(frozen=True)
class SourceDocument:
    filename: str
    sha256: str
    text: str


@dataclass(frozen=True)
class Architecture:
    schema_version: str
    project_name: str | None
    description: str | None
    architectural_style: str | None
    components: tuple[Component, ...]
    technologies: tuple[SourceExcerpt, ...]
    interfaces: tuple[SourceExcerpt, ...]
    data_models: tuple[SourceExcerpt, ...]
    deployment: tuple[SourceExcerpt, ...]
    security: tuple[SourceExcerpt, ...]
    testing: tuple[SourceExcerpt, ...]
    assumptions: tuple[SourceExcerpt, ...]
    open_questions: tuple[SourceExcerpt, ...]
    documentation_sections: tuple[Section, ...]
    architectural_views: tuple[ArchitecturalView, ...]
    sources: tuple[SourceDocument, ...]
    agent_assumptions: tuple[str, ...] = ()
    implementation_decisions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_json(self) -> str:
        """Stable UTF-8-compatible JSON, without timestamps or absolute paths."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
