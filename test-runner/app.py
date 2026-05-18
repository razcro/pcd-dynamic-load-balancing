import asyncio
import os
import time
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

PORT = int(os.getenv("PORT", "8181"))
BASE_URL = os.getenv("BASE_URL", "http://load-balancer:8080")
WORKER2_URL = os.getenv("WORKER2_URL", "http://worker-2:8000")
SCRIPTS_DIR = "/scripts"
RESULTS_DIR = "/results"

SCENARIOS = {
    "constant": {
        "script": "k6-load-balancing.js",
        "description": "Constant 30 VUs for 60s — baseline comparison",
    },
    "spike": {
        "script": "k6-spike.js",
        "description": "Traffic spike: 10 → 80 VUs in 5s — burst resilience",
    },
    "stress": {
        "script": "k6-stress.js",
        "description": "Ramp 5 → 150 VUs over 70s — find saturation point",
    },
    "failure": {
        "script": "k6-failure.js",
        "description": "30 VUs constant; worker-2 crashed at 20s — failure recovery",
    },
}

app = FastAPI(title="Load Test Runner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared mutable state (single-test-at-a-time model)
_process: Optional[asyncio.subprocess.Process] = None
_output_lines: list[str] = []
_status: str = "idle"       # idle | running | done | failed | stopped
_scenario: Optional[str] = None
_started_at: Optional[float] = None
_finished_at: Optional[float] = None
_state_lock = asyncio.Lock()


async def _stream_process(proc: asyncio.subprocess.Process) -> None:
    global _output_lines, _status, _finished_at
    assert proc.stdout is not None

    async for raw in proc.stdout:
        _output_lines.append(raw.decode("utf-8", errors="replace").rstrip())

    await proc.wait()
    _finished_at = time.time()
    _status = "done" if proc.returncode == 0 else "failed"


async def _crash_worker2_after(delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.get(f"{WORKER2_URL}/api/v1/crash")
        _output_lines.append(f"[test-runner] worker-2 crash signal sent at t+{delay:.0f}s")
    except Exception as exc:
        _output_lines.append(f"[test-runner] could not crash worker-2: {exc}")


@app.get("/tests/scenarios")
async def list_scenarios() -> dict:
    return {"scenarios": {k: v["description"] for k, v in SCENARIOS.items()}}


@app.post("/tests/run")
async def run_test(
    scenario: str,
    vus: int = 30,
    duration: str = "60s",
    delay_ms: int = 40,
    cpu_ms: int = 5,
) -> dict:
    global _process, _output_lines, _status, _scenario, _started_at, _finished_at

    async with _state_lock:
        if _status == "running":
            raise HTTPException(status_code=409, detail="A test is already running. Stop it first.")

        if scenario not in SCENARIOS:
            raise HTTPException(status_code=400, detail=f"Unknown scenario '{scenario}'. Valid: {list(SCENARIOS)}")

        cfg = SCENARIOS[scenario]
        script = f"{SCRIPTS_DIR}/{cfg['script']}"
        ts = int(time.time())
        summary_file = f"{RESULTS_DIR}/ui-{scenario}-{ts}.json"

        cmd = [
            "k6", "run",
            "--summary-export", summary_file,
            "--env", f"BASE_URL={BASE_URL}",
            "--env", f"VUS={vus}",
            "--env", f"DURATION={duration}",
            "--env", f"DELAY_MS={delay_ms}",
            "--env", f"CPU_MS={cpu_ms}",
            script,
        ]

        _output_lines = [f"[test-runner] starting scenario={scenario} vus={vus} duration={duration}"]
        _status = "running"
        _scenario = scenario
        _started_at = time.time()
        _finished_at = None

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        _process = proc

    asyncio.create_task(_stream_process(proc))

    if scenario == "failure":
        asyncio.create_task(_crash_worker2_after(20.0))

    return {"status": "started", "scenario": scenario, "vus": vus, "duration": duration}


@app.post("/tests/stop")
async def stop_test() -> dict:
    global _process, _status

    async with _state_lock:
        if _process is None or _status != "running":
            return {"status": "no_test_running"}
        _process.terminate()
        _status = "stopped"
        _finished_at = time.time()
        return {"status": "stopped"}


@app.get("/tests/status")
async def get_status() -> dict:
    elapsed = None
    if _started_at is not None:
        end = _finished_at if _finished_at else time.time()
        elapsed = round(end - _started_at, 1)
    return {
        "status": _status,
        "scenario": _scenario,
        "total_lines": len(_output_lines),
        "elapsed_s": elapsed,
    }


@app.get("/tests/output")
async def get_output(since: int = 0) -> dict:
    return {
        "status": _status,
        "lines": _output_lines[since:],
        "total": len(_output_lines),
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=PORT)
