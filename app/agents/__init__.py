"""The FinePrint agent team.

Each module owns one specialist: its prompt, its output schema and the helper
that renders its input. The orchestrator wires them together.
"""

from . import (  # noqa: F401
    simplified,
    advisor,
    cross_clause,
    hunters,
    profiler,
    reader,
    skeptic,
)

__all__ = [
    "advisor",
    "cross_clause",
    "hunters",
    "profiler",
    "reader",
    "skeptic",
]
