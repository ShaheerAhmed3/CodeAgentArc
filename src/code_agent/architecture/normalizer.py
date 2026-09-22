import hashlib
from pathlib import Path
import re

from code_agent.architecture.models import Architecture, Component, Section, SourceDocument, SourceExcerpt
from code_agent.architecture.parser import parse_documentation, parse_views


def _read_source(path: Path) -> SourceDocument:
    data = path.read_bytes()
    # Keep CRLF and all other source characters, including any BOM, in provenance.
    return SourceDocument(path.name, hashlib.sha256(data).hexdigest(), data.decode("utf-8"))


def _normalized_text(text: str) -> str:
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def _extract(sections: tuple[Section, ...], pattern: str) -> tuple[SourceExcerpt, ...]:
    return tuple(
        SourceExcerpt(section.id, section.path, section.content)
        for section in sections
        if section.content.strip() and re.search(pattern, " / ".join(section.path), re.IGNORECASE)
    )


def normalize_architecture(documentation: str | Path, views: str | Path) -> Architecture:
    docs_source = _read_source(Path(documentation))
    views_source = _read_source(Path(views))
    text = _normalized_text(docs_source.text)
    sections = parse_documentation(text)
    # UML payloads deliberately bypass newline normalization for exact preservation.
    diagrams = parse_views(views_source.text.removeprefix("\ufeff"))
    summary = next((s for s in sections if "executive summary" in s.title.lower()), None)
    description = summary.content.strip().split("\n\n")[0] if summary else None
    name_match = re.search(r"\bThe (.+?) system\b", description or "")
    if not name_match:
        name_match = re.search(r"^(?:Project|System) name:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    style_match = re.search(r"^Chosen architectural style:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    components: list[Component] = []
    for section in sections:
        if "architecture overview" in section.title.lower():
            for match in re.finditer(r"^\s*[*+-]\s+([^:\n]+):\s*(.+)$", section.content, re.MULTILINE):
                components.append(Component(match[1].strip(), match[2].strip(), section.id))
    warnings = [
        "Categorized fields use heading/label rules; unrecognized content remains in sections and sources.",
        "Normalization preserves source statements; it does not validate their consistency or suitability.",
    ]
    if not name_match:
        warnings.append("Project name was not recognized; no name inferred.")
    if not style_match:
        warnings.append("Architectural style was not recognized; no style inferred.")
    if not diagrams:
        warnings.append("No fenced PlantUML blocks found.")
    for index, diagram in enumerate(diagrams, 1):
        if not re.search(r"^\s*@startuml\b", diagram.plantuml_source, re.MULTILINE) or not re.search(r"^\s*@enduml\b", diagram.plantuml_source, re.MULTILINE):
            warnings.append(f"PlantUML block {index} is missing a start/end marker; source retained.")
    return Architecture(
        schema_version="1.0",
        project_name=name_match[1].strip() if name_match else None,
        description=description,
        architectural_style=style_match[1].strip() if style_match else None,
        components=tuple(components),
        technologies=_extract(sections, r"technology options|recommended default stack"),
        interfaces=_extract(sections, r"interface design|external APIs|internal contracts"),
        data_models=_extract(sections, r"data model|schema"),
        deployment=_extract(sections, r"executive summary|operations & deployment|migration, data conversion"),
        security=_extract(sections, r"security design"),
        testing=_extract(sections, r"testing strategy|executive summary"),
        assumptions=_extract(sections, r"^.* / Assumptions$|^Assumptions$"),
        open_questions=_extract(sections, r"unresolved stakeholder questions"),
        documentation_sections=sections,
        architectural_views=diagrams,
        sources=(docs_source, views_source),
        warnings=tuple(warnings),
    )
