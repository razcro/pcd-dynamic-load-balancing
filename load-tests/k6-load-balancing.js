import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

export const options = {
  scenarios: {
    constant_load: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 30),
      duration: __ENV.DURATION || "60s"
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.10"],
    http_req_duration: ["p(95)<1500"]
  }
};

const upstreamLatency = new Trend("upstream_latency_ms");
const missingWorkerHeader = new Rate("selected_worker_missing");
const worker1 = new Counter("worker_1_requests");
const worker2 = new Counter("worker_2_requests");
const worker3 = new Counter("worker_3_requests");

export default function () {
  const baseUrl = __ENV.BASE_URL || "http://localhost:8080";
  const delayMs = __ENV.DELAY_MS || "40";
  const cpuMs = __ENV.CPU_MS || "5";
  const failRate = __ENV.FAIL_RATE || "0";

  const response = http.get(`${baseUrl}/api/v1/analytics/event?delay_ms=${delayMs}&cpu_ms=${cpuMs}&fail_rate=${failRate}`);

  check(response, {
    "status is 200": (r) => r.status === 200,
    "selected worker header exists": (r) => Boolean(r.headers["X-Selected-Worker"])
  });

  const selectedWorker = response.headers["X-Selected-Worker"];
  missingWorkerHeader.add(!selectedWorker);

  if (selectedWorker === "worker-1") worker1.add(1);
  if (selectedWorker === "worker-2") worker2.add(1);
  if (selectedWorker === "worker-3") worker3.add(1);

  const upstreamLatencyHeader = response.headers["X-Upstream-Latency-Ms"];
  if (upstreamLatencyHeader) {
    upstreamLatency.add(Number(upstreamLatencyHeader));
  }

  sleep(Number(__ENV.SLEEP || 0.1));
}
