"""Job dataclass, status enum, and handler registry."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


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


JOB_HANDLERS: dict[str, Callable] = {}


def register_handler(job_type: str):
    def decorator(fn):
        JOB_HANDLERS[job_type] = fn
        return fn

    return decorator


@register_handler("demo")
def demo_handler(job: Job) -> None:
    pass
