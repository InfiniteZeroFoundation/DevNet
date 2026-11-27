"""HTTP /health endpoint — stdlib ThreadingHTTPServer, one JSON handler.

Records the actually-bound host/port in ``daemon_meta`` so ``status`` can
find the endpoint even with ephemeral ports.

BL-20: a "degraded" body (``last_tick`` older than ``stale_seconds``) is
served with HTTP 503, not 200, so a plain liveness probe (``curl -f``, a
container orchestrator's healthcheck) can tell the two states apart without
parsing JSON. This REPORTS degradation; it does not trigger a restart.
Docker Compose's ``restart:`` policy only reacts to container termination,
not health status — that only drives restarts in Swarm — so this was never
going to auto-restart the daemon regardless of status code. And restarting
on "degraded" would be wrong even if it could: a stale ``last_tick`` means
the loop is behind schedule, not stopped, and auto-restarting on
behind-schedule risks a restart loop under sustained load while destroying
the state needed to diagnose a hung loop. A genuinely stopped process is
what ``restart: unless-stopped`` already covers. Operators who want
restart-on-unhealthy need an external watchdog acting on the 503.

Issue #345: when a ChainHealthMonitor is attached, the body also carries the
config/RPC/signer checks and each configured model's GI + phase. A failed
check is "unhealthy" (also 503). The handler only reads the monitor's latest
snapshot; the network calls happen on the monitor's own thread.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from dincli.dind.capabilities import resource_snapshot
from dincli.dind.chain_health import snapshot_is_healthy
from dincli.dind.state import StateStore

logger = logging.getLogger("dincli")

# See the module docstring: 503 marks degraded so a plain liveness probe can
# tell without parsing JSON. It is a reporting signal only.
_DEGRADED_STATUS_CODE = 503


class HealthHandler(BaseHTTPRequestHandler):
    timeout = 5
    server: "HealthServer"
    stale_seconds: float = 30.0

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return

        try:
            payload = self._build_payload()
            body = json.dumps(payload).encode("utf-8")
            code = (
                200
                if payload["status"] == "healthy"
                else _DEGRADED_STATUS_CODE
            )
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            logger.exception("Health endpoint error")
            self.send_error(500)
        finally:
            self.server.state.close()  # Release this request thread's SQLite connection.

    def _build_payload(self) -> dict:
        now_ts = time.time()
        uptime_s = int(now_ts - self.server.start_time)
        pid = os.getpid()

        last_tick = self.server.state.get_meta("last_tick")
        last_success = self.server.state.get_meta("last_success")

        status = "healthy"
        if last_tick:
            tick_dt = datetime.fromisoformat(last_tick)
            age = (datetime.now(timezone.utc) - tick_dt).total_seconds()
            if age > self.stale_seconds:
                status = "degraded"

        queue = self.server.state.get_job_counts()

        state_dir = self.server.state.db_path.parent
        snap = resource_snapshot(state_dir)

        chain = None
        monitor = getattr(self.server, "chain_monitor", None)
        if monitor is not None:
            chain = monitor.snapshot()
            if not snapshot_is_healthy(chain):
                status = "unhealthy"

        payload = {
            "status": status,
            "uptime_s": uptime_s,
            "pid": pid,
            "instance_id": self.server.instance_id,
            "last_tick": last_tick,
            "last_success": last_success,
            "queue": queue,
            "resources": {
                "cpu_count": snap["cpu_count"],
                "disk_free_bytes": snap["disk_free_bytes"],
                "disk_total_bytes": snap["disk_total_bytes"],
                "ram_total_bytes": snap["ram_total_bytes"],
                "ram_free_bytes": snap["ram_free_bytes"],
                "cpu_speed_mhz": snap["cpu_speed_mhz"],
            },
        }
        if chain is not None:
            payload["checked_at"] = chain["checked_at"]
            payload["checks"] = chain["checks"]
            payload["models"] = chain["models"]
        return payload


class HealthServer(ThreadingHTTPServer):
    def __init__(self, host: str, port: int, state: StateStore):
        super().__init__((host, port), HealthHandler)
        self.state = state
        self.start_time = time.time()
        self.instance_id = uuid4().hex
        self.chain_monitor = None  # set by `dind start` (issue #345)

    def publish_endpoint(self) -> None:
        host, port = self.server_address
        self.state.set_meta("health_host", host)
        self.state.set_meta("health_port", str(port))
        self.state.set_meta("health_instance", self.instance_id)
        logger.info("Health server listening on %s:%d", host, port)
