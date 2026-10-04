"""The single place where Gemini is called.

Everything funnels through `chat_json` so that concurrency limiting,
retries and backoff behave identically for every agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from . import config

log = logging.getLogger("fineprint.llm")

_MAX_ATTEMPTS = 5
_BASE_DELAY = 1.2
_MAX_DELAY = 20.0

_client: genai.Client | None = None
_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None


class LLMError(RuntimeError):
    """Raised when a model call cannot be completed."""


def get_client() -> genai.Client:
    global _client
    if _client is None:
        config.require_live_config()
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    """One semaphore per running loop, sized by GEMINI_CONCURRENCY."""
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(max(1, config.GEMINI_CONCURRENCY))
        _semaphore_loop = loop
    return _semaphore


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, APIError):
        # Retry on standard network and rate limit errors
        code = getattr(exc, "code", getattr(exc, "status_code", None))
        if code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
    return isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError))


async def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 8000,
) -> dict[str, Any]:
    """Call the configured Gemini model and return the parsed JSON object."""
    client = get_client()
    semaphore = _get_semaphore()
    last_exc: Exception | None = None

    # We use response_mime_type="application/json" to force JSON output
    config_opts = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        max_output_tokens=max_tokens,
        response_mime_type="application/json",
    )

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with semaphore:
                # Use the asynchronous client properly for genai
                response = await client.aio.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=user_prompt,
                    config=config_opts,
                )
            raw = (response.text or "").strip()
            return _parse_json_object(raw)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= _MAX_ATTEMPTS or not _is_retryable(exc):
                break
            delay = min(_MAX_DELAY, _BASE_DELAY * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.3)
            log.warning(
                "Gemini call failed (attempt %s/%s): %s - retrying in %.1fs",
                attempt,
                _MAX_ATTEMPTS,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    raise LLMError(f"Gemini call failed: {last_exc}") from last_exc


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a model response that should be a single JSON object."""
    if not raw:
        raise LLMError("The model returned an empty response.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = json.loads(_extract_object(raw))
    if not isinstance(parsed, dict):
        raise LLMError("The model returned JSON that is not an object.")
    return parsed


def _extract_object(raw: str) -> str:
    """Recover the outermost {...} from a response wrapped in prose or fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError("No JSON object found in the model response.")
    return text[start : end + 1]
