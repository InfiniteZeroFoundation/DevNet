"""Tests for dind/process.py — PID file read/write/stale detection."""

import os
import signal

from dincli.dind.process import (
    is_process_running,
    read_pid,
    remove_pid,
    send_signal,
    write_pid,
)


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
