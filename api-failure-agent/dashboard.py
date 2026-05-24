"""
Streamlit Dashboard — Live visualization of API health & AI analysis.
Run: streamlit run dashboard.py
"""

import os
import json
import time
import requests
import streamlit as st
from datetime import datetime
from collections import defaultdict

PROMETHEUS = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

st.set_page_config(
    page_title="API Failure Detection Agent",
    page_icon="🔍",
    layout="wide",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'JetBrains Mono', monospace;
    background-color: #0a0e1a;
    color: #c9d1e0;
}

h1, h2, h3 { font-family: 'Syne', sans-serif; }

.stApp { background-color: #0a0e1a; }

.metric-card {
    background: linear-gradient(135deg, #111827 0%, #1a2035 100%);
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 12px;
}

.metric-card.critical { border-left: 4px solid #ef4444; }
.metric-card.high     { border-left: 4px solid #f97316; }
.metric-card.medium   { border-left: 4px solid #eab308; }
.metric-card.low      { border-left: 4px solid #22c55e; }
.metric-card.ok       { border-left: 4px solid #3b82f6; }

.endpoint-name {
    font-size: 16px;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 8px;
}

.stat-row {
    display: flex;
    gap: 24px;
    font-size: 13px;
    color: #94a3b8;
}

.stat-val { color: #f1f5f9; font-weight: 600; }

.severity-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
}
.badge-critical { background: #7f1d1d; color: #fca5a5; }
.badge-high     { background: #7c2d12; color: #fdba74; }
.badge-medium   { background: #713f12; color: #fde047; }
.badge-low      { background: #14532d; color: #86efac; }
.badge-ok       { background: #1e3a5f; color: #93c5fd; }

.ai-box {
    background: #0f172a;
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 20px;
    font-size: 13px;
    line-height: 1.7;
    white-space: pre-wrap;
    color: #93c5fd;
}

.status-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 8px;
}
.dot-ok       { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
.dot-warning  { background: #eab308; box-shadow: 0 0 6px #eab308; }
.dot-critical { background: #ef4444; box-shadow: 0 0 6px #ef4444; animation: pulse 1s infinite; }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

.header-title {
    font-family: 'Syne', sans-serif;
    font-size: 32px;
    font-weight: 800;
    background: linear-gradient(90deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 4px;
}

.header-sub {
    color: #475569;
    font-size: 12px;
    margin-bottom: 24px;
}

div[data-testid="stMetric"] {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 16px;
}
div[data-testid="stMetric"] label { color: #64748b !important; font-size: 11px !important; }
div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color: #e2e8f0 !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────
def prom_query(promql):
    try:
        r = requests.get(f"{PROMETHEUS}/api/v1/query", params={"query": promql}, timeout=4)
        return r.json().get("data", {}).get("result", [])
    except Exception:
        return []


def get_metrics():
    errors = prom_query('sum by (endpoint) (increase(http_requests_total{status=~"5.."}[5m]))')
    latency = prom_query('histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))')
    req_rate = prom_query('sum by (endpoint) (rate(http_requests_total[5m])) * 60')
    error_pct = prom_query(
        'sum by (endpoint) (rate(http_requests_total{status=~"5.."}[5m]))'
        ' / sum by (endpoint) (rate(http_requests_total[5m])) * 100'
    )
    return errors, latency, req_rate, error_pct


def load_logs():
    try:
        with open("logs/detections.jsonl") as f:
            return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []


def severity_color(s):
    return {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low"}.get(s, "ok")


def badge_html(severity):
    cls = f"badge-{severity.lower()}"
    return f'<span class="severity-badge {cls}">{severity}</span>'


# ── Layout ───────────────────────────────────────────────────────────────────
st.markdown('<div class="header-title">⚡ API Failure Detection Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="header-sub">Real-time monitoring powered by Prometheus + Claude AI</div>', unsafe_allow_html=True)

# Auto-refresh
refresh = st.sidebar.slider("Auto-refresh (seconds)", 10, 120, 30)
st.sidebar.markdown("---")
st.sidebar.markdown("**Prometheus**")
st.sidebar.code(PROMETHEUS)
st.sidebar.markdown("---")
if st.sidebar.button("🔄 Refresh Now"):
    st.rerun()

placeholder = st.empty()

while True:
    with placeholder.container():
        errors, latency, req_rate, error_pct = get_metrics()

        # Build maps
        lat_map = {r["metric"].get("endpoint", "?"): float(r["value"][1]) for r in latency if r["value"][1] != "NaN"}
        rate_map = {r["metric"].get("endpoint", "?"): float(r["value"][1]) for r in req_rate if r["value"][1] != "NaN"}
        epct_map = {r["metric"].get("endpoint", "?"): float(r["value"][1]) for r in error_pct if r["value"][1] != "NaN"}

        # Gather all endpoints
        all_endpoints = set(lat_map) | set(rate_map) | {r["metric"].get("endpoint", "?") for r in errors}

        # Build issue list
        issues = []
        for ep in all_endpoints:
            err_count = next((float(r["value"][1]) for r in errors if r["metric"].get("endpoint") == ep), 0)
            pct = epct_map.get(ep, 0)
            lat = lat_map.get(ep, 0)
            rps = rate_map.get(ep, 0)

            if pct > 50 or lat > 3.0:
                sev = "CRITICAL"
            elif pct > 25 or lat > 2.0:
                sev = "HIGH"
            elif pct > 10 or lat > 1.0:
                sev = "MEDIUM"
            elif err_count > 0:
                sev = "LOW"
            else:
                sev = "OK"

            issues.append({
                "endpoint": ep,
                "error_count": round(err_count),
                "error_pct": round(pct, 1),
                "p95_latency_s": round(lat, 2),
                "req_per_min": round(rps, 1),
                "severity": sev,
            })

        issues.sort(key=lambda x: ["CRITICAL","HIGH","MEDIUM","LOW","OK"].index(x["severity"]))

        # ── KPI Row ──────────────────────────────────────────────────────────
        col1, col2, col3, col4 = st.columns(4)
        total_errors = sum(i["error_count"] for i in issues)
        critical_count = sum(1 for i in issues if i["severity"] == "CRITICAL")
        avg_latency = round(sum(lat_map.values()) / len(lat_map), 2) if lat_map else 0
        healthy = sum(1 for i in issues if i["severity"] == "OK")

        col1.metric("Total Errors (5min)", total_errors)
        col2.metric("Critical Endpoints", critical_count)
        col3.metric("Avg p95 Latency", f"{avg_latency}s")
        col4.metric("Healthy Endpoints", f"{healthy}/{len(issues)}")

        st.markdown("---")

        # ── Endpoint Cards ────────────────────────────────────────────────────
        col_left, col_right = st.columns([1.2, 1])

        with col_left:
            st.markdown("### Endpoint Status")
            for i in issues:
                sev = i["severity"]
                color_cls = severity_color(sev)
                dot_cls = "dot-critical" if sev in ("CRITICAL","HIGH") else ("dot-warning" if sev == "MEDIUM" else "dot-ok")

                st.markdown(f"""
                <div class="metric-card {color_cls}">
                    <div class="endpoint-name">
                        <span class="status-dot {dot_cls}"></span>
                        {i['endpoint']}
                        &nbsp;&nbsp;{badge_html(sev)}
                    </div>
                    <div class="stat-row">
                        <span>Errors: <span class="stat-val">{i['error_count']}</span></span>
                        <span>Error%: <span class="stat-val">{i['error_pct']}%</span></span>
                        <span>p95: <span class="stat-val">{i['p95_latency_s']}s</span></span>
                        <span>Rate: <span class="stat-val">{i['req_per_min']}/min</span></span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        # ── AI Analysis Log ───────────────────────────────────────────────────
        with col_right:
            st.markdown("### Latest AI Analyses")
            logs = load_logs()
            if logs:
                for entry in reversed(logs[-5:]):
                    ts = entry.get("timestamp", "")[:19].replace("T", " ")
                    num_issues = len(entry.get("issues", []))
                    st.markdown(f"**🕐 {ts}** — {num_issues} issue(s)")
                    st.markdown(f'<div class="ai-box">{entry["analysis"]}</div>', unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
            else:
                st.info("No AI analyses yet. Run `python main.py` to start the agent.")

        # ── Footer ────────────────────────────────────────────────────────────
        st.markdown("---")
        st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Refreshing every {refresh}s")

    time.sleep(refresh)
    placeholder.empty()
