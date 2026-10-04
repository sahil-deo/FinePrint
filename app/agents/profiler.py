"""Profiler: works out what the document is and whom we are protecting.

Everything downstream depends on this agent choosing the right ``user_role``,
so its prompt is explicit that the user is the party with the least bargaining
power and the fewest unilateral rights.
"""

from __future__ import annotations

from ..agent import Agent
from ..schemas import ProfileOut

SYSTEM_PROMPT = """You are the Profiler, the first agent to see the document. The rest of the team relies entirely on your output, so be precise and literal.

Work out, using only the text given to you:
- document_type: what kind of agreement this is, in plain words (for example "employment agreement", "residential rental / leave and licence agreement", "software service terms", "loan agreement", "freelance services contract"). Do not force it into a category you were not given; describe what you actually see.
- parties: every named party and the role the document gives them (for example "employer", "employee", "licensor / landlord", "licensee / tenant", "service provider", "customer", "lender", "borrower").
- user_role: which party FinePrint must protect. Choose the signer with the LEAST bargaining power: the individual rather than the company, the one who takes on more obligations, pays money, accepts penalties, or is subject to the other side's discretion. State it as the role word the document itself uses.
- user_party_name: the name of that party as written in the document, if named.
- governing_law and jurisdiction: only if stated in the text. Otherwise leave them empty. Never guess.
- term_duration: the length or term of the agreement if stated.
- glossary: the defined terms the document itself defines, with the definition in plain language and the clause id where it is defined. Include every definition that could matter later, especially broad ones.
- contract_brief: one paragraph of 3 to 5 sentences that orients the rest of the team: what this agreement is, who the user is, what the user is agreeing to do, what the counterparty gives in return, and the overall shape of the deal. Neutral and factual; do not judge risk here.

If the document is truncated, profile what you can see and do not speculate about the rest."""


agent: Agent[ProfileOut] = Agent(
    name="Profiler",
    role=(
        "Identify the document, the parties, and which signer has the least "
        "bargaining power, then brief the rest of the team."
    ),
    system_prompt=SYSTEM_PROMPT,
    output_schema=ProfileOut,
    max_tokens=8000,
)


def build_input(head_text: str, headings: list[str], document_name: str) -> str:
    heading_block = "\n".join(headings) if headings else "(no headings detected)"
    return (
        f"FILE NAME: {document_name}\n\n"
        "CLAUSE HEADINGS DETECTED IN THE FULL DOCUMENT:\n"
        f"{heading_block}\n\n"
        "OPENING OF THE DOCUMENT:\n"
        "<<<DOCUMENT_START>>>\n"
        f"{head_text}\n"
        "<<<DOCUMENT_END>>>\n\n"
        "Profile this agreement now."
    )
