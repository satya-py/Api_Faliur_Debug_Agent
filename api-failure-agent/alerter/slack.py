"""
Alerter - Sends failure alerts to Slack.
Set your webhook URL in .env or as environment variable SLACK_WEBHOOK_URL.
"""

import os
import requests
from datetime import datetime

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

SEVERITY_EMOJI = {
    "LOW": "🟡",
    "MEDIUM": "🟠",
    "HIGH": "🔴",
    "CRITICAL": "🚨",
}


def send_slack_alert(issues: list, analysis: str) -> bool:
    """Send a formatted Slack alert. Returns True if successful."""
    if not SLACK_WEBHOOK_URL:
        print("  ⚠️  SLACK_WEBHOOK_URL not set — skipping Slack alert.")
        return False

    if not issues:
        return False

    # Build issue summary blocks
    issue_lines = []
    for i in issues:
        emoji = SEVERITY_EMOJI.get(i["severity"], "⚠️")
        issue_lines.append(
            f"{emoji} *{i['endpoint']}* — "
            f"{i['error_count']} errors ({i['error_pct']}% rate), "
            f"p95={i['p95_latency_s']}s [{i['severity']}]"
        )

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 API Failure Detected",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"*Affected endpoints:* {len(issues)}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Issues Detected:*\n" + "\n".join(issue_lines),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🤖 AI Root Cause Analysis:*\n```{analysis}```",
                },
            },
        ]
    }

    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        if r.status_code == 200:
            print("  📨 Slack alert sent successfully!")
            return True
        else:
            print(f"  ❌ Slack error: {r.status_code} — {r.text}")
            return False
    except Exception as e:
        print(f"  ❌ Slack request failed: {e}")
        return False
