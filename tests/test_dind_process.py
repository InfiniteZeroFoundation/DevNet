"""Tests for dind/process.py — PID file read/write/stale detection.

Also covers the BL-19 interaction between the lock and the PID file at the
CLI level: a crashed daemon's stale PID file must still be cleaned up by
`start`, and `stop`/`status` must trust the lock over the PID file.
"""

import os
import signal
import subprocess
import sys

from typer.testing import CliRunner

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


def test_status_reports_running_when_lock_held(tmp_path):
    paths = StateDirs(tmp_path)
    paths.pid_path.write_text(str(os.getpid()))
    lock_fd = acquire_state_lock(paths.lock_path)
    try:
        result = runner.invoke(app, ["status", "--state-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "dind is running" in result.output
    finally:
        release_state_lock(lock_fd)
