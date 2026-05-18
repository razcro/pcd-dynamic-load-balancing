#!/usr/bin/env bash
set -euo pipefail

RESULT_DIR="results"
mkdir -p "$RESULT_DIR"

echo "=== Failure Injection Experiment (latency_aware) ==="

ALGORITHM="latency_aware" docker compose up --build -d
sleep 8

echo "Saving pre-crash worker state..."
curl -s "http://localhost:8080/lb/workers" > "${RESULT_DIR}/failure-pre-crash-workers.json"

echo "Starting k6 load in the background (60s)..."
docker compose --profile loadtest run --rm \
  -e BASE_URL=http://load-balancer:8080 \
  -e VUS=30 \
  -e DURATION=60s \
  -e DELAY_MS=40 \
  -e CPU_MS=5 \
  k6 run --summary-export "/results/failure-k6-summary.json" /scripts/k6-failure.js &

K6_PID=$!

echo "Waiting 20 seconds before crashing worker-2..."
sleep 20

echo "Crashing worker-2..."
curl -s "http://localhost:3102/api/v1/crash" || true

echo "Worker-2 crashed. Saving post-crash state..."
sleep 5
curl -s "http://localhost:8080/lb/workers" > "${RESULT_DIR}/failure-post-crash-workers.json"
curl -s "http://localhost:8080/lb/stats" > "${RESULT_DIR}/failure-post-crash-stats.json"

echo "Waiting for k6 to finish..."
wait $K6_PID || true

echo "Saving final state..."
curl -s "http://localhost:8080/lb/stats" > "${RESULT_DIR}/failure-final-stats.json"
curl -s "http://localhost:8080/lb/workers" > "${RESULT_DIR}/failure-final-workers.json"
curl -s "http://localhost:8080/lb/metrics" > "${RESULT_DIR}/failure-final-metrics.prom"

docker compose down
echo "=== Failure experiment complete ==="
