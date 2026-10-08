"""Service ownership tests; these never start chain/IPFS nodes or contact them."""

import signal
import socket
import subprocess
import os
import sys
from unittest.mock import Mock

import pytest
import requests

from tests.dincli import services


@pytest.fixture
def harness(monkeypatch, tmp_path):
    process = Mock(pid=24680)
    process.poll.return_value = None
    process.wait.return_value = 0
    popen = Mock(return_value=process)
    killpg = Mock()
    monkeypatch.setattr(services.subprocess, "Popen", popen)
    monkeypatch.setattr(services.os, "killpg", killpg)
    clock = [0.0]
    monkeypatch.setattr(services.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(services.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))

    def start(ready=lambda: True, timeout=1, **kwargs):
        return services.start_service(
            ["fake-service", "--flag"], tmp_path, {"PATH": "/bin"},
            tmp_path / "service.log", ready, timeout=timeout, **kwargs,
        )

    return process, popen, killpg, clock, start, tmp_path / "service.log"


def assert_closed(process, popen, killpg):
    assert popen.call_args.kwargs["stdout"].closed
    assert killpg.call_args_list == [
        ((process.pid, signal.SIGTERM),),
        ((process.pid, signal.SIGKILL),),
    ]
    assert all(call.kwargs["timeout"] == 5 for call in process.wait.call_args_list)


def test_ready_service_has_its_own_session_and_idempotent_cleanup(harness):
    process, popen, killpg, _, start, log_path = harness
    service = start()
    assert service.process is process
    assert service.log_path == log_path
    assert popen.call_args.kwargs["start_new_session"] is True
    assert popen.call_args.kwargs["stderr"] == subprocess.STDOUT
    assert not popen.call_args.kwargs["stdout"].closed
    with service:
        pass
    service.close()
    assert_closed(process, popen, killpg)
    assert log_path.exists()


def test_timeout_cleans_up_and_retains_diagnostic_log(harness):
    process, popen, killpg, clock, start, log_path = harness

    def unready():
        popen.call_args.kwargs["stdout"].write("startup diagnostics\n")
        return False

    with pytest.raises(RuntimeError, match="timed out"):
        start(unready, timeout=0.25)
    assert clock[0] == pytest.approx(0.25)
    assert_closed(process, popen, killpg)
    assert "startup diagnostics" in log_path.read_text()


@pytest.mark.parametrize("poll_results", [[9], [None, 9]])
def test_child_exit_is_failure_even_when_probe_returns_true(harness, poll_results):
    process, popen, killpg, _, start, _ = harness
    process.poll.side_effect = poll_results
    probe = Mock(return_value=True)
    with pytest.raises(RuntimeError, match="exited"):
        start(probe)
    assert probe.call_count == len(poll_results) - 1
    assert_closed(process, popen, killpg)


def test_occupied_port_is_rejected_without_spawning(harness):
    _, popen, killpg, _, start, log_path = harness
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(RuntimeError, match="port .* unavailable"):
            start(port=listener.getsockname()[1])
    popen.assert_not_called()
    killpg.assert_not_called()
    assert not log_path.exists()


def test_probe_exception_cleans_up(harness):
    process, popen, killpg, _, start, log_path = harness
    with pytest.raises(RuntimeError, match="broken probe"):
        start(Mock(side_effect=ValueError("broken probe")))
    assert_closed(process, popen, killpg)
    assert log_path.exists()


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_startup_interruption_cleans_up_before_ownership_transfer(harness, interruption):
    process, popen, killpg, _, start, log_path = harness
    with pytest.raises(interruption):
        start(Mock(side_effect=interruption()))
    assert_closed(process, popen, killpg)
    assert log_path.exists()


def test_start_failure_closes_log_without_signalling(harness):
    _, popen, killpg, _, start, log_path = harness
    popen.side_effect = OSError("missing executable")
    with pytest.raises(RuntimeError, match="missing executable"):
        start()
    assert popen.call_args.kwargs["stdout"].closed
    killpg.assert_not_called()
    assert log_path.exists()


def test_cleanup_escalates_when_parent_does_not_exit(harness):
    process, popen, killpg, _, start, _ = harness
    service = start()
    process.wait.side_effect = [subprocess.TimeoutExpired("fake-service", 5), 0]
    service.close()
    assert_closed(process, popen, killpg)
    assert process.wait.call_count == 2


def test_already_exited_group_does_not_prevent_cleanup(harness):
    process, popen, killpg, _, start, _ = harness
    service = start()
    killpg.side_effect = ProcessLookupError
    service.close()
    assert_closed(process, popen, killpg)


def test_probe_cannot_return_success_after_deadline(harness):
    process, popen, killpg, clock, start, _ = harness

    def slow_probe():
        clock[0] = 2
        return True

    with pytest.raises(RuntimeError, match="timed out"):
        start(slow_probe)
    assert_closed(process, popen, killpg)


def test_real_child_is_reaped_and_log_preserved(tmp_path):
    log_path = tmp_path / "real-service.log"
    service = services.start_service(
        [sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"],
        tmp_path, os.environ.copy(), log_path,
        lambda: log_path.read_text().strip() == "ready", timeout=5,
    )
    try:
        assert os.getpgid(service.process.pid) == service.process.pid
    finally:
        service.close()
    assert service.process.poll() is not None
    assert log_path.read_text().strip() == "ready"


@pytest.mark.parametrize("body, expected", [
    ({"jsonrpc": "2.0", "id": 1, "result": "0x539"}, True),
    ({"jsonrpc": "2.0", "id": 1, "result": "0x1"}, False),
    ({"jsonrpc": "2.0", "id": 1, "result": "0x539", "error": {}}, False),
    ({"jsonrpc": "2.0", "id": 2, "result": "0x539"}, False),
    ({"id": 1, "result": "0x539"}, False),
    ({"jsonrpc": "2.0", "id": 1, "result": 1337}, False),
    ({"jsonrpc": "2.0", "id": 1, "result": "0xnope"}, False),
    ({"jsonrpc": "2.0", "id": 1, "result": "0x539 "}, False),
    ({"jsonrpc": "2.0", "id": True, "result": "0x539"}, False),
    ([], False),
])
def test_rpc_requires_matching_jsonrpc_chain(monkeypatch, body, expected):
    response = Mock(status_code=200)
    response.json.return_value = body
    post = Mock(return_value=response)
    monkeypatch.setattr(services.requests, "post", post)
    assert services.rpc_ready("http://local.invalid") is expected
    assert post.call_args.kwargs["timeout"] == 3
    assert post.call_args.kwargs["json"]["method"] == "eth_chainId"


@pytest.mark.parametrize("body, expected", [
    ({"Version": "0.32.1"}, True), ({"Version": ""}, False),
    ({"Version": "  "}, False), ({"Version": 1}, False), ({}, False), ([], False),
])
def test_ipfs_requires_nonempty_version(monkeypatch, body, expected):
    response = Mock(status_code=200)
    response.json.return_value = body
    post = Mock(return_value=response)
    monkeypatch.setattr(services.requests, "post", post)
    assert services.ipfs_ready() is expected
    assert post.call_args.kwargs["timeout"] == 3


@pytest.mark.parametrize("probe", [services.rpc_ready, services.ipfs_ready])
@pytest.mark.parametrize("failure", ["http", "json", "network"])
def test_readiness_handles_failed_http_json_and_network(monkeypatch, probe, failure):
    response = Mock(status_code=503 if failure == "http" else 200)
    response.json.side_effect = ValueError("invalid JSON")
    post = Mock(return_value=response)
    if failure == "network":
        post.side_effect = requests.ConnectionError("unreachable")
    monkeypatch.setattr(services.requests, "post", post)
    assert probe("http://local.invalid") is False
