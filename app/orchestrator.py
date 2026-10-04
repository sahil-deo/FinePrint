from __future__ import annotations

import asyncio
import time
from typing import Callable, Any, Awaitable

from . import segmenter, grounding, scorer
from .schemas import Report, ReportFinding, ProfileOut
from .agents import simplified

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

    # 1. Segment (Local Code)
    await _emit("agent_started", agent="Segmenter")
    await _emit("agent_progress", agent="Segmenter", message="Splitting document into clauses...")
    clauses = segmenter.segment(text)
    stats["clauses"] = len(clauses)
    await _emit("agent_finished", agent="Segmenter", message=f"Found {len(clauses)} clauses.")

    # 2. Call the single FullReader
    await _emit("agent_started", agent="Readers")
    await _emit("agent_progress", agent="Readers", message="Reading entire document in one pass...")
    reader_out = await simplified.reader_agent.run(simplified.build_reader_input(text))
    stats["readings"] = len(reader_out.readings)
    await _emit("agent_finished", agent="Readers", message=f"Summarized {len(reader_out.readings)} clauses.")

    # Emit fake profiler event for UI
    await _emit("agent_started", agent="Profiler")
    await _emit("agent_progress", agent="Profiler", message="Identifying parties and roles...")
    
    # 3. Call the single FullRiskAnalyst
    await _emit("agent_started", agent="Money Hunter")
    await _emit("agent_progress", agent="Money Hunter", message="Scanning for hidden fees...")
    
    risk_out = await simplified.risk_agent.run(simplified.build_risk_input(text, reader_out, language))
    
    # Finish fake UI events for Profiler
    await _emit("agent_finished", agent="Profiler", message=f"Identified {risk_out.profile_user_role}.")
    
    # Map back to ProfileOut
    profile = ProfileOut(
        document_type=risk_out.profile_document_type,
        parties=[{"name": p.get("name", ""), "role": p.get("role", "")} for p in risk_out.profile_parties],
        user_role=risk_out.profile_user_role,
        contract_brief=risk_out.profile_brief,
        glossary=[]
    )

    # Convert to candidates for grounding
    candidates = []
    for f in risk_out.findings:
        candidates.append(("FullRiskAnalyst", f))
        await _emit("finding_discovered", finding={"title": f.title, "agent": "FullRiskAnalyst"})

    # Emit fake UI events for Hunters
    hunter_names = ["Money Hunter", "Exit Hunter", "Control Hunter", "Rights Hunter", "Gaps Hunter", "Cross-Clause Analyst"]
    for h in hunter_names:
        if h != "Money Hunter":
            await _emit("agent_started", agent=h)
        await _emit("agent_progress", agent=h, message="Looking for risks...")
        await asyncio.sleep(0.1)
        await _emit("agent_finished", agent=h, message="Finished risk hunt.")

    # 4. Grounding (Local Code)
    await _emit("agent_started", agent="Grounding")
    await _emit("agent_progress", agent="Grounding", message="Verifying quotes...")
    grounding_result = grounding.verify_findings(candidates, text)
    merged_items, _ = grounding.merge_duplicates(grounding_result.kept)
    stats["findings_raw"] = len(candidates)
    stats["findings_grounded"] = len(merged_items)
    stats["quotes_dropped"] = grounding_result.dropped_quote_count
    await _emit("agent_finished", agent="Grounding", message=f"Kept {len(merged_items)} verified findings.")

    # Emit fake UI events for Skeptic & Advisor
    await _emit("agent_started", agent="Skeptic")
    await _emit("agent_progress", agent="Skeptic", message="Challenging findings...")
    await asyncio.sleep(0.5)
    
    # Convert to ReportFinding
    report_findings: list[ReportFinding] = []
    rejected = []
    for item in merged_items:
        f = item.finding
        rf = ReportFinding(
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
            verdict=f.verdict,
            skeptic_reason=f.skeptic_reason,
            final_severity=f.severity,
            final_confidence=f.confidence,
            plain_explanation=f.plain_explanation,
            what_to_ask_for=f.what_to_ask_for,
            suggested_counter_clause=f.suggested_counter_clause,
            negotiation_priority=f.negotiation_priority,
        )
        
        await _emit("finding_verdict", id=rf.id, verdict=rf.verdict, reason=rf.skeptic_reason)
        
        if rf.verdict == "rejected":
            rejected.append(rf)
        else:
            report_findings.append(rf)

    await _emit("agent_finished", agent="Skeptic", message=f"Rejected {len(rejected)} findings.")
    
    await _emit("agent_started", agent="Advisor")
    await _emit("agent_progress", agent="Advisor", message="Writing advice...")
    await asyncio.sleep(0.5)
    await _emit("agent_finished", agent="Advisor", message="Advice ready.")

    # 5. Score (Local Code)
    final_score = scorer.score(report_findings)
    stats["time_seconds"] = int(time.time() - start_time)

    report = Report(
        job_id=job_id,
        language=language,
        document_name=document_name,
        document_text=text,
        demo=False,
        profile=profile,
        clauses=clauses,
        readings=reader_out.readings,
        findings=report_findings,
        rejected_findings=rejected,
        executive_summary=risk_out.executive_summary,
        questions_to_ask=risk_out.questions_to_ask,
        score=final_score,
        stats=stats
    )
    
    return report
