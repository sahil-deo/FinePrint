from __future__ import annotations

from ..agent import Agent
from ..schemas import Clause, FindingsOut, ProfileOut, ClauseReading
from ..segmenter import render_clauses

_HUNTER_PROMPT = """You are a Risk Hunter. Your job is to find risky, unbalanced, or unclear clauses that disadvantage the user (the signer).

Review the chunk carefully for issues in your specific category: {category_focus}.
For every issue found, create a finding. If a finding spans multiple clauses, cite all relevant clause IDs.
Remember the non-negotiable rules: ground everything with verbatim quotes, don't flag harmless boilerplate.
"""

def _create_hunter(name: str, role: str, category_focus: str) -> Agent[FindingsOut]:
    return Agent(
        name=name,
        role=role,
        system_prompt=_HUNTER_PROMPT.replace("{category_focus}", category_focus),
        output_schema=FindingsOut,
        temperature=0.1,
    )

agents: list[Agent[FindingsOut]] = [
    _create_hunter(
        "Money Hunter",
        "Financial Risk Specialist",
        "penalties, fees, deductions, auto-renewals, price changes, forfeitures, hidden costs"
    ),
    _create_hunter(
        "Exit Hunter",
        "Termination and Exit Risk Specialist",
        "termination, notice periods, lock-ins, bonds, non-competes, renewal traps, difficulty leaving"
    ),
    _create_hunter(
        "Control Hunter",
        "Control and Autonomy Specialist",
        "unilateral changes, 'sole discretion', one-sided rights, asymmetry between the parties"
    ),
    _create_hunter(
        "Rights Hunter",
        "Legal Rights and Liability Specialist",
        "liability caps, indemnities, IP, data and privacy, confidentiality, dispute resolution, jurisdiction, waivers"
    ),
    _create_hunter(
        "Gaps Hunter",
        "Omissions and Gaps Specialist",
        "vague or undefined terms, buried exceptions, and important protections that are MISSING (for example no right for the user to terminate, no deadline for the other party's obligations)"
    ),
]

def build_input(profile: ProfileOut, readings: list[ClauseReading], chunk: list[Clause]) -> str:
    glossary = "\n".join(f"- {g.term}: {g.definition} ({g.clause_id})" for g in profile.glossary)
    summaries = "\n".join(f"[{r.clause_id}] {r.plain_summary}" for r in readings)
    return (
        f"CONTRACT BRIEF:\n{profile.contract_brief}\n\n"
        f"GLOSSARY:\n{glossary}\n\n"
        f"READER SUMMARIES (for context):\n{summaries}\n\n"
        "CONTRACT CHUNK:\n"
        "<<<CHUNK_START>>>\n"
        f"{render_clauses(chunk)}\n"
        "<<<CHUNK_END>>>\n\n"
        "Review the chunk carefully for issues in your specific category."
    )
