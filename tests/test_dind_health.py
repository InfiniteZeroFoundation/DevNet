"""Tests for dind/health.py — payload shape + degraded detection."""

import json
import socket
import threading
import time
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

from dincli.dind import health as health_module
from dincli.dind.capabilities import resource_snapshot as _real_resource_snapshot
from dincli.dind.health import HealthHandler, HealthServer
from dincli.dind.state import StateStore


@contextmanager
def _running_health_server(store, monkeypatch, before_ready=None):
    """Wait for serving entry, after both discovery metadata writes commit."""
    ready = threading.Event()
    serve_forever = health_module._ThreadingHTTPServer.serve_forever

    def serve_when_ready(http_server, **kwargs):
        ready.set()
        return serve_forever(http_server, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(health_module._ThreadingHTTPServer, "serve_forever", serve_when_ready)
        server = HealthServer("127.0.0.1", 0, store)

        def run():
            try:
                server.run()
            finally:
                store.close()  # StateStore connections are thread-local.

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            if before_ready is not None:
                before_ready(server, ready)
            assert ready.wait(5), "HealthServer never reached serving entry"
            yield server
        finally:
            # shutdown() blocks until serve_forever runs; never call it on
            # a server whose startup failed before entering the serving loop.
            if ready.wait(5):
                shutdown = threading.Thread(target=server.shutdown, daemon=True)
                shutdown.start()
                shutdown.join(timeout=5)
                assert not shutdown.is_alive(), "HealthServer shutdown timed out"
            thread.join(timeout=5)
            # Only clean up failed startup; normal shutdown must release its own port.
            if not ready.is_set() and not thread.is_alive() and hasattr(server, "server"):
                server.server.server_close()
            assert not thread.is_alive(), "HealthServer thread did not stop"


class FakeServer:
    server_address = ("127.0.0.1", 12345)


def _make_handler(store, path="/health"):
    handler = HealthHandler.__new__(HealthHandler)
    handler.state = store
    handler.start_time = time.time()
    handler.path = path
    handler.requestline = "GET " + path + " HTTP/1.0"
    handler.request_version = "HTTP/1.0"
    handler.command = "GET"
    handler.client_address = ("", 0)
    handler.server = FakeServer()
    handler._headers_buffer = []
    wfile = BytesIO()
    handler.wfile = wfile
    return handler, wfile


def _status_line(response: bytes) -> bytes:
    return response.split(b"\r\n", 1)[0]


def test_health_degraded_returns_503(tmp_path):
    """BL-20: a stale last_tick must be served as 503, not 200."""
    store = StateStore(tmp_path / "test.db")
    store.set_meta("last_tick", "2025-01-01T00:00:00+00:00")

    handler, wfile = _make_handler(store)
    handler.do_GET()
    response = wfile.getvalue()

    assert b"503" in _status_line(response)

    body = json.loads(response.split(b"\r\n\r\n", 1)[1])
    assert body["status"] == "degraded"
    store.close()


def test_health_healthy_returns_200(tmp_path):
    """Guards against an inverted status<->code condition."""
    from datetime import datetime, timezone

    store = StateStore(tmp_path / "test.db")
    store.set_meta("last_tick", datetime.now(timezone.utc).isoformat())

    handler, wfile = _make_handler(store)
    handler.do_GET()
    response = wfile.getvalue()

    assert b"200" in _status_line(response)

    body = json.loads(response.split(b"\r\n\r\n", 1)[1])
    assert body["status"] == "healthy"
    store.close()


def test_health_payload_shape(monkeypatch, tmp_path):
    captured = {}

    def spy_resource_snapshot(state_dir):
        captured["state_dir"] = state_dir
        return _real_resource_snapshot(state_dir)

    monkeypatch.setattr(health_module, "resource_snapshot", spy_resource_snapshot)

    store = StateStore(tmp_path / "test.db")
    store.set_meta("last_tick", "2025-01-01T00:00:00+00:00")

    handler, wfile = _make_handler(store)

    handler.do_GET()
    response = wfile.getvalue()
    # This handler is driven with a stale last_tick, i.e. degraded — BL-20
    # makes that 503, not 200.
    assert b"503" in _status_line(response)

    parts = response.split(b"\r\n\r\n", 1)
    body = json.loads(parts[1])

    assert body["status"] == "degraded"
    assert "uptime_s" in body
    assert "pid" in body
    assert "queue" in body
    assert "pending" in body["queue"]
    assert "cpu_count" in body["resources"]
    assert "disk_free_bytes" in body["resources"]
    assert "ram_total_bytes" in body["resources"]
    assert "ram_free_bytes" in body["resources"]
    assert "cpu_speed_mhz" in body["resources"]

    assert isinstance(captured["state_dir"], Path)

    store.close()


def test_health_healthy(tmp_path):
    from datetime import datetime, timezone

    store = StateStore(tmp_path / "test.db")
    store.set_meta("last_tick", datetime.now(timezone.utc).isoformat())

    handler, wfile = _make_handler(store)

    handler.do_GET()
    response = wfile.getvalue()
    parts = response.split(b"\r\n\r\n", 1)
    body = json.loads(parts[1])
    assert body["status"] == "healthy"
    store.close()


def test_health_404_on_other_paths(tmp_path):
    store = StateStore(tmp_path / "test.db")
    handler, wfile = _make_handler(store, path="/other")

    handler.do_GET()
    response = wfile.getvalue()
    assert b"404" in response
    store.close()


def test_health_no_network_gpu_probe(monkeypatch, tmp_path):
    store = StateStore(tmp_path / "test.db")
    monkeypatch.setattr(
        "dincli.dind.capabilities.shutil.which", lambda _cmd: True
    )
    monkeypatch.setattr(
        "dincli.dind.capabilities.glob.glob", lambda _p: ["/dev/nvidia0"]
    )

    socket_probe_calls = []

    def fake_socket_probe(*args, **kwargs):
        socket_probe_calls.append(True)
        return False

    monkeypatch.setattr(
        "dincli.dind.capabilities._socket_probe", fake_socket_probe
    )

    handler, wfile = _make_handler(store)
    handler.do_GET()
    assert len(socket_probe_calls) == 0

    parts = wfile.getvalue().split(b"\r\n\r\n", 1)
    body = json.loads(parts[1])
    assert body["status"] == "healthy"

    store.close()


def test_status_command_reads_degraded_through_503(tmp_path, monkeypatch):
    """BL-20: `dind status` must render "Health: degraded" for a 503
    response, not fall into the "(health endpoint unavailable)" branch that
    urlopen's HTTPError-on-non-2xx would otherwise cause."""
    import os as os_module

    from typer.testing import CliRunner

    from dincli.dind import control
    from dincli.dind.lock import acquire_state_lock, release_state_lock
    from dincli.dind.main import app
    from dincli.dind.paths import StateDirs

    paths = StateDirs(tmp_path)
    store = StateStore(paths.db_path)
    store.set_meta("last_tick", "2025-01-01T00:00:00+00:00")

    paths.pid_path.write_text(str(os_module.getpid()))
    lock_fd = acquire_state_lock(paths.lock_path)

    # `status` only proceeds to the /health block once it has verified this
    # is the instance the descriptor names (review finding 4) — a bare held
    # lock is no longer treated as "running" on its own, so this test needs
    # a real control endpoint standing in for the daemon under test.
    control_socket_path = control.socket_path_for(tmp_path)
    control_server = control.ControlServer(control_socket_path, "the-instance", threading.Event())
    control_server.start()
    control_thread = threading.Thread(target=control_server.run, daemon=True)
    control_thread.start()
    control.write_descriptor(
        paths.control_path,
        control.ControlDescriptor(
            instance_id="the-instance", socket_path=str(control_socket_path), pid=os_module.getpid()
        ),
    )

    # Force the exact old race: self.server exists, but discovery metadata
    # has not been published. No scheduling delay or default-port service
    # is needed to reproduce the incorrect readiness predicate.
    publishing = threading.Event()
    release_publication = threading.Event()
    set_meta = store.set_meta

    def gated_set_meta(key, value):
        if key == "health_host":
            publishing.set()
            assert release_publication.wait(5), "metadata publication not released"
        set_meta(key, value)

    monkeypatch.setattr(store, "set_meta", gated_set_meta)
    runner = CliRunner()

    def before_ready(server, ready):
        from urllib.error import URLError

        from dincli.dind import main as main_module

        try:
            assert publishing.wait(5), "HealthServer did not reach publication"
            assert hasattr(server, "server")  # The old readiness check passes.
            assert store.get_meta("health_host") is None
            assert store.get_meta("health_port") is None
            assert not ready.is_set()  # The replacement does not pass early.
            attempted = []

            def unavailable(url, **kwargs):
                attempted.append(url)
                raise URLError("unpublished test endpoint")

            with monkeypatch.context() as patch:
                patch.setattr(main_module, "resolve_health_host", lambda: "127.0.0.1")
                patch.setattr(main_module, "resolve_health_port", lambda: 1)
                patch.setattr(main_module.urllib.request, "urlopen", unavailable)
                early = runner.invoke(app, ["status", "--state-dir", str(tmp_path)])
            assert early.exit_code == 0, early.output
            assert attempted == ["http://127.0.0.1:1/health"]
            assert "(health endpoint unavailable)" in early.output
            assert "Health:    degraded" not in early.output
        finally:
            release_publication.set()

    try:
        with _running_health_server(store, monkeypatch, before_ready):
            result = runner.invoke(app, ["status", "--state-dir", str(tmp_path)])

            assert result.exit_code == 0, result.output
            assert "Health:    degraded" in result.output
            assert "(health endpoint unavailable)" not in result.output
    finally:
        release_publication.set()
        control_server.shutdown()
        control_thread.join(timeout=5)
        release_state_lock(lock_fd)
        store.close()


def test_health_server_releases_port(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "test.db")
    store.initialize()
    try:
        with _running_health_server(store, monkeypatch) as server:
            host, port = server.server.server_address

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, port))
        finally:
            probe.close()
    finally:
        store.close()
