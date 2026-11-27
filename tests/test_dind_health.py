"""Tests for dind/health.py — payload shape + degraded detection."""

import json
import socket
import threading
import time
from contextlib import ExitStack, contextmanager
from io import BytesIO
from pathlib import Path

import pytest

from dincli.dind import config as dind_config
from dincli.dind import health as health_module
from dincli.dind.capabilities import resource_snapshot as _real_resource_snapshot
from dincli.dind.chain_health import ChainHealthMonitor
from dincli.dind.health import HealthHandler, HealthServer
from dincli.dind.state import StateStore
from dincli.sdk.errors import NetworkError


@contextmanager
def _running_health_server(store, monkeypatch, before_ready=None):
    """Wait for serving entry, after both discovery metadata writes commit."""
    ready = threading.Event()
    serve_forever = health_module.ThreadingHTTPServer.serve_forever

    def serve_when_ready(http_server, **kwargs):
        ready.set()
        return serve_forever(http_server, **kwargs)

    with monkeypatch.context() as patch, HealthServer("127.0.0.1", 0, store) as server:
        patch.setattr(health_module.ThreadingHTTPServer, "serve_forever", serve_when_ready)

        def run():
            try:
                server.publish_endpoint()
                server.serve_forever()
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
            assert not thread.is_alive(), "HealthServer thread did not stop"


class FakeServer:
    server_address = ("127.0.0.1", 12345)


def _make_handler(store, path="/health"):
    handler = HealthHandler.__new__(HealthHandler)
    handler.path = path
    handler.requestline = "GET " + path + " HTTP/1.0"
    handler.request_version = "HTTP/1.0"
    handler.command = "GET"
    handler.client_address = ("", 0)
    handler.server = FakeServer()
    handler.server.instance_id = "the-instance"
    handler.server.state = store
    handler.server.start_time = time.time()
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
    with ExitStack() as cleanup:
        store = StateStore(paths.db_path)
        cleanup.callback(store.close)
        store.set_meta("last_tick", "2025-01-01T00:00:00+00:00")

        paths.pid_path.write_text(str(os_module.getpid()))
        lock_fd = acquire_state_lock(paths.lock_path)
        assert lock_fd is not None
        cleanup.callback(release_state_lock, lock_fd)

        # `status` only proceeds to the /health block once it has verified this
        # is the instance the descriptor names (review finding 4) — a bare held
        # lock is no longer treated as "running" on its own, so this test needs
        # a real control endpoint standing in for the daemon under test.
        control_socket_path = control.socket_path_for(tmp_path)
        control_server = control.ControlServer(control_socket_path, "the-instance", threading.Event())
        control_thread = threading.Thread(target=control_server.run, daemon=True)

        def join_control():
            if control_thread.ident is not None:
                control_thread.join(timeout=5)
                assert not control_thread.is_alive(), "ControlServer thread did not stop"

        # ExitStack runs each callback even if an earlier cleanup raises.
        # Register shutdown before start(), which can partially acquire resources.
        cleanup.callback(join_control)
        cleanup.callback(control_server.shutdown)
        control_server.start()
        control_thread.start()
        control.write_descriptor(
            paths.control_path,
            control.ControlDescriptor(
                instance_id="the-instance", socket_path=str(control_socket_path), pid=os_module.getpid()
            ),
        )

        # Force the exact old race: the listener exists, but discovery metadata
        # has not been published. No scheduling delay or default-port service
        # is needed to reproduce the incorrect readiness predicate.
        publishing = threading.Event()
        release_publication = threading.Event()
        cleanup.callback(release_publication.set)
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
                assert server.fileno() >= 0  # The old readiness check passes.
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

        with _running_health_server(store, monkeypatch, before_ready):
            result = runner.invoke(app, ["status", "--state-dir", str(tmp_path)])

            assert result.exit_code == 0, result.output
            assert "Health:    degraded" in result.output
            assert "(health endpoint unavailable)" not in result.output


def test_health_server_releases_port(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "test.db")
    store.initialize()
    try:
        with _running_health_server(store, monkeypatch) as server:
            host, port = server.server_address

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, port))
        finally:
            probe.close()
    finally:
        store.close()


def test_healthcheck_uses_published_endpoint_and_instance(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from dincli.dind.lock import acquire_state_lock, release_state_lock
    from dincli.dind.main import app
    from dincli.dind.paths import StateDirs

    paths = StateDirs(tmp_path)
    runner = CliRunner()
    args = ["healthcheck", "--state-dir", str(tmp_path)]
    with ExitStack() as cleanup:
        store = StateStore(paths.db_path)
        cleanup.callback(store.close)
        lock = acquire_state_lock(paths.lock_path)
        assert lock is not None
        cleanup.callback(release_state_lock, lock)
        with _running_health_server(store, monkeypatch) as server:
            # Keep one independent client connected across both probe and shutdown.
            cleanup.enter_context(socket.create_connection(server.server_address))
            assert runner.invoke(app, args).exit_code == 0
            store.set_meta("health_instance", "different-instance")
            assert runner.invoke(app, args).exit_code == 1
            store.set_meta("health_instance", server.instance_id)
            store.set_meta("last_tick", "2025-01-01T00:00:00+00:00")
            result = runner.invoke(app, args)
            assert result.exit_code == 1
            assert "503" in result.output


# ---------------------------------------------------------------------------
# Issue #345: config/RPC/signer checks and per-model GI phase
# ---------------------------------------------------------------------------

_MODEL = "0x6Ce502a2E01e2828B692983A8c206E187119753d"
_SECRET_URL = "https://rpc.example/v3/SECRET-API-KEY"


class _Call:
    def __init__(self, value, block):
        self._value = value
        self._block = block

    def call(self, *, block_identifier):
        assert block_identifier == self._block
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class _FakeChain:
    """Stands in for w3: block number plus GI()/GIstate() per coordinator."""

    def __init__(self, gi=2, state=6, block=123):
        self.gi, self.state, self.block = gi, state, block
        outer = self

        class _Eth:
            @property
            def block_number(self):
                return outer.block

            def contract(self, address, abi):
                class _Functions:
                    def GI(self):
                        return _Call(outer.gi, outer.block)

                    def GIstate(self):
                        return _Call(outer.state, outer.block)

                class _Contract:
                    functions = _Functions()

                return _Contract()

        self.eth = _Eth()


class _FakeSigner:
    def __init__(self, ok=True):
        self.ok = ok

    def can_decrypt(self):
        return self.ok


class _FakeSession:
    def __init__(self, chain=None, signer=None, network="local", w3_error=None):
        self._chain = chain if chain is not None else _FakeChain()
        self.signer = signer if signer is not None else _FakeSigner()
        self.network = network
        self._w3_error = w3_error

    @property
    def w3(self):
        if self._w3_error is not None:
            raise self._w3_error
        return self._chain


def _ok_rpc_config(monkeypatch):
    monkeypatch.setattr(
        "dincli.sdk.config.resolve_network_value",
        lambda network, key: _SECRET_URL,
    )


def _health_body(store, monitor):
    handler, wfile = _make_handler(store)
    handler.server.chain_monitor = monitor
    handler.do_GET()
    response = wfile.getvalue()
    return _status_line(response), json.loads(response.split(b"\r\n\r\n", 1)[1])


def _fresh_tick(store):
    from datetime import datetime, timezone

    store.set_meta("last_tick", datetime.now(timezone.utc).isoformat())


def test_health_reports_gi_phase_per_model(tmp_path, monkeypatch):
    _ok_rpc_config(monkeypatch)
    store = StateStore(tmp_path / "test.db")
    _fresh_tick(store)
    monitor = ChainHealthMonitor([_MODEL], session=_FakeSession())
    monitor.refresh()

    status_line, body = _health_body(store, monitor)

    assert b"200" in status_line
    assert body["status"] == "healthy"
    assert body["checks"]["config"] == {"ok": True, "network": "local"}
    assert body["checks"]["rpc"] == {"ok": True, "block": 123}
    assert body["checks"]["signer"] == {"ok": True}
    [model] = body["models"]
    assert model["coordinator"] == _MODEL
    assert model["gi"] == 2
    assert model["state"] == "DINaggregatorsRegistrationStarted"
    assert model["state_code"] == 6
    assert model["observed_for_s"] >= 0
    store.close()


def test_health_unreachable_rpc_is_unhealthy_503(tmp_path, monkeypatch):
    _ok_rpc_config(monkeypatch)
    store = StateStore(tmp_path / "test.db")
    _fresh_tick(store)
    error = NetworkError(f"could not reach {_SECRET_URL}", code="rpc_unreachable")
    monitor = ChainHealthMonitor([_MODEL], session=_FakeSession(w3_error=error))
    monitor.refresh()

    status_line, body = _health_body(store, monitor)

    assert b"503" in status_line
    assert body["status"] == "unhealthy"
    assert body["checks"]["rpc"] == {"ok": False, "error": "rpc_unreachable"}
    assert body["models"] == [{"coordinator": _MODEL, "error": "rpc_unavailable"}]
    assert "SECRET" not in json.dumps(body)
    store.close()


def test_health_missing_signer_is_unhealthy_503(tmp_path, monkeypatch):
    _ok_rpc_config(monkeypatch)
    store = StateStore(tmp_path / "test.db")
    _fresh_tick(store)
    session = _FakeSession(signer=_FakeSigner(ok=False))
    monitor = ChainHealthMonitor([], session=session)
    monitor.refresh()

    status_line, body = _health_body(store, monitor)

    assert b"503" in status_line
    assert body["status"] == "unhealthy"
    assert body["checks"]["signer"] == {"ok": False, "error": "signer_unavailable"}
    assert body["checks"]["rpc"]["ok"] is True
    store.close()


def test_health_signer_error_never_leaks_message(tmp_path, monkeypatch):
    _ok_rpc_config(monkeypatch)

    class _RaisingSigner:
        def can_decrypt(self):
            raise RuntimeError("password=hunter2 keystore={...}")

    store = StateStore(tmp_path / "test.db")
    _fresh_tick(store)
    monitor = ChainHealthMonitor([], session=_FakeSession(signer=_RaisingSigner()))
    monitor.refresh()

    _, body = _health_body(store, monitor)

    assert body["checks"]["signer"] == {"ok": False, "error": "signer_unavailable"}
    assert "hunter2" not in json.dumps(body)
    store.close()


def test_health_missing_rpc_config_is_unhealthy(tmp_path, monkeypatch):
    def missing(network, key):
        raise KeyError("rpc_url not set for network 'local'")

    monkeypatch.setattr("dincli.sdk.config.resolve_network_value", missing)
    store = StateStore(tmp_path / "test.db")
    _fresh_tick(store)
    monitor = ChainHealthMonitor([], session=_FakeSession())
    monitor.refresh()

    status_line, body = _health_body(store, monitor)

    assert b"503" in status_line
    assert body["checks"]["config"] == {"ok": False, "error": "config_error"}
    assert body["checks"]["rpc"] == {"ok": False, "error": "config_error"}
    store.close()


def test_health_model_read_failure_is_unhealthy(tmp_path, monkeypatch):
    _ok_rpc_config(monkeypatch)
    chain = _FakeChain(gi=ValueError("not a coordinator"))
    store = StateStore(tmp_path / "test.db")
    _fresh_tick(store)
    monitor = ChainHealthMonitor([_MODEL], session=_FakeSession(chain=chain))
    monitor.refresh()

    status_line, body = _health_body(store, monitor)

    assert b"503" in status_line
    assert body["models"] == [{"coordinator": _MODEL, "error": "model_read_failed"}]
    store.close()


def test_health_before_first_refresh_is_unhealthy(tmp_path):
    store = StateStore(tmp_path / "test.db")
    _fresh_tick(store)
    monitor = ChainHealthMonitor([_MODEL], session=_FakeSession())

    status_line, body = _health_body(store, monitor)

    assert b"503" in status_line
    assert body["checks"]["rpc"] == {"ok": False, "error": "checks_pending"}
    store.close()


def test_health_stale_snapshot_is_unhealthy(tmp_path, monkeypatch):
    _ok_rpc_config(monkeypatch)
    store = StateStore(tmp_path / "test.db")
    _fresh_tick(store)
    monitor = ChainHealthMonitor([_MODEL], session=_FakeSession(), interval_s=1.0)
    monitor.refresh()
    snap, taken = monitor._latest
    monitor._latest = (snap, taken - 60)  # refresh thread hung for a minute

    status_line, body = _health_body(store, monitor)

    assert b"503" in status_line
    assert body["checks"]["rpc"] == {"ok": False, "error": "checks_stale"}
    store.close()


def test_observed_since_holds_until_state_changes(monkeypatch):
    _ok_rpc_config(monkeypatch)
    chain = _FakeChain(gi=2, state=6)
    monitor = ChainHealthMonitor([_MODEL], session=_FakeSession(chain=chain))

    first = monitor.refresh()["models"][0]["observed_since"]
    time.sleep(0.01)
    assert monitor.refresh()["models"][0]["observed_since"] == first

    chain.state = 10
    model = monitor.refresh()["models"][0]
    assert model["state"] == "LMSstarted"
    assert model["observed_since"] != first


def test_resolve_health_models_env(monkeypatch):
    lower = _MODEL.lower()
    monkeypatch.setenv("DIN_DIND_HEALTH_MODELS", f" {lower}, ,{_MODEL} ")
    assert dind_config.resolve_health_models() == [_MODEL]


def test_resolve_health_models_config_list(monkeypatch):
    monkeypatch.delenv("DIN_DIND_HEALTH_MODELS", raising=False)
    monkeypatch.setattr(
        dind_config, "load_config", lambda: {"dind_health_models": [_MODEL]}
    )
    assert dind_config.resolve_health_models() == [_MODEL]


def test_resolve_health_models_default_empty(monkeypatch):
    monkeypatch.delenv("DIN_DIND_HEALTH_MODELS", raising=False)
    monkeypatch.setattr(dind_config, "load_config", lambda: {})
    assert dind_config.resolve_health_models() == []


def test_resolve_health_models_rejects_bad_address(monkeypatch):
    monkeypatch.setenv("DIN_DIND_HEALTH_MODELS", "0x1234")
    with pytest.raises(ValueError, match="not a valid address"):
        dind_config.resolve_health_models()
