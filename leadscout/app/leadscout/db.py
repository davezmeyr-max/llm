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
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# Columns added after 0.1.0; created on startup when missing.
MIGRATIONS = {
    "submitted_by": "TEXT NOT NULL DEFAULT ''",
    "batch": "TEXT NOT NULL DEFAULT ''",
    "started_at": "TEXT",
    "finished_at": "TEXT",
    "current_step": "TEXT NOT NULL DEFAULT ''",
}

MAX_ATTEMPTS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


class LeadStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(leads)")}
        for name, ddl in MIGRATIONS.items():
            if name not in cols:
                self._conn.execute(f"ALTER TABLE leads ADD COLUMN {name} {ddl}")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_batch ON leads(batch, status)")
        self._lock = threading.Lock()

    # ------------------------------------------------------------ writes

    def add(self, company: str, hints: str = "", submitted_by: str = "", batch: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO leads (company, hints, submitted_by, batch, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (company.strip(), hints.strip(), submitted_by.strip().lower(), batch.strip(), _now(), _now()),
            )
            return int(cur.lastrowid)

    def claim_next(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM leads WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return None
            now = _now()
            self._conn.execute(
                "UPDATE leads SET status='running', attempts=attempts+1, started_at=?, finished_at=NULL, "
                "current_step='starting', updated_at=? WHERE id=?",
                (now, now, row["id"]),
            )
            return dict(row) | {"attempts": row["attempts"] + 1}

    def set_step(self, lead_id: int, step: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE leads SET current_step=?, updated_at=? WHERE id=? AND status='running'",
                (step[:300], _now(), lead_id),
            )

    def complete(self, lead_id: int, profile: dict[str, Any], trace: list[dict[str, Any]]) -> None:
        with self._lock:
            now = _now()
            self._conn.execute(
                "UPDATE leads SET status='done', profile=?, trace=?, error=NULL, current_step='', "
                "finished_at=?, updated_at=? WHERE id=?",
                (json.dumps(profile), json.dumps(trace), now, now, lead_id),
            )

    def fail(self, lead_id: int, error: str, attempts: int) -> None:
        status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
        with self._lock:
            now = _now()
            self._conn.execute(
                "UPDATE leads SET status=?, error=?, current_step='', finished_at=?, updated_at=? WHERE id=?",
                (status, error[:2000], now if status == "failed" else None, now, lead_id),
            )

    def requeue_running(self) -> int:
        """On worker start: anything left 'running' was interrupted (e.g. GPU box destroyed)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE leads SET status='queued', current_step='', updated_at=? WHERE status='running'", (_now(),)
            )
            return cur.rowcount

    def retry(self, lead_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE leads SET status='queued', attempts=0, error=NULL, updated_at=? "
                "WHERE id=? AND status IN ('failed','done')",
                (_now(), lead_id),
            )
            return cur.rowcount == 1

    # ------------------------------------------------------------ reads

    def get(self, lead_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return self._decode(row) if row else None

    def list(self, status: str | None = None, limit: int = 100, batch: str | None = None) -> list[dict[str, Any]]:
        where, args = [], []
        if status:
            where.append("status=?")
            args.append(status)
        if batch:
            where.append("batch=?")
            args.append(batch)
        sql = "SELECT * FROM leads" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
        rows = self._conn.execute(sql, (*args, limit)).fetchall()
        return [self._decode(r) for r in rows]

    def counts(self, batch: str | None = None) -> dict[str, int]:
        if batch:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM leads WHERE batch=? GROUP BY status", (batch,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def batches(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT batch, MIN(created_at) AS created_at, COUNT(*) AS total, "
            "SUM(status='done') AS done, SUM(status='failed') AS failed, "
            "SUM(status='queued') AS queued, SUM(status='running') AS running "
            "FROM leads WHERE batch != '' GROUP BY batch ORDER BY MAX(id) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def running(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, company, current_step, started_at FROM leads WHERE status='running' ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def durations(self, limit: int = 50) -> list[float]:
        """Seconds per finished lead, most recent first."""
        rows = self._conn.execute(
            "SELECT started_at, finished_at FROM leads WHERE status='done' AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            a, b = _parse(r["started_at"]), _parse(r["finished_at"])
            if a and b and b >= a:
                out.append((b - a).total_seconds())
        return out

    def finished_since(self, since_iso: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM leads WHERE status='done' AND finished_at >= ?", (since_iso,)
        ).fetchone()
        return int(row["n"])

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str | None) -> None:
        with self._lock:
            if value is None:
                self._conn.execute("DELETE FROM meta WHERE key=?", (key,))
            else:
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ("profile", "trace"):
            if d.get(key):
                d[key] = json.loads(d[key])
        return d
