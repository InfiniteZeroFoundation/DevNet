import glob
import logging
import os
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dincli.sdk.config import (
    resolve_ipfs_config,
    resolve_network,
    resolve_network_value,
)

logger = logging.getLogger("dincli")


@dataclass
class CapabilitySummary:
    cpu_count: int
    cpu_speed_mhz: int | None
    ram_total_bytes: int | None
    ram_free_bytes: int | None
    disk_free_bytes: int | None
    disk_total_bytes: int | None
    gpu_available: bool
    rpc_reachable: bool | None
    ipfs_reachable: bool | None


def resource_snapshot(state_dir: Path) -> dict:
    cpu_count = os.cpu_count()

    cpu_speed_mhz = _detect_cpu_speed_mhz()

    ram_total = _detect_ram_total_bytes()
    ram_free = _detect_ram_free_bytes()

    disk_free = None
    disk_total = None
    try:
        disk = shutil.disk_usage(str(state_dir))
        disk_free = disk.free
        disk_total = disk.total
    except OSError:
        pass

    return {
        "cpu_count": cpu_count,
        "cpu_speed_mhz": cpu_speed_mhz,
        "ram_total_bytes": ram_total,
        "ram_free_bytes": ram_free,
        "disk_free_bytes": disk_free,
        "disk_total_bytes": disk_total,
    }


def detect_capabilities(state_dir: str | Path | None = None) -> CapabilitySummary:
    resolved = Path(state_dir) if state_dir else Path.cwd()
    snap = resource_snapshot(resolved)

    gpu = _detect_gpu_available()

    rpc_reachable = _probe_rpc_endpoint()
    ipfs_reachable = _probe_ipfs_endpoint()

    return CapabilitySummary(
        cpu_count=snap["cpu_count"],
        cpu_speed_mhz=snap["cpu_speed_mhz"],
        ram_total_bytes=snap["ram_total_bytes"],
        ram_free_bytes=snap["ram_free_bytes"],
        disk_free_bytes=snap["disk_free_bytes"],
        disk_total_bytes=snap["disk_total_bytes"],
        gpu_available=gpu,
        rpc_reachable=rpc_reachable,
        ipfs_reachable=ipfs_reachable,
    )


def score_capabilities(summary: CapabilitySummary) -> int:
    score = 0
    if summary.cpu_count and summary.cpu_count >= 4:
        score += 20
    elif summary.cpu_count and summary.cpu_count >= 2:
        score += 10
    if summary.cpu_speed_mhz and summary.cpu_speed_mhz >= 2000:
        score += 15
    elif summary.cpu_speed_mhz:
        score += 5
    if summary.ram_total_bytes and summary.ram_total_bytes >= 16 * 1024**3:
        score += 20
    elif summary.ram_total_bytes and summary.ram_total_bytes >= 8 * 1024**3:
        score += 10
    if summary.gpu_available:
        score += 25
    if summary.rpc_reachable:
        score += 10
    if summary.ipfs_reachable:
        score += 10
    return score


def compatible_with(summary: CapabilitySummary, requirements: dict) -> bool:
    if requirements.get("requires_gpu") and not summary.gpu_available:
        return False
    min_ram = requirements.get("min_ram_bytes")
    if min_ram is not None and summary.ram_total_bytes is not None:
        if summary.ram_total_bytes < min_ram:
            return False
    min_disk = requirements.get("min_disk_bytes")
    if min_disk is not None and summary.disk_free_bytes is not None:
        if summary.disk_free_bytes < min_disk:
            return False
    return True


def _detect_cpu_speed_mhz() -> int | None:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("cpu MHz"):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        return int(float(parts[1].strip()))
    except (OSError, ValueError):
        pass
    return None


def _detect_ram_total_bytes() -> int | None:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        return page_size * phys_pages
    except (ValueError, OSError, AttributeError):
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        val = int(line.split(":")[1].strip().split()[0])
                        return val * 1024
        except (OSError, ValueError):
            pass
    return None


def _detect_ram_free_bytes() -> int | None:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable"):
                    val = int(line.split(":")[1].strip().split()[0])
                    return val * 1024
    except (OSError, ValueError):
        pass
    return None


def _detect_gpu_available() -> bool:
    if shutil.which("nvidia-smi") is not None:
        return True
    if glob.glob("/dev/nvidia*"):
        return True
    return False


def _probe_rpc_endpoint() -> bool | None:
    try:
        network = resolve_network()
        rpc_url = resolve_network_value(network, "rpc_url")
    except (KeyError, ValueError):
        return None

    if not rpc_url:
        return None

    try:
        return _socket_probe(rpc_url)
    except Exception:
        return False


def _probe_ipfs_endpoint() -> bool | None:
    try:
        ipfs_config = resolve_ipfs_config()
    except Exception:
        return None

    api_url = ipfs_config.api_url_add
    if not api_url:
        return None

    try:
        return _socket_probe(api_url)
    except Exception:
        return False


def _socket_probe(url: str, timeout: float = 2.0) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port
    if port is None:
        if parsed.scheme == "https":
            port = 443
        elif parsed.scheme == "http":
            port = 80
        else:
            return False
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False
