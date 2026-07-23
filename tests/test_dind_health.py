"""Tests for dind/health.py — payload shape + degraded detection."""

import json
import time
from io import BytesIO

from dincli.dind.health import HealthHandler
from dincli.dind.state import StateStore


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


def test_health_payload_shape(tmp_path):
    store = StateStore(tmp_path / "test.db")
    store.set_meta("last_tick", "2025-01-01T00:00:00+00:00")

    handler, wfile = _make_handler(store)

    handler.do_GET()
    response = wfile.getvalue()
    assert b"HTTP/1.0 200" in response or b"200" in response

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
