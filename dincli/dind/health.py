"""HTTP /health endpoint — stdlib ThreadingHTTPServer, one JSON handler.

Records the actually-bound host/port in ``daemon_meta`` so ``status`` can
find the endpoint even with ephemeral ports.
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
            self.send_response(200)
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
