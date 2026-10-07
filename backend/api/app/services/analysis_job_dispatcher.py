from __future__ import annotations

from typing import Protocol

from backend.api.app.services.analysis_job_executor import AnalysisJobExecutor
from backend.api.app.services.analysis_job_queue import (
    AnalysisJobDescriptor,
    AnalysisJobQueue,
)
from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactRole,
    ArtifactStorage,
)
from backend.api.app.services.cloud_job import CloudJobStatus
from backend.api.app.services.cloud_job_repository import (
    CloudJobRepository,
    JobWriteConflictError,
)


class AnalysisJobDispatcher(Protocol):
    def dispatch(self, job_id: str) -> None: ...


class LocalInProcessDispatcher:
    def __init__(self, executor: AnalysisJobExecutor) -> None:
        self._executor = executor

    def dispatch(self, job_id: str) -> None:
        self._executor.submit(job_id)


class QueueBackedDispatcher:
    def __init__(
        self,
        repository: CloudJobRepository,
        storage: ArtifactStorage,
        queue: AnalysisJobQueue,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._queue = queue

    def dispatch(self, job_id: str) -> None:
        job = self._repository.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status is not CloudJobStatus.AWAITING_UPLOAD:
            raise ValueError("Job must be awaiting upload before dispatch")
        if not job.source_object_key:
            raise ValueError("Job source artifact is unavailable")
        source_key = ArtifactKey(
            ArtifactRole.SOURCE_UPLOAD,
            job.source_object_key,
        )
        if not self._storage.exists(source_key):
            raise ValueError("Job source artifact is unavailable")

        job.transition_to(CloudJobStatus.QUEUED, stage="queued")
        job.dispatch_pending = True
        self._repository.save(
            job,
            expected_status=CloudJobStatus.AWAITING_UPLOAD,
        )
        self._queue.enqueue(
            AnalysisJobDescriptor(
                job_id=job.job_id,
                source_artifact_key=job.source_object_key,
                title=job.title,
            )
        )
        _mark_dispatched(self._repository, job.job_id)


class DispatchReconciler:
    def __init__(
        self,
        repository: CloudJobRepository,
        queue: AnalysisJobQueue,
    ) -> None:
        self._repository = repository
        self._queue = queue

    def reconcile(self, *, limit: int = 100) -> int:
        dispatched = 0
        for job in self._repository.pending_dispatch(limit=limit):
            if not job.source_object_key:
                continue
            self._queue.enqueue(
                AnalysisJobDescriptor(
                    job_id=job.job_id,
                    source_artifact_key=job.source_object_key,
                    title=job.title,
                )
            )
            _mark_dispatched(self._repository, job.job_id)
            dispatched += 1
        return dispatched


def _mark_dispatched(repository: CloudJobRepository, job_id: str) -> None:
    current = repository.get(job_id)
    if (
        current is None
        or current.status is not CloudJobStatus.QUEUED
        or not current.dispatch_pending
    ):
        return
    current.dispatch_pending = False
    current.stage = "dispatched"
    try:
        repository.save(current, expected_status=CloudJobStatus.QUEUED)
    except JobWriteConflictError:
        # A worker may have claimed the just-enqueued delivery already. Its
        # conditional claim also clears dispatch_pending.
        return
