"""
AI Agent - Queries Prometheus for API anomalies,
then uses Google Gemini to explain root cause and recommend fixes.
"""

import os
import json
import requests
from datetime import datetime
import google.generativeai as genai

# ── Configure Gemini ─────────────────────────────────────────────────────────
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

PROMETHEUS = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

SYSTEM_PROMPT = """You are an expert site reliability engineer (SRE) and API debugging specialist.
You receive real-time API failure data and must:
1. Identify the most likely root cause in 2-3 sentences
2. Give exactly 3 specific, actionable debugging steps (numbered)
3. Rate severity: LOW / MEDIUM / HIGH / CRITICAL

Be concise, technical, and specific. No fluff. Format your response exactly as:

ROOT CAUSE:
<your analysis>

DEBUGGING STEPS:
1. <step>
2. <step>
3. <step>

SEVERITY: <level>
"""


def prom_query(promql: str) -> list:
    try:
        r = requests.get(
            f"{PROMETHEUS}/api/v1/query",
            params={"query": promql},
            timeout=5,
        )
        return r.json().get("data", {}).get("result", [])
    except Exception as e:
        print(f"  [Prometheus error] {e}")
        return []


def collect_metrics() -> dict:
    errors = prom_query(
        'sum by (endpoint) (increase(http_requests_total{status=~"5.."}[5m]))'
    )
    latency = prom_query(
        'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))'
    )
    req_rate = prom_query(
        'sum by (endpoint) (rate(http_requests_total[5m])) * 60'
    )
    error_pct = prom_query(
        'sum by (endpoint) (rate(http_requests_total{status=~"5.."}[5m])) '
        '/ sum by (endpoint) (rate(http_requests_total[5m])) * 100'
    )
    return {"errors": errors, "latency": latency, "req_rate": req_rate, "error_pct": error_pct}


def build_summary(metrics: dict) -> tuple:
    issues = []
    lines = [f"API Health Report — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]

    lat_map = {r["metric"].get("endpoint", "unknown"): float(r["value"][1])
               for r in metrics["latency"] if r["value"][1] != "NaN"}
    rate_map = {r["metric"].get("endpoint", "unknown"): float(r["value"][1])
                for r in metrics["req_rate"] if r["value"][1] != "NaN"}
    error_pct_map = {r["metric"].get("endpoint", "unknown"): float(r["value"][1])
                     for r in metrics["error_pct"] if r["value"][1] != "NaN"}

    for result in metrics["errors"]:
        ep = result["metric"].get("endpoint", "unknown")
        count = float(result["value"][1])
        if count < 1:
            continue

        lat = lat_map.get(ep, 0)
        pct = error_pct_map.get(ep, 0)
        rps = rate_map.get(ep, 0)

        if pct > 50 or lat > 3.0:       severity = "CRITICAL"
        elif pct > 25 or lat > 2.0:     severity = "HIGH"
        elif pct > 10 or lat > 1.0:     severity = "MEDIUM"
        else:                            severity = "LOW"

        issues.append({
            "endpoint": ep,
            "error_count": round(count),
            "error_pct": round(pct, 1),
            "p95_latency_s": round(lat, 2),
            "req_per_min": round(rps, 1),
            "severity": severity,
        })
        lines.append(
            f"🔴 {ep}\n"
            f"   Errors: {round(count)} in 5min ({round(pct,1)}% error rate)\n"
            f"   p95 Latency: {round(lat,2)}s\n"
            f"   Request rate: {round(rps,1)}/min\n"
            f"   Severity: {severity}\n"
        )

    for ep, lat in lat_map.items():
        if lat > 1.5 and not any(i["endpoint"] == ep for i in issues):
            issues.append({"endpoint": ep, "error_count": 0, "error_pct": 0,
                           "p95_latency_s": round(lat, 2), "req_per_min": rate_map.get(ep, 0), "severity": "MEDIUM"})
            lines.append(f"🐢 {ep} — High latency only: p95={round(lat,2)}s\n")

    return "\n".join(lines), issues


def analyze_with_gemini(summary: str) -> str:
    full_prompt = SYSTEM_PROMPT + "\n\n" + summary
    response = model.generate_content(full_prompt)
    return response.text


def save_to_log(issues: list, analysis: str):
    os.makedirs("logs", exist_ok=True)
    entry = {"timestamp": datetime.now().isoformat(), "issues": issues, "analysis": analysis}
    with open("logs/detections.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def run() -> tuple:
    print(f"\n{'='*55}")
    print(f"  Checking API health at {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}")

    metrics = collect_metrics()
    summary, issues = build_summary(metrics)

    if not issues:
        print("  ✅ All APIs healthy — no anomalies detected.")
        return [], None

    print(summary)
    print("  🤖 Sending to Gemini for analysis...")
    analysis = analyze_with_gemini(summary)

    print("\n  Gemini's Analysis:")
    print("  " + analysis.replace("\n", "\n  "))

    save_to_log(issues, analysis)
    return issues, analysis