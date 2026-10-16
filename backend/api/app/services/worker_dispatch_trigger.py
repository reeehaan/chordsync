"""Fire-and-forget nudge to the worker dispatcher after a job is queued.

The job and message are already saved, so a failure here must never fail job
creation; the scheduled run starts the worker instead.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

REASON_JOB_DISPATCHED = "job_dispatched"
REASON_SCHEDULED = "scheduled_reconcile"


class WorkerDispatchTrigger(Protocol):
    def notify(self, reason: str = REASON_JOB_DISPATCHED) -> None: ...


class NoopWorkerDispatchTrigger:
    def notify(self, reason: str = REASON_JOB_DISPATCHED) -> None:
        return None


class LambdaWorkerDispatchTrigger:
    """Asynchronous (``Event``) Lambda invoke: the call returns once Lambda has
    queued the event, without waiting for ECS. Errors are logged and swallowed."""

    def __init__(self, client: Any, function_name: str) -> None:
        if not function_name.strip():
            raise ValueError("dispatcher function name is required")
        self._client = client
        self._function_name = function_name

    def notify(self, reason: str = REASON_JOB_DISPATCHED) -> None:
        try:
            self._client.invoke(
                FunctionName=self._function_name,
                InvocationType="Event",
                Payload=json.dumps({"reason": reason}).encode("utf-8"),
            )
        except Exception as error:
            logger.warning(
                "worker dispatcher not notified (%s); scheduled reconcile will recover",
                type(error).__name__,
            )
