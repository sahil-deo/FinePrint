import asyncio
import json
import os
from pathlib import Path
from . import config, orchestrator

async def record(sample_file: Path):
    print(f"Recording {sample_file.name}...")
    text = sample_file.read_text()
    events = []
    
    async def emit(event_type: str, data: dict):
        events.append({"event": event_type, "data": data})
        print(f"  Event: {event_type}")

    job_id = f"demo_{sample_file.name}"
    report = await orchestrator.run_pipeline(
        job_id=job_id,
        text=text,
        language="en",
        document_name=sample_file.name,
        emit=emit,
    )
    
    cache_file = config.DEMO_CACHE_DIR / f"{sample_file.name}.json"
    cache_file.parent.mkdir(exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump({
            "events": events,
            "report": report.model_dump(),
        }, f, indent=2)
    print(f"Saved {cache_file}")

async def main():
    config.require_live_config()
    for sample in config.SAMPLE_DIR.glob("*.txt"):
        await record(sample)

if __name__ == "__main__":
    asyncio.run(main())
