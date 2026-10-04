from __future__ import annotations

from ..agent import Agent
from ..schemas import FindingsOut, ProfileOut, ClauseReading

_CROSS_CLAUSE_PROMPT = """Your job is to find risks that emerge when clauses are read together. You do not read the full raw text; instead, rely on the Reader Summaries and Glossary.

Look for:
- Contradictions.
- Clauses that override or hollow out others (e.g., "notwithstanding", "subject to", "at its sole discretion" reached via cross-reference).
- Conflicting numbers for the same term.
- Defined terms used more broadly than defined.

Create a finding for each issue. Quote every clause involved verbatim.
"""

agent: Agent[FindingsOut] = Agent(
    name="Cross-Clause Analyst",
    role="Contract Structure Specialist",
    system_prompt=_CROSS_CLAUSE_PROMPT,
    output_schema=FindingsOut,
    temperature=0.1,
)

def build_input(profile: ProfileOut, readings: list[ClauseReading]) -> str:
    glossary = "\n".join(f"- {g.term}: {g.definition} ({g.clause_id})" for g in profile.glossary)
    summaries = "\n".join(f"[{r.clause_id}] {r.plain_summary}" for r in readings)
    return (
        f"CONTRACT BRIEF:\n{profile.contract_brief}\n\n"
        f"GLOSSARY:\n{glossary}\n\n"
        f"READER SUMMARIES:\n{summaries}\n\n"
        "Find risks that emerge when clauses are read together."
    )
