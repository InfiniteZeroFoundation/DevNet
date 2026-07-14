"""PID file read/write, liveness detection, signal dispatch."""

import os
import signal
from pathlib import Path


def read_pid(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    content = pid_path.read_text().strip()
    if not content:
        return None
    try:
        return int(content)
    except ValueError:
        return None


def write_pid(pid_path: Path) -> None:
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))


def remove_pid(pid_path: Path) -> None:
    if pid_path.exists():
        pid_path.unlink(missing_ok=True)


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def send_signal(pid: int, sig: int = signal.SIGTERM) -> None:
    os.kill(pid, sig)
