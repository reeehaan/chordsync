"""Decide whether to start one Fargate worker. Never touches the work itself.

It only reads SQS queue attributes, so it can't receive, delete or hide a
message. Any number of invocations start at most one task per lease window.

Order of checks:

1. Is there visible work? If not: no_work.
2. Is a worker already active? If so: worker_already_active.
3. Take the DynamoDB lease. If not acquired: lock_not_acquired.
4. Recheck for active workers while holding the lease.
5. RunTask. On success the lease is kept as a short cool-down (ECS lists new
   tasks late); on failure it is released.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

logger = logging.getLogger("chordsync.dispatcher")
# Lambda's root logger is at WARNING, which dropped our INFO events. Set the
# level on this logger only (not boto3 or the root logger).
logger.setLevel(logging.INFO)

REASON_JOB_DISPATCHED = "job_dispatched"
REASON_SCHEDULED = "scheduled_reconcile"
KNOWN_REASONS = frozenset({REASON_JOB_DISPATCHED, REASON_SCHEDULED})


class DependencyError(Exception):
    """An AWS call failed. ``code`` is a short, safe label (never a message)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RunTaskRejected(DependencyError):
    """ECS refused to start the task (an exception or an entry in ``failures``)."""


@dataclass(frozen=True)
class QueueDepth:
    visible: int
    in_flight: int
    delayed: int = 0


@dataclass(frozen=True)
class ActiveTask:
    arn: str
    status: str  # PROVISIONING / PENDING / ACTIVATING / RUNNING


class QueueDepthReader(Protocol):
    def depth(self) -> QueueDepth: ...


class WorkerTasks(Protocol):
    def active(self) -> list[ActiveTask]: ...

    def start(self) -> str: ...


class Lease(Protocol):
    def acquire(self, owner: str, ttl_seconds: int) -> bool: ...

    def release(self, owner: str) -> None: ...


class Outcome(str, Enum):
    NO_WORK = "no_work"
    WORKER_ALREADY_ACTIVE = "worker_already_active"
    LOCK_NOT_ACQUIRED = "lock_not_acquired"
    WORKER_STARTED = "worker_started"
    RUN_TASK_FAILED = "run_task_failed"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"


@dataclass(frozen=True)
class DispatchResult:
    outcome: Outcome
    task_arn: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"outcome": self.outcome.value, "task_arn": self.task_arn, "detail": self.detail}


class WorkerDispatcher:
    def __init__(
        self,
        queue: QueueDepthReader,
        workers: WorkerTasks,
        lease: Lease,
        *,
        max_active_workers: int = 1,
        lease_seconds: int = 60,
        recheck_attempts: int = 2,
        recheck_delay_seconds: float = 3.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._queue = queue
        self._workers = workers
        self._lease = lease
        self._max_active = max_active_workers
        self._lease_seconds = lease_seconds
        self._recheck_attempts = recheck_attempts
        self._recheck_delay = recheck_delay_seconds
        self._sleep = sleep

    def dispatch(self, reason: str) -> DispatchResult:
        reason = reason if reason in KNOWN_REASONS else "unknown"
        try:
            return self._dispatch(reason)
        except RunTaskRejected as error:
            return self._finish(reason, Outcome.RUN_TASK_FAILED, detail=error.code)
        except DependencyError as error:
            return self._finish(reason, Outcome.DEPENDENCY_UNAVAILABLE, detail=error.code)

    def _dispatch(self, reason: str) -> DispatchResult:
        depth = self._look_for_work(reason)
        if depth.visible <= 0:
            # In-flight messages belong to a live worker, or reappear on their own.
            return self._finish(reason, Outcome.NO_WORK, depth=depth)
        if len(self._workers.active()) >= self._max_active:
            return self._finish(reason, Outcome.WORKER_ALREADY_ACTIVE, depth=depth)

        owner = uuid.uuid4().hex
        if not self._lease.acquire(owner, self._lease_seconds):
            return self._finish(reason, Outcome.LOCK_NOT_ACQUIRED, depth=depth)
        started = False
        try:
            active = self._workers.active()
            if len(active) >= self._max_active:
                return self._finish(reason, Outcome.WORKER_ALREADY_ACTIVE, depth=depth)
            task_arn = self._workers.start()
            started = True
            return self._finish(reason, Outcome.WORKER_STARTED, task_arn=task_arn, depth=depth)
        finally:
            if not started:
                self._release_quietly(owner)

    def _look_for_work(self, reason: str) -> QueueDepth:
        depth = self._queue.depth()
        if reason != REASON_JOB_DISPATCHED:
            return depth
        # SQS counts lag a few seconds behind; look again briefly.
        for _ in range(self._recheck_attempts):
            if depth.visible > 0 or depth.in_flight > 0 or depth.delayed > 0:
                break
            self._sleep(self._recheck_delay)
            depth = self._queue.depth()
        return depth

    def _release_quietly(self, owner: str) -> None:
        try:
            self._lease.release(owner)
        except DependencyError:
            logger.warning(json.dumps({"event": "lock_release_failed"}))

    @staticmethod
    def _finish(
        reason: str,
        outcome: Outcome,
        *,
        task_arn: str | None = None,
        detail: str | None = None,
        depth: QueueDepth | None = None,
    ) -> DispatchResult:
        event: dict[str, object] = {"event": outcome.value, "reason": reason}
        if task_arn:
            event["task_arn"] = task_arn
        if detail:
            event["detail"] = detail
        if depth is not None:
            event.update(visible=depth.visible, in_flight=depth.in_flight, delayed=depth.delayed)
        (logger.error if outcome in {Outcome.RUN_TASK_FAILED, Outcome.DEPENDENCY_UNAVAILABLE} else logger.info)(
            json.dumps(event)
        )
        return DispatchResult(outcome, task_arn, detail)
