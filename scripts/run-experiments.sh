#!/usr/bin/env bash
# k6 exits with code 99 when thresholds are breached — that is a valid
# experiment result, not a script error. We capture it and continue.
set -uo pipefail

ALGORITHMS=("round_robin" "least_connections" "latency_aware")
RESULT_DIR="results"

mkdir -p "$RESULT_DIR"
chmod 777 "$RESULT_DIR"

# --- Scenario 1: Constant Load (baseline comparison) ---
for algorithm in "${ALGORITHMS[@]}"; do
  echo "=== Constant Load: ${algorithm} ==="

  ALGORITHM="$algorithm" docker compose up --build -d
  sleep 8

  ALGORITHM="$algorithm" docker compose --profile loadtest run --rm \
    -e BASE_URL=http://load-balancer:8080 \
    -e VUS=30 \
    -e DURATION=60s \
    -e DELAY_MS=40 \
    -e CPU_MS=5 \
    -e FAIL_RATE=0 \
    k6 run --summary-export "/results/${algorithm}-constant-summary.json" /scripts/k6-load-balancing.js || true

  curl -s "http://localhost:8787/lb/stats"   > "${RESULT_DIR}/${algorithm}-constant-stats.json"
  curl -s "http://localhost:8787/lb/workers" > "${RESULT_DIR}/${algorithm}-constant-workers.json"
  curl -s "http://localhost:8787/lb/metrics" > "${RESULT_DIR}/${algorithm}-constant-metrics.prom"

  docker compose down
  sleep 3
done

# --- Scenario 2: Spike Test ---
for algorithm in "${ALGORITHMS[@]}"; do
  echo "=== Spike Test: ${algorithm} ==="

  ALGORITHM="$algorithm" docker compose up --build -d
  sleep 8

  ALGORITHM="$algorithm" docker compose --profile loadtest run --rm \
    -e BASE_URL=http://load-balancer:8080 \
    -e DELAY_MS=40 \
    -e CPU_MS=5 \
    k6 run --summary-export "/results/${algorithm}-spike-summary.json" /scripts/k6-spike.js || true

  curl -s "http://localhost:8787/lb/stats"   > "${RESULT_DIR}/${algorithm}-spike-stats.json"
  curl -s "http://localhost:8787/lb/workers" > "${RESULT_DIR}/${algorithm}-spike-workers.json"

  docker compose down
  sleep 3
done

# --- Scenario 3: Stress Test ---
for algorithm in "${ALGORITHMS[@]}"; do
  echo "=== Stress Test: ${algorithm} ==="

  ALGORITHM="$algorithm" docker compose up --build -d
  sleep 8

  ALGORITHM="$algorithm" docker compose --profile loadtest run --rm \
    -e BASE_URL=http://load-balancer:8080 \
    -e DELAY_MS=40 \
    -e CPU_MS=5 \
    k6 run --summary-export "/results/${algorithm}-stress-summary.json" /scripts/k6-stress.js || true

  curl -s "http://localhost:8787/lb/stats"   > "${RESULT_DIR}/${algorithm}-stress-stats.json"
  curl -s "http://localhost:8787/lb/workers" > "${RESULT_DIR}/${algorithm}-stress-workers.json"

  docker compose down
  sleep 3
done

# --- Scenario 4: Failure Injection ---
echo "=== Running failure injection experiment ==="
chmod +x scripts/failure-experiment.sh
./scripts/failure-experiment.sh

echo ""
echo "All experiments complete. Results saved in ${RESULT_DIR}/"
ls -la "${RESULT_DIR}/"
