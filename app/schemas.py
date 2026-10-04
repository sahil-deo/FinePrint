"""Shared pydantic models for the pipeline and the final report."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["high", "medium", "low"]
Balance = Literal["user_favourable", "neutral", "one_sided", "unclear"]
Verdict = Literal["confirmed", "downgraded", "needs_review", "rejected"]


class Lenient(BaseModel):
    """Base model that tolerates extra keys from the model."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


def normalise_severity(value: object) -> object:
    """Map the many words models use onto the three rubric levels."""
    if isinstance(value, str):
        key = value.strip().lower()
        if key in {"critical", "severe", "high", "serious"}:
            return "high"
        if key in {"moderate", "medium", "med"}:
            return "medium"
        if key in {"minor", "low", "informational", "info", "none"}:
            return "low"
    return value


def normalise_confidence(value: object) -> object:
    """Coerce a confidence into the 0-1 range, tolerating percentages."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.6
    if number > 1:
        number = number / 100 if number <= 100 else 1.0
    return min(1.0, max(0.0, number))


# ---------------------------------------------------------------------------
# Segmenter output (code, not an agent)
# ---------------------------------------------------------------------------


class Clause(Lenient):
    clause_id: str
    heading: str = ""
    text: str
    start: int
    end: int
    cross_references: list[str] = Field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.clause_id} {self.heading}".strip()


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------


class Party(Lenient):
    name: str
    role: str


class GlossaryEntry(Lenient):
    term: str
    definition: str
    clause_id: str = ""


class ProfileOut(Lenient):
    document_type: str
    parties: list[Party] = Field(default_factory=list)
    user_role: str
    user_party_name: str = ""
    governing_law: str = ""
    jurisdiction: str = ""
    term_duration: str = ""
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    contract_brief: str


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


class ClauseReading(Lenient):
    clause_id: str
    plain_summary: str
    obligations_on_user: list[str] = Field(default_factory=list)
    obligations_on_counterparty: list[str] = Field(default_factory=list)
    money_or_penalties: list[str] = Field(default_factory=list)
    time_limits: list[str] = Field(default_factory=list)
    balance: Balance = "unclear"
    notes: str = ""

    @field_validator("balance", mode="before")
    @classmethod
    def _normalise_balance(cls, value: object) -> object:
        if isinstance(value, str):
            key = value.strip().lower().replace(" ", "_").replace("-", "_")
            mapping = {
                "user_favorable": "user_favourable",
                "user_favourable": "user_favourable",
                "favourable": "user_favourable",
                "favorable": "user_favourable",
                "neutral": "neutral",
                "balanced": "neutral",
                "one_sided": "one_sided",
                "onesided": "one_sided",
                "unclear": "unclear",
                "ambiguous": "unclear",
            }
            return mapping.get(key, "unclear")
        return value


class ReaderOut(Lenient):
    readings: list[ClauseReading] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Hunters and Cross-Clause Analyst
# ---------------------------------------------------------------------------


class RawFinding(Lenient):
    title: str
    category: str = ""
    clause_ids: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    what_it_says: str = ""
    why_risky_for_user: str = ""
    severity: Severity = "medium"
    confidence: float = 0.6
    generally_negotiable: bool = False
    legal_interpretation: bool = False

    @field_validator("severity", mode="before")
    @classmethod
    def _normalise_severity(cls, value: object) -> object:
        return normalise_severity(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalise_confidence(cls, value: object) -> object:
        return normalise_confidence(value)

    @field_validator("clause_ids", "evidence_quotes", mode="before")
    @classmethod
    def _listify(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class FindingsOut(Lenient):
    findings: list[RawFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Skeptic
# ---------------------------------------------------------------------------


class SkepticReview(Lenient):
    finding_id: str
    verdict: Verdict = "needs_review"
    final_severity: Severity = "medium"
    final_confidence: float = 0.5
    reason: str = ""

    @field_validator("final_severity", mode="before")
    @classmethod
    def _normalise_final_severity(cls, value: object) -> object:
        return normalise_severity(value)

    @field_validator("final_confidence", mode="before")
    @classmethod
    def _normalise_final_confidence(cls, value: object) -> object:
        return normalise_confidence(value)

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalise_verdict(cls, value: object) -> object:
        if isinstance(value, str):
            key = value.strip().lower().replace(" ", "_").replace("-", "_")
            mapping = {
                "confirmed": "confirmed",
                "confirm": "confirmed",
                "valid": "confirmed",
                "upheld": "confirmed",
                "downgraded": "downgraded",
                "downgrade": "downgraded",
                "needs_review": "needs_review",
                "review": "needs_review",
                "uncertain": "needs_review",
                "rejected": "rejected",
                "reject": "rejected",
                "invalid": "rejected",
            }
            return mapping.get(key, "needs_review")
        return value


class SkepticOut(Lenient):
    reviews: list[SkepticReview] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Advisor
# ---------------------------------------------------------------------------


class Advice(Lenient):
    finding_id: str
    plain_explanation: str = ""
    what_to_ask_for: str = ""
    suggested_counter_clause: str = ""
    negotiation_priority: int = 5

    @field_validator("negotiation_priority", mode="before")
    @classmethod
    def _as_int(cls, value: object) -> object:
        try:
            return int(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 5


class AdvisorOut(Lenient):
    advice: list[Advice] = Field(default_factory=list)


class AdvisorSummaryOut(Lenient):
    executive_summary: str
    questions_to_ask: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------


class ReportFinding(Lenient):
    id: str
    title: str
    category: str
    clause_ids: list[str]
    evidence_quotes: list[str]
    what_it_says: str
    why_risky_for_user: str
    severity: Severity
    confidence: float
    generally_negotiable: bool
    legal_interpretation: bool = False
    found_by: list[str] = Field(default_factory=list)
    verdict: Verdict = "needs_review"
    skeptic_reason: str = ""
    final_severity: Severity = "medium"
    final_confidence: float = 0.5
    plain_explanation: str = ""
    what_to_ask_for: str = ""
    suggested_counter_clause: str = ""
    negotiation_priority: int = 5


class ScoreOut(Lenient):
    risk_score: int
    verdict_label: str
    raw_total: float
    counts: dict[str, int] = Field(default_factory=dict)


class Report(Lenient):
    job_id: str
    language: str
    document_name: str
    document_text: str
    demo: bool = False
    profile: ProfileOut | None = None
    clauses: list[Clause] = Field(default_factory=list)
    readings: list[ClauseReading] = Field(default_factory=list)
    findings: list[ReportFinding] = Field(default_factory=list)
    rejected_findings: list[ReportFinding] = Field(default_factory=list)
    executive_summary: str = ""
    questions_to_ask: list[str] = Field(default_factory=list)
    score: ScoreOut | None = None
    stats: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
