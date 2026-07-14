"""Tests for dind/state.py — SQLite enqueue/claim/complete/fail/retention."""


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
