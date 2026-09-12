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
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

from dincli.dind.capabilities import resource_snapshot
from dincli.dind.state import StateStore

logger = logging.getLogger("dincli")

# See the module docstring: 503 marks degraded so a plain liveness probe can
# tell without parsing JSON. It is a reporting signal only.
_DEGRADED_STATUS_CODE = 503


class _ThreadingHTTPServer(HTTPServer):
    daemon_threads = True


class HealthHandler(BaseHTTPRequestHandler):
    state: StateStore = None
    start_time: float = 0.0
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

    def _build_payload(self) -> dict:
        now_ts = time.time()
        uptime_s = int(now_ts - self.start_time)
        pid = os.getpid()

        last_tick = self.state.get_meta("last_tick")
        last_success = self.state.get_meta("last_success")

        status = "healthy"
        if last_tick:
            tick_dt = datetime.fromisoformat(last_tick)
            age = (datetime.now(timezone.utc) - tick_dt).total_seconds()
            if age > self.stale_seconds:
                status = "degraded"

        queue = self.state.get_job_counts()

        state_dir = self.state.db_path.parent
        snap = resource_snapshot(state_dir)

        return {
            "status": status,
            "uptime_s": uptime_s,
            "pid": pid,
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


class HealthServer:
    def __init__(self, host: str, port: int, state: StateStore):
        self.host = host
        self.port = port
        self.state = state

    def run(self) -> None:
        HealthHandler.state = self.state
        HealthHandler.start_time = time.time()

        self.server = _ThreadingHTTPServer((self.host, self.port), HealthHandler)

        actual_host, actual_port = self.server.server_address
        self.state.set_meta("health_host", actual_host)
        self.state.set_meta("health_port", str(actual_port))

        logger.info("Health server listening on %s:%d", actual_host, actual_port)
        try:
            self.server.serve_forever(poll_interval=0.5)
        finally:
            self.server.server_close()

    def shutdown(self) -> None:
        if hasattr(self, "server") and self.server:
            self.server.shutdown()
            self.server.server_close()
