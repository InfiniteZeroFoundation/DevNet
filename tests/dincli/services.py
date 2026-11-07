"""Own local integration services without disturbing pre-existing processes."""

import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, IO

import requests


class OwnedService:
    """A child session and its log; cleanup is safe to call more than once."""

    def __init__(self, process: subprocess.Popen, log: IO, log_path: Path, diagnostics=None):
        self.process = process
        self.log_path = log_path
        self._log = log
        self._closed = False
        self._diagnostics = diagnostics

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        primary = None

        def failed(error, stage):
            nonlocal primary
            if primary is None:
                primary = error
            else:
                primary.add_note(
                    f"Service {stage} also failed: {type(error).__name__}"
                )

        # Attempt every cleanup step independently. An interrupted/failed TERM
        # must not prevent escalation, reaping, or log closure.
        try:
            # start_new_session makes the child PID its process-group ID.
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except BaseException as error:
            failed(error, "termination")
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        except BaseException as error:
            failed(error, "grace wait")
        try:
            # Also reap descendants when the parent exits before them.
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except BaseException as error:
            failed(error, "escalation")
        try:
            self.process.wait(timeout=5)
        except BaseException as error:
            failed(error, "reaping")
        try:
            self._log.close()
        except BaseException as error:
            failed(error, "log cleanup")
        if primary is not None:
            if self._diagnostics is not None:
                try:
                    self._diagnostics.note_failure("service_cleanup", primary)
                except BaseException as error:
                    primary.add_note(f"Cleanup recording also failed: {type(error).__name__}")
            raise primary

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.close()
        except BaseException as error:
            if exc_value is None:
                raise
            note = f"Owned service cleanup also failed: {type(error).__name__}"
            exc_value.add_note(note)
            print(note, file=sys.stderr)


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
    diagnostics=None,
) -> OwnedService:
    """Start a service, returning ownership only after a live child is ready."""
    if port is not None:
        _check_port(port)
    log = None
    service = None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if diagnostics is None:
            log = log_path.open("w")
        else:
            log = diagnostics.open_stream(log_path.stem)
            log_path = log.path
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        service = OwnedService(process, log, log_path, diagnostics=diagnostics)
        deadline = time.monotonic() + timeout
        while True:
            if diagnostics is not None:
                log.check()
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
        except BaseException as cleanup_exc:
            if not isinstance(exc, Exception):
                exc.add_note(f"Service startup cleanup also failed: {type(cleanup_exc).__name__}")
                raise exc
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
