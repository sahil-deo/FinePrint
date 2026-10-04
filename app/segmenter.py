"""Deterministic clause segmentation. No LLM involved.

Splits an agreement into clauses while preserving the document's own
numbering, headings, character offsets and cross-references. Documents with no
numbering fall back to paragraph splitting with synthetic ids.
"""

from __future__ import annotations

import re

from .schemas import Clause

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

#: 1. / 1.1 / 1.1.2 / 12.3) / A.1 at the start of a line.
_NUMBER_RE = re.compile(
    r"^[ \t]*(?P<id>(?:\d{1,2}|[A-Z])(?:\.\d{1,2}){0,3})[.)]?[ \t]+(?=\S)",
)

#: (a) / (iv) / (1) sub-items - these stay inside their parent clause.
_SUBITEM_RE = re.compile(r"^[ \t]*\((?:[a-z]{1,3}|[ivxl]{1,5}|\d{1,2})\)[ \t]+")

#: ARTICLE 5 / SECTION 3 / CLAUSE 7 headings.
_WORD_NUMBER_RE = re.compile(
    r"^[ \t]*(?:ARTICLE|SECTION|CLAUSE|PART)[ \t]+(?P<id>\d{1,2}|[IVXL]{1,6})"
    r"[ \t]*[.:\-]?[ \t]*(?P<heading>.*)$",
    re.IGNORECASE,
)

#: Cross-references such as "Clause 5.1" or "Clauses 2.2 and 4.1".
_CROSSREF_RE = re.compile(
    r"\b(?:clause|clauses|section|sections|article|articles|para|paragraph)\s+"
    r"((?:\d{1,2}(?:\.\d{1,2}){0,3})(?:\s*(?:,|and|to|&)\s*\d{1,2}(?:\.\d{1,2}){0,3})*)",
    re.IGNORECASE,
)

_ID_IN_REF_RE = re.compile(r"\d{1,2}(?:\.\d{1,2}){0,3}")

#: Lines that are a standalone heading (ALL CAPS or Title Case, short, no period).
_MIN_CLAUSE_CHARS = 28


def normalise_text(raw: str) -> str:
    """Normalise newlines and strip control characters, preserving offsets."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    # Collapse runs of blank lines but keep paragraph boundaries.
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if stripped.endswith((".", ";", ",")):
        return False
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio > 0.75


def _extract_heading(body: str) -> tuple[str, str]:
    """Pull a heading off the front of a clause body if there is one."""
    lines = body.split("\n")
    first = lines[0].strip()
    if not first:
        return "", body

    # "DEFINITIONS\n1.1 ..." style, or a section title standing alone.
    if _is_heading_line(first):
        rest = "\n".join(lines[1:]).strip()
        return (first.title() if first.isupper() else first), rest

    # Inline heading: "TERM AND TERMINATION. The Company may ..."
    match = re.match(r"^([A-Z][A-Z \-&/,']{3,60})(?:[.:\-]\s+|\n)(.+)", body, re.DOTALL)
    if match:
        return match.group(1).strip().title(), match.group(2).strip()

    return "", body


def _find_cross_references(text: str, own_id: str) -> list[str]:
    refs: list[str] = []
    for match in _CROSSREF_RE.finditer(text):
        for ref in _ID_IN_REF_RE.findall(match.group(1)):
            if ref != own_id and ref not in refs:
                refs.append(ref)
    return refs


def _numbered_boundaries(text: str) -> list[tuple[int, str, str]]:
    """Locate numbered clause starts: (offset, clause_id, inline_heading)."""
    boundaries: list[tuple[int, str, str]] = []
    offset = 0
    for line in text.split("\n"):
        line_start = offset
        offset += len(line) + 1

        if _SUBITEM_RE.match(line):
            continue

        word_match = _WORD_NUMBER_RE.match(line)
        if word_match:
            boundaries.append(
                (
                    line_start,
                    word_match.group("id"),
                    word_match.group("heading").strip(),
                )
            )
            continue

        num_match = _NUMBER_RE.match(line)
        if num_match:
            clause_id = num_match.group("id")
            # A bare year or amount at line start is not a clause number.
            if re.fullmatch(r"\d{4}", clause_id):
                continue
            boundaries.append((line_start, clause_id, ""))

    return boundaries


def _paragraph_clauses(text: str) -> list[Clause]:
    """Fallback for documents with no usable numbering."""
    clauses: list[Clause] = []
    cursor = 0
    index = 0
    for block in re.split(r"\n\s*\n", text):
        start = text.find(block, cursor)
        if start == -1:
            start = cursor
        cursor = start + len(block)
        body = block.strip()
        if len(body) < _MIN_CLAUSE_CHARS:
            continue
        index += 1
        heading, stripped_body = _extract_heading(body)
        clause_id = f"P{index}"
        clauses.append(
            Clause(
                clause_id=clause_id,
                heading=heading,
                text=stripped_body or body,
                start=start,
                end=start + len(block),
                cross_references=_find_cross_references(body, clause_id),
            )
        )
    return clauses


def segment(raw_text: str) -> list[Clause]:
    """Split an agreement into clauses.

    Returns clauses in document order with offsets into the normalised text
    (the same text that is stored in the report and rendered in the UI).
    """
    text = normalise_text(raw_text)
    if not text:
        return []

    boundaries = _numbered_boundaries(text)

    # Too few numbered starts means this is prose; use paragraphs instead.
    if len(boundaries) < 3:
        return _paragraph_clauses(text)

    clauses: list[Clause] = []
    seen_ids: dict[str, int] = {}
    section_heading = ""

    # Anything before the first numbered clause is the preamble.
    preamble = text[: boundaries[0][0]].strip()
    if len(preamble) >= _MIN_CLAUSE_CHARS:
        clauses.append(
            Clause(
                clause_id="P0",
                heading="Preamble",
                text=preamble,
                start=0,
                end=len(preamble),
                cross_references=_find_cross_references(preamble, "P0"),
            )
        )

    for i, (start, clause_id, inline_heading) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        block = text[start:end]
        body = block.strip()
        if not body:
            continue

        # Strip the number itself off the body for readability.
        body = _WORD_NUMBER_RE.sub("", body, count=1) if inline_heading else body
        body = _NUMBER_RE.sub("", body, count=1)
        body = body.strip()

        heading = inline_heading
        if not heading:
            heading, body = _extract_heading(body)
            body = body.strip()

        # "2. APPOINTMENT AND TERM" with sub-clauses under it is a section
        # title, not a clause. Remember it and hang it on the children.
        is_section_title = (
            not body
            and bool(heading)
            and i + 1 < len(boundaries)
            and boundaries[i + 1][1].startswith(f"{clause_id}.")
        )
        if is_section_title:
            section_heading = heading
            continue

        if not heading and "." in clause_id and section_heading:
            heading = section_heading
        elif heading and "." not in clause_id:
            section_heading = heading

        if len(body) < 4:
            continue

        # Guarantee unique ids even if the document repeats a number.
        unique_id = clause_id
        if unique_id in seen_ids:
            seen_ids[unique_id] += 1
            unique_id = f"{clause_id}#{seen_ids[clause_id]}"
        else:
            seen_ids[unique_id] = 1

        clauses.append(
            Clause(
                clause_id=unique_id,
                heading=heading,
                text=body,
                start=start,
                end=end,
                cross_references=_find_cross_references(block, clause_id),
            )
        )

    return clauses or _paragraph_clauses(text)


def clause_headings(clauses: list[Clause]) -> list[str]:
    """Compact heading list used to orient the Profiler."""
    out: list[str] = []
    for clause in clauses:
        label = clause.heading or clause.text[:60].replace("\n", " ")
        out.append(f"{clause.clause_id}: {label}")
    return out


def render_clauses(clauses: list[Clause], *, with_text: bool = True) -> str:
    """Render clauses as a numbered block for prompting."""
    parts: list[str] = []
    for clause in clauses:
        header = f"[{clause.clause_id}]"
        if clause.heading:
            header += f" {clause.heading}"
        parts.append(f"{header}\n{clause.text}" if with_text else header)
    return "\n\n".join(parts)


def chunk_clauses(clauses: list[Clause], size: int) -> list[list[Clause]]:
    return [clauses[i : i + size] for i in range(0, len(clauses), size)]


def context_windows(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split raw text into overlapping windows for long documents."""
    if len(text) <= max_chars:
        return [text]
    windows: list[str] = []
    step = max(1, max_chars - overlap)
    for start in range(0, len(text), step):
        window = text[start : start + max_chars]
        if window.strip():
            windows.append(window)
        if start + max_chars >= len(text):
            break
    return windows
