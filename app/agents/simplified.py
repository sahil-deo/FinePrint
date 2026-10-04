from __future__ import annotations

import json
from pydantic import Field
from ..agent import Agent
from ..schemas import Lenient, ClauseReading, Severity, Verdict, ReaderOut

class UnifiedFinding(Lenient):
    title: str
    category: str
    clause_ids: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    what_it_says: str = ""
    why_risky_for_user: str = ""
    severity: Severity = "medium"
    confidence: float = 0.8
    generally_negotiable: bool = False
    legal_interpretation: bool = False
    verdict: Verdict = "confirmed"
    skeptic_reason: str = "Verified by unified risk analysis."
    plain_explanation: str = ""
    what_to_ask_for: str = ""
    suggested_counter_clause: str = ""
    negotiation_priority: int = 5

class UnifiedRiskOut(Lenient):
    profile_document_type: str = "Agreement"
    profile_parties: list[dict] = Field(default_factory=list)
    profile_user_role: str = "User"
    profile_brief: str = ""
    findings: list[UnifiedFinding] = Field(default_factory=list)
    executive_summary: str = ""
    questions_to_ask: list[str] = Field(default_factory=list)

_READER_PROMPT = """You translate clauses into plain language for a person with no legal training.
Be accurate and complete. Output a simple reading of the entire document's clauses.

For EVERY clause in the text, produce one entry in the `readings` list with:
- clause_id
- plain_summary
- obligations_on_user
- obligations_on_counterparty
- money_or_penalties
- time_limits
- balance
- notes
"""

_RISK_PROMPT = """You are a master contract analyst. You read the full contract and the plain-language summaries.
You must find all hidden risks, challenge your own findings (acting as a skeptic), and provide negotiation advice.

Remember the rules:
- Protect the party with the least bargaining power.
- Every finding MUST quote the exact source text verbatim in `evidence_quotes`.
- Do not flag standard boilerplate.

Also extract the document profile (document_type, parties, user_role, brief).
Output the findings, an executive summary, and questions to ask.
"""

reader_agent = Agent(
    name="FullReader",
    role="Reads the entire document",
    system_prompt=_READER_PROMPT,
    output_schema=ReaderOut,
    temperature=0.1,
)

risk_agent = Agent(
    name="FullRiskAnalyst",
    role="Analyzes all risks in one pass",
    system_prompt=_RISK_PROMPT,
    output_schema=UnifiedRiskOut,
    temperature=0.1,
)

def build_reader_input(text: str) -> str:
    return f"CONTRACT TEXT:\n{text}\n\nProduce the clause readings."

def build_risk_input(text: str, readings: ReaderOut, language: str) -> str:
    readings_json = json.dumps([r.model_dump() for r in readings.readings], indent=2)
    return (
        f"LANGUAGE FOR ADVICE: {language}\n\n"
        f"CONTRACT TEXT:\n{text}\n\n"
        f"READER SUMMARIES:\n{readings_json}\n\n"
        "Find all risks, profile the document, and output the unified report."
    )
