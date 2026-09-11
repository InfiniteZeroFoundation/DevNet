"""Scheduler loop with injectable stop_event/max_ticks for testability.

Heartbeat = direct ``daemon_meta.last_tick`` update (not a queue row).
Each tick: heartbeat, then claim/dispatch one pending job.
"""

import json
import logging
from datetime import datetime, timezone
from threading import Event

from dincli.dind.jobs import JOB_HANDLERS, Job, JobContext
from dincli.dind.state import StateStore
from dincli.sdk.errors import DinError
from dincli.sdk.serialize import to_envelope
from dincli.sdk.session import DinSession

logger = logging.getLogger("dincli")

# Not part of the SDK's reserved-code taxonomy (dincli/sdk/errors.py) — this
# is a dind-only bound on what an unexpected handler exception can turn into,
# so an arbitrary traceback can never become an unbounded DB row.
_INTERNAL_ERROR_CODE = "internal_error"
_MAX_INTERNAL_ERROR_MESSAGE = 500


class DaemonLoop:
    def __init__(
        self,
        state: StateStore,
        stop_event: Event,
        tick_interval: float = 1.0,
        max_ticks: int | None = None,
        session: DinSession | None = None,
    ):
        self.state = state
        self._stop = stop_event
        self.tick_interval = tick_interval
        self.max_ticks = max_ticks
        self.tick_count = 0
        # session=None -> a bare DinSession(). Every DinSession property is
        # lazy, so this touches neither the chain nor the keystore until a
        # handler actually reads .network/.w3/.address (§3.7).
        self._ctx = JobContext(
            state=state,
            session=session if session is not None else DinSession(),
        )

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

        # DaemonLoop owns result persistence, not the handler: a handler
        # returns a success envelope and neither persists nor catches. This
        # is the only place that writes an error's stable `code` into
        # last_error — str(DinError) is the message, never the code, so the
        # retry policy needs this split, not `str(e)` at the call site.
        try:
            result = handler(job, self._ctx)
        except DinError as e:
            envelope = to_envelope(error=e, network=self._ctx.session.network)
            self.state.fail_job(job.id, e.code, result=json.dumps(envelope))
            return
        except Exception as e:
            message = str(e)
            if len(message) > _MAX_INTERNAL_ERROR_MESSAGE:
                message = message[:_MAX_INTERNAL_ERROR_MESSAGE] + "…"
            internal_error = DinError(message, code=_INTERNAL_ERROR_CODE)
            envelope = to_envelope(error=internal_error, network=self._ctx.session.network)
            self.state.fail_job(job.id, _INTERNAL_ERROR_CODE, result=json.dumps(envelope))
            return

        result_json = json.dumps(result) if result is not None else None
        self.state.complete_job(job.id, result=result_json)
        self.state.set_meta("last_success", now)
