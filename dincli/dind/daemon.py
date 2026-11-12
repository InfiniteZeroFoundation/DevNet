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
            self._fail(job.id, e.code, e)
            return
        except Exception as e:
            self._fail(job.id, _INTERNAL_ERROR_CODE, _bound_internal_error(e))
            return

        try:
            result_json = json.dumps(result) if result is not None else None
        except (TypeError, ValueError) as e:
            # A handler's return value is the last thing standing between a
            # "successful" job and one that never persisted a usable result.
            # This boundary sat outside the try/except above until review
            # finding 3 — an unserializable result raised here, unguarded,
            # would kill the loop exactly like the two branches above.
            self._fail(job.id, _INTERNAL_ERROR_CODE, _bound_internal_error(e))
            return

        self.state.complete_job(job.id, result=result_json)
        self.state.set_meta("last_success", now)

    def _fail(self, job_id: int, code: str, error: DinError) -> None:
        """Persist a job failure. Never depends on resolving any session
        property: if that fails too — e.g. the original failure *was*
        network resolution, or a config file became unreadable after the
        session was built but before it first resolved a network — the
        envelope simply omits `meta.network` (an already-optional field)
        rather than letting a second, unhandled exception escape from an
        exception handler and kill the loop (review finding 3)."""
        network = _safe_network(self._ctx.session)
        envelope = to_envelope(error=error, network=network)
        self.state.fail_job(job_id, code, result=json.dumps(envelope))


def _bound_internal_error(e: Exception) -> DinError:
    message = str(e)
    if len(message) > _MAX_INTERNAL_ERROR_MESSAGE:
        message = message[:_MAX_INTERNAL_ERROR_MESSAGE] + "…"
    return DinError(message, code=_INTERNAL_ERROR_CODE)


def _safe_network(session: DinSession) -> str | None:
    """Best-effort ``session.network`` for error-envelope metadata.

    Deliberately never raises. ``network`` is a lazy property that itself
    performs config/network resolution, so reading it can fail for exactly
    the same reasons a job handler just failed — including, but not limited
    to, the original failure. Swallowing that here (rather than propagating
    it) is what lets ``_fail()`` be called unconditionally from every
    failure branch in ``_tick()``.
    """
    try:
        return session.network
    except Exception:
        return None
