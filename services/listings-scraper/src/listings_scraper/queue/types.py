"""Public types for the job queue module."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ErrorClass(str, Enum):
    """Classification supplied by callers to ``JobQueue.fail()``.

    The retry policy lives outside the queue module — workers map their
    underlying exceptions onto one of these values and the queue applies
    per-class retry limits read from env.
    """

    TRANSIENT = "transient"
    ANTIBOT = "antibot"
    PARSE = "parse"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEADLETTER = "deadletter"


@dataclass(slots=True)
class NewJob:
    """An unsubmitted job to enqueue."""

    suburb_id: int | None
    category: str
    filters: dict[str, Any] = field(default_factory=dict)
    scrape_list_id: int | None = None


@dataclass(slots=True)
class Job:
    """A persisted job row, returned by every public queue method."""

    id: int
    scrape_list_id: int | None
    suburb_id: int | None
    category: str
    filters: dict[str, Any]
    status: JobStatus
    attempts: int
    last_error_class: str | None
    last_error_message: str | None
    claimed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class UnknownJobError(LookupError):
    """Raised when a queue method is asked about a job_id that doesn't exist."""
