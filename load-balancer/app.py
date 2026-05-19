import asyncio
import collections
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

ALGORITHM = os.getenv("ALGORITHM", "round_robin")
PORT = int(os.getenv("PORT", "8080"))
WORKERS_ENV = os.getenv("WORKERS", "")
TEST_RUNNER_URL = os.getenv("TEST_RUNNER_URL", "http://test-runner:8181")
HEALTH_PATH = os.getenv("HEALTH_PATH", "/api/v1/health")
REQUEST_TIMEOUT_MS = int(os.getenv("REQUEST_TIMEOUT_MS", "5000"))
HEALTH_TIMEOUT_MS = int(os.getenv("HEALTH_TIMEOUT_MS", "800"))
HEALTH_CHECK_INTERVAL_MS = int(os.getenv("HEALTH_CHECK_INTERVAL_MS", "1000"))
EWMA_ALPHA = float(os.getenv("EWMA_ALPHA", "0.25"))

SUPPORTED_ALGORITHMS = {"round_robin", "least_connections", "latency_aware"}

if ALGORITHM not in SUPPORTED_ALGORITHMS:
    raise RuntimeError(f"Unsupported ALGORITHM={ALGORITHM}. Use one of {sorted(SUPPORTED_ALGORITHMS)}.")


@dataclass
class Worker:
    name: str
    base_url: str
    healthy: bool = False
    in_flight: int = 0
    ewma_latency_ms: float = 100.0
    total_requests: int = 0
    failed_requests: int = 0
    last_health_check_at: float = 0.0
    last_error: Optional[str] = None


LATENCY_WINDOW_SIZE = 1000


@dataclass
class GlobalStats:
    total_requests: int = 0
    failed_requests: int = 0
    duration_ms_sum: float = 0.0
    by_status: Dict[str, int] = field(default_factory=dict)
    latency_window: collections.deque = field(default_factory=lambda: collections.deque(maxlen=LATENCY_WINDOW_SIZE))


def parse_workers(value: str) -> List[Worker]:
    workers: List[Worker] = []

    for index, entry in enumerate(part.strip() for part in value.split(",") if part.strip()):
        if "=" in entry:
            name, url = entry.split("=", 1)
        else:
            name, url = f"worker-{index + 1}", entry

        workers.append(Worker(name=name.strip(), base_url=url.strip().rstrip("/")))

    if not workers:
        raise RuntimeError("WORKERS must be configured.")

    return workers


workers = parse_workers(WORKERS_ENV)
stats = GlobalStats()
rr_index = 0
lock = asyncio.Lock()

app = FastAPI(title="Dynamic Load Balancer")

client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_MS / 1000.0)
health_client = httpx.AsyncClient(timeout=HEALTH_TIMEOUT_MS / 1000.0)
test_runner_client = httpx.AsyncClient(timeout=120.0)

app.mount("/static", StaticFiles(directory="static"), name="static")


def percentile(data: collections.deque, p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = int(len(sorted_data) * p / 100.0)
    index = min(index, len(sorted_data) - 1)
    return sorted_data[index]


def ewma(old_value: float, new_value: float) -> float:
    return EWMA_ALPHA * new_value + (1.0 - EWMA_ALPHA) * old_value


def healthy_workers() -> List[Worker]:
    return [worker for worker in workers if worker.healthy]


def worker_score(worker: Worker) -> float:
    queue_penalty = worker.in_flight * 20.0
    failure_penalty = worker.failed_requests * 5.0
    return worker.ewma_latency_ms + queue_penalty + failure_penalty


async def select_worker() -> Optional[Worker]:
    global rr_index

    candidates = healthy_workers()

    if not candidates:
        return None

    if ALGORITHM == "round_robin":
        async with lock:
            worker = candidates[rr_index % len(candidates)]
            rr_index += 1
            return worker

    if ALGORITHM == "least_connections":
        return min(candidates, key=lambda worker: (worker.in_flight, worker.ewma_latency_ms))

    return min(candidates, key=worker_score)


async def run_health_check(worker: Worker) -> None:
    started = time.perf_counter()

    try:
        response = await health_client.get(f"{worker.base_url}{HEALTH_PATH}")
        duration_ms = (time.perf_counter() - started) * 1000
        worker.healthy = response.status_code < 500
        worker.last_health_check_at = time.time()

        if worker.healthy:
            worker.last_error = None
        else:
            worker.last_error = f"health status {response.status_code}"

    except Exception as exc:
        worker.healthy = False
        worker.last_health_check_at = time.time()
        worker.last_error = str(exc)


async def health_loop() -> None:
    while True:
        await asyncio.gather(*(run_health_check(worker) for worker in workers))
        await asyncio.sleep(HEALTH_CHECK_INTERVAL_MS / 1000.0)


@app.on_event("startup")
async def on_startup() -> None:
    asyncio.create_task(health_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await client.aclose()
    await health_client.aclose()
    await test_runner_client.aclose()


def worker_to_dict(worker: Worker) -> Dict[str, object]:
    return {
        "name": worker.name,
        "base_url": worker.base_url,
        "healthy": worker.healthy,
        "in_flight": worker.in_flight,
        "ewma_latency_ms": round(worker.ewma_latency_ms, 2),
        "score": round(worker_score(worker), 2),
        "total_requests": worker.total_requests,
        "failed_requests": worker.failed_requests,
        "last_health_check_at": worker.last_health_check_at,
        "last_error": worker.last_error,
    }


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    with open("static/dashboard.html", "r", encoding="utf-8") as file:
        return file.read()


@app.get("/lb/health")
async def lb_health() -> JSONResponse:
    healthy_count = len(healthy_workers())

    return JSONResponse(
        status_code=200 if healthy_count else 503,
        content={
            "status": "ok" if healthy_count else "unavailable",
            "algorithm": ALGORITHM,
            "healthy_workers": healthy_count,
            "total_workers": len(workers),
        },
    )


@app.get("/lb/workers")
async def lb_workers() -> Dict[str, object]:
    return {
        "algorithm": ALGORITHM,
        "workers": [worker_to_dict(worker) for worker in workers],
    }


@app.get("/lb/stats")
async def lb_stats() -> Dict[str, object]:
    avg_latency = stats.duration_ms_sum / stats.total_requests if stats.total_requests else 0.0

    return {
        "algorithm": ALGORITHM,
        "total_requests": stats.total_requests,
        "failed_requests": stats.failed_requests,
        "failure_rate": round(stats.failed_requests / stats.total_requests, 4) if stats.total_requests else 0.0,
        "average_latency_ms": round(avg_latency, 2),
        "p95_latency_ms": round(percentile(stats.latency_window, 95), 2),
        "p99_latency_ms": round(percentile(stats.latency_window, 99), 2),
        "by_status": stats.by_status,
        "workers": [worker_to_dict(worker) for worker in workers],
    }


@app.get("/lb/metrics")
async def lb_metrics() -> PlainTextResponse:
    lines: List[str] = []

    lines.append("# HELP lb_requests_total Total proxied requests.")
    lines.append("# TYPE lb_requests_total counter")
    lines.append(f'lb_requests_total{{algorithm="{ALGORITHM}"}} {stats.total_requests}')

    lines.append("# HELP lb_failed_requests_total Failed proxied requests.")
    lines.append("# TYPE lb_failed_requests_total counter")
    lines.append(f'lb_failed_requests_total{{algorithm="{ALGORITHM}"}} {stats.failed_requests}')

    lines.append("# HELP lb_request_duration_ms_sum Sum of request durations in milliseconds.")
    lines.append("# TYPE lb_request_duration_ms_sum counter")
    lines.append(f'lb_request_duration_ms_sum{{algorithm="{ALGORITHM}"}} {stats.duration_ms_sum}')

    lines.append("# HELP lb_request_latency_p95_ms 95th percentile latency over last 1000 requests.")
    lines.append("# TYPE lb_request_latency_p95_ms gauge")
    lines.append(f'lb_request_latency_p95_ms{{algorithm="{ALGORITHM}"}} {percentile(stats.latency_window, 95):.2f}')

    lines.append("# HELP lb_request_latency_p99_ms 99th percentile latency over last 1000 requests.")
    lines.append("# TYPE lb_request_latency_p99_ms gauge")
    lines.append(f'lb_request_latency_p99_ms{{algorithm="{ALGORITHM}"}} {percentile(stats.latency_window, 99):.2f}')

    for worker in workers:
        lines.append(f'lb_worker_healthy{{name="{worker.name}"}} {1 if worker.healthy else 0}')
        lines.append(f'lb_worker_in_flight{{name="{worker.name}"}} {worker.in_flight}')
        lines.append(f'lb_worker_ewma_latency_ms{{name="{worker.name}"}} {worker.ewma_latency_ms:.2f}')
        lines.append(f'lb_worker_requests_total{{name="{worker.name}"}} {worker.total_requests}')
        lines.append(f'lb_worker_failed_requests_total{{name="{worker.name}"}} {worker.failed_requests}')
        lines.append(f'lb_worker_score{{name="{worker.name}"}} {worker_score(worker):.2f}')

    for status, count in stats.by_status.items():
        lines.append(f'lb_response_status_total{{status="{status}"}} {count}')

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


async def proxy_to_worker(request: Request, worker: Worker) -> Response:
    path = request.url.path
    query = request.url.query
    target = f"{worker.base_url}{path}"
    if query:
        target += f"?{query}"

    worker.in_flight += 1
    worker.total_requests += 1
    stats.total_requests += 1

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)

    started = time.perf_counter()

    try:
        upstream = await client.request(
            method=request.method,
            url=target,
            headers=headers,
            content=body if body else None,
        )

        duration_ms = (time.perf_counter() - started) * 1000
        worker.ewma_latency_ms = ewma(worker.ewma_latency_ms, duration_ms)
        stats.duration_ms_sum += duration_ms
        stats.latency_window.append(duration_ms)

        status_key = str(upstream.status_code)
        stats.by_status[status_key] = stats.by_status.get(status_key, 0) + 1

        if upstream.status_code >= 500:
            worker.failed_requests += 1
            stats.failed_requests += 1

        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in {"content-encoding", "transfer-encoding", "connection"}
        }
        response_headers["x-selected-worker"] = worker.name
        response_headers["x-lb-algorithm"] = ALGORITHM
        response_headers["x-upstream-latency-ms"] = str(round(duration_ms, 2))

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=upstream.headers.get("content-type"),
        )

    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        worker.healthy = False
        worker.failed_requests += 1
        worker.last_error = str(exc)
        stats.failed_requests += 1
        stats.duration_ms_sum += duration_ms
        stats.by_status["proxy_error"] = stats.by_status.get("proxy_error", 0) + 1

        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_error",
                "algorithm": ALGORITHM,
                "worker": worker.name,
                "duration_ms": round(duration_ms, 2),
                "message": str(exc),
            },
        )

    finally:
        worker.in_flight -= 1


@app.api_route("/tests/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_test_runner(path: str, request: Request) -> Response:
    query = request.url.query
    target = f"{TEST_RUNNER_URL}/tests/{path}"
    if query:
        target += f"?{query}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    try:
        resp = await test_runner_client.request(
            method=request.method,
            url=target,
            headers=headers,
            content=body or None,
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers={k: v for k, v in resp.headers.items() if k.lower() not in {"content-encoding", "transfer-encoding", "connection"}},
            media_type=resp.headers.get("content-type"),
        )
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": "test_runner_unavailable", "message": str(exc)})


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request) -> Response:
    worker = await select_worker()

    if worker is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "no_healthy_workers",
                "algorithm": ALGORITHM,
                "workers": [worker_to_dict(item) for item in workers],
            },
        )

    return await proxy_to_worker(request, worker)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=PORT)
