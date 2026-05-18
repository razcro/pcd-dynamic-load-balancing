#!/usr/bin/env python3
"""
Parse k6 JSON summary files + LB stats JSON files from results/
and print a structured dict of all numbers needed for the paper.
"""
import json
import os
import sys

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"  [warn] cannot read {path}: {e}", file=sys.stderr)
        return None


def k6_metric(summary, *keys, default=None):
    """Navigate nested k6 summary dict."""
    d = summary
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
        if d is None:
            return default
    return d


def extract_k6(summary):
    """Pull the metrics we care about from a k6 summary-export JSON."""
    if not summary:
        return {}
    m = summary.get("metrics", {})

    def g(name, stat):
        entry = m.get(name, {})
        if "values" in entry:
            return entry["values"].get(stat)
        return entry.get(stat)

    avg_ms     = g("http_req_duration", "avg")
    p95_ms     = g("http_req_duration", "p(95)")
    p99_ms     = g("http_req_duration", "p(99)")
    rps        = g("http_reqs", "rate")          # req/s
    fail_rate  = g("http_req_failed", "rate")    # fraction 0..1

    return {
        "avg_ms":    round(avg_ms,   2) if avg_ms    is not None else None,
        "p95_ms":    round(p95_ms,   2) if p95_ms    is not None else None,
        "p99_ms":    round(p99_ms,   2) if p99_ms    is not None else None,
        "rps":       round(rps,      2) if rps        is not None else None,
        "fail_pct":  round(fail_rate * 100, 2) if fail_rate is not None else None,
    }


def extract_lb_stats(stats):
    if not stats:
        return {}
    return {
        "avg_ms":   stats.get("average_latency_ms"),
        "p95_ms":   stats.get("p95_latency_ms"),
        "p99_ms":   stats.get("p99_latency_ms"),
        "total_req":stats.get("total_requests"),
        "fail_pct": round(stats.get("failure_rate", 0) * 100, 2),
        "workers":  stats.get("workers", []),
    }


def extract_lb_workers(workers_json):
    if not workers_json:
        return {}
    result = {}
    for w in workers_json.get("workers", []):
        result[w["name"]] = {
            "total_requests": w.get("total_requests"),
            "ewma_latency_ms": w.get("ewma_latency_ms"),
            "healthy": w.get("healthy"),
        }
    return result


ALGORITHMS = ["round_robin", "least_connections", "latency_aware"]
SCENARIOS  = ["constant", "spike", "stress"]

data = {}

for alg in ALGORITHMS:
    data[alg] = {}
    for sc in SCENARIOS:
        k6_file    = os.path.join(RESULTS_DIR, f"{alg}-{sc}-summary.json")
        stats_file = os.path.join(RESULTS_DIR, f"{alg}-{sc}-stats.json")
        workers_file = os.path.join(RESULTS_DIR, f"{alg}-{sc}-workers.json")

        k6      = extract_k6(load_json(k6_file))
        lb      = extract_lb_stats(load_json(stats_file))
        workers = extract_lb_workers(load_json(workers_file))

        # Prefer k6 numbers; fall back to LB stats
        merged = {
            "avg_ms":   k6.get("avg_ms")   or lb.get("avg_ms"),
            "p95_ms":   k6.get("p95_ms")   or lb.get("p95_ms"),
            "p99_ms":   k6.get("p99_ms")   or lb.get("p99_ms"),
            "rps":      k6.get("rps"),
            "fail_pct": k6.get("fail_pct") if k6.get("fail_pct") is not None else lb.get("fail_pct"),
            "workers":  workers,
        }
        data[alg][sc] = merged

# Failure experiment
fail_pre   = extract_lb_workers(load_json(os.path.join(RESULTS_DIR, "failure-pre-crash-workers.json")))
fail_post  = extract_lb_workers(load_json(os.path.join(RESULTS_DIR, "failure-post-crash-workers.json")))
fail_stats = extract_lb_stats(load_json(os.path.join(RESULTS_DIR, "failure-post-crash-stats.json")))
fail_final = extract_lb_stats(load_json(os.path.join(RESULTS_DIR, "failure-final-stats.json")))
fail_k6    = extract_k6(load_json(os.path.join(RESULTS_DIR, "failure-k6-summary.json")))

data["failure"] = {
    "pre_crash_workers":  fail_pre,
    "post_crash_workers": fail_post,
    "post_crash_stats":   fail_stats,
    "final_stats":        fail_final,
    "k6":                 fail_k6,
}

print(json.dumps(data, indent=2))
