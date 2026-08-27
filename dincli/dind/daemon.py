"""Scheduler loop with injectable stop_event/max_ticks for testability.

Heartbeat = direct ``daemon_meta.last_tick`` update (not a queue row).
Each tick: heartbeat, then claim/dispatch one pending job.
"""

import json
import logging
import time
from datetime import datetime, timezone
from threading import Event

from dincli.dind.jobs import JOB_HANDLERS, Job
from dincli.dind.state import StateStore

logger = logging.getLogger("dincli")


class DaemonLoop:
    def __init__(
        self,
        state: StateStore,
        stop_event: Event,
        tick_interval: float = 1.0,
        max_ticks: int | None = None,
    ):
        self.state = state
        self._stop = stop_event
        self.tick_interval = tick_interval
        self.max_ticks = max_ticks
        self.tick_count = 0

    def run(self) -> None:
        while not self._stop.is_set():
            if self.max_ticks is not None and self.tick_count >= self.max_ticks:
                break

            self._tick()
            self.tick_count += 1

            self._stop.wait(self.tick_interval)

    def _tick(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.state.set_meta("last_tick", now)

        row = self.state.claim_next()
        if row is None:
            return

        job = Job(
            type=row["type"],
            payload=json.loads(row.get("payload", "{}")),
            id=row["id"],
        )

        handler = JOB_HANDLERS.get(job.type)
        if handler is None:
            self.state.fail_job(job.id, f"No handler for job type: {job.type}")
            return

        try:
            handler(job)
            self.state.complete_job(job.id)
            self.state.set_meta("last_success", now)
        except Exception as e:
            self.state.fail_job(job.id, str(e))
