# Integrated System Requirements and Conformance Specification

| ID | Requirement | Priority | Verification Method | Evidence |
|---|---|---|---|---|
| R1 | The system shall deploy at least three worker instances. | Must | Docker Compose inspection | `docker-compose.yml` |
| R2 | The load balancer shall support round-robin routing. | Must | Functional test | `ALGORITHM=round_robin` |
| R3 | The load balancer shall support least-connections routing. | Must | Functional test | `ALGORITHM=least_connections` |
| R4 | The load balancer shall support latency-aware routing. | Must | Functional test | `ALGORITHM=latency_aware` |
| R5 | The system shall expose health checks for all workers. | Must | HTTP test | `/api/v1/health`, `/lb/workers` |
| R6 | The system shall expose Prometheus-compatible metrics. | Must | Metrics scrape | `/lb/metrics` |
| R7 | The system shall support synthetic workload generation. | Must | k6 experiment | `load-tests/k6-load-balancing.js` |
| R8 | The system shall support failure injection. | Must | Worker crash test | `/api/v1/crash` |
| R9 | The system should expose a live dashboard for experiment observation. | Should | Browser test | `/dashboard` |
| R10 | The system should support heterogeneous worker performance. | Should | Configuration review | `SLOWDOWN_FACTOR` |
| R11 | The experiment should export reproducible result files. | Should | Script execution | `results/` |
| R12 | The load balancer may be extended with additional algorithms. | May | Code review | `select_worker()` |

## Conformance Checks

| Check | Description | Pass Criterion |
|---|---|---|
| C1 | Start deployment | `docker compose up --build` starts all services |
| C2 | Worker health | `/lb/health` returns 200 with at least one healthy worker |
| C3 | Routing | `/api/v1/analytics/event` returns `X-Selected-Worker` |
| C4 | Metrics | `/lb/metrics` contains `lb_requests_total` |
| C5 | Failure handling | crashed worker becomes unhealthy and stops receiving traffic |
