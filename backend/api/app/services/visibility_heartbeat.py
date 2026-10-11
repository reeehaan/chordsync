from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from types import TracebackType
from typing import Callable

from backend.api.app.services.analysis_job_queue import (
    AnalysisJobQueue,
    QueueDelivery,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisibilityPolicy:
    """How long a claimed delivery stays hidden from other consumers.

    The receive call hides the message for ``initial_timeout_seconds``. While
    the job is processing, a heartbeat resets the timeout to
    ``extension_seconds`` every ``heartbeat_interval_seconds``, so at least
    ``extension_seconds - heartbeat_interval_seconds`` of visibility always
    remains. Heartbeats stop after ``max_processing_seconds`` so a hung worker
    cannot hide a message forever; the message then reappears within one
    extension period and the normal retry/DLQ path applies.
    """

    initial_timeout_seconds: int = 1800
    heartbeat_interval_seconds: float = 300
    extension_seconds: int = 1800
    max_processing_seconds: int = 3600

    def __post_init__(self) -> None:
        if not 0 < self.heartbeat_interval_seconds < self.extension_seconds:
            raise ValueError("Heartbeat interval must be shorter than the extension")
        if self.extension_seconds > 43200 or self.initial_timeout_seconds > 43200:
            raise ValueError("SQS visibility timeouts cannot exceed 12 hours")


DEFAULT_VISIBILITY_POLICY = VisibilityPolicy()


class VisibilityHeartbeat:
    """Extends one delivery's visibility on a background thread while active."""

    def __init__(
        self,
        queue: AnalysisJobQueue,
        delivery: QueueDelivery,
        policy: VisibilityPolicy = DEFAULT_VISIBILITY_POLICY,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._queue = queue
        self._delivery = delivery
        self._policy = policy
        self._clock = clock
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = clock()
        self.extensions = 0

    def __enter__(self) -> VisibilityHeartbeat:
        self._started_at = self._clock()
        self._thread = threading.Thread(
            target=self._run,
            name=f"visibility-heartbeat-{self._delivery.descriptor.job_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    def stop(self) -> None:
        """Stop extending and wait, so no extension races a later ack/release."""
        self._stopped.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def tick(self) -> bool:
        """Extend visibility once. Returns False once the processing cap is hit."""
        job_id = self._delivery.descriptor.job_id
        elapsed = self._clock() - self._started_at
        if elapsed >= self._policy.max_processing_seconds:
            logger.warning(
                "[job %s] visibility heartbeat stopped after %.0fs; "
                "processing exceeded the %ds cap",
                job_id,
                elapsed,
                self._policy.max_processing_seconds,
            )
            return False
        try:
            self._queue.extend_visibility(
                self._delivery,
                visibility_timeout_seconds=self._policy.extension_seconds,
            )
        except Exception as error:
            # Never acknowledge here: a failed extension at worst lets the
            # message reappear, and duplicate claims are rejected by the
            # job's conditional PROCESSING state.
            logger.warning(
                "[job %s] visibility extension failed (%s); will retry",
                job_id,
                type(error).__name__,
            )
            return True
        self.extensions += 1
        return True

    def _run(self) -> None:
        while not self._stopped.wait(self._policy.heartbeat_interval_seconds):
            if not self.tick():
                return
