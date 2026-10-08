"""Bounded evidence for isolated harness commands and owned service output.

Only caller-supplied labels and explicit outcome metadata enter the manifest.
Command arguments, environments and stdin are deliberately never recorded.
"""

import errno
import json
import locale
import os
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path


class DiagnosticsError(RuntimeError):
    """Evidence could not be retained, so the run must fail."""


class DiagnosticsLimitError(DiagnosticsError):
    """A continuously counted output budget was exceeded."""


class DiagnosticsWriteError(DiagnosticsError):
    """A diagnostics file could not be written."""


def _label(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value))[:80] or "command"


def _secondary(primary: BaseException, error: BaseException) -> None:
    """Keep interruption/command failures primary even if evidence also fails."""
    note = f"Diagnostics/cleanup also failed: {type(error).__name__}"
    primary.add_note(note)
    print(note, file=sys.stderr)


class _Capture:
    def __init__(self, owner, label: str, retain: bool):
        self.owner = owner
        self.label = label
        self.path = owner._path(label, ".log")
        self.data = bytearray() if retain else None
        self.count = 0
        self._size = 0
        self.truncated = False
        try:
            self.file = owner._open_file(self.path.name)
        except OSError as exc:
            raise DiagnosticsWriteError("Cannot create diagnostics stream") from exc

    def feed(self, data: bytes) -> None:
        if not data:
            return
        with self.owner._lock:
            self.count += len(data)
            available = min(
                max(0, self.owner.stream_limit - self._size),
                max(0, self.owner.total_limit - self.owner._retained),
            )
            kept = data[:available]
            if kept:
                try:
                    written = self.file.write(kept) or 0
                except OSError as exc:
                    raise DiagnosticsWriteError("Cannot write diagnostics stream") from exc
                # A short write still consumes retained disk budget.
                self._size += written
                self.owner._retained += written
                if self.data is not None:
                    self.data.extend(kept[:written])
                if written != len(kept):
                    raise DiagnosticsWriteError("Short diagnostics write")
            if len(kept) != len(data):
                self.truncated = True
                raise DiagnosticsLimitError("Diagnostics output budget exceeded")

    def close(self) -> None:
        try:
            self.file.close()
        except OSError as exc:
            raise DiagnosticsWriteError("Cannot close diagnostics stream") from exc


class ServiceStream:
    """Popen stdout target that continuously drains a capped service log.

    Stop the owned service before close(). check() surfaces asynchronous failures;
    after a limit/write failure the reader keeps discarding to avoid pipe stalls.
    """

    def __init__(self, owner, label: str):
        self.owner = owner
        self._capture = _Capture(owner, label, retain=False)
        self.path = self._capture.path
        self._reader = self._writer = None
        self._stop = threading.Event()
        self._error = None
        self.closed = False
        try:
            self._reader, self._writer = os.pipe()
            self._thread = threading.Thread(target=self._drain, daemon=True)
            self._thread.start()
        except BaseException as primary:
            self._stop.set()
            self._error = DiagnosticsWriteError("Service diagnostics setup failed")
            thread = getattr(self, "_thread", None)
            if thread is not None and thread.is_alive():
                try:
                    thread.join(timeout=1)
                except BaseException as exc:
                    _secondary(primary, exc)
            for fd in (self._reader, self._writer):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError as exc:
                        _secondary(primary, exc)
            try:
                self._capture.close()
            except BaseException as exc:
                _secondary(primary, exc)
            raise

    def fileno(self) -> int:
        return self._writer

    def _drain(self) -> None:
        try:
            os.set_blocking(self._reader, False)
            with selectors.DefaultSelector() as selector:
                selector.register(self._reader, selectors.EVENT_READ)
                stop_deadline = None
                while True:
                    if self._stop.is_set() and stop_deadline is None:
                        stop_deadline = time.monotonic() + 0.5
                    if stop_deadline is not None and time.monotonic() >= stop_deadline:
                        break
                    if not selector.select(0.05):
                        if self._stop.is_set():
                            break
                        continue
                    try:
                        data = os.read(self._reader, 65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        break
                    with self.owner._lock:
                        if self._error is None:
                            try:
                                self._capture.feed(data)
                            except DiagnosticsError as exc:
                                self._error = exc
                        else:
                            self._capture.count += len(data)
        except BaseException as exc:
            if self._error is None:
                self._error = DiagnosticsWriteError(
                    f"Service diagnostics reader failed: {type(exc).__name__}"
                )
        finally:
            with self.owner._lock:
                if self._reader is not None:
                    os.close(self._reader)
                    self._reader = None

    def check(self) -> None:
        if self._error is not None:
            raise self._error

    def close(self) -> None:
        def failed(error):
            if self._error is None:
                self._error = error
            elif self._error is not error:
                _secondary(self._error, error)

        # Even interruption during one phase must not bypass the remaining
        # phases. Keep a failed writer close retryable on the next close().
        self._stop.set()
        if self._writer is not None:
            try:
                os.close(self._writer)
                self._writer = None
            except BaseException as exc:
                if isinstance(exc, OSError) and exc.errno == errno.EBADF:
                    self._writer = None
                failed(exc)
        if not self.closed:
            self.closed = True
            try:
                self._thread.join(timeout=1)
            except BaseException as exc:
                failed(exc)
            if self._thread.is_alive():
                try:
                    self._thread.join(timeout=1)
                except BaseException as exc:
                    failed(exc)
            with self.owner._lock:
                if self._thread.is_alive():
                    failed(DiagnosticsWriteError("Service diagnostics reader did not stop"))
                try:
                    self._capture.close()
                except BaseException as exc:
                    failed(exc)
            outcome = "ok" if self._error is None else type(self._error).__name__
            try:
                self.owner.record(
                    self._capture.label, outcome,
                    bytes_seen=self._capture.count,
                    truncated=self._capture.truncated,
                    file=self.path.name,
                )
            except BaseException as exc:
                failed(exc)
        self.check()


class Diagnostics:
    """One run's capped logs and a separately bounded outcome manifest."""

    def __init__(
        self, results_dir: Path, *, stream_limit: int = 10 * 1024 * 1024,
        total_limit: int = 100 * 1024 * 1024, manifest_limit: int = 64 * 1024,
    ):
        if min(stream_limit, total_limit) < 0 or manifest_limit < 128:
            raise ValueError("Invalid diagnostics budgets")
        self.results_dir = Path(os.path.abspath(results_dir))
        self._dir_fd = self._open_directory(self.results_dir)
        self.stream_limit = stream_limit
        self.total_limit = total_limit
        self.manifest_limit = manifest_limit
        self._lock = threading.RLock()
        self._retained = 0
        self._sequence = 0
        self._streams = []
        self._failures = []
        self._manifest_bytes = 0
        self._manifest_full = False
        self.manifest_path = self._path("manifest", ".jsonl")
        try:
            self._manifest = self._open_file(self.manifest_path.name)
        except OSError as exc:
            os.close(self._dir_fd)
            self._dir_fd = None
            raise DiagnosticsWriteError("Cannot create diagnostics manifest") from exc

    @staticmethod
    def _open_directory(path: Path) -> int:
        """Create/open each component without following symlink ancestors."""
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in path.parts[1:]:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                next_fd = os.open(
                    component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                os.close(descriptor)
                descriptor = next_fd
            return descriptor
        except BaseException as exc:
            os.close(descriptor)
            if isinstance(exc, OSError):
                raise DiagnosticsWriteError("Unsafe or unavailable diagnostics directory") from exc
            raise

    def _open_file(self, name: str):
        if self._dir_fd is None:
            raise DiagnosticsWriteError("Diagnostics is closed")
        descriptor = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=self._dir_fd,
        )
        try:
            return os.fdopen(descriptor, "wb", buffering=0)
        except BaseException:
            os.close(descriptor)
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.close()
        except BaseException as exc:
            if exc_value is None:
                raise
            _secondary(exc_value, exc)

    def _path(self, label: str, suffix: str) -> Path:
        # Exclusive creation also refuses a preexisting symlink or another run's file.
        with self._lock:
            self._sequence += 1
            return self.results_dir / f"{self._sequence:04d}_{_label(label)}{suffix}"

    def record(self, label: str, outcome: str, **safe_fields) -> None:
        """Append explicit metadata; callers must never supply secret values."""
        record = {"label": _label(label), "outcome": str(outcome)[:120]}
        record.update(safe_fields)
        try:
            data = (json.dumps(record, ensure_ascii=True, default=str) + "\n").encode()
            with self._lock:
                if self._manifest_full:
                    return
                if self._manifest_bytes + len(data) > self.manifest_limit - 80:
                    data = b'{"outcome":"manifest_limit","omitted":true}\n'
                    self._manifest_full = True
                written = self._manifest.write(data) or 0
                self._manifest_bytes += written
                if written != len(data):
                    raise OSError("Short manifest write")
        except (OSError, ValueError) as exc:
            raise DiagnosticsWriteError("Cannot write diagnostics manifest") from exc

    def open_stream(self, label: str) -> ServiceStream:
        stream = ServiceStream(self, label)
        self._streams.append(stream)
        return stream

    def note_failure(self, label: str, error: BaseException) -> None:
        """Remember an owned cleanup failure even if its immediate caller exits."""
        self._failures.append(error)
        self.record(label, "cleanup_error", error_type=type(error).__name__)

    def check(self) -> None:
        if self._failures:
            raise self._failures[0]
        for stream in self._streams:
            stream.check()

    def close(self) -> None:
        primary = self._failures[0] if self._failures else None
        for stream in self._streams:
            try:
                stream.close()
            except BaseException as exc:
                if primary is None:
                    primary = exc
                else:
                    _secondary(primary, exc)
        try:
            self._manifest.close()
        except BaseException as exc:
            if primary is None:
                primary = exc
            else:
                _secondary(primary, exc)
        if self._dir_fd is not None:
            try:
                os.close(self._dir_fd)
            except BaseException as exc:
                if primary is None:
                    primary = exc
                else:
                    _secondary(primary, exc)
            self._dir_fd = None
        if primary is not None:
            raise primary

    @staticmethod
    def _stop(process) -> None:
        # Try every cleanup step even if TERM/wait itself fails or is interrupted.
        primary = None
        for sig, wait_timeout in ((signal.SIGTERM, 0.5), (signal.SIGKILL, 1)):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            except BaseException as exc:
                if primary is None:
                    primary = exc
                else:
                    _secondary(primary, exc)
            try:
                process.wait(timeout=wait_timeout)
            except subprocess.TimeoutExpired as exc:
                if sig == signal.SIGKILL:
                    if primary is None:
                        primary = exc
                    else:
                        _secondary(primary, exc)
            except BaseException as exc:
                if primary is None:
                    primary = exc
                else:
                    _secondary(primary, exc)
        if primary is not None:
            raise primary

    def run(
        self, command, *, cwd, env, timeout, input_text=None, label="command",
    ) -> subprocess.CompletedProcess[str]:
        """Capture a host command without unlimited communicate() buffers."""
        self.check()
        started = time.monotonic()
        captures = []
        process = None
        primary = None
        outcome = "error"
        # Caller-handled exceptions must not suppress our finalization failures.
        propagating = False
        encoding = locale.getpreferredencoding(False)
        selector = selectors.DefaultSelector()
        try:
            stdout = _Capture(self, f"{label}_stdout", retain=True)
            captures.append(stdout)
            stderr = _Capture(self, f"{label}_stderr", retain=True)
            captures.append(stderr)
            process = subprocess.Popen(
                command, cwd=cwd, env=env,
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,
            )
            for pipe, capture in ((process.stdout, stdout), (process.stderr, stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, capture)
            pending = memoryview(input_text.encode(encoding)) if input_text is not None else None
            if pending is not None:
                os.set_blocking(process.stdin.fileno(), False)
                if len(pending):
                    selector.register(process.stdin, selectors.EVENT_WRITE)
                else:
                    process.stdin.close()
            deadline = None if timeout is None else started + timeout
            while selector.get_map() or process.poll() is None:
                if deadline is not None and time.monotonic() >= deadline:
                    outcome = "timeout"
                    raise subprocess.TimeoutExpired(command, timeout)
                self.check()
                delay = 0.05 if deadline is None else min(0.05, max(0, deadline - time.monotonic()))
                for key, _ in selector.select(delay):
                    if key.events == selectors.EVENT_WRITE:
                        try:
                            written = os.write(key.fd, pending[:65536])
                            pending = pending[written:]
                        except BrokenPipeError:
                            pending = pending[:0]
                        except BlockingIOError:
                            continue
                        if not pending:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        try:
                            data = os.read(key.fd, 65536)
                        except BlockingIOError:
                            continue
                        if data:
                            key.data.feed(data)
                        else:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
            result = subprocess.CompletedProcess(
                command, process.returncode,
                self._text(stdout.data, encoding), self._text(stderr.data, encoding),
            )
            outcome = "ok" if result.returncode == 0 else "nonzero"
            return result
        except BaseException as exc:
            primary = exc
            propagating = True
            if isinstance(exc, DiagnosticsLimitError):
                outcome = "diagnostics_limit"
            elif isinstance(exc, DiagnosticsError):
                outcome = "diagnostics_error"
            elif isinstance(exc, KeyboardInterrupt):
                outcome = "interrupted"
            raise
        finally:
            if process is not None:
                try:
                    self._stop(process)
                except BaseException as exc:
                    if primary is not None:
                        _secondary(primary, exc)
                    else:
                        primary = exc
                # Drain finite bytes remaining after shutdown. Secondary errors do
                # not replace a timeout/interruption that explains the failure.
                for pipe, capture in zip((process.stdout, process.stderr), captures):
                    if pipe.closed:
                        continue
                    try:
                        while True:
                            data = os.read(pipe.fileno(), 65536)
                            if not data:
                                break
                            capture.feed(data)
                    except BlockingIOError:
                        pass
                    except BaseException as exc:
                        if primary is not None:
                            _secondary(primary, exc)
                        else:
                            primary = exc
                    finally:
                        try:
                            pipe.close()
                        except BaseException as exc:
                            if primary is not None:
                                _secondary(primary, exc)
                            else:
                                primary = exc
                if process.stdin is not None:
                    try:
                        process.stdin.close()
                    except BaseException as exc:
                        if primary is not None:
                            _secondary(primary, exc)
                        else:
                            primary = exc
            try:
                selector.close()
            except BaseException as exc:
                if primary is not None:
                    _secondary(primary, exc)
                else:
                    primary = exc
            if isinstance(primary, subprocess.TimeoutExpired) and len(captures) == 2:
                primary.output = bytes(captures[0].data) or None
                primary.stderr = bytes(captures[1].data) or None
            for capture in captures:
                try:
                    capture.close()
                except BaseException as exc:
                    if primary is not None:
                        _secondary(primary, exc)
                    else:
                        primary = exc
            try:
                self.record(
                    label, outcome, duration=round(time.monotonic() - started, 3),
                    returncode=None if process is None else process.returncode,
                    files=[capture.path.name for capture in captures],
                    truncated=any(capture.truncated for capture in captures),
                )
            except BaseException as exc:
                if primary is not None:
                    _secondary(primary, exc)
                else:
                    primary = exc
            # A finally-created failure must prevent a successful return.
            if primary is not None and not propagating:
                if process is not None and process.returncode not in (None, 0):
                    primary.add_note(f"Command exited with status {process.returncode}")
                raise primary

    @staticmethod
    def _text(data: bytes, encoding: str) -> str:
        return data.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")


def write_cleanup_summary(
    results_dir: Path, *, scratch_removed: bool, errors: list[str],
) -> Path:
    """Retain final cleanup outcomes after command/service diagnostics close.

    Error metadata is restricted to stage:type (or type) tokens; never pass
    exception messages. Only the first 200 entries are retained, with omission
    counts. The separate summary stays below the reserved 64 KiB budget.
    """
    if type(scratch_removed) is not bool:
        raise ValueError("scratch_removed must be a boolean")
    safe_errors = []
    token = r"[A-Za-z_][A-Za-z0-9_-]{0,63}"
    for value in errors[:200]:
        if isinstance(value, str) and re.fullmatch(rf"{token}(?::{token})?", value):
            safe_errors.append(value)
        else:
            safe_errors.append("invalid_error_metadata")
    data = (json.dumps({
        "scratch_removed": scratch_removed,
        "errors": safe_errors,
        "errors_omitted": max(0, len(errors) - len(safe_errors)),
    }, ensure_ascii=True) + "\n").encode()
    path = Path(os.path.abspath(results_dir))
    directory = Diagnostics._open_directory(path)
    descriptor = None
    primary = None
    propagating = False
    temporary = f".cleanup-{uuid.uuid4().hex}.tmp"
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory,
        )
        # os.write can return a short count without raising on a full filesystem.
        written = os.write(descriptor, data)
        if written != len(data):
            raise OSError("Short cleanup summary write")
        os.link(
            temporary, "cleanup.json", src_dir_fd=directory,
            dst_dir_fd=directory, follow_symlinks=False,
        )
        return path / "cleanup.json"
    except BaseException as exc:
        primary = exc
        propagating = True
        if isinstance(exc, OSError):
            primary = DiagnosticsWriteError("Cannot retain cleanup summary")
            raise primary from exc
        raise
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        except BaseException as exc:
            if primary is not None:
                _secondary(primary, exc)
            else:
                primary = exc
        for owned_fd in (descriptor, directory):
            if owned_fd is None:
                continue
            try:
                os.close(owned_fd)
            except BaseException as exc:
                if primary is not None:
                    _secondary(primary, exc)
                else:
                    primary = exc
        if primary is not None and not propagating:
            raise DiagnosticsWriteError("Cannot close cleanup summary") from primary
