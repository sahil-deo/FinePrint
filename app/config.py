"""Central configuration. Everything that can vary comes from the environment.

No model name, key or tuning constant is hardcoded anywhere else in the app.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------------------
# Environment-driven settings
# ---------------------------------------------------------------------------

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "").strip()
GEMINI_CONCURRENCY: int = int(os.getenv("GEMINI_CONCURRENCY", "3") or "3")
DEMO_MODE: bool = os.getenv("FINEPRINT_DEMO", "0").strip() == "1"

# ---------------------------------------------------------------------------
# Pipeline tuning constants
# ---------------------------------------------------------------------------

#: Largest slice of raw contract text handed to a single LLM call.
MAX_CONTEXT_CHARS = 18_000

#: Overlap between context windows so a clause is never cut in half.
CONTEXT_OVERLAP_CHARS = 1_500

#: Clauses per Reader agent task.
READER_CHUNK_SIZE = 6

#: Characters of the head of the document given to the Profiler.
PROFILER_HEAD_CHARS = 6_000

#: Findings per Skeptic batch.
SKEPTIC_BATCH_SIZE = 5

#: Findings per Advisor batch.
ADVISOR_BATCH_SIZE = 5

#: Ratio above which an evidence quote counts as present in the source.
GROUNDING_THRESHOLD = 0.90

#: Title similarity above which two findings on the same clauses are merged.
MERGE_TITLE_THRESHOLD = 0.72

#: Upload guardrail.
MAX_UPLOAD_BYTES = 6 * 1024 * 1024

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SAMPLE_DIR = ROOT / "sample"
DEMO_CACHE_DIR = ROOT / "demo_cache"
STATIC_DIR = ROOT / "static"

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
}


def language_name(code: str) -> str:
    return SUPPORTED_LANGUAGES.get(code, "English")


def live_mode_available() -> bool:
    """True when real Groq calls can be made."""
    return bool(GEMINI_API_KEY and GEMINI_MODEL)


def require_live_config() -> None:
    """Fail fast with a clear message when live mode is impossible."""
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not GEMINI_MODEL:
        missing.append("GEMINI_MODEL")
    if missing:
        raise RuntimeError(
            "FinePrint cannot start a live analysis: missing "
            + " and ".join(missing)
            + ". Set them in .env (see .env.example), or set FINEPRINT_DEMO=1 "
            "to replay recorded runs without any API calls."
        )


def effective_demo_mode() -> bool:
    """Demo mode is on when asked for, or when live config is unavailable."""
    return DEMO_MODE or not live_mode_available()
