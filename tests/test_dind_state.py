"""Tests for dind/state.py — SQLite enqueue/claim/complete/fail/retention."""

import sqlite3
from datetime import datetime, timezone

from dincli.dind.state import StateStore


def test_enqueue_claim_complete(tmp_path):
    store = StateStore(tmp_path / "test.db")
    jid = store.enqueue("demo", {"x": 1})
    assert jid == 1

    row = store.claim_next()
    assert row is not None
    assert row["type"] == "demo"
    assert row["status"] == "running"
    assert row["attempts"] == 1

    store.complete_job(jid)

    row2 = store.claim_next()
    assert row2 is None

    store.close()


def test_enqueue_fail(tmp_path):
    store = StateStore(tmp_path / "test.db")
    jid = store.enqueue("fail_job")
    row = store.claim_next()
    assert row["id"] == jid
    assert row["status"] == "running"

    store.fail_job(jid, "something went wrong")

    row = store.claim_next()
    assert row is None

    store.close()


def test_reset_running_jobs(tmp_path):
    store = StateStore(tmp_path / "test.db")
    jid = store.enqueue("demo")
    store.claim_next()

    counts = store.get_job_counts()
    assert counts["running"] == 1

    store.reset_running_jobs()

    counts = store.get_job_counts()
    assert counts["running"] == 0
    assert counts["pending"] == 1

    row = store.claim_next()
    assert row["last_error"] == "interrupted@shutdown"
    assert row["attempts"] == 2

    store.close()


def test_meta_round_trip(tmp_path):
    store = StateStore(tmp_path / "test.db")
    store.set_meta("key1", "val1")
    assert store.get_meta("key1") == "val1"
    assert store.get_meta("nonexistent") is None

    store.set_meta("key1", "val2")
    assert store.get_meta("key1") == "val2"
    store.close()


def test_job_counts(tmp_path):
    store = StateStore(tmp_path / "test.db")
    store.enqueue("a")
    store.enqueue("b")
    counts = store.get_job_counts()
    assert counts["pending"] == 2
    assert counts["running"] == 0
    assert counts["failed"] == 0
    store.close()


def test_retention_caps_history(tmp_path):
    store = StateStore(tmp_path / "test.db", retention_limit=3)
    for i in range(10):
        jid = store.enqueue(f"job_{i}")
        store.claim_next()
        store.complete_job(jid)

    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    total = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE status IN ('done', 'failed')"
    ).fetchone()[0]
    conn.close()
    assert total <= 3

    store.close()


def test_restart_recovery(tmp_path):
    store = StateStore(tmp_path / "test.db")
    store.enqueue("demo")
    store.claim_next()
    store.close()

    store2 = StateStore(tmp_path / "test.db")
    counts = store2.get_job_counts()
    assert counts["running"] == 1
    store2.reset_running_jobs()
    counts = store2.get_job_counts()
    assert counts["running"] == 0
    assert counts["pending"] == 1
    store2.close()


# ── result column (task_110926_15, §3.7) ────────────────────────────────────


def test_complete_job_persists_result(tmp_path):
    store = StateStore(tmp_path / "test.db")
    jid = store.enqueue("demo")
    store.claim_next()

    store.complete_job(jid, result='{"status": "ok"}')

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    conn.close()
    assert row["status"] == "done"
    assert row["result"] == '{"status": "ok"}'
    store.close()


def test_complete_job_without_result_leaves_it_null(tmp_path):
    store = StateStore(tmp_path / "test.db")
    jid = store.enqueue("demo")
    store.claim_next()
    store.complete_job(jid)

    row = store.claim_next()
    assert row is None
    store.close()


def test_fail_job_persists_result_alongside_last_error(tmp_path):
    store = StateStore(tmp_path / "test.db")
    jid = store.enqueue("demo")
    store.claim_next()

    store.fail_job(jid, "signer_unavailable", result='{"status": "error"}')

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    conn.close()
    assert row["status"] == "failed"
    assert row["last_error"] == "signer_unavailable"
    assert row["result"] == '{"status": "error"}'
    store.close()


def test_result_survives_retention_cap(tmp_path):
    """Results age out through the existing retention cap for free, since
    they live on the job row rather than in daemon_meta."""
    store = StateStore(tmp_path / "test.db", retention_limit=1)
    jid1 = store.enqueue("demo")
    store.claim_next()
    store.complete_job(jid1, result='{"n": 1}')

    jid2 = store.enqueue("demo")
    store.claim_next()
    store.complete_job(jid2, result='{"n": 2}')

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM jobs WHERE status = 'done'").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["result"] == '{"n": 2}'
    store.close()


def test_initialize_new_database_is_a_noop(tmp_path):
    """A brand-new DB already has `result` via SCHEMA; initialize() must not
    fail or duplicate it."""
    store = StateStore(tmp_path / "test.db")
    store.initialize()

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    columns = [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]
    conn.close()
    assert columns.count("result") == 1
    store.close()


def test_initialize_migrates_legacy_database_without_result_column(tmp_path):
    """Migration guard against a hand-built LEGACY schema — opening a
    new-schema DB twice would test nothing."""
    db_path = tmp_path / "legacy.db"
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            payload     TEXT    NOT NULL DEFAULT '{}',
            attempts    INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL,
            last_error  TEXT
        );
        CREATE TABLE daemon_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO jobs(type, status, payload, created_at, updated_at) "
        "VALUES ('demo', 'done', '{}', ?, ?)",
        (now, now),
    )
    conn.commit()
    conn.close()

    columns_before = {
        row[1]
        for row in sqlite3.connect(str(db_path)).execute("PRAGMA table_info(jobs)")
    }
    assert "result" not in columns_before

    store = StateStore(db_path)
    store.initialize()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    columns_after = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    surviving = conn.execute("SELECT * FROM jobs WHERE type = 'demo'").fetchone()
    conn.close()

    assert "result" in columns_after
    assert surviving is not None
    assert surviving["status"] == "done"
    assert surviving["result"] is None
    store.close()
