"""Container health probe. Keep its startup independent of the interactive CLI."""

import json
import sys
import urllib.request

from dincli.dind.config import resolve_state_dir
from dincli.dind.lock import is_locked
from dincli.dind.paths import StateDirs
from dincli.dind.state import StateStore


def check_health(state_dir: str | None = None) -> int:
    paths = StateDirs(resolve_state_dir(state_dir))
    if not is_locked(paths.lock_path):
        return 1

    store = StateStore(paths.db_path)
    try:
        host = store.get_meta("health_host")
        port = store.get_meta("health_port")
        instance_id = store.get_meta("health_instance")
        if not host or not port or not instance_id:
            return 1
        if host == "0.0.0.0":
            host = "127.0.0.1"
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=3) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or payload.get("instance_id") != instance_id:
            return 1
        if payload.get("status") != "healthy":
            return 1
        return 0
    except (OSError, ValueError) as exc:
        print(f"Health check failed: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(check_health())
