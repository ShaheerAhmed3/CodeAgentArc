"""Extract headings and fenced diagrams; intentionally not a UML/Markdown engine."""

import re

from code_agent.architecture.models import ArchitecturalView, Section

_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)")
_CAPTION = re.compile(r"^\s*(\d+)\.\s+(.+?)\s+[—–-]\s+(.+?)\s*$")


def _closes_fence(line: str, marker: str) -> bool:
    return re.fullmatch(r" {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}\s*", line) is not None


def parse_documentation(text: str) -> tuple[Section, ...]:
    lines = text.splitlines(keepends=True)
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    title, level, start = "Preamble", 0, 0
    content: list[str] = []
    fence: str | None = None

    def append_section() -> None:
        if content or level:
            sections.append(Section(
                f"section-{len(sections) + 1}", title, level,
                tuple(item[1] for item in stack), start + 1, "".join(content),
            ))

    for index, line in enumerate(lines):
        if fence:
            content.append(line)
            if _closes_fence(line, fence):
                fence = None
            continue
        opening = _FENCE.match(line)
        if opening:
            fence = opening[1]
            content.append(line)
            continue
        heading = _HEADING.match(line)
        if heading:
            append_section()
            title, level, start = heading[2], len(heading[1]), index
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            content = []
        else:
            content.append(line)
    if fence:
        raise ValueError("Unclosed code fence in architecture documentation")
    append_section()
    return tuple(sections)


def parse_views(text: str) -> tuple[ArchitecturalView, ...]:
    views: list[ArchitecturalView] = []
    category: str | None = None
    number: int | None = None
    diagram_type: str | None = None
    caption: str | None = None
    marker: str | None = None
    language = ""
    start = 0
    content: list[str] = []
    for index, line in enumerate(text.splitlines(keepends=True)):
        if marker:
            if _closes_fence(line, marker):
                if language == "plantuml":
                    source = "".join(content)
                    name = re.search(r"^\s*@startuml(?:[ \t]+([^\r\n]+))?", source, re.MULTILINE)
                    views.append(ArchitecturalView(
                        category, number, diagram_type,
                        name[1].strip() if name and name[1] else None,
                        caption, start + 1, source,
                    ))
                marker = None
                content = []
            else:
                content.append(line)
            continue
        opening = _FENCE.match(line)
        if opening:
            marker, language, start = opening[1], opening[2].strip().lower(), index + 1
            continue
        heading = _HEADING.match(line)
        if heading:
            category = heading[2]
            number, diagram_type, caption = None, None, None
            continue
        label = _CAPTION.match(line)
        if label:
            number, diagram_type, caption = int(label[1]), label[2], line.strip()
    if marker:
        raise ValueError("Unclosed code fence in architecture views")
    return tuple(views)
