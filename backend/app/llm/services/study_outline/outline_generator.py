"""Generate and revise study-focused section outlines from document layout."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

HEADING_LABELS = frozenset({
    "title",
    "section_header",
    "document_index",
    "page_header",
})

OUTLINE_PROMPT = ChatPromptTemplate.from_template(
    """
You are helping a student study a book or PDF. Given structural headings extracted
from the document, produce a focused study outline — NOT every heading in the book,
only the sections worth studying as distinct units.

Rules:
- Group related material into study sections (chapters, major topics).
- Use subsections in the JSON only for internal structure (parent_id). Students study
  at the top level (level 1) — each top-level section covers itself and all its children.
- Maximum depth: 2 levels preferred (section → optional subsection metadata).
- Each item needs: id (slug like "ch-1"), title, level (1-3), parent_id (null for top),
  order (0-based among siblings), page_start, page_end.
- page_start/page_end should cover the pages where that section's content lives.
- Skip front matter (copyright, TOC-only pages) unless they contain study material.
- Aim for 5-20 top-level study sections for a typical textbook chapter range.

Document: {filename}

Extracted headings (page, label, text):
{headings}

Respond with JSON only:
{{"sections": [{{"id": "...", "title": "...", "level": 1, "parent_id": null, "order": 0, "page_start": 1, "page_end": 10}}]}}
""",
)

REVISION_PROMPT = ChatPromptTemplate.from_template(
    """
You are revising a study outline for a document based on student feedback.

Document: {filename}

Current outline (JSON):
{current_outline}

Student revision request:
{instruction}

Apply the requested changes. Keep valid JSON with the same schema:
{{"sections": [{{"id": "...", "title": "...", "level": 1, "parent_id": null, "order": 0, "page_start": 1, "page_end": 10}}]}}

Respond with JSON only.
""",
)

NOTES_PROMPT = ChatPromptTemplate.from_template(
    """
You are a study assistant. Write clear, concise study notes for this section of a document.

Document: {filename}
Section: {section_title}
Pages: {page_start}–{page_end}

Relevant content from the document:
{content}

Write structured study notes in markdown: key concepts, definitions, important points,
and a brief summary. Be accurate — only include what the content supports.
""",
)

QUESTIONS_PROMPT = ChatPromptTemplate.from_template(
    """
You are a study assistant. Generate practice questions for this section.

Document: {filename}
Section: {section_title}

Relevant content:
{content}

Generate {count} study questions (mix of recall and understanding). Respond with JSON only:
{{"questions": [{{"question": "...", "hint": "..."}}]}}
""",
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def _extract_headings(layout: dict[str, Any]) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    for page in layout.get("pages", []):
        page_no = page.get("page_no", 0)
        for element in page.get("elements", []):
            label = (element.get("label") or "").lower().replace(" ", "_")
            text = (element.get("text") or "").strip()
            if not text or label not in HEADING_LABELS:
                continue
            headings.append({
                "page": page_no,
                "label": label,
                "text": text[:300],
            })
    return headings


def _extract_section_content(
    layout: dict[str, Any],
    *,
    page_start: int,
    page_end: int,
) -> str:
    parts: list[str] = []
    for page in layout.get("pages", []):
        page_no = page.get("page_no", 0)
        if page_no < page_start or page_no > page_end:
            continue
        for element in page.get("elements", []):
            text = (element.get("text") or "").strip()
            if text:
                parts.append(text)
    combined = "\n\n".join(parts)
    return combined[:12000]


def _parse_json_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _descendant_sections(
    section_id: str,
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    children = [s for s in sections if s.get("parent_id") == section_id]
    return children + [
        descendant
        for child in children
        for descendant in _descendant_sections(str(child["id"]), sections)
    ]


def section_study_scope(
    section: dict[str, Any],
    outline: dict[str, Any],
) -> dict[str, Any]:
    """Expand a section to include all descendant subsections as one study unit."""
    sections = outline.get("sections", [])
    descendants = _descendant_sections(str(section["id"]), sections)
    scoped = [section, *descendants]
    return {
        **section,
        "page_start": min(s["page_start"] for s in scoped),
        "page_end": max(s["page_end"] for s in scoped),
    }


def _normalize_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for i, section in enumerate(sections):
        normalized.append({
            "id": str(section.get("id") or f"section-{i}"),
            "title": str(section.get("title") or f"Section {i + 1}"),
            "level": int(section.get("level") or 1),
            "parent_id": section.get("parent_id"),
            "order": int(section.get("order", i)),
            "page_start": int(section.get("page_start") or 1),
            "page_end": int(section.get("page_end") or section.get("page_start") or 1),
        })
    return normalized


def generate_study_outline(
    layout: dict[str, Any],
    *,
    filename: str = "",
) -> dict[str, Any]:
    """Build a study outline from layout headings via LLM."""
    headings = _extract_headings(layout)
    if not headings:
        page_count = layout.get("page_count", 1)
        return {
            "filename": filename,
            "sections": [{
                "id": "full-document",
                "title": "Full document",
                "level": 1,
                "parent_id": None,
                "order": 0,
                "page_start": 1,
                "page_end": max(page_count, 1),
            }],
        }

    headings_text = "\n".join(
        f"- p{h['page']} [{h['label']}] {h['text']}" for h in headings[:200]
    )
    chain = OUTLINE_PROMPT | _llm | StrOutputParser()
    raw = chain.invoke({"filename": filename, "headings": headings_text})
    parsed = _parse_json_response(raw)
    sections = _normalize_sections(parsed.get("sections", []))

    return {"filename": filename, "sections": sections}


def revise_study_outline(
    current_outline: dict[str, Any],
    *,
    filename: str,
    instruction: str,
) -> dict[str, Any]:
    """Revise an existing study outline based on user feedback."""
    chain = REVISION_PROMPT | _llm | StrOutputParser()
    raw = chain.invoke({
        "filename": filename,
        "current_outline": json.dumps(current_outline, ensure_ascii=False),
        "instruction": instruction,
    })
    parsed = _parse_json_response(raw)
    sections = _normalize_sections(parsed.get("sections", []))
    return {"filename": filename, "sections": sections}


def generate_section_notes(
    layout: dict[str, Any],
    section: dict[str, Any],
    *,
    filename: str = "",
) -> str:
    """Generate study notes for a single section."""
    content = _extract_section_content(
        layout,
        page_start=section["page_start"],
        page_end=section["page_end"],
    )
    chain = NOTES_PROMPT | _llm | StrOutputParser()
    return chain.invoke({
        "filename": filename,
        "section_title": section["title"],
        "page_start": section["page_start"],
        "page_end": section["page_end"],
        "content": content or "(No text content found for this page range.)",
    })


def generate_section_questions(
    layout: dict[str, Any],
    section: dict[str, Any],
    *,
    filename: str = "",
    count: int = 5,
) -> list[dict[str, str]]:
    """Generate practice questions for a single section."""
    content = _extract_section_content(
        layout,
        page_start=section["page_start"],
        page_end=section["page_end"],
    )
    chain = QUESTIONS_PROMPT | _llm | StrOutputParser()
    raw = chain.invoke({
        "filename": filename,
        "section_title": section["title"],
        "content": content or "(No text content found.)",
        "count": count,
    })
    parsed = _parse_json_response(raw)
    return parsed.get("questions", [])


def outline_to_json_bytes(outline: dict[str, Any]) -> bytes:
    return json.dumps(outline, ensure_ascii=False).encode("utf-8")
