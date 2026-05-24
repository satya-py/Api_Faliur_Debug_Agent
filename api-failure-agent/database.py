"""
database.py — SQLite database for storing all detections, analyses, and log submissions.
Replaces the flat detections.jsonl file with a proper queryable database.
"""

import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "api_agent.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS detections (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                source      TEXT DEFAULT 'auto',   -- 'auto' or 'manual'
                raw_input   TEXT,                  -- pasted log text (if manual)
                issues_json TEXT NOT NULL,
                analysis    TEXT NOT NULL,
                severity    TEXT NOT NULL,          -- highest severity in this batch
                endpoint_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS endpoint_stats (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                detection_id  INTEGER REFERENCES detections(id),
                timestamp     TEXT NOT NULL,
                endpoint      TEXT NOT NULL,
                error_count   INTEGER DEFAULT 0,
                error_pct     REAL DEFAULT 0,
                p95_latency   REAL DEFAULT 0,
                req_per_min   REAL DEFAULT 0,
                severity      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO settings VALUES ('check_interval_minutes', '5');
            INSERT OR IGNORE INTO settings VALUES ('analysis_window_minutes', '5');
            INSERT OR IGNORE INTO settings VALUES ('alert_on_severity', 'MEDIUM');
        """)
    print(f"  ✅ Database initialised: {DB_PATH}")


def save_detection(issues: list, analysis: str, source: str = "auto", raw_input: str = None) -> int:
    """Save a detection batch. Returns the new detection id."""
    if not issues:
        return -1

    severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "OK"]
    severities = [i.get("severity", "OK") for i in issues]
    highest = min(severities, key=lambda s: severity_order.index(s) if s in severity_order else 99)

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO detections
               (timestamp, source, raw_input, issues_json, analysis, severity, endpoint_count)
               VALUES (?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), source, raw_input,
             json.dumps(issues), analysis, highest, len(issues))
        )
        det_id = cur.lastrowid

        for issue in issues:
            conn.execute(
                """INSERT INTO endpoint_stats
                   (detection_id, timestamp, endpoint, error_count, error_pct,
                    p95_latency, req_per_min, severity)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (det_id, datetime.now().isoformat(),
                 issue.get("endpoint", "unknown"),
                 issue.get("error_count", 0),
                 issue.get("error_pct", 0),
                 issue.get("p95_latency_s", 0),
                 issue.get("req_per_min", 0),
                 issue.get("severity", "OK"))
            )
    return det_id


def get_recent_detections(limit: int = 20, source: str = None) -> list:
    """Fetch recent detections, optionally filtered by source."""
    with get_conn() as conn:
        if source:
            rows = conn.execute(
                "SELECT * FROM detections WHERE source=? ORDER BY timestamp DESC LIMIT ?",
                (source, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM detections ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_endpoint_trend(endpoint: str, hours: int = 24) -> list:
    """Get error % trend for a specific endpoint over last N hours."""
    since = datetime.now().isoformat()[:10]  # simple date filter
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT timestamp, error_pct, p95_latency, severity
               FROM endpoint_stats
               WHERE endpoint=? AND timestamp >= ?
               ORDER BY timestamp ASC""",
            (endpoint, since)
        ).fetchall()
    return [dict(r) for r in rows]


def get_summary_stats() -> dict:
    """Aggregate stats for the dashboard KPI cards."""
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
        critical = conn.execute(
            "SELECT COUNT(*) FROM detections WHERE severity='CRITICAL'"
        ).fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM detections WHERE timestamp >= date('now')"
        ).fetchone()[0]
        top_endpoint = conn.execute(
            """SELECT endpoint, COUNT(*) as cnt FROM endpoint_stats
               WHERE severity IN ('CRITICAL','HIGH')
               GROUP BY endpoint ORDER BY cnt DESC LIMIT 1"""
        ).fetchone()
        manual_count = conn.execute(
            "SELECT COUNT(*) FROM detections WHERE source='manual'"
        ).fetchone()[0]

    return {
        "total_detections": total,
        "critical_count": critical,
        "today_count": today,
        "top_failing_endpoint": dict(top_endpoint) if top_endpoint else None,
        "manual_analyses": manual_count,
    }


def get_setting(key: str) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
            (key, str(value))
        )
