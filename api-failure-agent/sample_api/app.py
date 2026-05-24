"""
Sample API - Simulates real API traffic with intentional failures
so you can test the AI agent without a real production system.
"""

from fastapi import FastAPI
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import random
import time
import threading

app = FastAPI(title="Sample API")

# ── Prometheus Metrics ──────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)
ERROR_RATE = Gauge("api_error_rate", "Current error rate per endpoint", ["endpoint"])
ACTIVE_CONNECTIONS = Gauge("api_active_connections", "Active connections", ["endpoint"])

# ── Simulate failure scenarios ──────────────────────────────────────────────
SCENARIOS = {
    "/api/payments": {"error_rate": 0.45, "min_latency": 0.5, "max_latency": 4.0},
    "/api/users":    {"error_rate": 0.05, "min_latency": 0.05, "max_latency": 0.3},
    "/api/orders":   {"error_rate": 0.20, "min_latency": 0.2, "max_latency": 2.0},
    "/api/products": {"error_rate": 0.02, "min_latency": 0.03, "max_latency": 0.2},
}


def simulate_request(endpoint: str):
    cfg = SCENARIOS[endpoint]
    latency = random.uniform(cfg["min_latency"], cfg["max_latency"])
    time.sleep(latency)
    status = "503" if random.random() < cfg["error_rate"] else "200"
    REQUEST_COUNT.labels("GET", endpoint, status).inc()
    REQUEST_LATENCY.labels(endpoint).observe(latency)
    ERROR_RATE.labels(endpoint).set(cfg["error_rate"])
    return status, latency


# ── Background traffic generator ────────────────────────────────────────────
def generate_traffic():
    """Continuously generates fake API traffic in background."""
    endpoints = list(SCENARIOS.keys())
    while True:
        ep = random.choice(endpoints)
        try:
            simulate_request(ep)
        except Exception:
            pass
        time.sleep(random.uniform(0.1, 0.5))


threading.Thread(target=generate_traffic, daemon=True).start()


# ── API Endpoints ────────────────────────────────────────────────────────────
@app.get("/api/payments")
def payments():
    status, latency = simulate_request("/api/payments")
    return {"status": status, "latency_ms": round(latency * 1000)}


@app.get("/api/users")
def users():
    status, latency = simulate_request("/api/users")
    return {"status": status, "latency_ms": round(latency * 1000)}


@app.get("/api/orders")
def orders():
    status, latency = simulate_request("/api/orders")
    return {"status": status, "latency_ms": round(latency * 1000)}


@app.get("/api/products")
def products():
    status, latency = simulate_request("/api/products")
    return {"status": status, "latency_ms": round(latency * 1000)}


@app.get("/metrics")
def metrics():
    """Prometheus scrapes this endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
def root():
    return {"message": "Sample API running", "endpoints": list(SCENARIOS.keys())}
