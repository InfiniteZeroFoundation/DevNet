"""Tests for dind/process.py — PID file read/write/stale detection.

Also covers the BL-19 interaction between the lock and the PID file at the
CLI level: a crashed daemon's stale PID file must still be cleaned up by
`start`, and `stop`/`status` must trust the lock over the PID file.
"""

import os
import signal
import subprocess
import sys
import threading

from typer.testing import CliRunner

from dincli.dind import control
from dincli.dind.lock import acquire_state_lock, release_state_lock
from dincli.dind.main import app
from dincli.dind.paths import StateDirs
from dincli.dind.process import (
    is_process_running,
    read_pid,
    remove_pid,
    send_signal,
    write_pid,
)

runner = CliRunner()


def test_write_read_remove_pid(tmp_path):
    pid_path = tmp_path / "dind.pid"
    write_pid(pid_path)

    pid = read_pid(pid_path)
    assert pid == os.getpid()

    remove_pid(pid_path)
    assert not pid_path.exists()


def test_read_pid_none_when_missing(tmp_path):
    assert read_pid(tmp_path / "nonexistent") is None


def test_read_pid_none_when_empty(tmp_path):
    pid_path = tmp_path / "empty.pid"
    pid_path.write_text("")
    assert read_pid(pid_path) is None


def test_read_pid_none_when_garbage(tmp_path):
    pid_path = tmp_path / "garbage.pid"
    pid_path.write_text("abc")
    assert read_pid(pid_path) is None


def test_is_process_running_self():
    assert is_process_running(os.getpid()) is True


def test_is_process_running_dead():
    import subprocess

    proc = subprocess.Popen(["true"])
    proc.wait()
    assert is_process_running(proc.pid) is False


def test_is_process_running_nonexistent():
    assert is_process_running(99999999) is False


def test_remove_pid_missing_is_noop(tmp_path):
    remove_pid(tmp_path / "nonexistent")


def _reset_dincli_logger():
    import logging

    logger = logging.getLogger("dincli")
    logger.handlers.clear()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def test_start_cleans_stale_pid_and_proceeds(tmp_path, monkeypatch):
    """BL-19 regression: a crashed daemon leaves a dead PID file and a
    released lock. The next start must acquire, clean up the stale PID,
    and proceed exactly as before the lock existed."""
    monkeypatch.setenv("DIN_DIND_MAX_TICKS", "1")
    paths = StateDirs(tmp_path)

    dead_proc = subprocess.Popen(["true"])
    dead_proc.wait()
    paths.pid_path.write_text(str(dead_proc.pid))

    try:
        result = runner.invoke(
            app, ["start", "--state-dir", str(tmp_path), "--health-port", "0"]
        )
        assert result.exit_code == 0, result.output
        # The PID file this invocation wrote is cleaned up on the way out.
        assert not paths.pid_path.exists()
    finally:
        _reset_dincli_logger()


def test_stop_refuses_to_signal_live_process_when_lock_free(tmp_path):
    """A free lock is authoritative evidence no daemon owns this state dir,
    even when the PID file names a process that happens to be alive."""
    paths = StateDirs(tmp_path)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        paths.pid_path.write_text(str(proc.pid))

        result = runner.invoke(app, ["stop", "--state-dir", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert "stale" in result.output
        assert not paths.pid_path.exists()
        # stop() must not have signaled the unrelated live process.
        assert proc.poll() is None
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_status_reports_stopped_when_lock_free_even_if_pid_alive(tmp_path):
    paths = StateDirs(tmp_path)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        paths.pid_path.write_text(str(proc.pid))

        result = runner.invoke(app, ["status", "--state-dir", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert "stale PID" in result.output
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_status_reports_lock_held_but_unverified_without_control_endpoint(tmp_path):
    """review finding 4: holding the lock proves SOME process owns this
    state dir, not that it is the PID on file. Without a control endpoint
    to verify identity against (no descriptor at all here — as an older
    daemon would leave, or one still starting), status must not claim
    "running"."""
    paths = StateDirs(tmp_path)
    paths.pid_path.write_text(str(os.getpid()))
    lock_fd = acquire_state_lock(paths.lock_path)
    try:
        result = runner.invoke(app, ["status", "--state-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "dind is running" not in result.output
        assert "could not be verified" in result.output
    finally:
        release_state_lock(lock_fd)


def test_status_reports_verified_running_with_control_endpoint(tmp_path):
    """With a live control endpoint whose instance id matches the
    descriptor, status can and does confirm "running"."""
    paths = StateDirs(tmp_path)
    paths.pid_path.write_text(str(os.getpid()))
    lock_fd = acquire_state_lock(paths.lock_path)
    socket_path = control.socket_path_for(tmp_path)
    server = control.ControlServer(socket_path, "the-instance", threading.Event())
    server.start()
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    control.write_descriptor(
        paths.control_path,
        control.ControlDescriptor(
            instance_id="the-instance", socket_path=str(socket_path), pid=os.getpid()
        ),
    )
    try:
        result = runner.invoke(app, ["status", "--state-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "dind is running" in result.output
    finally:
        server.shutdown()
        thread.join(timeout=5)
        release_state_lock(lock_fd)


# ── review finding 4: stop/start target a verified daemon, not a bare PID
# (Plans/task-14-15-remediation-plan.md §9) ─────────────────────────────────


def test_stop_signals_verified_daemon_via_control_channel(tmp_path):
    """An ordinary stop against a real control endpoint: the request is
    accepted, the daemon's stop_event is set, and once the lock is released
    (simulating the daemon's own shutdown completing) `stop` reports
    success — all without ever calling os.kill."""
    paths = StateDirs(tmp_path)
    paths.pid_path.write_text(str(os.getpid()))
    lock_fd = acquire_state_lock(paths.lock_path)

    stop_event = threading.Event()
    socket_path = control.socket_path_for(tmp_path)
    server = control.ControlServer(socket_path, "the-instance", stop_event)
    server.start()
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    control.write_descriptor(
        paths.control_path,
        control.ControlDescriptor(
            instance_id="the-instance", socket_path=str(socket_path), pid=os.getpid()
        ),
    )

    released = threading.Event()

    def _release_lock_once_stopped():
        # Stands in for the real daemon's own shutdown: once it observes
        # stop_event, it eventually exits and the kernel releases its flock.
        if stop_event.wait(timeout=5):
            release_state_lock(lock_fd)
            released.set()

    watcher = threading.Thread(target=_release_lock_once_stopped, daemon=True)
    watcher.start()
    try:
        result = runner.invoke(
            app, ["stop", "--state-dir", str(tmp_path), "--timeout", "5"]
        )
        assert result.exit_code == 0, result.output
        assert "Stop acknowledged" in result.output
        assert "dind stopped." in result.output
        assert stop_event.is_set()
    finally:
        watcher.join(timeout=5)
        server.shutdown()
        thread.join(timeout=5)
        if not released.is_set():
            release_state_lock(lock_fd)


def test_stop_rejects_replacement_instance_and_leaves_it_running(tmp_path):
    """The exact race in review finding 4: `stop` is targeting a descriptor
    that names an instance which is no longer the one holding the lock — a
    replacement is running in its place. The replacement's stop_event must
    stay unset, and `stop` must report the mismatch rather than silently
    doing nothing or acting on the wrong instance."""
    paths = StateDirs(tmp_path)
    paths.pid_path.write_text(str(os.getpid()))
    lock_fd = acquire_state_lock(paths.lock_path)

    replacement_stop_event = threading.Event()
    socket_path = control.socket_path_for(tmp_path)
    replacement_server = control.ControlServer(
        socket_path, "replacement-instance", replacement_stop_event
    )
    replacement_server.start()
    thread = threading.Thread(target=replacement_server.run, daemon=True)
    thread.start()

    # The descriptor on disk still names the OLD instance the stop command
    # read before the replacement took over.
    control.write_descriptor(
        paths.control_path,
        control.ControlDescriptor(
            instance_id="stale-old-instance", socket_path=str(socket_path), pid=os.getpid()
        ),
    )
    try:
        result = runner.invoke(app, ["stop", "--state-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "different dind instance" in result.output
        assert not replacement_stop_event.is_set()

        # The replacement is provably still alive and correctly addressable.
        response = control.send_command(socket_path, "replacement-instance", "ping")
        assert response["status"] == "ok"
    finally:
        replacement_server.shutdown()
        thread.join(timeout=5)
        release_state_lock(lock_fd)


def test_stop_reports_clearly_when_control_endpoint_unreachable(tmp_path):
    """Lock held, descriptor present, but nothing is listening at the
    socket (e.g. the daemon died between writing the descriptor and
    binding, or without cleaning up). Must report the condition, never
    fall back to signalling the PID."""
    paths = StateDirs(tmp_path)
    paths.pid_path.write_text(str(os.getpid()))
    lock_fd = acquire_state_lock(paths.lock_path)
    control.write_descriptor(
        paths.control_path,
        control.ControlDescriptor(
            instance_id="ghost-instance",
            socket_path=str(tmp_path / "nothing-here.sock"),
            pid=os.getpid(),
        ),
    )
    try:
        result = runner.invoke(app, ["stop", "--state-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "did not respond" in result.output
    finally:
        release_state_lock(lock_fd)


def test_start_not_blocked_by_stale_pid_reused_by_unrelated_live_process(tmp_path, monkeypatch):
    """review finding 4's second defect: once start() holds the exclusive
    lock, that alone proves no other dind owns this state dir. A leftover
    PID file naming a live-but-unrelated process must not block startup —
    and that process must never be signalled."""
    monkeypatch.setenv("DIN_DIND_MAX_TICKS", "1")
    paths = StateDirs(tmp_path)

    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        paths.pid_path.write_text(str(unrelated.pid))

        result = runner.invoke(
            app, ["start", "--state-dir", str(tmp_path), "--health-port", "0"]
        )
        assert result.exit_code == 0, result.output
        assert "already running" not in result.output

        # The unrelated process was never touched.
        assert unrelated.poll() is None
    finally:
        unrelated.kill()
        unrelated.wait(timeout=10)
        _reset_dincli_logger()
