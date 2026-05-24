"""
dashboard.py — Upgraded Streamlit Dashboard
Features:
  • Paste your own logs for instant AI analysis
  • Choose analysis time window (5m / 15m / 1h)
  • Choose auto-check interval
  • SQLite-backed history with stats
  • Live Prometheus monitoring
"""

from dotenv import load_dotenv
import os
load_dotenv()
import os
import json
import time
import requests
import streamlit as st
from datetime import datetime
# ── path fix so imports work when run from api-failure-agent/ ─────────────────
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    init_db, save_detection, get_recent_detections,
    get_summary_stats, get_setting, set_setting
)
from log_parser import test_endpoint, build_url_summary, parse_json_logs, aggregate_to_issues, build_manual_summary

import google.generativeai as genai

PROMETHEUS = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY", "")
if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)
    gemini_model = genai.GenerativeModel("gemini-2.5-flash")
else:
    gemini_model = None

SYSTEM_PROMPT = """You are an expert SRE and API debugging specialist.
Analyse the API failure data and respond EXACTLY in this format:

ROOT CAUSE:
<2-3 sentence analysis>

DEBUGGING STEPS:
1. <specific step>
2. <specific step>
3. <specific step>

SEVERITY: <LOW|MEDIUM|HIGH|CRITICAL>
"""

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="API Failure Detection Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@700;800;900&display=swap');

html, body, [class*="css"] { font-family: 'JetBrains Mono', monospace; background:#0a0e1a; color:#c9d1e0; }
h1,h2,h3 { font-family:'Syne',sans-serif; }
.stApp { background:#0a0e1a; }
section[data-testid="stSidebar"] { background:#080c18 !important; border-right:1px solid #1e293b; }

/* Cards */
.metric-card { background:linear-gradient(135deg,#111827,#1a2035); border:1px solid #1e293b;
    border-radius:12px; padding:20px 24px; margin-bottom:12px; }
.metric-card.critical { border-left:4px solid #ef4444; }
.metric-card.high     { border-left:4px solid #f97316; }
.metric-card.medium   { border-left:4px solid #eab308; }
.metric-card.low      { border-left:4px solid #22c55e; }
.metric-card.ok       { border-left:4px solid #3b82f6; }

.endpoint-name { font-size:15px; font-weight:700; color:#e2e8f0; margin-bottom:8px; }
.stat-row { display:flex; gap:20px; font-size:12px; color:#94a3b8; flex-wrap:wrap; }
.stat-val { color:#f1f5f9; font-weight:700; }

/* Badges */
.severity-badge { display:inline-block; padding:2px 10px; border-radius:4px;
    font-size:10px; font-weight:700; letter-spacing:.08em; }
.badge-critical { background:#7f1d1d; color:#fca5a5; }
.badge-high     { background:#7c2d12; color:#fdba74; }
.badge-medium   { background:#713f12; color:#fde047; }
.badge-low      { background:#14532d; color:#86efac; }
.badge-ok       { background:#1e3a5f; color:#93c5fd; }

/* Dots */
.status-dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:7px; }
.dot-ok      { background:#22c55e; box-shadow:0 0 6px #22c55e; }
.dot-warning { background:#eab308; box-shadow:0 0 6px #eab308; }
.dot-critical{ background:#ef4444; box-shadow:0 0 6px #ef4444; animation:blink 1s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }

/* AI box */
.ai-box { background:#0f172a; border:1px solid #1e3a5f; border-radius:10px;
    padding:18px; font-size:12.5px; line-height:1.75; white-space:pre-wrap; color:#93c5fd;
    margin-bottom:10px; }

/* Gemini badge */
.gemini-tag { display:inline-block; background:#14532d; color:#4ade80;
    border:1px solid #166534; padding:2px 8px; border-radius:4px;
    font-size:10px; font-weight:700; margin-bottom:6px; }

/* Manual badge */
.manual-tag { display:inline-block; background:#1e1b4b; color:#a5b4fc;
    border:1px solid #3730a3; padding:2px 8px; border-radius:4px;
    font-size:10px; font-weight:700; margin-bottom:6px; }

/* Section header */
.section-hdr { font-family:'Syne',sans-serif; font-size:18px; font-weight:800;
    color:#e2e8f0; margin:6px 0 12px; padding-bottom:6px;
    border-bottom:1px solid #1e293b; }

/* Log paste area */
.stTextArea textarea { background:#0f172a !important; color:#93c5fd !important;
    border:1px solid #1e3a5f !important; font-family:'JetBrains Mono',monospace !important;
    font-size:12px !important; border-radius:8px !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background:#080c18; border-radius:8px; padding:4px; }
.stTabs [data-baseweb="tab"] { color:#64748b; font-family:'JetBrains Mono',monospace;
    font-size:12px; font-weight:600; }
.stTabs [aria-selected="true"] { color:#60a5fa !important; background:#111827 !important;
    border-radius:6px; }

/* KPI */
div[data-testid="stMetric"] { background:#111827; border:1px solid #1e293b;
    border-radius:10px; padding:14px; }
div[data-testid="stMetric"] label { color:#64748b !important; font-size:10px !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] { color:#e2e8f0 !important; font-size:22px !important; }

/* Title */
.main-title { font-family:'Syne',sans-serif; font-size:28px; font-weight:900;
    background:linear-gradient(90deg,#60a5fa,#34d399); -webkit-background-clip:text;
    -webkit-text-fill-color:transparent; margin-bottom:2px; }
.main-sub { color:#475569; font-size:11px; margin-bottom:16px; }

/* Stat pill */
.stat-pill { display:inline-block; background:#111827; border:1px solid #1e293b;
    border-radius:20px; padding:3px 12px; font-size:11px; color:#94a3b8; margin:2px; }

/* Format badge */
.fmt-badge { display:inline-block; background:#0c1a2e; color:#38bdf8;
    border:1px solid #0369a1; padding:2px 8px; border-radius:4px; font-size:10px;
    font-weight:700; }

button[kind="primary"] { background:#1d4ed8 !important; border:none !important;
    font-family:'JetBrains Mono',monospace !important; font-weight:700 !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def prom_query(promql):
    try:
        r = requests.get(f"{PROMETHEUS}/api/v1/query", params={"query": promql}, timeout=4)
        return r.json().get("data", {}).get("result", [])
    except Exception:
        return []

def prom_ok():
    try:
        return requests.get(f"{PROMETHEUS}/-/healthy", timeout=2).status_code == 200
    except Exception:
        return False

def get_live_metrics(window_min: int):
    w = f"{window_min}m"
    errors    = prom_query(f'sum by (endpoint) (increase(http_requests_total{{status=~"5.."}}[{w}]))')
    latency   = prom_query(f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[{w}]))')
    req_rate  = prom_query(f'sum by (endpoint) (rate(http_requests_total[{w}])) * 60')
    error_pct = prom_query(
        f'sum by (endpoint) (rate(http_requests_total{{status=~"5.."}}[{w}]))'
        f' / sum by (endpoint) (rate(http_requests_total[{w}])) * 100'
    )
    return errors, latency, req_rate, error_pct

def build_issues_from_prometheus(errors, latency, req_rate, error_pct):
    lat_map  = {r["metric"].get("endpoint","?"): float(r["value"][1]) for r in latency  if r["value"][1] != "NaN"}
    rate_map = {r["metric"].get("endpoint","?"): float(r["value"][1]) for r in req_rate if r["value"][1] != "NaN"}
    epct_map = {r["metric"].get("endpoint","?"): float(r["value"][1]) for r in error_pct if r["value"][1] != "NaN"}
    all_eps  = set(lat_map) | set(rate_map) | {r["metric"].get("endpoint","?") for r in errors}

    issues = []
    for ep in all_eps:
        err_count = next((float(r["value"][1]) for r in errors if r["metric"].get("endpoint")==ep), 0)
        pct = epct_map.get(ep, 0)
        lat = lat_map.get(ep, 0)
        rps = rate_map.get(ep, 0)
        if pct > 50 or lat > 3.0:   sev = "CRITICAL"
        elif pct > 25 or lat > 2.0: sev = "HIGH"
        elif pct > 10 or lat > 1.0: sev = "MEDIUM"
        elif err_count > 0:          sev = "LOW"
        else:                        sev = "OK"
        issues.append({"endpoint":ep,"error_count":round(err_count),"error_pct":round(pct,1),
                       "p95_latency_s":round(lat,2),"req_per_min":round(rps,1),"severity":sev})
    issues.sort(key=lambda x: ["CRITICAL","HIGH","MEDIUM","LOW","OK"].index(x["severity"]))
    return issues

def severity_cls(s):
    return {"CRITICAL":"critical","HIGH":"high","MEDIUM":"medium","LOW":"low"}.get(s,"ok")

def badge(s):
    return f'<span class="severity-badge badge-{s.lower()}">{s}</span>'

def dot(sev):
    d = "dot-critical" if sev in ("CRITICAL","HIGH") else ("dot-warning" if sev=="MEDIUM" else "dot-ok")
    return f'<span class="status-dot {d}"></span>'

def render_endpoint_card(i):
    sev = i["severity"]
    st.markdown(f"""
    <div class="metric-card {severity_cls(sev)}">
        <div class="endpoint-name">{dot(sev)}{i['endpoint']}&nbsp;&nbsp;{badge(sev)}</div>
        <div class="stat-row">
            <span>Errors: <span class="stat-val">{i['error_count']}</span></span>
            <span>Error%: <span class="stat-val">{i['error_pct']}%</span></span>
            <span>p95: <span class="stat-val">{i.get('p95_latency_s',0)}s</span></span>
            <span>Rate: <span class="stat-val">{i.get('req_per_min',0)}/min</span></span>
        </div>
    </div>""", unsafe_allow_html=True)

def call_gemini(summary: str) -> str:
    if not gemini_model:
        return "❌ GOOGLE_API_KEY not configured."
    try:
        resp = gemini_model.generate_content(SYSTEM_PROMPT + "\n\n" + summary)
        return resp.text
    except Exception as e:
        return f"❌ Gemini error: {e}"

def render_detection(det, show_raw=False):
    ts = det.get("timestamp","")[:19].replace("T"," ")
    src = det.get("source","auto")
    tag = '<span class="manual-tag">📋 MANUAL</span>' if src=="manual" else '<span class="gemini-tag">✨ LIVE</span>'
    issues = json.loads(det.get("issues_json","[]"))
    st.markdown(f'{tag} &nbsp; <b style="color:#e2e8f0">{ts}</b> — {len(issues)} endpoint(s) · <b style="color:#ef4444">{det.get("severity","?")}</b>', unsafe_allow_html=True)
    if show_raw and det.get("raw_input"):
        with st.expander("📄 View original pasted logs"):
            st.code(det["raw_input"][:2000], language="text")
    st.markdown(f'<div class="ai-box">{det.get("analysis","")}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-family:Syne,sans-serif;font-size:20px;font-weight:900;color:#60a5fa;margin-bottom:4px;">⚡ Controls</div>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("**⏱ Analysis Time Window**")
    window_label = st.select_slider(
        "How far back to look",
        options=["1 min", "5 min", "15 min", "30 min", "1 hour"],
        value="5 min",
        label_visibility="collapsed"
    )
    window_map = {"1 min":1,"5 min":5,"15 min":15,"30 min":30,"1 hour":60}
    window_minutes = window_map[window_label]

    st.markdown("**🔄 Auto-Refresh**")
    refresh_sec = st.select_slider(
        "Dashboard refresh rate",
        options=[10, 20, 30, 60, 120],
        value=30,
        label_visibility="collapsed"
    )

    st.markdown("**🔔 Auto-Check Interval**")
    check_interval = st.select_slider(
        "How often the agent checks",
        options=["1 min", "5 min", "10 min", "15 min", "30 min"],
        value="5 min",
        label_visibility="collapsed"
    )
    set_setting("check_interval_minutes", str(window_map.get(check_interval, 5)))
    set_setting("analysis_window_minutes", str(window_minutes))

    st.markdown("---")
    st.markdown("**📡 Prometheus**")
    prometheus_healthy = prom_ok()
    if prometheus_healthy:
        st.success(f"✅ Connected\n`{PROMETHEUS}`")
    else:
        st.error(f"❌ Not reachable\n`{PROMETHEUS}`")

    st.markdown("**🤖 AI Engine**")
    if GOOGLE_KEY:
        st.success("✅ Gemini 1.5 Flash")
    else:
        st.error("❌ No API key")

    st.markdown("---")
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.rerun()


# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
st.markdown('<div class="main-title">⚡ API Failure Detection Agent</div>', unsafe_allow_html=True)
st.markdown(f'<div class="main-sub">Real-time monitoring · Google Gemini AI · Window: <b>{window_label}</b> · Refresh: {refresh_sec}s</div>', unsafe_allow_html=True)

tab_live, tab_paste, tab_history, tab_stats = st.tabs([
    "📡  Live Monitor", "📋  Paste Logs", "🗂  History", "📊  Statistics"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE MONITOR
# ══════════════════════════════════════════════════════════════════════════════
with tab_live:
    live_placeholder = st.empty()

    with live_placeholder.container():
        if not prometheus_healthy:
            st.error("⚠️ Prometheus is not running. Start it first, then refresh.")
        else:
            errors, latency, req_rate, error_pct = get_live_metrics(window_minutes)
            issues = build_issues_from_prometheus(errors, latency, req_rate, error_pct)

            # KPI row
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Total Errors", sum(i["error_count"] for i in issues))
            c2.metric("Critical Endpoints", sum(1 for i in issues if i["severity"]=="CRITICAL"))
            lat_vals = [i["p95_latency_s"] for i in issues if i["p95_latency_s"] > 0]
            c3.metric("Avg p95 Latency", f"{round(sum(lat_vals)/len(lat_vals),2)}s" if lat_vals else "—")
            c4.metric("Healthy", f"{sum(1 for i in issues if i['severity']=='OK')}/{len(issues)}")

            st.markdown("---")

            col_ep, col_ai = st.columns([1.2, 1])

            with col_ep:
                st.markdown('<div class="section-hdr">Endpoint Status</div>', unsafe_allow_html=True)
                if not issues:
                    st.info("No endpoints found yet. Make sure the sample API is running.")
                for i in issues:
                    render_endpoint_card(i)

            with col_ai:
                st.markdown('<div class="section-hdr">Latest AI Analyses</div>', unsafe_allow_html=True)
                recent = get_recent_detections(limit=5, source="auto")
                if recent:
                    for det in recent:
                        render_detection(det)
                else:
                    st.info("No analyses yet. Run `python main.py` to start the agent.")

        st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Window: {window_label} · Refreshing in {refresh_sec}s")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — PASTE YOUR LOGS
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — PASTE LOGS / TEST ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════
with tab_paste:
    st.markdown('<div class="section-hdr">🔍 Test Any Endpoint or Paste JSON Logs</div>', unsafe_allow_html=True)

    # ── Mode toggle ───────────────────────────────────────────────────────────
    mode = st.radio(
        "Choose input type",
        ["🌐 Test a URL endpoint", "📋 Paste JSON logs"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # MODE 1: URL ENDPOINT TESTER
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "🌐 Test a URL endpoint":
        st.markdown("**Paste any URL — the agent will hit it multiple times and diagnose it with AI**")

        col_url, col_n = st.columns([3, 1])
        with col_url:
            url_input = st.text_input(
                "Endpoint URL",
                placeholder="https://your-api.com/api/payments",
                label_visibility="collapsed"
            )
        with col_n:
            num_requests = st.selectbox(
                "Requests",
                [5, 10, 20, 50],
                index=1,
                label_visibility="collapsed"
            )

        col_timeout, col_btn2 = st.columns([1, 2])
        with col_timeout:
            timeout = st.selectbox("Timeout (s)", [5, 10, 30], index=1)
        with col_btn2:
            test_clicked = st.button(
                f"🚀 Test Endpoint ({num_requests} requests)",
                type="primary",
                use_container_width=True
            )

        # Example URLs hint
        st.caption("Examples: https://httpbin.org/status/503  ·  https://httpbin.org/delay/3  ·  http://localhost:8000/api/payments")

        if test_clicked:
            if not url_input.strip():
                st.warning("Please enter a URL first.")
            elif not url_input.startswith("http"):
                st.warning("URL must start with http:// or https://")
            elif not gemini_model:
                st.error("GOOGLE_API_KEY not set in .env")
            else:
                # Live progress bar
                progress = st.progress(0, text=f"Testing {url_input} ...")
                result_placeholder = st.empty()

                with st.spinner(f"Sending {num_requests} requests to {url_input}..."):
                    import threading

                    test_result = {}
                    def run_test():
                        test_result["data"] = test_endpoint(url_input, num_requests, timeout)

                    t = threading.Thread(target=run_test)
                    t.start()

                    # Update progress while waiting
                    for pct in range(1, 95, 5):
                        time.sleep(0.4)
                        progress.progress(pct, text=f"Testing... ({pct}%)")
                        if not t.is_alive():
                            break
                    t.join()
                    progress.progress(100, text="Done! Calling Gemini AI...")

                result = test_result.get("data", {})
                if not result:
                    st.error("Test failed — could not connect.")
                else:
                    # Build and call Gemini
                    summary_text = build_url_summary(result)
                    analysis = call_gemini(summary_text)

                    # Convert to issue format for DB
                    issue = {
                        "endpoint": result["url"],
                        "error_count": result["error_count"],
                        "error_pct": result["error_pct"],
                        "p95_latency_s": result["p95_latency_s"],
                        "req_per_min": round(result["total_requests"] / 1, 1),
                        "severity": result["severity"],
                    }
                    det_id = save_detection([issue], analysis, source="manual", raw_input=url_input)
                    progress.empty()

                    # ── Results UI ────────────────────────────────────────────
                    st.markdown("---")
                    sev = result["severity"]
                    sev_color = {"CRITICAL":"#ef4444","HIGH":"#f97316","MEDIUM":"#eab308","LOW":"#22c55e","OK":"#3b82f6"}.get(sev,"#94a3b8")

                    # Top summary row
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Total Requests", result["total_requests"])
                    m2.metric("Errors", f"{result['error_count']} ({result['error_pct']}%)")
                    m3.metric("p95 Latency", f"{result['p95_latency_s']}s")
                    m4.metric("Avg Latency", f"{result['avg_latency_s']}s")
                    m5.metric("Severity", sev)

                    st.markdown("<br>", unsafe_allow_html=True)

                    col_detail, col_analysis = st.columns([1, 1.3])

                    with col_detail:
                        st.markdown("**Request Details**")
                        st.markdown(f"""
                        <div class="metric-card {severity_cls(sev)}">
                            <div class="endpoint-name">{dot(sev)}{result['url']}&nbsp;&nbsp;{badge(sev)}</div>
                            <div class="stat-row" style="flex-direction:column;gap:6px;margin-top:8px;">
                                <span>Status codes seen: <span class="stat-val">{result['status_codes']}</span></span>
                                <span>Min latency: <span class="stat-val">{result['min_latency_s']}s</span></span>
                                <span>Max latency: <span class="stat-val">{result['max_latency_s']}s</span></span>
                                <span>p95 latency: <span class="stat-val">{result['p95_latency_s']}s</span></span>
                                <span>Error rate: <span class="stat-val">{result['error_pct']}%</span></span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                        # Per-request breakdown
                        with st.expander("📋 Per-request breakdown"):
                            for idx, r in enumerate(result["raw_results"]):
                                icon = "✅" if not r["error"] else "❌"
                                reason = r.get("reason", "")
                                st.markdown(
                                    f"`#{idx+1}` {icon} Status: **{r['status']}** "
                                    f"| Latency: **{r['duration']}s** "
                                    f"{'| ' + reason if reason else ''}"
                                )

                    with col_analysis:
                        st.markdown('<span class="gemini-tag">✨ GEMINI AI DIAGNOSIS</span>', unsafe_allow_html=True)
                        st.markdown(f'<div class="ai-box">{analysis}</div>', unsafe_allow_html=True)
                        st.success(f"✅ Saved to database (ID: {det_id})")

    # ══════════════════════════════════════════════════════════════════════════
    # MODE 2: PASTE JSON LOGS
    # ══════════════════════════════════════════════════════════════════════════
    else:
        st.markdown("**Paste your JSON log lines below — one JSON object per line**")
        st.code('{"path":"/api/payments","status":503,"duration_ms":4200}', language="json")

        log_input = st.text_area(
            "Paste logs",
            height=200,
            placeholder='{"path":"/api/payments","status":503,"duration_ms":4200}\n{"path":"/api/users","status":200,"duration_ms":120}',
            label_visibility="collapsed"
        )

        if st.button("🤖 Analyse Logs with Gemini", type="primary"):
            if not log_input.strip():
                st.warning("Please paste some log lines first.")
            elif not gemini_model:
                st.error("GOOGLE_API_KEY not set.")
            else:
                with st.spinner("Parsing and analysing..."):
                    records = parse_json_logs(log_input)
                    if not records:
                        st.error("Could not parse any JSON log records. Check the format.")
                    else:
                        issues = aggregate_to_issues(records)
                        summary_text = build_manual_summary(issues, "JSON", len(records))
                        analysis = call_gemini(summary_text)
                        det_id = save_detection(issues, analysis, source="manual", raw_input=log_input)

                        st.markdown("---")
                        st.markdown(f'<span class="stat-pill">{len(records)} lines parsed</span> <span class="stat-pill">{len(issues)} endpoints</span>', unsafe_allow_html=True)
                        st.markdown("<br>", unsafe_allow_html=True)

                        col_c, col_r = st.columns([1, 1.2])
                        with col_c:
                            st.markdown("**Detected Issues**")
                            for i in issues:
                                render_endpoint_card(i)
                        with col_r:
                            st.markdown('<span class="gemini-tag">✨ GEMINI ANALYSIS</span>', unsafe_allow_html=True)
                            st.markdown(f'<div class="ai-box">{analysis}</div>', unsafe_allow_html=True)
                            st.success(f"✅ Saved to database (ID: {det_id})")
# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — HISTORY
# ══════════════════════════════════════════════════════════════════════════════
with tab_history:
    st.markdown('<div class="section-hdr">🗂 Detection History (SQLite)</div>', unsafe_allow_html=True)

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filter_source = st.selectbox("Source", ["All", "Live (auto)", "Manual (pasted)"])
    with col_f2:
        filter_severity = st.selectbox("Min Severity", ["All", "CRITICAL", "HIGH", "MEDIUM", "LOW"])
    with col_f3:
        history_limit = st.selectbox("Show last", [10, 25, 50, 100], index=1)

    src_map = {"All": None, "Live (auto)": "auto", "Manual (pasted)": "manual"}
    detections = get_recent_detections(limit=history_limit, source=src_map[filter_source])

    sev_order = {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3,"OK":4}
    if filter_severity != "All":
        detections = [d for d in detections
                      if sev_order.get(d.get("severity","OK"),4) <= sev_order[filter_severity]]

    st.markdown(f"**{len(detections)} detections found**")
    st.markdown("---")

    if not detections:
        st.info("No detections yet. Run the agent or paste logs in the Paste Logs tab.")
    else:
        for det in detections:
            with st.expander(
                f"{'🔴' if det['severity']=='CRITICAL' else '🟠' if det['severity']=='HIGH' else '🟡' if det['severity']=='MEDIUM' else '🟢'} "
                f"  {det['timestamp'][:19].replace('T',' ')}  ·  {det['severity']}  ·  "
                f"{'📋 Manual' if det['source']=='manual' else '📡 Live'}  ·  {det['endpoint_count']} endpoint(s)"
            ):
                render_detection(det, show_raw=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — STATISTICS
# ══════════════════════════════════════════════════════════════════════════════
with tab_stats:
    st.markdown('<div class="section-hdr">📊 Project Statistics</div>', unsafe_allow_html=True)

    stats = get_summary_stats()

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Detections", stats["total_detections"])
    c2.metric("Critical Events", stats["critical_count"])
    c3.metric("Detected Today", stats["today_count"])
    c4.metric("Manual Analyses", stats["manual_analyses"])

    st.markdown("---")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Most Failing Endpoint (All Time)**")
        top = stats.get("top_failing_endpoint")
        if top:
            st.markdown(f"""
            <div class="metric-card critical">
                <div class="endpoint-name">🔴 {top['endpoint']}</div>
                <div class="stat-row"><span>CRITICAL/HIGH detections: <span class="stat-val">{top['cnt']}</span></span></div>
            </div>""", unsafe_allow_html=True)
        else:
            st.info("Not enough data yet.")

    with col_b:
        st.markdown("**Current Settings**")
        st.markdown(f"""
        <div class="metric-card ok">
            <div class="stat-row" style="flex-direction:column;gap:8px;">
                <span>Analysis window: <span class="stat-val">{window_label}</span></span>
                <span>Auto-check interval: <span class="stat-val">{check_interval}</span></span>
                <span>Dashboard refresh: <span class="stat-val">{refresh_sec}s</span></span>
                <span>Prometheus: <span class="stat-val">{'✅ Connected' if prometheus_healthy else '❌ Offline'}</span></span>
                <span>Gemini: <span class="stat-val">{'✅ Ready' if GOOGLE_KEY else '❌ No key'}</span></span>
            </div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Recent Manual Analyses**")
    manual = get_recent_detections(limit=5, source="manual")
    if manual:
        for det in manual:
            render_detection(det, show_raw=True)
    else:
        st.info("No manual analyses yet. Use the 'Paste Logs' tab to analyse your own logs.")

    st.caption(f"Database: {os.path.abspath('api_agent.db')} · Updated: {datetime.now().strftime('%H:%M:%S')}")
