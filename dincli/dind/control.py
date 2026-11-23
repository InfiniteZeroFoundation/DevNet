"""Local control channel for the dind lifecycle (review finding 4).

`stop`/`status` used to read a PID file and separately probe whether *some*
process holds the state-directory lock. Neither observation proves the
saved PID belongs to that lock holder: a replacement daemon can start
between the two reads, or the PID can simply have been reused by an
unrelated process by the time either command acts on it. This module gives
`stop`/`status` something to talk to instead of a bare integer.

Protocol, deliberately small (see Plans/task-14-15-remediation-plan.md §9):

- While holding the state directory's exclusive lifetime lock (``lock.py``,
  still the sole authority on "who owns this state dir"), a daemon mints a
  random instance id and publishes it, together with an AF_UNIX socket
  path, in a descriptor file inside the state directory
  (``StateDirs.control_path``). The PID recorded there is diagnostic only
  — nothing here signals it.
- The socket itself lives OUTSIDE the (user-chosen, arbitrarily permissioned)
  state directory, in a private same-user control directory this module
  creates and verifies itself — never a caller-supplied directory this
  module would otherwise need to silently chmod.
- A request is one bounded, newline-delimited JSON object:
  ``{"v": 1, "instance_id": ..., "cmd": ...}``. The server only acts on a
  request whose ``instance_id`` matches its own current one; an unknown
  command, a bad version, an oversized/malformed request, or a mismatched
  id all get a clear rejection — never a crash, and never a fallback to
  acting on the caller's behalf regardless of identity.

What this does and does not prove, precisely: a successful response proves
the client reached a process that, at the moment it accepted the
connection, held this state directory's exclusive lifetime lock under the
identity recorded in the descriptor, and chose to act on the request.
Same-user filesystem permissions on the control directory and socket
(0700/0600) are the actual access control; ``SO_PEERCRED`` is used as a
best-effort second check on platforms that support it (Linux), not a
substitute — the instance id alone is *not* authentication, only a
freshness/identity check that rejects a stale, since-replaced target
instead of silently retargeting to whatever now holds the lock. This is
narrower than a fully race-free guarantee: nothing here proves the
*descriptor read* and the *connection* happened atomically with respect to
a third `start()`, only that the server which accepted the connection will
refuse to honor a request meant for a different instance.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import socket
import stat
import struct
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

PROTOCOL_VERSION = 1

_MAX_REQUEST_BYTES = 4096
_ACCEPT_POLL_S = 0.5   # server accept() timeout granularity, bounds shutdown latency
_IO_TIMEOUT_S = 5.0    # default per-connection client/server read+write bound


class ControlError(Exception):
    """Any control-channel condition a caller must report, never paper over
    by falling back to raw PID signalling."""


# ── descriptor (state-dir side; ordinary file, no path-length concerns) ────


@dataclass(frozen=True)
class ControlDescriptor:
    instance_id: str
    socket_path: str
    pid: int


def write_descriptor(descriptor_path: Path, descriptor: ControlDescriptor) -> None:
    """Publish ``descriptor`` atomically. Callers only do this while holding
    the exclusive state-directory lock."""
    payload = json.dumps(
        {
            "instance_id": descriptor.instance_id,
            "socket_path": descriptor.socket_path,
            "pid": descriptor.pid,
        }
    )
    tmp_path = descriptor_path.with_name(descriptor_path.name + f".tmp-{os.getpid()}")
    tmp_path.write_text(payload)
    os.replace(tmp_path, descriptor_path)  # atomic on POSIX, same filesystem


def read_descriptor(descriptor_path: Path) -> ControlDescriptor | None:
    """Best-effort read. Returns ``None`` for anything not cleanly
    parseable — missing, corrupt, or mid-write — rather than raising: an
    unreadable descriptor is exactly the "no verified control endpoint"
    case callers must already handle."""
    try:
        data = json.loads(descriptor_path.read_text())
        return ControlDescriptor(
            instance_id=str(data["instance_id"]),
            socket_path=str(data["socket_path"]),
            pid=int(data["pid"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remove_descriptor(descriptor_path: Path) -> None:
    descriptor_path.unlink(missing_ok=True)


# ── control socket placement (outside the state dir; path-length bounded) ──


def _control_root() -> Path:
    """A private, same-user directory to hold control sockets.

    Prefers ``$XDG_RUNTIME_DIR`` — systemd creates it 0700, owned by the
    user, and tied to the login session, so this module need not manage its
    lifecycle. Falls back to a fixed per-uid path under the system temp
    directory, which :func:`_ensure_control_dir` creates and verifies
    itself.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        return Path(runtime_dir) / "dincli-dind"
    return Path(tempfile.gettempdir()) / f"dincli-dind-{os.getuid()}"


def _ensure_control_dir(path: Path) -> Path:
    """Create/verify a same-user, non-group/other-accessible directory.

    Never *fixes* an existing directory's ownership or permissions — if
    ``path`` already exists but is not exclusively ours, this raises rather
    than silently chmod-ing something this module did not create (plan §9:
    "avoid requiring an arbitrary user-selected parent directory to be
    silently chmodded").
    """
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as e:
        raise ControlError(f"could not create control directory {path}: {e}") from e
    try:
        st = path.stat()
    except OSError as e:
        raise ControlError(f"could not stat control directory {path}: {e}") from e
    if st.st_uid != os.getuid():
        raise ControlError(f"control directory {path} is not owned by the current user")
    if stat.S_IMODE(st.st_mode) & (stat.S_IRWXG | stat.S_IRWXO):
        raise ControlError(
            f"control directory {path} is accessible to other users "
            f"(mode {oct(stat.S_IMODE(st.st_mode))})"
        )
    return path


def socket_path_for(state_dir: str | Path) -> Path:
    """A short, deterministic AF_UNIX path for ``state_dir``.

    Content-addressed on the resolved state directory rather than embedding
    it directly: ``state_dir`` is caller-chosen and can be arbitrarily long,
    while ``sockaddr_un`` paths are capped well below common filesystem
    limits (~104 bytes on macOS/BSD, ~108 on Linux). Being deterministic
    also means a replacement daemon for the SAME state dir binds at the
    SAME path its predecessor used — which is what lets a stale leftover
    socket be recognized and cleared on the next start (see
    ``ControlServer.start``).
    """
    control_dir = _ensure_control_dir(_control_root())
    digest = hashlib.sha256(str(Path(state_dir).resolve()).encode()).hexdigest()[:24]
    return control_dir / f"{digest}.sock"


# ── wire framing ────────────────────────────────────────────────────────


def _send(sock: socket.socket, payload: dict) -> None:
    sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def _recv_json(sock: socket.socket) -> dict | None:
    """Read one bounded, newline-delimited JSON object. Returns ``None`` on
    a clean EOF before any data; raises ``ValueError`` for anything
    oversized or malformed so the caller can reject rather than hang."""
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(256)
        if not chunk:
            if not buf:
                return None
            raise ValueError("truncated request")
        buf += chunk
        if len(buf) > _MAX_REQUEST_BYTES:
            raise ValueError("request exceeds size limit")
    line, _, _rest = buf.partition(b"\n")
    try:
        data = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"malformed request: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("request must be a JSON object")
    return data


def _peer_is_same_user(conn: socket.socket) -> bool:
    """Best-effort ``SO_PEERCRED`` check (Linux). Where unsupported or
    unavailable, this returns ``True`` and access control rests entirely on
    the 0700 control directory + 0600 socket file permissions — same-user
    filesystem access is still required to reach ``connect()`` at all."""
    so_peercred = getattr(socket, "SO_PEERCRED", None)
    if so_peercred is None:
        return True
    try:
        creds = conn.getsockopt(socket.SOL_SOCKET, so_peercred, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", creds)
    except OSError:
        return True
    return uid == os.getuid()


# ── server ──────────────────────────────────────────────────────────────


class ControlServer:
    """Runs the stop/ping service for one daemon instance.

    Independent of the job loop: bind in :meth:`start` (while the lifetime
    lock is held), then run :meth:`run`'s accept loop on its own thread. A
    valid, instance-matched ``stop`` sets ``stop_event`` — the same event
    ``install_shutdown_handlers`` sets for SIGTERM/SIGINT — so a
    control-triggered stop takes the identical shutdown path.
    """

    def __init__(self, socket_path: Path, instance_id: str, stop_event: threading.Event):
        self._socket_path = Path(socket_path)
        self._instance_id = instance_id
        self._stop_event = stop_event
        self._shutdown = threading.Event()
        self._sock: socket.socket | None = None

    def start(self) -> None:
        """Bind and listen. Call while holding the state-directory lock, on
        the same thread that will later call :meth:`run` — or any thread,
        so long as it happens-before ``run``."""
        # A leftover socket file at this exact path can only be this SAME
        # state dir's own prior instance (the path is content-addressed on
        # state_dir, see socket_path_for) — safe to clear because the
        # caller holds the exclusive lifetime lock, so no other current
        # instance can be listening on it.
        with contextlib.suppress(OSError):
            self._socket_path.unlink()

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old_umask = os.umask(0o177)
        try:
            sock.bind(str(self._socket_path))
        except OSError as e:
            sock.close()
            os.umask(old_umask)
            raise ControlError(f"could not bind control socket {self._socket_path}: {e}") from e
        os.umask(old_umask)
        os.chmod(self._socket_path, 0o600)
        sock.listen(4)
        sock.settimeout(_ACCEPT_POLL_S)
        self._sock = sock

    def run(self) -> None:
        """Accept loop. Run this on a dedicated daemon thread; it returns
        once :meth:`shutdown` is called."""
        assert self._sock is not None, "call start() before run()"
        while not self._shutdown.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                self._handle(conn)

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(_IO_TIMEOUT_S)
        if not _peer_is_same_user(conn):
            with contextlib.suppress(OSError):
                _send(conn, {"status": "error", "reason": "peer_rejected"})
            return
        try:
            request = _recv_json(conn)
        except ValueError:
            with contextlib.suppress(OSError):
                _send(conn, {"status": "error", "reason": "malformed_request"})
            return
        except OSError:
            return
        if request is None:
            return
        with contextlib.suppress(OSError):
            _send(conn, self._dispatch(request))

    def _dispatch(self, request: dict) -> dict:
        if request.get("v") != PROTOCOL_VERSION:
            return {"status": "error", "reason": "unsupported_version"}
        if request.get("instance_id") != self._instance_id:
            # The core of finding 4's fix: never act on behalf of an
            # instance id that isn't ours, even if the command is one we'd
            # otherwise honor. A stale client (old descriptor, replaced
            # instance) gets an explicit rejection instead of silently
            # affecting whichever instance happens to answer at this path.
            return {"status": "error", "reason": "instance_mismatch"}
        cmd = request.get("cmd")
        if cmd == "ping":
            return {"status": "ok", "instance_id": self._instance_id}
        if cmd == "stop":
            self._stop_event.set()
            return {"status": "ok", "instance_id": self._instance_id}
        return {"status": "error", "reason": "unknown_command"}

    def shutdown(self) -> None:
        """Stop the accept loop and remove the socket file. Idempotent."""
        self._shutdown.set()
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._sock.close()
        with contextlib.suppress(OSError):
            self._socket_path.unlink()


# ── client ──────────────────────────────────────────────────────────────


def send_command(
    socket_path: str | Path, instance_id: str, cmd: str, timeout: float = _IO_TIMEOUT_S
) -> dict:
    """Connect to ``socket_path`` and issue one bounded request.

    Raises :class:`ControlError` for anything a caller must not paper over
    with a PID-signal fallback: a missing socket, a refused/timed-out
    connection, or a response that fails to parse. A well-formed rejection
    (e.g. ``instance_mismatch``) is returned normally — that is a valid,
    informative answer, not a transport failure.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        try:
            sock.connect(str(socket_path))
        except OSError as e:
            raise ControlError(f"control endpoint at {socket_path} unreachable: {e}") from e
        try:
            _send(sock, {"v": PROTOCOL_VERSION, "instance_id": instance_id, "cmd": cmd})
            response = _recv_json(sock)
        except (OSError, ValueError) as e:
            raise ControlError(f"control endpoint at {socket_path} did not answer: {e}") from e
    finally:
        sock.close()
    if response is None:
        raise ControlError(f"control endpoint at {socket_path} closed without a response")
    return response


def new_instance_id() -> str:
    return secrets.token_hex(16)
