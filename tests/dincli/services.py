"""Own local integration services without disturbing pre-existing processes."""

import os
import re
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable, IO

import requests


class OwnedService:
    """A child session and its log; cleanup is safe to call more than once."""

    def __init__(self, process: subprocess.Popen, log: IO, log_path: Path):
        self.process = process
        self.log_path = log_path
        self._log = log
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            # start_new_session makes the child PID its process-group ID.
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            finally:
                # Also reap descendants when the parent exits before them.
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=5)
        finally:
            self._log.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def _check_port(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Loopback port {port} is unavailable") from exc


def start_service(
    command: list,
    cwd: Path,
    env: dict,
    log_path: Path,
    ready: Callable[[], bool],
    timeout: float = 30,
    port: int | None = None,
) -> OwnedService:
    """Start a service, returning ownership only after a live child is ready."""
    if port is not None:
        _check_port(port)
    log = None
    service = None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("w")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        service = OwnedService(process, log, log_path)
        deadline = time.monotonic() + timeout
        while True:
            if process.poll() is not None:
                raise RuntimeError("Service exited before readiness")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Service readiness timed out after {timeout}s")
            is_ready = ready()
            if process.poll() is not None:
                raise RuntimeError("Service exited during readiness probe")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Service readiness timed out after {timeout}s")
            if is_ready:
                return service
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    except BaseException as exc:
        try:
            if service is not None:
                service.close()
            elif log is not None:
                log.close()
        except Exception as cleanup_exc:
            raise RuntimeError(
                f"Service startup failed: {exc}; cleanup failed: {cleanup_exc}; log: {log_path}"
            ) from exc
        if not isinstance(exc, Exception):
            raise
        raise RuntimeError(f"Service startup failed: {exc}; log: {log_path}") from exc


def rpc_ready(url: str, expected_chain_id: int = 1337) -> bool:
    try:
        response = requests.post(
            url,
            json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
            timeout=3,
        )
        if response.status_code != 200:
            return False
        body = response.json()
        return (
            isinstance(body, dict)
            and body.get("jsonrpc") == "2.0"
            and type(body.get("id")) is int
            and body.get("id") == 1
            and "error" not in body
            and isinstance(body.get("result"), str)
            and re.fullmatch(r"0x[0-9a-fA-F]+", body["result"]) is not None
            and int(body["result"], 16) == expected_chain_id
        )
    except (requests.RequestException, ValueError, TypeError):
        return False


def ipfs_ready(url: str = "http://127.0.0.1:5001/api/v0/version") -> bool:
    try:
        response = requests.post(url, timeout=3)
        if response.status_code != 200:
            return False
        body = response.json()
        return (
            isinstance(body, dict)
            and isinstance(body.get("Version"), str)
            and bool(body["Version"].strip())
        )
    except (requests.RequestException, ValueError, TypeError):
        return False
