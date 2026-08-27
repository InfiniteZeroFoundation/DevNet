"""SQLite state store — jobs queue + daemon metadata.

WAL mode for safe concurrency. Per-thread connections. Retention cap on
done/failed history from day one.

Tables:
  jobs (id, type, status, payload, attempts, created_at, updated_at, last_error)
  daemon_meta (key, value)
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    payload     TEXT    NOT NULL DEFAULT '{}',
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    last_error  TEXT
);

CREATE TABLE IF NOT EXISTS daemon_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class StateStore:
    def __init__(self, db_path: Path, retention_limit: int = 1000):
        self.db_path = db_path
        self.retention_limit = retention_limit
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA)
            self._local.conn = conn
        return self._local.conn

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ── daemon_meta ──────────────────────────────────────────────────────

    def set_meta(self, key: str, value: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO daemon_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()

    def get_meta(self, key: str) -> str | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM daemon_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    # ── jobs ─────────────────────────────────────────────────────────────

    def enqueue(self, job_type: str, payload: dict | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO jobs(type, status, payload, created_at, updated_at) "
            "VALUES (?, 'pending', ?, ?, ?)",
            (job_type, json.dumps(payload or {}), now, now),
        )
        conn.commit()
        return cursor.lastrowid

    def claim_next(self) -> dict | None:
        conn = self._get_conn()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE jobs SET status = 'running', updated_at = ?, "
            "attempts = attempts + 1 WHERE id = ?",
            (now, row["id"]),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (row["id"],)
        ).fetchone()
        return dict(row)

    def complete_job(self, job_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE jobs SET status = 'done', updated_at = ? WHERE id = ?",
            (now, job_id),
        )
        conn.commit()
        self._retain()

    def fail_job(self, job_id: int, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE jobs SET status = 'failed', updated_at = ?, last_error = ? "
            "WHERE id = ?",
            (now, error, job_id),
        )
        conn.commit()
        self._retain()

    def reset_running_jobs(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE jobs SET status = 'pending', updated_at = ?, "
            "last_error = 'interrupted@shutdown' "
            "WHERE status = 'running'",
            (now,),
        )
        conn.commit()

    def get_job_counts(self) -> dict:
        conn = self._get_conn()
        queries = {
            "pending": "WHERE status = 'pending'",
            "running": "WHERE status = 'running'",
            "failed": "WHERE status = 'failed'",
        }
        result = {}
        for key, clause in queries.items():
            row = conn.execute(
                f"SELECT COUNT(*) as c FROM jobs {clause}"
            ).fetchone()
            result[key] = row["c"]
        return result

    # ── retention ────────────────────────────────────────────────────────

    def _retain(self) -> None:
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COUNT(*) as c FROM jobs WHERE status IN ('done', 'failed')"
        ).fetchone()["c"]
        if total > self.retention_limit:
            excess = total - self.retention_limit
            conn.execute(
                "DELETE FROM jobs WHERE id IN ("
                "  SELECT id FROM jobs WHERE status IN ('done', 'failed') "
                "  ORDER BY updated_at ASC LIMIT ?"
                ")",
                (excess,),
            )
            conn.commit()
