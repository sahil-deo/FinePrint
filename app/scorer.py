"""Risk scoring. Arithmetic only, no model involved, fully deterministic.

Each surviving finding contributes ``severity_weight * final_confidence``:

    high = 3, medium = 2, low = 1

The weighted total is mapped onto 0-100 with a saturating curve so that a
handful of serious problems already reads as dangerous, while a long tail of
minor notes cannot push a fair document into the red:

    risk_score = round(100 * (1 - exp(-total / 8)))

Verdict bands:

    0-24   Fair
    25-49  Review carefully
    50-74  Risky
    75-100 Dangerous
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from .schemas import ReportFinding, ScoreOut

SEVERITY_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0}

#: Verdicts whose findings count towards the score. Rejected ones never do.
SCORING_VERDICTS = {"confirmed", "downgraded", "needs_review"}

#: Controls how quickly the curve saturates.
SATURATION = 8.0

VERDICT_BANDS: Sequence[tuple[int, str]] = (
    (25, "Fair"),
    (50, "Review carefully"),
    (75, "Risky"),
    (101, "Dangerous"),
)


def weighted_total(findings: Iterable[ReportFinding]) -> float:
    """Sum of severity weight times confidence over scoring findings."""
    total = 0.0
    for finding in findings:
        if finding.verdict not in SCORING_VERDICTS:
            continue
        weight = SEVERITY_WEIGHT.get(finding.final_severity, 2.0)
        confidence = min(1.0, max(0.0, float(finding.final_confidence)))
        total += weight * confidence
    return round(total, 4)


def score_from_total(total: float) -> int:
    """Map a weighted total onto a saturating 0-100 scale."""
    total = max(0.0, total)
    return int(round(100 * (1 - math.exp(-total / SATURATION))))


def verdict_label(score: int) -> str:
    for ceiling, label in VERDICT_BANDS:
        if score < ceiling:
            return label
    return VERDICT_BANDS[-1][1]


def count_by(findings: Iterable[ReportFinding]) -> dict[str, int]:
    """Counts by severity (scoring findings) and by Skeptic verdict (all)."""
    counts = {
        "high": 0,
        "medium": 0,
        "low": 0,
        "confirmed": 0,
        "downgraded": 0,
        "needs_review": 0,
        "rejected": 0,
        "total": 0,
    }
    for finding in findings:
        counts[finding.verdict] = counts.get(finding.verdict, 0) + 1
        if finding.verdict in SCORING_VERDICTS:
            counts["total"] += 1
            counts[finding.final_severity] = counts.get(finding.final_severity, 0) + 1
    return counts


def score(findings: Sequence[ReportFinding]) -> ScoreOut:
    """Produce the final score block for the report."""
    total = weighted_total(findings)
    value = score_from_total(total)
    return ScoreOut(
        risk_score=value,
        verdict_label=verdict_label(value),
        raw_total=total,
        counts=count_by(findings),
    )
