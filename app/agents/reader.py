"""Readers: parallel plain-language passes over small batches of clauses.

Readers do not hunt for risk. Their job is an honest, mechanical translation
of each clause so the Hunters and the Cross-Clause Analyst can reason over a
compact, faithful view of the whole document.
"""

from __future__ import annotations

from ..agent import Agent
from ..schemas import Clause, ProfileOut, ReaderOut
from ..segmenter import render_clauses

SYSTEM_PROMPT = """You are a Reader. You translate clauses into plain language for a person with no legal training. You are not judging risk yet; another team does that. Be accurate and complete rather than interesting.

For EVERY clause you are given, produce one entry with:
- clause_id: exactly the id shown in square brackets. Never invent or renumber ids.
- plain_summary: one or two short sentences in simple language. Explain what the clause actually does. Avoid legal vocabulary; if you must use a legal term, put it in brackets after the plain word.
- obligations_on_user: what this clause requires the user to do, give up, or tolerate. One short item each. Empty list if none.
- obligations_on_counterparty: what the other party must do under this clause. Empty list if none. An empty list here next to a long user list is itself worth noticing.
- money_or_penalties: every amount, rate, fee, deposit, deduction, forfeiture or financial consequence mentioned, with the figure as written.
- time_limits: every period, deadline, notice requirement or duration, as written.
- balance: one of user_favourable, neutral, one_sided, unclear. Use one_sided when the clause gives one party a right or protection the other does not have. Use unclear when the wording is too vague to tell.
- notes: anything surprising, internally inconsistent, unusually broad, or that seems to reach further than its heading suggests. Keep it to one sentence, or leave it empty.

Return one entry per clause given, in the same order. Do not skip clauses and do not add clauses that were not given to you."""


agent: Agent[ReaderOut] = Agent(
    name="Readers",
    role=(
        "Turn each clause into an accurate plain-language summary with its "
        "obligations, money, time limits and balance."
    ),
    system_prompt=SYSTEM_PROMPT,
    output_schema=ReaderOut,
    max_tokens=8000,
)


def build_input(brief: str, profile: ProfileOut, clauses: list[Clause]) -> str:
    return (
        f"CONTRACT BRIEF:\n{brief}\n\n"
        f"THE USER (the party to protect): {profile.user_role}"
        + (f" - {profile.user_party_name}" if profile.user_party_name else "")
        + "\n\n"
        "CLAUSES TO READ:\n"
        "<<<CLAUSES_START>>>\n"
        f"{render_clauses(clauses)}\n"
        "<<<CLAUSES_END>>>\n\n"
        f"Produce exactly {len(clauses)} entries, one per clause above."
    )
