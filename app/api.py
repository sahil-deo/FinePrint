from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import FastAPI, UploadFile, Form, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, orchestrator
from .schemas import Report

app = FastAPI(title="FinePrint")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class JobStore:
    def __init__(self):
        self.jobs: dict[str, Report] = {}
        self.events: dict[str, list[str]] = {}
        self.waiters: dict[str, list[asyncio.Event]] = {}
        
    def add_event(self, job_id: str, event_type: str, data: dict):
        if job_id not in self.events:
            self.events[job_id] = []
        payload = json.dumps({"event": event_type, "data": data})
        self.events[job_id].append(payload)
        for w in self.waiters.get(job_id, []):
            w.set()

    def set_report(self, job_id: str, report: Report):
        self.jobs[job_id] = report

store = JobStore()

async def analyze_task(job_id: str, text: str, language: str, filename: str):
    store.events[job_id] = []
    store.waiters[job_id] = []
    
    if config.effective_demo_mode():
        # DEMO REPLAY MODE
        try:
            demo_file = config.DEMO_CACHE_DIR / f"{filename}.json"
            if demo_file.exists():
                with open(demo_file, "r") as f:
                    cached = json.load(f)
                for ev in cached.get("events", []):
                    await asyncio.sleep(0.3)  # realistic delay
                    store.add_event(job_id, ev["event"], ev["data"])
                store.set_report(job_id, Report.model_validate(cached["report"]))
                return
        except Exception as e:
            print(f"Demo replay failed: {e}")
    
    async def emit(event_type: str, data: dict):
        store.add_event(job_id, event_type, data)
        
    try:
        report = await orchestrator.run_pipeline(job_id, text, language, filename, emit)
        store.set_report(job_id, report)
        store.add_event(job_id, "report_ready", {"job_id": job_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        store.add_event(job_id, "error", {"message": str(e)})

@app.post("/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    language: str = Form("en"),
    file: UploadFile | None = None
):
    job_id = str(uuid.uuid4())
    content = text
    filename = "pasted_text"
    if file and file.filename:
        filename = file.filename
        raw = await file.read()
        try:
            # Handle PDF if pdfplumber is available, else just decode
            if filename.lower().endswith(".pdf"):
                try:
                    import pdfplumber
                    import io
                    with pdfplumber.open(io.BytesIO(raw)) as pdf:
                        content = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
                except ImportError:
                    content = raw.decode("utf-8", errors="ignore")
            else:
                content = raw.decode("utf-8", errors="ignore")
        except Exception:
            raise HTTPException(400, "Could not read file.")
            
    background_tasks.add_task(analyze_task, job_id, content, language, filename)
    return {"job_id": job_id}

@app.get("/stream/{job_id}")
async def stream(job_id: str, request: Request):
    async def event_generator() -> AsyncGenerator[str, None]:
        if job_id not in store.events:
            store.events[job_id] = []
            store.waiters[job_id] = []
            
        idx = 0
        waiter = asyncio.Event()
        store.waiters[job_id].append(waiter)
        try:
            while True:
                if await request.is_disconnected():
                    break
                if idx < len(store.events[job_id]):
                    yield f"data: {store.events[job_id][idx]}\n\n"
                    if "report_ready" in store.events[job_id][idx] or "error" in store.events[job_id][idx]:
                        break
                    idx += 1
                else:
                    waiter.clear()
                    try:
                        await asyncio.wait_for(waiter.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
        finally:
            if waiter in store.waiters.get(job_id, []):
                store.waiters[job_id].remove(waiter)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/report/{job_id}")
def get_report(job_id: str):
    if job_id not in store.jobs:
        raise HTTPException(404, "Report not found or not finished.")
    return store.jobs[job_id].model_dump()

@app.get("/sample/{name}")
def get_sample(name: str):
    path = config.SAMPLE_DIR / name
    if not path.exists():
        raise HTTPException(404, "Sample not found.")
    return {"text": path.read_text()}

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="static")
