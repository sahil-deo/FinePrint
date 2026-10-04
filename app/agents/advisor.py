from __future__ import annotations

import json
from ..agent import Agent
from ..schemas import AdvisorOut, AdvisorSummaryOut, ReportFinding, ProfileOut
from ..config import language_name

_ADVISOR_PROMPT = """You take confirmed and needs_review findings and explain them simply.

For each finding, output:
- plain_explanation: simple reading level explanation (in the chosen language; keep legal terms in English in brackets)
- what_to_ask_for: practical advice
- suggested_counter_clause: text they could suggest instead
- negotiation_priority: 1-10 rank (1=lowest, 10=highest)
"""

_SUMMARY_PROMPT = """Read the contract brief and the final findings, and produce an executive summary.

Output:
- A 3-4 sentence executive summary.
- 3-5 "Questions to ask before you sign".
"""

advice_agent: Agent[AdvisorOut] = Agent(
    name="Advisor",
    role="Client Advisor",
    system_prompt=_ADVISOR_PROMPT,
    output_schema=AdvisorOut,
    temperature=0.1,
)

summary_agent: Agent[AdvisorSummaryOut] = Agent(
    name="Summary Advisor",
    role="Client Advisor (Summary)",
    system_prompt=_SUMMARY_PROMPT,
    output_schema=AdvisorSummaryOut,
    temperature=0.1,
)

def build_advice_input(findings: list[ReportFinding], language_code: str) -> str:
    lang = language_name(language_code)
    findings_json = [
        {
            "id": f.id,
            "title": f.title,
            "what_it_says": f.what_it_says,
            "why_risky_for_user": f.why_risky_for_user,
            "final_severity": f.final_severity,
        }
        for f in findings
    ]
    return (
        f"LANGUAGE: {lang}\n\n"
        "FINDINGS:\n"
        f"{json.dumps(findings_json, indent=2)}\n\n"
        "Provide advice for each finding."
    )

def build_summary_input(profile: ProfileOut, findings: list[ReportFinding], language_code: str) -> str:
    lang = language_name(language_code)
    findings_json = [
        {
            "id": f.id,
            "title": f.title,
            "final_severity": f.final_severity,
        }
        for f in findings
    ]
    return (
        f"LANGUAGE: {lang}\n\n"
        f"CONTRACT BRIEF:\n{profile.contract_brief}\n\n"
        "FINDINGS:\n"
        f"{json.dumps(findings_json, indent=2)}\n\n"
        "Produce an executive summary and questions to ask."
    )
