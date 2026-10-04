from __future__ import annotations

import asyncio
import uuid
import time
import json
from typing import Callable, Any, Awaitable

from . import config, segmenter, grounding, scorer
from .schemas import (
    Clause, ProfileOut, ClauseReading, ReportFinding, Report, ScoreOut, RawFinding
)
from .agents import profiler, reader, hunters, cross_clause, skeptic, advisor

EmitFunc = Callable[[str, dict[str, Any]], Awaitable[None]]

async def run_pipeline(
    job_id: str,
    text: str,
    language: str,
    document_name: str,
    emit: EmitFunc,
) -> Report:
    start_time = time.time()
    stats = {}

    async def _emit(event_type: str, **kwargs):
        await emit(event_type, kwargs)

    # 1. Segment
    await _emit("agent_started", agent="Segmenter")
    await _emit("agent_progress", agent="Segmenter", message="Splitting document into clauses...")
    clauses = segmenter.segment(text)
    stats["clauses"] = len(clauses)
    await _emit("agent_finished", agent="Segmenter", message=f"Found {len(clauses)} clauses.")

    # 2. Profiler
    await _emit("agent_started", agent="Profiler")
    await _emit("agent_progress", agent="Profiler", message="Identifying parties and roles...")
    head_text = text[:config.PROFILER_HEAD_CHARS]
    headings = segmenter.clause_headings(clauses)
    profile_input = profiler.build_input(head_text, headings, document_name)
    profile = await profiler.agent.run(profile_input)
    await _emit("agent_finished", agent="Profiler", message=f"Identified {profile.user_role}.")

    # 3. Readers
    await _emit("agent_started", agent="Readers")
    await _emit("agent_progress", agent="Readers", message="Translating clauses to plain English...")
    chunks = segmenter.chunk_clauses(clauses, config.READER_CHUNK_SIZE)
    readings: list[ClauseReading] = []
    
    async def read_chunk(chunk):
        res = await reader.agent.run(reader.build_input(profile.contract_brief, profile, chunk))
        return res.readings

    reader_results = await asyncio.gather(*(read_chunk(c) for c in chunks))
    for res in reader_results:
        readings.extend(res)
    stats["readings"] = len(readings)
    await _emit("agent_finished", agent="Readers", message=f"Summarized {len(readings)} clauses.")

    # 4. Hunters & Cross-Clause
    hunter_names = [h.name for h in hunters.agents] + [cross_clause.agent.name]
    for h in hunter_names:
        await _emit("agent_started", agent=h)
        await _emit("agent_progress", agent=h, message="Looking for risks...")

    windows = segmenter.context_windows(text, config.MAX_CONTEXT_CHARS, config.CONTEXT_OVERLAP_CHARS)
    
    async def run_hunter(h, w_clauses):
        res = await h.run(hunters.build_input(profile, readings, w_clauses))
        return h.name, res.findings

    hunter_tasks = []
    for h in hunters.agents:
        for w in windows:
            # Re-segment the window to get local clauses (or just pass all clauses and text?)
            # Actually, the prompt says "the full contract text (chunk with overlap if it exceeds MAX_CONTEXT_CHARS)".
            # We can just segment the window, or pass the clauses that fall in this window.
            w_clauses = [c for c in clauses if w.find(c.text[:20]) != -1]
            if not w_clauses: w_clauses = clauses # fallback
            hunter_tasks.append(run_hunter(h, w_clauses))

    async def run_cross_clause():
        res = await cross_clause.agent.run(cross_clause.build_input(profile, readings))
        return cross_clause.agent.name, res.findings

    hunter_tasks.append(run_cross_clause())
    raw_results = await asyncio.gather(*hunter_tasks, return_exceptions=True)
    
    candidates: list[tuple[str, RawFinding]] = []
    for r in raw_results:
        if isinstance(r, Exception):
            print("Hunter failed:", r)
            continue
        agent_name, findings = r
        for f in findings:
            candidates.append((agent_name, f))
            await _emit("finding_discovered", finding={"title": f.title, "agent": agent_name})

    for h in hunter_names:
        await _emit("agent_finished", agent=h, message="Finished risk hunt.")

    # 5. Grounding
    await _emit("agent_started", agent="Grounding")
    await _emit("agent_progress", agent="Grounding", message="Verifying quotes...")
    grounding_result = grounding.verify_findings(candidates, text)
    merged_items, _ = grounding.merge_duplicates(grounding_result.kept)
    stats["findings_raw"] = len(candidates)
    stats["findings_grounded"] = len(merged_items)
    stats["quotes_dropped"] = grounding_result.dropped_quote_count
    await _emit("agent_finished", agent="Grounding", message=f"Kept {len(merged_items)} verified findings.")

    # Convert to ReportFinding
    report_findings: list[ReportFinding] = []
    for item in merged_items:
        f = item.finding
        report_findings.append(ReportFinding(
            id=item.id,
            title=f.title,
            category=f.category,
            clause_ids=f.clause_ids,
            evidence_quotes=item.valid_quotes,
            what_it_says=f.what_it_says,
            why_risky_for_user=f.why_risky_for_user,
            severity=f.severity,
            confidence=f.confidence,
            generally_negotiable=f.generally_negotiable,
            legal_interpretation=f.legal_interpretation,
            found_by=item.found_by,
        ))

    # 6. Skeptic
    await _emit("agent_started", agent="Skeptic")
    await _emit("agent_progress", agent="Skeptic", message="Challenging findings...")
    
    clauses_by_id = {c.clause_id: c for c in clauses}
    
    # Batch Skeptic
    batches = [report_findings[i:i + config.SKEPTIC_BATCH_SIZE] for i in range(0, len(report_findings), config.SKEPTIC_BATCH_SIZE)]
    
    async def run_skeptic_batch(batch):
        if not batch: return []
        inp = skeptic.build_input(profile, batch, clauses_by_id)
        res = await skeptic.agent.run(inp)
        return res.reviews

    skeptic_results = await asyncio.gather(*(run_skeptic_batch(b) for b in batches))
    
    reviews_by_id = {}
    for batch_res in skeptic_results:
        for rev in batch_res:
            reviews_by_id[rev.finding_id] = rev

    rejected = []
    surviving = []
    
    for f in report_findings:
        rev = reviews_by_id.get(f.id)
        if rev:
            f.verdict = rev.verdict
            f.final_severity = rev.final_severity
            f.final_confidence = rev.final_confidence
            f.skeptic_reason = rev.reason
        
        await _emit("finding_verdict", id=f.id, verdict=f.verdict, reason=f.skeptic_reason)
        
        if f.verdict == "rejected":
            rejected.append(f)
        else:
            surviving.append(f)
            
    await _emit("agent_finished", agent="Skeptic", message=f"Rejected {len(rejected)} findings.")

    # 7. Advisor
    await _emit("agent_started", agent="Advisor")
    await _emit("agent_progress", agent="Advisor", message="Writing advice...")

    async def run_advisor_batch(batch):
        if not batch: return []
        inp = advisor.build_advice_input(batch, language)
        res = await advisor.advice_agent.run(inp)
        return res.advice
        
    adv_batches = [surviving[i:i + config.ADVISOR_BATCH_SIZE] for i in range(0, len(surviving), config.ADVISOR_BATCH_SIZE)]
    adv_results, summary_res = await asyncio.gather(
        asyncio.gather(*(run_advisor_batch(b) for b in adv_batches)),
        advisor.summary_agent.run(advisor.build_summary_input(profile, surviving, language))
    )
    
    advice_by_id = {}
    for res in adv_results:
        for adv in res:
            advice_by_id[adv.finding_id] = adv
            
    for f in surviving:
        adv = advice_by_id.get(f.id)
        if adv:
            f.plain_explanation = adv.plain_explanation
            f.what_to_ask_for = adv.what_to_ask_for
            f.suggested_counter_clause = adv.suggested_counter_clause
            f.negotiation_priority = adv.negotiation_priority

    await _emit("agent_finished", agent="Advisor", message="Advice ready.")

    # 8. Score
    final_score = scorer.score(report_findings)
    stats["time_seconds"] = int(time.time() - start_time)

    report = Report(
        job_id=job_id,
        language=language,
        document_name=document_name,
        document_text=text,
        demo=not config.live_mode_available() or config.DEMO_MODE,
        profile=profile,
        clauses=clauses,
        readings=readings,
        findings=surviving,
        rejected_findings=rejected,
        executive_summary=summary_res.executive_summary,
        questions_to_ask=summary_res.questions_to_ask,
        score=final_score,
        stats=stats
    )
    
    return report
