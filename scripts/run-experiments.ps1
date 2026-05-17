$ErrorActionPreference = "Stop"

$Algorithms = @("round_robin", "least_connections", "latency_aware")
$ResultDir = "results"

New-Item -ItemType Directory -Force -Path $ResultDir | Out-Null

foreach ($Algorithm in $Algorithms) {
    Write-Host "=== Running experiment for algorithm: $Algorithm ==="

    $env:ALGORITHM = $Algorithm
    docker compose up --build -d

    Start-Sleep -Seconds 8

    docker compose --profile loadtest run --rm `
        -e BASE_URL=http://load-balancer:8080 `
        -e VUS=30 `
        -e DURATION=60s `
        -e DELAY_MS=40 `
        -e CPU_MS=5 `
        -e FAIL_RATE=0 `
        k6 run --summary-export "/results/$Algorithm-summary.json" /scripts/k6-load-balancing.js

    Invoke-WebRequest -Uri "http://localhost:8080/lb/stats" -OutFile "$ResultDir/$Algorithm-stats.json"
    Invoke-WebRequest -Uri "http://localhost:8080/lb/workers" -OutFile "$ResultDir/$Algorithm-workers.json"
    Invoke-WebRequest -Uri "http://localhost:8080/lb/metrics" -OutFile "$ResultDir/$Algorithm-metrics.prom"

    docker compose down
    Start-Sleep -Seconds 3
}

Write-Host "Results saved in $ResultDir"
