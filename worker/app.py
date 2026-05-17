import asyncio
import math
import os
import random
import signal
import time
from datetime import datetime, timezone
from typing import Dict, Any

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse

INSTANCE_ID = os.getenv("INSTANCE_ID", os.getenv("HOSTNAME", "worker"))
PORT = int(os.getenv("PORT", "8000"))
SLOWDOWN_FACTOR = float(os.getenv("SLOWDOWN_FACTOR", "1.0"))
ERROR_RATE = float(os.getenv("ERROR_RATE", "0.0"))

app = FastAPI(title=f"Analytics Worker {INSTANCE_ID}")

state: Dict[str, Any] = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "requests_total": 0,
    "failed_requests_total": 0,
    "processing_time_ms_sum": 0.0,
    "last_event_at": None,
}


def busy_cpu(milliseconds: int) -> None:
    end = time.perf_counter() + milliseconds / 1000.0
    value = 0.0

    while time.perf_counter() < end:
        value += math.sqrt(random.random() * 10_000)

    if value < 0:
        print(value)


@app.get("/api/v1/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "instance_id": INSTANCE_ID,
        "slowdown_factor": SLOWDOWN_FACTOR,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/analytics/event")
async def analytics_event(
    delay_ms: int = Query(default=30, ge=0, le=10_000),
    cpu_ms: int = Query(default=0, ge=0, le=5_000),
    fail_rate: float = Query(default=0.0, ge=0.0, le=1.0),
) -> JSONResponse:
    started = time.perf_counter()

    effective_delay = int(delay_ms * SLOWDOWN_FACTOR)
    effective_cpu = int(cpu_ms * SLOWDOWN_FACTOR)
    effective_fail_rate = max(ERROR_RATE, fail_rate)

    if effective_cpu > 0:
        busy_cpu(effective_cpu)

    if effective_delay > 0:
        await asyncio.sleep(effective_delay / 1000.0)

    duration_ms = (time.perf_counter() - started) * 1000

    state["requests_total"] += 1
    state["processing_time_ms_sum"] += duration_ms
    state["last_event_at"] = datetime.now(timezone.utc).isoformat()

    payload = {
        "status": "ok",
        "instance_id": INSTANCE_ID,
        "event_type": "page_view",
        "delay_ms": effective_delay,
        "cpu_ms": effective_cpu,
        "duration_ms": round(duration_ms, 2),
        "timestamp": state["last_event_at"],
    }

    if random.random() < effective_fail_rate:
        state["failed_requests_total"] += 1
        payload["status"] = "simulated_failure"
        return JSONResponse(status_code=503, content=payload)

    return JSONResponse(status_code=200, content=payload)


@app.post("/api/v1/analytics/event")
async def analytics_event_post(
    delay_ms: int = Query(default=30, ge=0, le=10_000),
    cpu_ms: int = Query(default=0, ge=0, le=5_000),
    fail_rate: float = Query(default=0.0, ge=0.0, le=1.0),
) -> JSONResponse:
    return await analytics_event(delay_ms=delay_ms, cpu_ms=cpu_ms, fail_rate=fail_rate)


@app.get("/api/v1/status")
async def status() -> Dict[str, Any]:
    total = int(state["requests_total"])
    avg = state["processing_time_ms_sum"] / total if total else 0.0

    return {
        "instance_id": INSTANCE_ID,
        "slowdown_factor": SLOWDOWN_FACTOR,
        "error_rate": ERROR_RATE,
        "requests_total": total,
        "failed_requests_total": state["failed_requests_total"],
        "average_processing_time_ms": round(avg, 2),
        "started_at": state["started_at"],
        "last_event_at": state["last_event_at"],
    }


@app.get("/api/v1/crash")
async def crash() -> PlainTextResponse:
    os.kill(os.getpid(), signal.SIGTERM)
    return PlainTextResponse("crashing")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=PORT)
