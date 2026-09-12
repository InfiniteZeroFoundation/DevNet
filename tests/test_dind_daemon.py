"""Tests for dind/daemon.py — event loop with heartbeat + demo job."""

import json
import sqlite3
import threading

from dincli.dind import jobs as jobs_mod
from dincli.dind.daemon import DaemonLoop
from dincli.dind.state import StateStore
from dincli.sdk.errors import SignerUnavailable
from dincli.sdk.operations.platform import StakeInfo
from dincli.sdk.session import DinSession


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


# ── review finding 3: error persistence must not depend on the failing
# session property (Plans/task-14-15-remediation-plan.md §8) ───────────────


class _NetworkRaisesSession:
    """A session whose ``.network`` property is itself what's broken.

    Simulates a config file that becomes unreadable/invalid before the
    session ever resolves a network — the property raises every time it is
    read, typed or not, so the daemon's error handler cannot rely on a
    second successful read.
    """

    def __init__(self, exc: Exception):
        self._exc = exc

    @property
    def network(self):
        raise self._exc


def test_daemon_loop_din_error_persists_when_network_unavailable(tmp_path):
    """A real DinSession with an invalid network fails read_stake with a
    typed DinError (ConfigError, from the SDK's own normalization) whose
    `.network` property raises again on every access. The failure must still
    land as a `failed` row with a stable code and envelope — omitting
    `meta.network` rather than crashing the loop — and the loop must then
    process the next queued job."""
    db_path = tmp_path / "test.db"
    store = StateStore(db_path)
    jid = store.enqueue("read_stake", {"address": "0x" + "11" * 20})
    jid2 = store.enqueue("demo")
    stop = threading.Event()

    loop = DaemonLoop(
        store, stop, tick_interval=0.01, max_ticks=2,
        session=DinSession(network="bad-network"),
    )
    loop.run()  # must not raise

    row = _fetch_job(db_path, jid)
    assert row["status"] == "failed"
    assert row["last_error"] == "config_error"
    envelope = json.loads(row["result"])
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "config_error"
    assert "network" not in envelope["meta"]

    row2 = _fetch_job(db_path, jid2)
    assert row2["status"] == "done"
    store.close()


def test_daemon_loop_unexpected_error_persists_when_network_unavailable(tmp_path):
    """A handler's unexpected (non-DinError) exception is bounded into
    `internal_error` even when the session's `.network` property itself
    raises an unexpected exception while the handler builds the error
    envelope. No second, unhandled resolution failure may escape, and the
    loop must still process the next queued job."""

    def boom_handler(job, ctx):
        raise RuntimeError("handler blew up")

    jobs_mod.JOB_HANDLERS["boom_network"] = boom_handler
    db_path = tmp_path / "test.db"
    store = StateStore(db_path)
    try:
        jid = store.enqueue("boom_network")
        jid2 = store.enqueue("demo")
        stop = threading.Event()

        session = _NetworkRaisesSession(RuntimeError("network probe exploded"))
        loop = DaemonLoop(store, stop, tick_interval=0.01, max_ticks=2, session=session)
        loop.run()  # must not raise

        row = _fetch_job(db_path, jid)
        assert row["status"] == "failed"
        assert row["last_error"] == "internal_error"
        envelope = json.loads(row["result"])
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "internal_error"
        assert "network" not in envelope["meta"]

        row2 = _fetch_job(db_path, jid2)
        assert row2["status"] == "done"
    finally:
        del jobs_mod.JOB_HANDLERS["boom_network"]
        store.close()


def test_daemon_loop_unserializable_result_fails_job(tmp_path):
    """A handler returning a value `json.dumps()` cannot serialize must not
    kill the loop — result serialization sits outside the handler's own
    try/except today, so this boundary needs its own protection. The job
    must be recorded as failed, and the loop must still process the next
    queued job."""

    def unserializable_handler(job, ctx):
        return {"not_json": {1, 2, 3}}  # a set is not JSON-serializable

    jobs_mod.JOB_HANDLERS["unserializable"] = unserializable_handler
    db_path = tmp_path / "test.db"
    store = StateStore(db_path)
    try:
        jid = store.enqueue("unserializable")
        jid2 = store.enqueue("demo")
        stop = threading.Event()

        loop = DaemonLoop(
            store, stop, tick_interval=0.01, max_ticks=2, session=_FakeSession()
        )
        loop.run()  # must not raise

        row = _fetch_job(db_path, jid)
        assert row["status"] == "failed"
        assert row["last_error"] == "internal_error"
        envelope = json.loads(row["result"])
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "internal_error"

        row2 = _fetch_job(db_path, jid2)
        assert row2["status"] == "done"
    finally:
        del jobs_mod.JOB_HANDLERS["unserializable"]
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
