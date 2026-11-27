import json

from typer.testing import CliRunner

from dincli.dind.capabilities import (
    CapabilitySummary,
    _detect_cpu_speed_mhz,
    _detect_gpu_available,
    _detect_ram_free_bytes,
    _detect_ram_total_bytes,
    _socket_probe,
    compatible_with,
    detect_capabilities,
    resource_snapshot,
    score_capabilities,
)
from dincli.dind.main import app


def test_resource_snapshot_returns_expected_keys(tmp_path):
    snap = resource_snapshot(tmp_path)
    assert "cpu_count" in snap
    assert "cpu_speed_mhz" in snap
    assert "ram_total_bytes" in snap
    assert "ram_free_bytes" in snap
    assert "disk_free_bytes" in snap
    assert "disk_total_bytes" in snap
    assert isinstance(snap["cpu_count"], int)
    assert snap["disk_free_bytes"] is not None
    assert snap["disk_total_bytes"] is not None


def test_detect_capabilities_returns_summary(monkeypatch, tmp_path):
    # Keep the detect test hermetic: no live RPC/IPFS socket probes during the unit run.
    monkeypatch.setattr(
        "dincli.dind.capabilities._socket_probe", lambda *a, **k: False
    )
    summary = detect_capabilities(tmp_path)
    assert isinstance(summary, CapabilitySummary)
    assert isinstance(summary.cpu_count, int)
    assert summary.cpu_count > 0
    assert isinstance(summary.gpu_available, bool)
    assert summary.disk_free_bytes is not None
    assert summary.disk_total_bytes is not None


def test_detect_capabilities_no_state_dir_uses_cwd(monkeypatch):
    monkeypatch.setattr(
        "dincli.dind.capabilities._socket_probe", lambda *a, **k: False
    )
    summary = detect_capabilities()
    assert isinstance(summary, CapabilitySummary)
    assert summary.cpu_count is not None


def test_score_capabilities_baseline():
    summary = CapabilitySummary(
        cpu_count=1,
        cpu_speed_mhz=None,
        ram_total_bytes=4 * 1024**3,
        ram_free_bytes=2 * 1024**3,
        disk_free_bytes=10 * 1024**3,
        disk_total_bytes=100 * 1024**3,
        gpu_available=False,
        rpc_reachable=False,
        ipfs_reachable=False,
    )
    score = score_capabilities(summary)
    assert score == 0


def test_score_capabilities_full():
    summary = CapabilitySummary(
        cpu_count=8,
        cpu_speed_mhz=3000,
        ram_total_bytes=32 * 1024**3,
        ram_free_bytes=16 * 1024**3,
        disk_free_bytes=100 * 1024**3,
        disk_total_bytes=500 * 1024**3,
        gpu_available=True,
        rpc_reachable=True,
        ipfs_reachable=True,
    )
    score = score_capabilities(summary)
    assert score == 100


def test_score_capabilities_partial():
    summary = CapabilitySummary(
        cpu_count=2,
        cpu_speed_mhz=1500,
        ram_total_bytes=8 * 1024**3,
        ram_free_bytes=4 * 1024**3,
        disk_free_bytes=10 * 1024**3,
        disk_total_bytes=50 * 1024**3,
        gpu_available=False,
        rpc_reachable=True,
        ipfs_reachable=True,
    )
    score = score_capabilities(summary)
    assert 20 <= score <= 50, f"score={score}"


def test_compatible_with_requires_gpu():
    s = CapabilitySummary(1, None, None, None, None, None, False, None, None)
    assert compatible_with(s, {"requires_gpu": True}) is False
    assert compatible_with(s, {"requires_gpu": False}) is True
    s2 = CapabilitySummary(1, None, None, None, None, None, True, None, None)
    assert compatible_with(s2, {"requires_gpu": True}) is True


def test_compatible_with_ram_check():
    s = CapabilitySummary(1, None, 4 * 1024**3, None, None, None, False, None, None)
    assert compatible_with(s, {"min_ram_bytes": 8 * 1024**3}) is False
    assert compatible_with(s, {"min_ram_bytes": 2 * 1024**3}) is True
    assert compatible_with(s, {}) is True


def test_compatible_with_disk_check():
    s = CapabilitySummary(
        1, None, None, None, 10 * 1024**3, 100 * 1024**3, False, None, None
    )
    assert compatible_with(s, {"min_disk_bytes": 20 * 1024**3}) is False
    assert compatible_with(s, {"min_disk_bytes": 5 * 1024**3}) is True


def test_compatible_with_none_ram_total():
    s = CapabilitySummary(1, None, None, None, None, None, False, None, None)
    assert compatible_with(s, {"min_ram_bytes": 8 * 1024**3}) is True


def test_compatible_with_combined_constraints():
    s = CapabilitySummary(
        4, 2000, 16 * 1024**3, 8 * 1024**3, 50 * 1024**3, 200 * 1024**3,
        True, True, True,
    )
    assert compatible_with(
        s, {"requires_gpu": True, "min_ram_bytes": 12 * 1024**3, "min_disk_bytes": 40 * 1024**3}
    ) is True
    assert compatible_with(
        s, {"requires_gpu": True, "min_ram_bytes": 20 * 1024**3}
    ) is False


def test_capabilities_command_json_output(monkeypatch, tmp_path):
    state_dir = str(tmp_path)

    def mock_detect(sd):
        return CapabilitySummary(
            cpu_count=4, cpu_speed_mhz=2000,
            ram_total_bytes=8 * 1024**3, ram_free_bytes=4 * 1024**3,
            disk_free_bytes=50 * 1024**3, disk_total_bytes=100 * 1024**3,
            gpu_available=True, rpc_reachable=True, ipfs_reachable=True,
        )

    monkeypatch.setattr(
        "dincli.dind.capabilities.detect_capabilities", mock_detect
    )

    runner = CliRunner()
    result = runner.invoke(app, ["capabilities", "--state-dir", state_dir])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["cpu_count"] == 4
    assert data["gpu_available"] is True
    assert data["rpc_reachable"] is True
    assert data["ipfs_reachable"] is True


def test_socket_probe_unreachable():
    assert _socket_probe("https://192.0.2.1", timeout=0.1) is False


def test_socket_probe_missing_host():
    assert _socket_probe("some://") is False


def test_detect_cpu_speed_returns_int_or_none():
    result = _detect_cpu_speed_mhz()
    assert result is None or isinstance(result, int)


def test_detect_ram_total_returns_int_or_none():
    result = _detect_ram_total_bytes()
    assert result is None or isinstance(result, int)


def test_detect_ram_free_returns_int_or_none():
    result = _detect_ram_free_bytes()
    assert result is None or isinstance(result, int)


def test_detect_gpu_available_returns_bool(monkeypatch):
    monkeypatch.setattr(
        "dincli.dind.capabilities.shutil.which", lambda _cmd: None
    )
    monkeypatch.setattr(
        "dincli.dind.capabilities.glob.glob", lambda _p: []
    )
    assert _detect_gpu_available() is False
