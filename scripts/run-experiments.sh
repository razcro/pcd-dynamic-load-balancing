#!/usr/bin/env bash
set -euo pipefail

ALGORITHMS=("round_robin" "least_connections" "latency_aware")
RESULT_DIR="results"

mkdir -p "$RESULT_DIR"

for algorithm in "${ALGORITHMS[@]}"; do
  echo "=== Running experiment for algorithm: ${algorithm} ==="

  ALGORITHM="$algorithm" docker compose up --build -d
  sleep 8

  docker compose --profile loadtest run --rm \
    -e BASE_URL=http://load-balancer:8080 \
    -e VUS=30 \
    -e DURATION=60s \
    -e DELAY_MS=40 \
    -e CPU_MS=5 \
    -e FAIL_RATE=0 \
    k6 run --summary-export "/results/${algorithm}-summary.json" /scripts/k6-load-balancing.js

  curl -s "http://localhost:8080/lb/stats" > "${RESULT_DIR}/${algorithm}-stats.json"
  curl -s "http://localhost:8080/lb/workers" > "${RESULT_DIR}/${algorithm}-workers.json"
  curl -s "http://localhost:8080/lb/metrics" > "${RESULT_DIR}/${algorithm}-metrics.prom"

  docker compose down
  sleep 3
done

echo "Results saved in ${RESULT_DIR}"
