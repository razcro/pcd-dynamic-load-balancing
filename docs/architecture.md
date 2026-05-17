# Architecture

## Components

### Worker service

A replicated FastAPI service that simulates a real-time analytics backend. Each worker exposes:

- `/api/v1/health`
- `/api/v1/analytics/event`
- `/api/v1/status`
- `/api/v1/crash`

The event endpoint simulates processing using two parameters:

- `delay_ms`: artificial I/O-like delay;
- `cpu_ms`: artificial CPU work.

`worker-3` has a higher `SLOWDOWN_FACTOR`, which creates a heterogeneous cluster.

### Dynamic load balancer

A FastAPI reverse proxy that receives all client traffic and selects a backend worker.

It exposes:

- `/lb/health`
- `/lb/workers`
- `/lb/stats`
- `/lb/metrics`
- `/dashboard`

### Monitoring

Prometheus scrapes `/lb/metrics` every two seconds.

### Load testing

k6 generates synthetic HTTP traffic against `/api/v1/analytics/event`.

## Data Flow

```text
Client / k6
   |
   v
Load Balancer
   |
   +--> worker-1
   +--> worker-2
   +--> worker-3
```

The selected worker is returned in the `X-Selected-Worker` response header.
