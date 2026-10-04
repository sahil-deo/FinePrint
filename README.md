# FinePrint

A multi-agent hidden-clause finder for any agreement. FinePrint helps ordinary people understand what they are signing before they sign it, flagging risky clauses, challenging its own findings, and explaining what to ask for instead.

## How it works

FinePrint uses a specialized team of AI agents working together without any heavy framework (no LangChain/CrewAI). It relies entirely on `asyncio` and simple Python objects.

```text
Segmenter (Code) -> Profiler -> Readers (Parallel) -> Hunters (Parallel) -> Cross-Clause Analyst -> Grounding (Code) -> Skeptic -> Advisor -> Score
```

### The Grounding Guardrail
FinePrint is heavily constrained against hallucination.
1. Every finding must include a VERBATIM quote from the document.
2. A deterministic Python grounding check verifies the quote exists in the text.
3. If the quote isn't in the document, the finding is silently dropped.
4. An adversarial Skeptic agent then reviews every surviving finding and tries to disprove it.

## Setup and Run

1. `pip install -r requirements.txt`
2. `cp .env.example .env`
3. Add your `GEMINI_API_KEY` and `GEMINI_MODEL` to `.env`.
4. Run the server: `uvicorn app.api:app --reload`
5. Open `http://localhost:8000`

### Demo Mode
If you don't have a Gemini API key, you can run FinePrint in demo mode, which replays recorded events.
Set `FINEPRINT_DEMO=1` in your `.env` or just run the server without an API key.

To record a new demo cache:
`python -m app.record_demo`

## Scoring
The risk score is a deterministic calculation:
1. Each surviving finding gets a weight based on severity (High=3, Medium=2, Low=1).
2. Weight is multiplied by the Skeptic's final confidence (0-1).
3. The sum is passed through a saturating exponential curve: `round(100 * (1 - exp(-total / 8)))`

## Limitations
- No OCR: FinePrint currently only supports text-based PDFs and plain text.
- AI can make mistakes: This is a decision-support tool, not legal advice. Always verify important points with a qualified lawyer.
