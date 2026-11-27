"""PID file bookkeeping; daemon identity and shutdown use lock/control state."""

import os
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
