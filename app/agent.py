"""The tiny Agent abstraction used by every specialist in FinePrint.

An agent is a name, a role, a system prompt and a pydantic output schema.
``run`` builds the prompt, calls the model, validates the result, and retries
once with the validation error appended so the model can correct itself.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from . import llm

log = logging.getLogger("fineprint.agent")

TOut = TypeVar("TOut", bound=BaseModel)

JSON_ONLY_RULE = (
    "Respond with a single JSON object matching the schema and nothing else."
)

SEVERITY_RUBRIC = """SEVERITY RUBRIC (use exactly these definitions):
- high: could cause significant financial loss, remove a fundamental right, trap the user, or is hard or impossible to reverse.
- medium: meaningfully one-sided, costly, or restrictive, but limited in scope or negotiable.
- low: minor imbalance, vagueness, or inconvenience worth knowing about."""

SHARED_RULES = """You are one specialist in FinePrint, a team of agents that helps an ordinary person understand an agreement before they sign it.

NON-NEGOTIABLE RULES:
1. Always reason from the perspective of the person signing who has the least bargaining power (called "the user"), as identified by the Profiler.
2. Ground everything in the document. Every claim must cite clause ids and include a VERBATIM quote copied character-for-character from the supplied text. Never paraphrase inside a quote. Never invent a quote. If you cannot quote the document for a point, do not make the point.
3. Never cite statutes, case law, regulations or "market standards" as facts unless they appear in the document itself. You may say "this is commonly negotiated" or "unusual compared to typical agreements of this kind" as general knowledge, clearly not as law.
4. Do not flag ordinary boilerplate unless something about it is unusual, one-sided, or unclear. Prefer fewer, well-supported findings over many weak ones.
5. Anything that depends on legal interpretation must be marked as such, and your output should suggest consulting a qualified lawyer on those points.
6. Never discuss pricing, plans, subscriptions, costs of using software, or any business model. You only analyse the agreement in front of you."""


class Agent(Generic[TOut]):
    """A single LLM specialist with a validated output contract."""

    def __init__(
        self,
        *,
        name: str,
        role: str,
        system_prompt: str,
        output_schema: type[TOut],
        temperature: float = 0.1,
        max_tokens: int = 8000,
    ) -> None:
        self.name = name
        self.role = role
        self.output_schema = output_schema
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = self._compose_system_prompt(system_prompt)

    def _compose_system_prompt(self, body: str) -> str:
        schema = json.dumps(
            self.output_schema.model_json_schema(), indent=2, ensure_ascii=False
        )
        return (
            f"{SHARED_RULES}\n\n"
            f"YOUR ROLE: {self.role}\n\n"
            f"{body.strip()}\n\n"
            f"OUTPUT JSON SCHEMA:\n{schema}\n\n"
            f"{JSON_ONLY_RULE}"
        )

    async def run(self, user_input: str) -> TOut:
        """Call the model and return a validated schema instance."""
        prompt = user_input
        last_error: Exception | None = None

        for attempt in (1, 2):
            try:
                raw: dict[str, Any] = await llm.chat_json(
                    system_prompt=self.system_prompt,
                    user_prompt=prompt,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                return self.output_schema.model_validate(raw)
            except (ValidationError, llm.LLMError, ValueError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                log.warning("%s output rejected, retrying once: %s", self.name, exc)
                prompt = (
                    f"{user_input}\n\n"
                    "YOUR PREVIOUS RESPONSE WAS REJECTED. Error:\n"
                    f"{_short(exc)}\n\n"
                    "Fix exactly these problems and respond again with a single "
                    "JSON object matching the schema and nothing else."
                )

        raise llm.LLMError(
            f"{self.name} did not produce a valid response: {_short(last_error)}"
        ) from last_error


def _short(exc: Exception | None, limit: int = 1500) -> str:
    text = str(exc or "unknown error")
    return text if len(text) <= limit else text[:limit] + " ...(truncated)"
