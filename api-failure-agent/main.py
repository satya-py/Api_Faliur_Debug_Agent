"""
main.py — Entry point. Reads check interval from SQLite settings
so the dashboard can control it live.
"""

import os
import time
import schedule
from dotenv import load_dotenv
import streamlit as st


load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, get_setting
from agent.analyzer import run
from alerter.slack import send_slack_alert
api_key=st.secrets.GOOGLE_API_KEY

init_db()

def get_interval():
    val = get_setting("check_interval_minutes")
    try:
        return int(val) if val else 5
    except Exception:
        return 5

def get_window():
    val = get_setting("analysis_window_minutes")
    try:
        return int(val) if val else 5
    except Exception:
        return 5

def job():
    window = get_window()
    issues, analysis = run(window_minutes=window)
    if issues and analysis:
        send_slack_alert(issues, analysis)

interval = get_interval()

print("=" * 55)
print("  🚀 API Failure Detection Agent")
print("  Powered by Prometheus + Google Gemini AI")
print("=" * 55)
print(f"  Check interval : every {interval} minute(s)")
print(f"  Analysis window: last {get_window()} minute(s)")
print(f"  Prometheus URL : {os.getenv('PROMETHEUS_URL', 'http://localhost:9090')}")
print(f"  Gemini API     : {'✅ configured' if os.getenv('GOOGLE_API_KEY') else '❌ GOOGLE_API_KEY missing!'}")
print(f"  Slack alerts   : {'✅ enabled' if os.getenv('SLACK_WEBHOOK_URL') else '⚠️  disabled'}")
print("=" * 55)

if not os.getenv("GOOGLE_API_KEY"):
    print("\n❌ ERROR: GOOGLE_API_KEY not set in .env!")
    print("   Get your free key: https://aistudio.google.com/app/apikey")
    exit(1)

job()

schedule.every(interval).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(1)
