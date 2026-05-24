import os
import time
import schedule
from dotenv import load_dotenv

load_dotenv()

from agent.analyzer import run
from alerter.slack import send_slack_alert

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))

def job():
    issues, analysis = run()
    if issues and analysis:
        send_slack_alert(issues, analysis)

print("=" * 55)
print("  🚀 API Failure Detection Agent")
print("  Powered by Prometheus + Google Gemini AI")
print("=" * 55)
print(f"  Check interval : every {CHECK_INTERVAL_MINUTES} minute(s)")
print(f"  Prometheus URL : {os.getenv('PROMETHEUS_URL', 'http://localhost:9090')}")
print(f"  Gemini API     : {'✅ configured' if os.getenv('GOOGLE_API_KEY') else '❌ GOOGLE_API_KEY missing!'}")
print(f"  Slack alerts   : {'✅ enabled' if os.getenv('SLACK_WEBHOOK_URL') else '⚠️  disabled'}")
print("=" * 55)

if not os.getenv("GOOGLE_API_KEY"):
    print("\n❌ ERROR: GOOGLE_API_KEY not set in .env!")
    print("   Get your free key: https://aistudio.google.com/app/apikey")
    exit(1)

job()

schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(1)