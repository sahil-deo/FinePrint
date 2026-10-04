from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.segmenter import segment
from app.grounding import quote_in_source
from app.scorer import score_from_total
from app.api import app, store
from app import config

client = TestClient(app)

def test_segmenter():
    text = """
1. PREMISES AND TERM
1.1 The Landlord agrees to lease the property.
1.2 The lease term is 11 months.

2. RENT
2.1 Rent is ₹45,000.
"""
    clauses = segment(text)
    assert len(clauses) >= 3
    ids = [c.clause_id for c in clauses]
    assert "1.1" in ids
    assert "1.2" in ids
    assert "2.1" in ids

def test_grounding_quote_in_source():
    source = "The Company may, at its sole discretion, deduct up to 10% of the base salary."
    
    # Exact match
    assert quote_in_source("at its sole discretion", source) == True
    
    # Whitespace normalized match
    assert quote_in_source("at its    sole \n discretion", source) == True
    
    # Invalid match
    assert quote_in_source("at its absolute discretion", source) == False

def test_scorer():
    assert score_from_total(0) == 0
    assert score_from_total(8) > 50  # saturating curve
    assert score_from_total(100) == 100

def test_demo_mode_replay():
    # Write a fake cache file
    demo_file = config.DEMO_CACHE_DIR / "fake_sample.txt.json"
    demo_file.parent.mkdir(exist_ok=True)
    demo_file.write_text(json.dumps({
        "events": [{"event": "report_ready", "data": {}}],
        "report": {
            "job_id": "demo_fake_sample.txt",
            "language": "en",
            "document_name": "fake_sample.txt",
            "document_text": "fake",
            "demo": True,
            "profile": None,
            "clauses": [],
            "readings": [],
            "findings": [],
            "rejected_findings": [],
            "executive_summary": "Test",
            "questions_to_ask": [],
            "score": {"risk_score": 10, "verdict_label": "Fair", "raw_total": 0.0, "counts": {}},
            "stats": {},
            "warnings": []
        }
    }))
    
    # Call analyze endpoint in demo mode
    old_demo = config.DEMO_MODE
    config.DEMO_MODE = True
    
    try:
        response = client.post("/analyze", data={"text": "fake", "language": "en"})
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        
        # In testing, the background task runs in the same event loop but we need it to finish
        import time
        time.sleep(0.5) # Wait for background task to populate store
        
        report_resp = client.get(f"/report/{job_id}")
        if report_resp.status_code == 200:
            assert report_resp.json()["executive_summary"] == "Test"
    finally:
        config.DEMO_MODE = old_demo
