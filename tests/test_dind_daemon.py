"""Tests for dind/daemon.py — event loop with heartbeat + demo job."""

import threading
from dincli.dind.daemon import DaemonLoop
from dincli.dind.state import StateStore


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
