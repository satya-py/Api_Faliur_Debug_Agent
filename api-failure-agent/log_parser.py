"""
log_parser.py — Handles both URL endpoint testing AND pasted JSON logs.
"""

import re
import json
import time
import requests
from collections import defaultdict
from datetime import datetime


# ── URL Endpoint Tester ───────────────────────────────────────────────────────
def test_endpoint(url: str, num_requests: int = 10, timeout: int = 10) -> dict:
    """
    Hit a URL N times and collect status codes + latencies.
    Returns a structured result dict.
    """
    results = []
    errors = 0

    for i in range(num_requests):
        try:
            start = time.time()
            r = requests.get(url, timeout=timeout)
            duration = round(time.time() - start, 3)
            status = r.status_code
            is_error = status >= 400
            if is_error:
                errors += 1
            results.append({"status": status, "duration": duration, "error": is_error})
        except requests.exceptions.ConnectionError:
            errors += 1
            results.append({"status": 0, "duration": timeout, "error": True, "reason": "Connection refused"})
        except requests.exceptions.Timeout:
            errors += 1
            results.append({"status": 0, "duration": timeout, "error": True, "reason": "Timeout"})
        except Exception as e:
            errors += 1
            results.append({"status": 0, "duration": timeout, "error": True, "reason": str(e)})
        time.sleep(0.3)  # small delay between requests

    total = len(results)
    durations = sorted([r["duration"] for r in results])
    p95_idx = int(len(durations) * 0.95)
    p95 = durations[min(p95_idx, len(durations) - 1)]
    avg_latency = round(sum(durations) / len(durations), 3)
    error_pct = round(errors / total * 100, 1)
    statuses = [r["status"] for r in results]

    # Severity
    if error_pct > 50 or p95 > 3.0:    severity = "CRITICAL"
    elif error_pct > 25 or p95 > 2.0:  severity = "HIGH"
    elif error_pct > 10 or p95 > 1.0:  severity = "MEDIUM"
    elif errors > 0:                    severity = "LOW"
    else:                               severity = "OK"

    # Extract path from URL
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path or "/"
        host = parsed.netloc
    except Exception:
        path = url
        host = url

    return {
        "url": url,
        "host": host,
        "path": path,
        "total_requests": total,
        "error_count": errors,
        "error_pct": error_pct,
        "p95_latency_s": round(p95, 3),
        "avg_latency_s": avg_latency,
        "min_latency_s": round(durations[0], 3),
        "max_latency_s": round(durations[-1], 3),
        "status_codes": list(set(statuses)),
        "severity": severity,
        "raw_results": results,
    }


def build_url_summary(result: dict) -> str:
    """Build summary text to send to Gemini."""
    lines = [
        f"Endpoint Health Check — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"URL: {result['url']}",
        f"",
        f"Results ({result['total_requests']} requests made):",
        f"  Error count   : {result['error_count']} ({result['error_pct']}%)",
        f"  p95 Latency   : {result['p95_latency_s']}s",
        f"  Avg Latency   : {result['avg_latency_s']}s",
        f"  Min Latency   : {result['min_latency_s']}s",
        f"  Max Latency   : {result['max_latency_s']}s",
        f"  Status codes  : {result['status_codes']}",
        f"  Severity      : {result['severity']}",
        f"",
        f"Diagnose this endpoint and give root cause + 3 debugging steps.",
    ]
    return "\n".join(lines)


# ── JSON Log Parser ───────────────────────────────────────────────────────────
def parse_json_logs(text: str) -> list:
    records = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
            path = (obj.get("path") or obj.get("url") or
                    obj.get("endpoint") or obj.get("request_path") or "unknown")
            status = int(obj.get("status") or obj.get("status_code") or
                         obj.get("http_status") or 200)
            duration = float(obj.get("duration_ms", 0) or 0) / 1000
            if duration == 0:
                duration = float(obj.get("duration") or obj.get("latency") or
                                 obj.get("response_time") or 0)
            records.append({"path": path, "status": status, "duration": duration})
        except Exception:
            continue
    return records


def aggregate_to_issues(records: list) -> list:
    if not records:
        return []
    stats = defaultdict(lambda: {"total": 0, "errors": 0, "durations": []})
    for r in records:
        ep = r["path"]
        stats[ep]["total"] += 1
        if r["status"] >= 500:
            stats[ep]["errors"] += 1
        if r["duration"] > 0:
            stats[ep]["durations"].append(r["duration"])

    issues = []
    for ep, s in stats.items():
        total = s["total"]
        errors = s["errors"]
        error_pct = round(errors / total * 100, 1) if total > 0 else 0
        durations = sorted(s["durations"])
        p95 = 0.0
        if durations:
            idx = int(len(durations) * 0.95)
            p95 = round(durations[min(idx, len(durations)-1)], 2)

        if error_pct > 50 or p95 > 3.0:   severity = "CRITICAL"
        elif error_pct > 25 or p95 > 2.0: severity = "HIGH"
        elif error_pct > 10 or p95 > 1.0: severity = "MEDIUM"
        elif errors > 0:                   severity = "LOW"
        else:                              severity = "OK"

        issues.append({
            "endpoint": ep, "error_count": errors, "error_pct": error_pct,
            "p95_latency_s": p95, "req_per_min": round(total/5, 1),
            "severity": severity, "total_requests": total,
        })

    issues.sort(key=lambda x: ["CRITICAL","HIGH","MEDIUM","LOW","OK"].index(x["severity"]))
    return issues


def build_manual_summary(issues: list, fmt: str, line_count: int) -> str:
    lines = [
        f"Manual Log Analysis — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Format: {fmt} | Lines parsed: {line_count}\n",
    ]
    for i in issues:
        icon = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢","OK":"✅"}.get(i["severity"],"⚪")
        lines.append(
            f"{icon} {i['endpoint']}\n"
            f"   Requests: {i['total_requests']} | Errors: {i['error_count']} ({i['error_pct']}%)\n"
            f"   p95 Latency: {i['p95_latency_s']}s | Severity: {i['severity']}\n"
        )
    lines.append("Analyze and give root cause + 3 debugging steps.")
    return "\n".join(lines)