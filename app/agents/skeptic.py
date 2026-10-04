from __future__ import annotations

import json
from ..agent import Agent
from ..schemas import SkepticOut, ReportFinding, Clause, ProfileOut

_SKEPTIC_PROMPT = """You are an adversarial reviewer. You are given a list of findings from other agents, along with the relevant clause text and the contract brief.
Your job is to try to DISPROVE each finding.

Is the clause misread? Is it standard and harmless? Is the severity overstated? Is something elsewhere in the document already protecting the user?

For each finding, output a verdict (confirmed | downgraded | needs_review | rejected), final_severity, final_confidence, and a 1-2 sentence reason.
Be rigorous. Reject findings that are petty or misunderstand standard mechanics.
"""

agent: Agent[SkepticOut] = Agent(
    name="Skeptic",
    role="Adversarial Reviewer",
    system_prompt=_SKEPTIC_PROMPT,
    output_schema=SkepticOut,
    temperature=0.0,
)

def build_input(profile: ProfileOut, findings: list[ReportFinding], clauses_by_id: dict[str, Clause]) -> str:
    findings_json = [
        {
            "id": f.id,
            "title": f.title,
            "category": f.category,
            "severity": f.severity,
            "why_risky_for_user": f.why_risky_for_user,
            "clause_ids": f.clause_ids,
        }
        for f in findings
    ]
    
    clauses_text = []
    for f in findings:
        for cid in f.clause_ids:
            if cid in clauses_by_id:
                c = clauses_by_id[cid]
                clauses_text.append(f"[{c.clause_id}] {c.heading}\n{c.text}")
    clauses_block = "\n\n".join(list(set(clauses_text)))

    return (
        f"CONTRACT BRIEF:\n{profile.contract_brief}\n\n"
        "RELEVANT CLAUSES:\n"
        "<<<CLAUSES_START>>>\n"
        f"{clauses_block}\n"
        "<<<CLAUSES_END>>>\n\n"
        "FINDINGS TO REVIEW:\n"
        f"{json.dumps(findings_json, indent=2)}\n\n"
        "Review these findings now."
    )
