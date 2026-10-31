"""SQLite-backed lead queue. One table; status moves queued -> running -> done | failed."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company     TEXT NOT NULL,
    hints       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'queued',
    attempts    INTEGER NOT NULL DEFAULT 0,
    profile     TEXT,
    trace       TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status, id);
"""

MAX_ATTEMPTS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LeadStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(leads)")}
        if "submitted_by" not in cols:  # migration from 0.1.2
            self._conn.execute("ALTER TABLE leads ADD COLUMN submitted_by TEXT NOT NULL DEFAULT ''")
        self._lock = threading.Lock()

    def add(self, company: str, hints: str = "", submitted_by: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO leads (company, hints, submitted_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (company.strip(), hints.strip(), submitted_by.strip().lower(), _now(), _now()),
            )
            return int(cur.lastrowid)

    def claim_next(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM leads WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE leads SET status='running', attempts=attempts+1, updated_at=? WHERE id=?",
                (_now(), row["id"]),
            )
            return dict(row) | {"attempts": row["attempts"] + 1}

    def complete(self, lead_id: int, profile: dict[str, Any], trace: list[dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE leads SET status='done', profile=?, trace=?, error=NULL, updated_at=? WHERE id=?",
                (json.dumps(profile), json.dumps(trace), _now(), lead_id),
            )

    def fail(self, lead_id: int, error: str, attempts: int) -> None:
        status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
        with self._lock:
            self._conn.execute(
                "UPDATE leads SET status=?, error=?, updated_at=? WHERE id=?",
                (status, error[:2000], _now(), lead_id),
            )

    def requeue_running(self) -> int:
        """On worker start: anything left 'running' was interrupted (e.g. GPU box destroyed)."""
        with self._lock:
            cur = self._conn.execute("UPDATE leads SET status='queued', updated_at=? WHERE status='running'", (_now(),))
            return cur.rowcount

    def retry(self, lead_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE leads SET status='queued', attempts=0, error=NULL, updated_at=? "
                "WHERE id=? AND status IN ('failed','done')",
                (_now(), lead_id),
            )
            return cur.rowcount == 1

    def get(self, lead_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return self._decode(row) if row else None

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM leads WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode(r) for r in rows]

    def counts(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ("profile", "trace"):
            if d.get(key):
                d[key] = json.loads(d[key])
        return d
