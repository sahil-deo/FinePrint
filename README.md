# FinePrint

**Live Deployment**: [https://fineprint-sngs.onrender.com/](https://fineprint-sngs.onrender.com/)

FinePrint is an AI-powered contract analysis tool designed to help ordinary people understand what they are signing before they sign it. It dissects legal agreements into plain language, surfaces hidden traps and one-sided clauses, verifies evidence against the document to eliminate hallucinations, and provides concrete negotiation advice and counter-clauses.

---

## Key Features

- **Plain-Language Summaries**: Translates dense legal jargon into plain language, identifying user vs. counterparty obligations, monetary penalties, time limits, and overall clause balance.
- **Hidden Risk & Trap Detection**: Uncovers exit penalties, IP assignments, unilateral modification rights, harsh indemnities, and unfair arbitration clauses.
- **Strict Grounding Guardrail**: Zero-tolerance policy for hallucinations. Every detected risk must cite a verbatim quote from the text, which is deterministically verified by Python string-matching code before reaching the report.
- **Adversarial Skepticism**: Filters out boilerplate and false alarms by rigorously evaluating each candidate finding.
- **Negotiation Playbook**: Generates actionable advice, replacement counter-clause drafting, priority rankings, and specific questions to ask the other party.
- **Multilingual Support**: Delivers negotiation advice and executive summaries in **English (`en`)**, **Hindi (`hi`)**, or **Marathi (`mr`)**.
- **Flexible Document Ingestion**: Paste raw text or upload contracts directly as `.txt` or `.pdf` files.
- **Real-Time Streaming UI**: Live progress tracking via Server-Sent Events (SSE) without page reloads.
- **Zero-Dependency Frontend**: Pure HTML5, CSS3, and vanilla ES6 JavaScript—no Node.js build step or bulky frontend dependencies required.
- **Demo Replay Mode**: Complete offline evaluation mode replaying cached runs without requiring an API key.

---

## How It Works: The Analysis Pipeline

FinePrint blends deterministic Python parsing and verification with Google Gemini models. Rather than relying on heavyweight agent frameworks (like LangChain or CrewAI), the core pipeline runs on native `asyncio`, Pydantic models, and structured JSON schemas.

```text
Contract Text / PDF
        │
        ▼
[1] Clause Segmenter (Deterministic Python)
        │
        ▼
[2] FullReader Agent (Gemini)
        │  ↳ Plain summaries, obligations, balance, penalties per clause
        ▼
[3] FullRiskAnalyst Agent (Gemini)
        │  ↳ Profiles contract, extracts risky findings with verbatim quotes,
        │    evaluates findings adversarially, generates counter-clauses & questions
        ▼
[4] Grounding & Deduplication (Deterministic Python)
        │  ↳ Verifies quotes against source text (threshold = 0.90)
        │  ↳ Drops ungrounded quotes / merges duplicates (threshold = 0.72)
        ▼
[5] Risk Scorer (Deterministic Python)
        │  ↳ Saturating exponential curve mapping risk to 0-100 scale
        ▼
Structured Report & SSE Event Stream
```

### 1. Deterministic Clause Segmentation (`app/segmenter.py`)
Splits the contract into distinct, numbered clauses and extracts cross-references using regex and structural layout rules.

### 2. FullReader Pass (`app/agents/simplified.py`)
Reads all clauses in a single pass to produce:
- Plain-English summaries
- Obligations placed on the user vs. the counterparty
- Monetary terms, fees, and penalties
- Deadlines and critical dates
- Clause balance rating (`user_favourable`, `neutral`, `one_sided`, or `unclear`)

### 3. FullRiskAnalyst Pass (`app/agents/simplified.py`)
Conducts unified document profiling, risk discovery, skepticism, and negotiation advice in one pass:
- **Contract Profile**: Identifies document type, contracting parties, and user role.
- **Risk Findings**: Identifies hidden clauses and assigns severity, confidence, and verbatim quotes.
- **Adversarial Review**: Tests findings to weed out standard commercial boilerplate and confirm genuine exposure.
- **Negotiation Strategy**: Drafts proposed replacement clauses and lists questions to ask before signing.
*(Note: The orchestrator emits SSE status updates for the UI visualization matching each analysis phase).*

### 4. Deterministic Grounding Guardrail (`app/grounding.py`)
Before any finding is presented in the final report:
- Every cited quote is verified against the source text using whitespace- and punctuation-tolerant fuzzy matching (`GROUNDING_THRESHOLD = 0.90`).
- If an LLM-generated quote does not exist verbatim in the document, it is stripped. Findings with no surviving quotes are dropped completely.
- Duplicate findings covering the same clauses are merged (`MERGE_TITLE_THRESHOLD = 0.72`).

### 5. Risk Scoring (`app/scorer.py`)
The risk score is a deterministic mathematical calculation (no LLM subjectivity):
1. Each verified finding is assigned a weight based on severity:
   - **High**: 3.0
   - **Medium**: 2.0
   - **Low**: 1.0
2. The weight is multiplied by the confidence score (0.0 to 1.0).
3. The sum of all active findings is mapped onto a 0–100 scale using a saturating exponential curve:
   $$\text{risk\_score} = \text{round}\left(100 \times \left(1 - e^{-\frac{\text{total}}{8}}\right)\right)$$
4. The final score corresponds to one of four clear verdict bands:
   - **0 – 24**: Fair
   - **25 – 49**: Review carefully
   - **50 – 74**: Risky
   - **75 – 100**: Dangerous

---

## API Endpoints

The FastAPI backend exposes the following REST & streaming endpoints:

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/analyze` | `POST` | Initiates analysis in background. Accepts `text` (form field), `language` (`en`, `hi`, `mr`), and optional `file` upload (.txt or .pdf). Returns `{"job_id": "<uuid>"}`. |
| `/stream/{job_id}` | `GET` | Server-Sent Events (SSE) stream broadcasting real-time progress events (`agent_started`, `finding_discovered`, `finding_verdict`, `report_ready`, etc.). |
| `/report/{job_id}` | `GET` | Returns the complete final structured report JSON (`Report` schema). |
| `/sample/{name}` | `GET` | Returns built-in sample contract text (e.g. `rental_agreement.txt`, `employment_nimbus.txt`). |
| `/healthz` | `GET` | Health check endpoint returning `{"status": "ok"}`. |

---

## Setup and Run Locally

### Prerequisites
- Python 3.10+
- A Google Gemini API Key

### Installation

1. **Clone the repository and install dependencies**:
   ```bash
   git clone https://github.com/sahil-deo/FinePrint.git
   cd fineprint
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your settings:
   ```env
   # Your Google Gemini API key
   GEMINI_API_KEY=your_gemini_api_key_here

   # Gemini chat model (e.g. gemini-2.5-flash)
   GEMINI_MODEL=gemini-2.5-flash

   # Maximum parallel LLM calls
   GEMINI_CONCURRENCY=5

   # Set to 1 to run purely in offline demo replay mode
   FINEPRINT_DEMO=0
   ```

3. **Start the server**:
   ```bash
   uvicorn app.api:app --reload
   ```

4. **Open in browser**:
   Navigate to `http://localhost:8000` to use the web application.

---

## Demo Mode

FinePrint can run entirely offline without a Gemini API key:
- Set `FINEPRINT_DEMO=1` in your `.env`, or simply leave `GEMINI_API_KEY` blank.
- The server will automatically replay pre-recorded SSE event streams from `demo_cache/<sample_name>.json`.

To record a new demo cache from a sample contract:
```bash
python -m app.record_demo
```

---

## Testing

Run unit tests covering the segmenter, grounding fuzzy matcher, risk scoring math, and demo mode replay:
```bash
python3 -m pytest
```

---

## Technology Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/), [Pydantic v2](https://docs.pydantic.dev/), [Uvicorn](https://www.uvicorn.org/)
- **LLM SDK**: [Google GenAI SDK (`google-genai`)](https://github.com/googleapis/python-genai)
- **PDF Extraction**: [pdfplumber](https://github.com/jsvine/pdfplumber)
- **Frontend**: Vanilla HTML5, CSS3 (custom CSS design system), Modern JavaScript (Fetch & EventSource API)
- **Deployment**: Docker (`Dockerfile`), Render (`render.yaml`)
