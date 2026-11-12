"""Tests for dind/control.py — the local control channel that lets
`stop`/`status` verify a daemon's identity instead of trusting a bare PID
(review finding 4; Plans/task-14-15-remediation-plan.md §9)."""

import os
import threading

import pytest

from dincli.dind import control


def _start_server(socket_path, instance_id, stop_event=None):
    stop_event = stop_event or threading.Event()
    server = control.ControlServer(socket_path, instance_id, stop_event)
    server.start()
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread, stop_event


def _stop_server(server, thread):
    server.shutdown()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_socket_path_is_deterministic_and_short(tmp_path):
    p1 = control.socket_path_for(tmp_path)
    p2 = control.socket_path_for(tmp_path)
    assert p1 == p2
    assert len(str(p1)) < 100  # sockaddr_un limit, see module docstring


def test_socket_path_differs_by_state_dir(tmp_path):
    a = control.socket_path_for(tmp_path / "a")
    b = control.socket_path_for(tmp_path / "b")
    assert a != b


def test_ping_round_trip(tmp_path):
    sock_path = control.socket_path_for(tmp_path)
    server, thread, _ = _start_server(sock_path, "inst-1")
    try:
        response = control.send_command(sock_path, "inst-1", "ping", timeout=2.0)
        assert response == {"status": "ok", "instance_id": "inst-1"}
    finally:
        _stop_server(server, thread)


def test_stop_sets_event_only_for_matching_instance(tmp_path):
    sock_path = control.socket_path_for(tmp_path)
    stop_event = threading.Event()
    server, thread, _ = _start_server(sock_path, "inst-1", stop_event)
    try:
        response = control.send_command(sock_path, "inst-1", "stop", timeout=2.0)
        assert response["status"] == "ok"
        assert stop_event.is_set()
    finally:
        _stop_server(server, thread)


def test_mismatched_instance_id_is_rejected_and_does_not_stop(tmp_path):
    """The core of the fix: a request naming a stale/wrong instance id must
    not be honored, even for a recognized command."""
    sock_path = control.socket_path_for(tmp_path)
    stop_event = threading.Event()
    server, thread, _ = _start_server(sock_path, "current-instance", stop_event)
    try:
        response = control.send_command(sock_path, "stale-instance", "stop", timeout=2.0)
        assert response == {"status": "error", "reason": "instance_mismatch"}
        assert not stop_event.is_set()
    finally:
        _stop_server(server, thread)


def test_replacement_rejects_old_instance_new_stays_running(tmp_path):
    """Simulates the exact race in review finding 4: `stop` read a
    descriptor for instance A; before it connects, A exits and a
    replacement instance B binds at the same (content-addressed) socket
    path. The request naming A must be rejected, and B's own stop_event
    must remain unset — B keeps running."""
    sock_path = control.socket_path_for(tmp_path)

    server_a, thread_a, stop_event_a = _start_server(sock_path, "instance-a")
    _stop_server(server_a, thread_a)  # A "exits" — frees the socket path

    stop_event_b = threading.Event()
    server_b, thread_b, _ = _start_server(sock_path, "instance-b", stop_event_b)
    try:
        # A stale `stop` still carrying A's instance id.
        response = control.send_command(sock_path, "instance-a", "stop", timeout=2.0)
        assert response == {"status": "error", "reason": "instance_mismatch"}
        assert not stop_event_b.is_set()

        # The correctly-addressed request still works against B.
        response_b = control.send_command(sock_path, "instance-b", "stop", timeout=2.0)
        assert response_b["status"] == "ok"
        assert stop_event_b.is_set()
    finally:
        _stop_server(server_b, thread_b)


def test_unknown_command_rejected(tmp_path):
    sock_path = control.socket_path_for(tmp_path)
    server, thread, _ = _start_server(sock_path, "inst-1")
    try:
        response = control.send_command(sock_path, "inst-1", "reboot", timeout=2.0)
        assert response == {"status": "error", "reason": "unknown_command"}
    finally:
        _stop_server(server, thread)


def test_unreachable_socket_raises_control_error(tmp_path):
    missing = tmp_path / "does-not-exist.sock"
    with pytest.raises(control.ControlError):
        control.send_command(missing, "inst-1", "ping", timeout=1.0)


def test_malformed_request_rejected_without_crashing_server(tmp_path):
    import socket as socket_mod

    sock_path = control.socket_path_for(tmp_path)
    server, thread, _ = _start_server(sock_path, "inst-1")
    try:
        raw = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_STREAM)
        raw.settimeout(2.0)
        raw.connect(str(sock_path))
        raw.sendall(b"not json at all\n")
        response = control._recv_json(raw)
        raw.close()
        assert response == {"status": "error", "reason": "malformed_request"}

        # The server must still be alive and answer a well-formed request.
        response_ok = control.send_command(sock_path, "inst-1", "ping", timeout=2.0)
        assert response_ok["status"] == "ok"
    finally:
        _stop_server(server, thread)


def test_oversized_request_rejected_without_crashing_server(tmp_path):
    import socket as socket_mod

    sock_path = control.socket_path_for(tmp_path)
    server, thread, _ = _start_server(sock_path, "inst-1")
    try:
        raw = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_STREAM)
        raw.settimeout(2.0)
        raw.connect(str(sock_path))
        raw.sendall(b"x" * (control._MAX_REQUEST_BYTES + 1024) + b"\n")
        raw.close()

        response_ok = control.send_command(sock_path, "inst-1", "ping", timeout=2.0)
        assert response_ok["status"] == "ok"
    finally:
        _stop_server(server, thread)


def test_descriptor_round_trip(tmp_path):
    descriptor_path = tmp_path / "dind.control.json"
    descriptor = control.ControlDescriptor(
        instance_id="abc123", socket_path=str(tmp_path / "x.sock"), pid=os.getpid()
    )
    control.write_descriptor(descriptor_path, descriptor)
    loaded = control.read_descriptor(descriptor_path)
    assert loaded == descriptor


def test_read_descriptor_missing_file_returns_none(tmp_path):
    assert control.read_descriptor(tmp_path / "nope.json") is None


def test_read_descriptor_corrupt_file_returns_none(tmp_path):
    descriptor_path = tmp_path / "dind.control.json"
    descriptor_path.write_text("{not valid json")
    assert control.read_descriptor(descriptor_path) is None


def test_control_dir_rejects_existing_dir_with_group_or_other_access(tmp_path, monkeypatch):
    """_ensure_control_dir must refuse to silently adopt (or chmod) a
    pre-existing directory it does not control the permissions of."""
    unsafe_dir = tmp_path / "unsafe-control"
    unsafe_dir.mkdir(mode=0o755)

    monkeypatch.setattr(control, "_control_root", lambda: unsafe_dir)
    with pytest.raises(control.ControlError):
        control.socket_path_for(tmp_path / "somestate")
