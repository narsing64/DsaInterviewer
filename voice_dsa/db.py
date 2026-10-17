"""SQLite persistence for finished interviews (progress tracking)."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "sessions.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY, problem_id TEXT, problem_title TEXT, topic TEXT,
            difficulty TEXT, total_score INTEGER, verdict TEXT, hints_used INTEGER,
            duration_sec INTEGER, transcript TEXT, scores TEXT, report TEXT, created_at TEXT)""")


def save_session(state: dict) -> None:
    p, s = state["problem"], state["scores"] or {}
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            state["id"], p["id"], p["title"], p["topic"], p["difficulty"], s.get("total", 0),
            s.get("verdict", "Unknown"), state["hints"], state["duration_sec"],
            json.dumps(state["transcript"]), json.dumps(s), json.dumps(state.get("report") or {}),
            datetime.now().isoformat(timespec="seconds")))


def history() -> list:
    with _conn() as c:
        rows = c.execute("""SELECT session_id, problem_title, topic, difficulty, total_score, verdict,
                            hints_used, duration_sec, created_at FROM sessions ORDER BY created_at DESC""").fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    for k in ("transcript", "scores", "report"):
        d[k] = json.loads(d[k] or "null")
    return d


def stats() -> dict:
    rows = history()
    if not rows:
        return {"total": 0, "average": 0, "best": 0, "topics": {}, "recent": []}
    topics: dict = {}
    for r in rows:
        t = topics.setdefault(r["topic"], {"count": 0, "sum": 0})
        t["count"] += 1
        t["sum"] += r["total_score"]
    return {
        "total": len(rows),
        "average": round(sum(r["total_score"] for r in rows) / len(rows), 1),
        "best": max(r["total_score"] for r in rows),
        "topics": {k: {"count": v["count"], "average": round(v["sum"] / v["count"], 1)} for k, v in topics.items()},
        "recent": list(reversed(rows[:10])),
    }
