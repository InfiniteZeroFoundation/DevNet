"""Tests for dind/lock.py — flock-based atomic start (BL-19).

Includes the real race: two `dind start` subprocesses, released together,
where exactly one must win.
"""

import errno
import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from dincli.dind.lock import acquire_state_lock, is_locked, release_state_lock


def test_acquire_then_release_roundtrip(tmp_path):
    lock_path = tmp_path / "dind.lock"
    fd = acquire_state_lock(lock_path)
    assert fd is not None
    release_state_lock(fd)


def test_second_acquire_blocked_while_first_held(tmp_path):
    lock_path = tmp_path / "dind.lock"
    fd1 = acquire_state_lock(lock_path)
    assert fd1 is not None
    try:
        assert acquire_state_lock(lock_path) is None
    finally:
        release_state_lock(fd1)

    # Free again after release.
    fd2 = acquire_state_lock(lock_path)
    assert fd2 is not None
    release_state_lock(fd2)


def test_is_locked_reflects_holder(tmp_path):
    lock_path = tmp_path / "dind.lock"
    assert is_locked(lock_path) is False

    fd = acquire_state_lock(lock_path)
    assert is_locked(lock_path) is True

    release_state_lock(fd)
    assert is_locked(lock_path) is False


def test_non_contention_errors_propagate(tmp_path, monkeypatch):
    lock_path = tmp_path / "dind.lock"

    from dincli.dind import lock as lock_module

    real_flock = lock_module.fcntl.flock

    def fake_flock(fd, op):
        if op & lock_module.fcntl.LOCK_EX:
            raise OSError(errno.EROFS, "read-only filesystem")
        return real_flock(fd, op)

    monkeypatch.setattr(lock_module.fcntl, "flock", fake_flock)

    with pytest.raises(OSError) as excinfo:
        acquire_state_lock(lock_path)
    assert excinfo.value.errno == errno.EROFS

    # The fd from the failed attempt must have been closed, not leaked: a
    # real acquire against the same path must still succeed afterwards.
    monkeypatch.setattr(lock_module.fcntl, "flock", real_flock)
    fd = acquire_state_lock(lock_path)
    assert fd is not None
    release_state_lock(fd)


def test_lock_released_on_hard_kill(tmp_path):
    lock_path = tmp_path / "dind.lock"
    read_fd, write_fd = os.pipe()

    script = (
        "import os\n"
        "from dincli.dind.lock import acquire_state_lock\n"
        f"acquire_state_lock({str(lock_path)!r})\n"
        f"os.write({write_fd}, b'x')\n"
        "import time\n"
        "time.sleep(30)\n"
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        pass_fds=(write_fd,),
    )
    os.close(write_fd)
    try:
        ready = os.read(read_fd, 1)
        assert ready == b"x"

        proc.kill()  # SIGKILL — no chance for the child to clean up
        proc.wait(timeout=10)

        fd = acquire_state_lock(lock_path)
        assert fd is not None, "lock was not released after SIGKILL"
        release_state_lock(fd)
    finally:
        os.close(read_fd)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


# ── the real race ───────────────────────────────────────────────────────────

_DIND_START_TIMEOUT = 30


_DIND_ENTRYPOINT = "from dincli.dind.main import app; app()"


def _run_dind_start(barrier, state_dir, env, results, idx):
    barrier.wait()
    proc = subprocess.Popen(
        [
            sys.executable, "-c", _DIND_ENTRYPOINT,
            "start",
            "--state-dir", str(state_dir),
            "--health-port", "0",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=_DIND_START_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=_DIND_START_TIMEOUT)
        raise
    results[idx] = (proc.returncode, stdout, stderr)


@pytest.mark.parametrize("attempt", range(3))
def test_two_racing_starts_exactly_one_wins(tmp_path, attempt):
    state_dir = tmp_path / f"race-{attempt}"
    env = dict(os.environ)
    env["DIN_DIND_MAX_TICKS"] = "3"

    # The barrier only synchronizes process LAUNCH, not arrival at the
    # stale-PID-check/write-PID window inside `start()` — interpreter
    # startup jitter (hundreds of ms) usually spaces the two processes out
    # enough that even an unprotected check-then-write never actually
    # overlaps. DIN_DIND_TEST_PID_DELAY_S (main.py::start(), test-only)
    # sleeps inside that window, long enough to dwarf that jitter, so both
    # processes are provably inside it at the same time. With the flock in
    # place this changes nothing for the loser: it is turned away at lock
    # acquisition, before it ever reaches the delay. Without the lock (see
    # the neutered-lock self-check in this module's docstring/history) both
    # processes fall through to the delay and then both write a PID file —
    # this is what actually gives the assertions below teeth.
    env["DIN_DIND_TEST_PID_DELAY_S"] = "1.0"

    # Three ticks at the default 1.0s tick_interval keeps the winner alive
    # ~3s — comfortably longer than the loser needs to fail. Assert that
    # assumption explicitly rather than relying on it.
    from dincli.dind.daemon import DaemonLoop
    import inspect
    default_interval = inspect.signature(DaemonLoop.__init__).parameters[
        "tick_interval"
    ].default
    assert default_interval == 1.0

    barrier = threading.Barrier(2)
    results = [None, None]
    threads = [
        threading.Thread(
            target=_run_dind_start, args=(barrier, state_dir, env, results, i)
        )
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=_DIND_START_TIMEOUT + 5)
        assert not t.is_alive(), "racing dind start hung the test"

    codes = [r[0] for r in results]
    assert sorted(codes) == [0, 1], f"expected one winner one loser, got {results}"

    loser_stderr = results[codes.index(1)][2]
    assert (
        "already running" in loser_stderr or "already starting" in loser_stderr
    ), loser_stderr
