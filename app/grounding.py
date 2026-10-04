"""The grounding guardrail: code, not an agent.

A finding only survives if at least one of its evidence quotes genuinely
appears in the source document. This is what stops the pipeline from
presenting an invented clause as fact. Matching is whitespace- and
quote-insensitive and allows a small amount of fuzz for OCR-style noise, but
nothing close to a paraphrase.

Surviving findings are then de-duplicated: when several agents describe the
same clause with a similar title, the best-supported one is kept and every
contributing agent is recorded.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from . import config
from .schemas import RawFinding

_QUOTE_CHARS = dict.fromkeys(
    map(ord, "\u2018\u2019\u201a\u201b\u2032\u00b4\u0060"), "'"
)
_QUOTE_CHARS.update(dict.fromkeys(map(ord, "\u201c\u201d\u201e\u201f\u2033"), '"'))
_DASH_CHARS = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015"), "-")

_MIN_QUOTE_CHARS = 12
_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "and",
    "or",
    "in",
    "on",
    "for",
    "by",
    "is",
    "be",
    "any",
    "all",
    "this",
    "that",
    "with",
    "shall",
    "may",
    "no",
    "not",
    "at",
    "as",
    "clause",
    "user",
    "employee",
    "licensee",
    "company",
    "licensor",
}


def normalise(text: str) -> str:
    """Canonical form used for quote comparison."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_QUOTE_CHARS).translate(_DASH_CHARS)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\s]+", " ", text)
    return text.strip().lower()


def _strip_ellipses(text: str) -> list[str]:
    """Split a quote containing an ellipsis into its contiguous fragments."""
    parts = re.split(r"\s*(?:\.\.\.|\u2026|\[\.\.\.\])\s*", text)
    return [p.strip() for p in parts if len(p.strip()) >= _MIN_QUOTE_CHARS]


def quote_in_source(quote: str, normalised_source: str) -> bool:
    """True when ``quote`` appears in the source under normalisation.

    Exact (normalised) substring match first; then a sliding fuzzy match with a
    high ratio threshold; then, for quotes stitched together with an ellipsis,
    each fragment must be present.
    """
    needle = normalise(quote)
    if len(needle) < _MIN_QUOTE_CHARS:
        return False
    if needle in normalised_source:
        return True

    fragments = _strip_ellipses(quote)
    if len(fragments) > 1:
        return all(
            quote_in_source(fragment, normalised_source) for fragment in fragments
        )

    return _fuzzy_contains(needle, normalised_source, config.GROUNDING_THRESHOLD)


def _fuzzy_contains(needle: str, haystack: str, threshold: float) -> bool:
    """Sliding-window fuzzy containment.

    Anchors on the needle's first distinctive word so the scan stays cheap on
    long documents, then compares windows of the needle's length.
    """
    if not needle or not haystack:
        return False

    anchors = [w for w in needle.split()[:6] if len(w) > 3] or needle.split()[:1]
    span = len(needle)
    slack = max(12, int(span * 0.25))

    positions: list[int] = []
    for anchor in anchors:
        start = 0
        while len(positions) < 400:
            index = haystack.find(anchor, start)
            if index == -1:
                break
            positions.append(index)
            start = index + 1
    if not positions:
        return False

    for position in sorted(set(positions)):
        begin = max(0, position - slack)
        window = haystack[begin : position + span + slack]
        if not window:
            continue
        # The window is deliberately longer than the needle, so score by how
        # much of the needle is matched rather than by overall similarity.
        if _coverage_ratio(window, needle) >= threshold:
            return True
    return False


def _coverage_ratio(window: str, needle: str) -> float:
    """Fraction of the needle that appears, in order, inside the window."""
    matcher = SequenceMatcher(None, window, needle, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / max(1, len(needle))


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass
class VerifiedFinding:
    """A finding that survived grounding, with provenance attached."""

    finding: RawFinding
    found_by: list[str] = field(default_factory=list)
    valid_quotes: list[str] = field(default_factory=list)
    dropped_quotes: list[str] = field(default_factory=list)
    id: str = ""


@dataclass
class GroundingResult:
    kept: list[VerifiedFinding]
    dropped: int
    dropped_quote_count: int


def verify_findings(
    candidates: list[tuple[str, RawFinding]],
    source_text: str,
) -> GroundingResult:
    """Drop findings whose evidence cannot be located in the document."""
    haystack = normalise(source_text)
    kept: list[VerifiedFinding] = []
    dropped = 0
    dropped_quotes = 0

    for agent_name, finding in candidates:
        valid: list[str] = []
        invalid: list[str] = []
        for quote in finding.evidence_quotes:
            cleaned = (quote or "").strip().strip('"').strip()
            if not cleaned:
                continue
            if quote_in_source(cleaned, haystack):
                if cleaned not in valid:
                    valid.append(cleaned)
            else:
                invalid.append(cleaned)

        dropped_quotes += len(invalid)
        if not valid:
            dropped += 1
            continue

        grounded = finding.model_copy(update={"evidence_quotes": valid})
        kept.append(
            VerifiedFinding(
                finding=grounded,
                found_by=[agent_name],
                valid_quotes=valid,
                dropped_quotes=invalid,
            )
        )

    return GroundingResult(kept=kept, dropped=dropped, dropped_quote_count=dropped_quotes)


# ---------------------------------------------------------------------------
# Duplicate merging
# ---------------------------------------------------------------------------


def _title_key(title: str) -> set[str]:
    words = re.findall(r"[a-z]+", (title or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _title_similarity(a: str, b: str) -> float:
    key_a, key_b = _title_key(a), _title_key(b)
    if key_a and key_b:
        overlap = len(key_a & key_b) / len(key_a | key_b)
        if overlap >= 0.5:
            return max(overlap, SequenceMatcher(None, a.lower(), b.lower()).ratio())
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _clause_set(finding: RawFinding) -> set[str]:
    return {c.strip() for c in finding.clause_ids if c and c.strip()}


_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _support_score(item: VerifiedFinding) -> tuple:
    finding = item.finding
    return (
        len(item.found_by),
        len(item.valid_quotes),
        _SEVERITY_RANK.get(finding.severity, 2),
        finding.confidence,
        len(finding.why_risky_for_user or ""),
    )


def merge_duplicates(items: list[VerifiedFinding]) -> tuple[list[VerifiedFinding], int]:
    """Merge findings that share clause ids and describe the same problem."""
    merged: list[VerifiedFinding] = []
    merge_count = 0

    for item in items:
        target: VerifiedFinding | None = None
        for existing in merged:
            shared = _clause_set(item.finding) & _clause_set(existing.finding)
            if not shared:
                continue
            similarity = _title_similarity(item.finding.title, existing.finding.title)
            if similarity >= config.MERGE_TITLE_THRESHOLD:
                target = existing
                break

        if target is None:
            merged.append(item)
            continue

        merge_count += 1
        winner, loser = (
            (item, target)
            if _support_score(item) > _support_score(target)
            else (target, item)
        )

        found_by = list(dict.fromkeys(target.found_by + item.found_by))
        quotes = list(dict.fromkeys(winner.valid_quotes + loser.valid_quotes))[:6]
        clause_ids = list(
            dict.fromkeys(winner.finding.clause_ids + loser.finding.clause_ids)
        )
        severity = (
            winner.finding.severity
            if _SEVERITY_RANK.get(winner.finding.severity, 2)
            >= _SEVERITY_RANK.get(loser.finding.severity, 2)
            else loser.finding.severity
        )
        confidence = max(winner.finding.confidence, loser.finding.confidence)
        # Independent agreement is evidence; nudge confidence up a little.
        if len(found_by) > 1:
            confidence = min(1.0, confidence + 0.05 * (len(found_by) - 1))

        target.finding = winner.finding.model_copy(
            update={
                "evidence_quotes": quotes,
                "clause_ids": clause_ids,
                "severity": severity,
                "confidence": confidence,
                "generally_negotiable": winner.finding.generally_negotiable
                or loser.finding.generally_negotiable,
                "legal_interpretation": winner.finding.legal_interpretation
                or loser.finding.legal_interpretation,
            }
        )
        target.found_by = found_by
        target.valid_quotes = quotes
        target.dropped_quotes = list(
            dict.fromkeys(target.dropped_quotes + item.dropped_quotes)
        )

    for index, item in enumerate(merged, start=1):
        item.id = f"F{index:02d}"

    return merged, merge_count
