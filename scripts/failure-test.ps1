$ErrorActionPreference = "Stop"

Write-Host "Starting latency-aware experiment..."
$env:ALGORITHM = "latency_aware"
docker compose up --build -d

Start-Sleep -Seconds 8

Write-Host "Crashing worker-2..."
Invoke-WebRequest -Uri "http://localhost:3102/api/v1/crash" -UseBasicParsing | Out-Null

Start-Sleep -Seconds 5

Write-Host "Current load-balancer worker state:"
Invoke-WebRequest -Uri "http://localhost:8080/lb/workers" -UseBasicParsing

Write-Host "Run a load test manually or inspect http://localhost:8080/dashboard"
