import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

export const options = {
  scenarios: {
    stress: {
      executor: "ramping-vus",
      startVUs: 5,
      stages: [
        { duration: "15s", target: 30 },
        { duration: "15s", target: 80 },
        { duration: "15s", target: 150 },
        { duration: "15s", target: 300 },
        { duration: "10s", target: 10 }
      ]
    }
  },
  thresholds: {
    http_req_duration: ["p(95)<5000"],
    error_rate: ["rate<0.50"]
  }
};

const upstreamLatency = new Trend("upstream_latency_ms");
const errorRate = new Rate("error_rate");
const worker1 = new Counter("worker_1_requests");
const worker2 = new Counter("worker_2_requests");
const worker3 = new Counter("worker_3_requests");

export default function () {
  const baseUrl = __ENV.BASE_URL || "http://localhost:8787";
  const delayMs = __ENV.DELAY_MS || "40";
  const cpuMs = __ENV.CPU_MS || "5";

  const response = http.get(`${baseUrl}/api/v1/analytics/event?delay_ms=${delayMs}&cpu_ms=${cpuMs}`);

  const success = response.status === 200;
  check(response, { "status is 200": () => success });
  errorRate.add(!success);

  const selectedWorker = response.headers["X-Selected-Worker"];
  if (selectedWorker === "worker-1") worker1.add(1);
  if (selectedWorker === "worker-2") worker2.add(1);
  if (selectedWorker === "worker-3") worker3.add(1);

  const latencyHeader = response.headers["X-Upstream-Latency-Ms"];
  if (latencyHeader) upstreamLatency.add(Number(latencyHeader));

  sleep(0.05);
}
