# Dynamic Load Balancing for a Real-Time Analytics Dashboard

Standalone distributed-systems project for evaluating dynamic load-balancing strategies in a containerized real-time analytics backend.

The project contains:

- 3 replicated worker services;
- a custom dynamic load balancer;
- a browser analytics dashboard;
- Prometheus-compatible metrics;
- k6 load tests;
- scripts for running comparative experiments.

## Research Question

Which dynamic load-balancing strategy provides the best trade-off between responsiveness, stability, and overhead in a distributed real-time analytics dashboard under variable workload, heterogeneous workers, and failures?

## Algorithms

The load balancer supports three algorithms:

1. `round_robin` — static baseline.
2. `least_connections` — routes to the worker with the fewest active requests.
3. `latency_aware` — routes using an EWMA latency score plus queue penalty.

## Architecture

```text
k6 / browser / client
        |
        v
Dynamic Load Balancer :8080
        |
  -------------------------
  |           |           |
worker-1   worker-2   worker-3
        |
        v
Prometheus :9090
```

The dashboard is available at:

```text
http://localhost:8080/dashboard
```

## Requirements

- Docker Desktop
- Docker Compose
- Optional: k6 installed locally if you want to run load tests outside Docker

## Quick Start

```bash
docker compose up --build
```

Open:

```text
http://localhost:8080/dashboard
```

Test through the load balancer:

```bash
curl "http://localhost:8080/api/v1/analytics/event?delay_ms=50&cpu_ms=5"
```

Check worker state:

```bash
curl http://localhost:8080/lb/workers
```

Check load-balancer stats:

```bash
curl http://localhost:8080/lb/stats
```

Prometheus metrics:

```bash
curl http://localhost:8080/lb/metrics
```

## Run with a specific algorithm

PowerShell:

```powershell
$env:ALGORITHM="latency_aware"
docker compose up --build
```

Git Bash / Linux / macOS:

```bash
ALGORITHM=latency_aware docker compose up --build
```

Allowed values:

```text
round_robin
least_connections
latency_aware
```

## Run load test with k6

Using Docker:

```bash
docker compose --profile loadtest run --rm k6
```

Or locally:

```bash
k6 run -e BASE_URL=http://localhost:8080 load-tests/k6-load-balancing.js
```

## Run all comparative experiments

PowerShell:

```powershell
.\scripts\run-experiments.ps1
```

Git Bash / Linux / macOS:

```bash
chmod +x scripts/run-experiments.sh
./scripts/run-experiments.sh
```

Results are saved in:

```text
results/
```

## Failure Injection

Crash worker 2:

```bash
curl http://localhost:3102/api/v1/crash
```

Then inspect the load balancer:

```bash
curl http://localhost:8080/lb/workers
```

The crashed worker should become unhealthy and receive no more traffic.

## Useful URLs

| Component | URL |
|---|---|
| Dashboard | http://localhost:8080/dashboard |
| Load balancer health | http://localhost:8080/lb/health |
| Worker status | http://localhost:8080/lb/workers |
| JSON stats | http://localhost:8080/lb/stats |
| Prometheus metrics | http://localhost:8080/lb/metrics |
| Prometheus UI | http://localhost:9090 |

## Evaluation Metrics

- average latency;
- p95 and p99 latency;
- throughput;
- failed request rate;
- worker request distribution;
- in-flight requests per worker;
- EWMA latency per worker;
- recovery after worker crash;
- behavior under heterogeneous workers.

## Recommended Report Title

**Dynamic Load Balancing for a Real-Time Analytics Dashboard: A Comparative Evaluation of Round-Robin, Least-Connections, and Latency-Aware Routing**
