"""Tests for dind/daemon.py — event loop with heartbeat + demo job."""

import json
import sqlite3
import threading

from dincli.dind import jobs as jobs_mod
from dincli.dind.daemon import DaemonLoop
from dincli.dind.state import StateStore
from dincli.sdk.errors import SignerUnavailable
from dincli.sdk.operations.platform import StakeInfo


def _fetch_job(db_path, job_id):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row)


class _FakeSession:
    network = "local"


def test_daemon_loop_heartbeat_advances(tmp_path):
    store = StateStore(tmp_path / "test.db")
    stop = threading.Event()

    loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=3)
    loop.run()

    last_tick = store.get_meta("last_tick")
    assert last_tick is not None
    store.close()


def test_daemon_loop_runs_demo_job(tmp_path):
    store = StateStore(tmp_path / "test.db")
    store.enqueue("demo")
    stop = threading.Event()

    loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=3)
    loop.run()

    last_success = store.get_meta("last_success")
    assert last_success is not None

    counts = store.get_job_counts()
    assert counts["pending"] == 0
    assert counts["running"] == 0
    store.close()


def test_daemon_loop_stops_on_event(tmp_path):
    store = StateStore(tmp_path / "test.db")
    stop = threading.Event()
    stop.set()

    loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=1000)
    loop.run()

    assert loop.tick_count == 0
    store.close()


def test_daemon_loop_unknown_job_type_fails(tmp_path):
    store = StateStore(tmp_path / "test.db")
    store.enqueue("nonexistent_handler")
    stop = threading.Event()

    loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=3)
    loop.run()

    row = store.claim_next()
    assert row is None

    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    failed = conn.execute(
        "SELECT * FROM jobs WHERE type = 'nonexistent_handler' AND status = 'failed'"
    ).fetchone()
    conn.close()
    assert failed is not None
    store.close()


# ── JobContext / real job type (task_110926_15, §3.7) ──────────────────────


def test_daemon_loop_read_stake_success_envelope(tmp_path, monkeypatch):
    address = "0x" + "ab" * 20
    stake = StakeInfo(
        network="local",
        address=address,
        stake_wei=123456789012345678901234,
        stake_contract="0x" + "cd" * 20,
    )
    monkeypatch.setattr(jobs_mod, "get_stake", lambda session, address=None: stake)

    db_path = tmp_path / "test.db"
    store = StateStore(db_path)
    jid = store.enqueue("read_stake", {"address": address})
    stop = threading.Event()

    loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=1, session=_FakeSession())
    loop.run()

    row = _fetch_job(db_path, jid)
    assert row["status"] == "done"
    envelope = json.loads(row["result"])
    assert envelope["status"] == "ok"
    assert envelope["data"]["stake_wei"] == "123456789012345678901234"
    assert envelope["meta"]["network"] == "local"
    store.close()


def test_daemon_loop_din_error_persists_stable_code_and_envelope(tmp_path, monkeypatch):
    """A SignerUnavailable from get_stake (no address, no signer) must land as
    `failed` with `last_error` set to the CODE, never str(e) — the daemon's
    retry policy keys off the stable string, not the message."""
    err = SignerUnavailable("No password available for wallet 'default'.")

    def raise_signer_unavailable(session, address=None):
        raise err

    monkeypatch.setattr(jobs_mod, "get_stake", raise_signer_unavailable)

    db_path = tmp_path / "test.db"
    store = StateStore(db_path)
    jid = store.enqueue("read_stake")
    stop = threading.Event()

    loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=1, session=_FakeSession())
    loop.run()

    row = _fetch_job(db_path, jid)
    assert row["status"] == "failed"
    assert row["last_error"] == "signer_unavailable"
    envelope = json.loads(row["result"])
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "signer_unavailable"
    store.close()


def test_daemon_loop_generic_exception_bounded_internal_error(tmp_path):
    """A handler raising a plain exception must not leak an unbounded
    traceback into the DB — it gets a distinct, bounded internal-error
    envelope instead of the DinError's own code/message."""

    def boom_handler(job, ctx):
        raise RuntimeError("x" * 5000)

    jobs_mod.JOB_HANDLERS["boom"] = boom_handler
    db_path = tmp_path / "test.db"
    store = StateStore(db_path)
    try:
        jid = store.enqueue("boom")
        stop = threading.Event()

        loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=1, session=_FakeSession())
        loop.run()

        row = _fetch_job(db_path, jid)
        assert row["status"] == "failed"
        assert row["last_error"] == "internal_error"
        envelope = json.loads(row["result"])
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "internal_error"
        assert len(envelope["error"]["message"]) < 5000
    finally:
        del jobs_mod.JOB_HANDLERS["boom"]
        store.close()


def test_daemon_loop_no_session_builds_bare_default(tmp_path):
    """DaemonLoop(session=None) must still run a job type that never touches
    the session (demo) — proving the bare DinSession() default is safe."""
    store = StateStore(tmp_path / "test.db")
    store.enqueue("demo")
    stop = threading.Event()

    loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=1)
    loop.run()

    assert loop._ctx.session is not None
    counts = store.get_job_counts()
    assert counts["pending"] == 0
    store.close()
