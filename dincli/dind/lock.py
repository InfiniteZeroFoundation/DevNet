"""Cross-process advisory lock for a dind state directory (BL-19).

``flock``, not ``O_EXCL`` on the PID file: the kernel releases an ``flock``
when the owning process dies for any reason, including ``SIGKILL``. An
``O_EXCL`` marker file would survive a hard kill instead, leaving exactly the
stale artifact the existing stale-PID cleanup exists to paper over.

POSIX-only (``fcntl``). The daemon already ships only ``systemd``/``launchd``
examples, so this does not narrow the platforms it actually runs on — the
import is guarded so the failure mode elsewhere is a clear ``RuntimeError``
rather than an ``ImportError`` surfacing deep in a traceback.
"""

import errno
import os
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised only off POSIX
    fcntl = None

# flock() reports contention as EWOULDBLOCK, which is EAGAIN on every
# platform where this module can even import; EACCES covers the (rare)
# platforms/filesystems that report lock contention that way instead.
_CONTENTION_ERRNOS = {errno.EACCES, errno.EAGAIN}


def _require_fcntl() -> None:
    if fcntl is None:
        raise RuntimeError("dind's state lock requires a POSIX platform (fcntl)")


def acquire_state_lock(lock_path: str | Path) -> int | None:
    """Try to take the exclusive, non-blocking lock at ``lock_path``.

    Returns the open fd on success — the caller owns it and must eventually
    pass it to :func:`release_state_lock`, exactly once.

    Returns ``None`` ONLY on contention: another process already holds the
    lock (``EACCES``/``EAGAIN`` from ``flock``). Every other failure —
    ``EPERM``/``EROFS``/``ENOENT``/``ENOSPC`` opening the file, or any
    non-contention errno from ``flock`` — closes the fd (if one was opened)
    and re-raises, so a permissions or disk fault is never reported to the
    operator as "already running".
    """
    _require_fcntl()

    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Failures here (EPERM/EROFS/ENOENT/ENOSPC, ...) propagate as-is: there is
    # no fd yet to close, and they are not lock contention.
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        os.close(fd)
        if e.errno in _CONTENTION_ERRNOS:
            return None
        raise
    return fd


def release_state_lock(fd: int) -> None:
    """Release a lock acquired by :func:`acquire_state_lock`.

    Not idempotent, and deliberately so: after ``close(2)`` the OS may hand
    that integer to an unrelated open file elsewhere in the process, so a
    second call here would unlock and close a stranger's descriptor. Callers
    must call this exactly once per successful acquisition, from a single
    ``finally``.
    """
    _require_fcntl()
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def is_locked(lock_path: str | Path) -> bool:
    """Non-blocking probe: does some other process hold this lock?

    Tries to acquire it and releases immediately on success. A free lock is
    positive evidence that no process owns the state directory, regardless
    of what any PID file says. Non-contention failures propagate, matching
    :func:`acquire_state_lock`.
    """
    fd = acquire_state_lock(lock_path)
    if fd is None:
        return True
    release_state_lock(fd)
    return False
