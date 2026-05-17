# Experiment Plan

## Research Question

Which dynamic load-balancing strategy provides the best trade-off between responsiveness, stability, and overhead in a distributed real-time analytics dashboard?

## Algorithms

| Algorithm | Role |
|---|---|
| Round-robin | Static baseline |
| Least-connections | Adaptive baseline |
| Latency-aware | Proposed adaptive strategy |

## Metrics

| Metric | Source |
|---|---|
| Average latency | k6 and `/lb/stats` |
| p95 / p99 latency | k6 |
| Throughput | k6 |
| Error rate | k6 and `/lb/stats` |
| Worker request distribution | k6 custom counters and `/lb/workers` |
| Health status | `/lb/workers` |
| Recovery after crash | `/lb/workers` and k6 errors |
| EWMA latency | `/lb/workers` and Prometheus |

## Scenario 1: Constant Load

- 30 virtual users.
- 60 seconds.
- `delay_ms=40`, `cpu_ms=5`.

Expected outcome: compare baseline latency and request distribution.

## Scenario 2: Heterogeneous Workers

- `worker-3` has `SLOWDOWN_FACTOR=2.5`.
- Same load as Scenario 1.

Expected outcome: adaptive algorithms should reduce traffic to the slower worker.

## Scenario 3: Traffic Spike

Change k6 configuration to ramp from 10 to 80 users.

Expected outcome: compare p95 latency and stability.

## Scenario 4: Failure Injection

Crash worker 2:

```bash
curl http://localhost:3102/api/v1/crash
```

Expected outcome: the load balancer should mark worker 2 as unhealthy and stop routing to it.

## Scenario 5: Stress Test

Increase VUs until error rate or p95 latency becomes unacceptable.

Expected outcome: identify saturation behavior for each algorithm.
