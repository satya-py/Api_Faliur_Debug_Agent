# ⚡ API Failure Detection Agent

An AI-powered agent that monitors your APIs in real-time, detects anomalies,
and uses Claude AI to explain root causes and recommend debugging steps.

**Stack:** Python · FastAPI · Prometheus · Claude API · Streamlit · Slack

---

## Project Structure

```
api-failure-agent/
├── sample_api/
│   └── app.py            ← Fake API that generates real metrics + failures
├── agent/
│   └── analyzer.py       ← Queries Prometheus, calls Claude AI
├── alerter/
│   └── slack.py          ← Sends formatted Slack alerts
├── prometheus/
│   └── prometheus.yml    ← Prometheus scrape config (put .exe here too)
├── logs/
│   └── detections.jsonl  ← Auto-created; stores all AI analyses
├── dashboard.py          ← Streamlit live dashboard
├── main.py               ← Main scheduler (runs agent every N minutes)
├── requirements.txt
└── .env.example          ← Copy to .env and fill in your keys
```

---

## Windows Setup (Step by Step)

### Step 1 — Install Python dependencies

Open Command Prompt or PowerShell inside this folder:

```bat
pip install -r requirements.txt
```

---

### Step 2 — Download Prometheus for Windows

1. Go to: https://prometheus.io/download/
2. Download the **windows-amd64** `.zip`
3. Extract and copy `prometheus.exe` into the `prometheus/` folder

Your folder should look like:
```
prometheus/
├── prometheus.exe    ← the binary you downloaded
└── prometheus.yml    ← already included in this project
```

---

### Step 3 — Set up your environment variables

Copy `.env.example` to `.env`:

```bat
copy .env.example .env
```

Then open `.env` in Notepad and fill in:

```
ANTHROPIC_API_KEY=your_key_here          ← get from console.anthropic.com
SLACK_WEBHOOK_URL=your_webhook_here      ← optional, skip if you don't want Slack
CHECK_INTERVAL_MINUTES=5
```

---

### Step 4 — Run everything (3 terminals)

**Terminal 1 — Start the sample API:**
```bat
uvicorn sample_api.app:app --port 8000
```
This starts a fake API at http://localhost:8000 that auto-generates
traffic with realistic failures. Check metrics at http://localhost:8000/metrics

**Terminal 2 — Start Prometheus:**
```bat
cd prometheus
prometheus.exe --config.file=prometheus.yml
```
Prometheus dashboard at http://localhost:9090

**Terminal 3 — Start the AI agent:**
```bat
python main.py
```
The agent checks for failures every 5 minutes and prints Claude's analysis.

**Terminal 4 (optional) — Start the dashboard:**
```bat
streamlit run dashboard.py
```
Live visual dashboard at http://localhost:8501

---

## How It Works

```
sample_api/app.py     →  exposes /metrics (Prometheus format)
                      ↓
prometheus.exe        →  scrapes metrics every 15s, stores them
                      ↓
agent/analyzer.py     →  queries Prometheus for error spikes & latency
                      ↓
Claude API            →  explains root cause + gives 3 debugging steps
                      ↓
alerter/slack.py      →  sends formatted alert to Slack
dashboard.py          →  shows live status + AI analyses in browser
```

## What Gets Detected

- **Error spikes** — 5xx responses above threshold in last 5 minutes
- **High latency** — p95 latency above 1s per endpoint
- **Error rate %** — percentage of failing requests per endpoint
- **Severity levels** — AUTO (CRITICAL / HIGH / MEDIUM / LOW / OK)

## Example Claude Output

```
ROOT CAUSE:
The /api/payments endpoint is experiencing a 45% error rate with p95
latency of 3.8s, coinciding with high request volume. This pattern
suggests database connection pool exhaustion or a downstream payment
processor timeout rather than a code error.

DEBUGGING STEPS:
1. Check your database connection pool utilization — run:
   SELECT count(*) FROM pg_stat_activity WHERE state = 'active'
2. Inspect payment processor logs for timeout errors in the last 30 minutes
3. Review recent deployments to payments-service; roll back if deployed in last 2h

SEVERITY: CRITICAL
```

---

## Getting a Slack Webhook (Free)

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Choose a workspace → go to "Incoming Webhooks"
4. Toggle ON → "Add New Webhook to Workspace"
5. Copy the webhook URL → paste into `.env`

---

## Customizing Check Intervals

In `.env`:
```
CHECK_INTERVAL_MINUTES=2   ← check every 2 minutes
```

---

## Stopping Everything

Press `Ctrl+C` in each terminal.


## ⚠️ Download Prometheus Separately
Prometheus binaries are not included (too large for GitHub).
Download from: https://prometheus.io/download/
Choose: windows-amd64 → extract into `prometheus-3.11.3.windows-amd64/`
