"""Job dataclass, status enum, handler registry, and job execution context."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from dincli.dind.state import StateStore
from dincli.sdk.operations.platform import get_stake
from dincli.sdk.serialize import to_envelope
from dincli.sdk.session import DinSession


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    type: str
    payload: dict = field(default_factory=dict)
    id: int | None = None
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0


@dataclass
class JobContext:
    """Per-tick execution context handed to every job handler.

    ``session`` is never None. ``DaemonLoop`` constructs a bare ``DinSession()``
    when none is supplied at construction time, so a handler can always read
    ``ctx.session`` without a None check. Every ``DinSession`` property is
    lazy, so this costs nothing at construction and touches neither the chain
    nor the keystore until a handler actually reads ``.network``/``.w3``/
    ``.address``.
    """

    state: StateStore
    session: DinSession


JOB_HANDLERS: dict[str, Callable] = {}


def register_handler(job_type: str):
    def decorator(fn):
        JOB_HANDLERS[job_type] = fn
        return fn

    return decorator


@register_handler("demo")
def demo_handler(job: Job, ctx: JobContext) -> None:
    pass


@register_handler("read_stake")
def read_stake_handler(job: Job, ctx: JobContext) -> dict:
    # payload: {"address": "0x..."} — an explicit address needs no keystore.
    # No address falls back to ctx.session.address, which raises
    # SignerUnavailable when no non-interactive password source exists;
    # DaemonLoop, not this handler, turns that into a job error (§3.7).
    return to_envelope(
        get_stake(ctx.session, address=job.payload.get("address")),
        network=ctx.session.network,
    )
