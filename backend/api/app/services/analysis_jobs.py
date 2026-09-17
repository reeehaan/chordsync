from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import BinaryIO, Protocol
from uuid import uuid4

from analysis.fusion.models import SharedTimeline
from backend.api.app.models.analysis_job import (
    AnalysisJobCreateRequest,
    AnalysisJobError,
    AnalysisJobResponse,
    AnalysisJobStatus,
)
from backend.api.app.services.analysis_input_storage import (
    AnalysisInputMetadata,
    AnalysisInputStorage,
    LocalAnalysisInputStorage,
)


@dataclass
class AnalysisJobRecord:
    job_id: str
    title: str
    status: AnalysisJobStatus
    created_at: datetime
    updated_at: datetime
    input: AnalysisInputMetadata | None = None
    result: SharedTimeline | None = None
    error: AnalysisJobError | None = None


class AnalysisJobRepository(Protocol):
    def add(self, job: AnalysisJobRecord) -> None: ...

    def get(self, job_id: str) -> AnalysisJobRecord | None: ...

    def save(self, job: AnalysisJobRecord) -> None: ...


class InMemoryAnalysisJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisJobRecord] = {}
        self._lock = Lock()

    def add(self, job: AnalysisJobRecord) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> AnalysisJobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def save(self, job: AnalysisJobRecord) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def count(self) -> int:
        with self._lock:
            return len(self._jobs)


class AnalysisJobService:
    def __init__(
        self,
        repository: AnalysisJobRepository,
        input_storage: AnalysisInputStorage | None = None,
    ) -> None:
        self._repository = repository
        self._input_storage = input_storage or LocalAnalysisInputStorage()
        self._lifecycle_lock = Lock()

    def create(
        self,
        request: AnalysisJobCreateRequest,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> AnalysisJobResponse:
        now = datetime.now(timezone.utc)
        job_id = str(uuid4())
        input_metadata = self._input_storage.store(
            job_id=job_id,
            original_filename=original_filename,
            content_type=content_type,
            source=source,
        )
        job = AnalysisJobRecord(
            job_id=job_id,
            title=request.title,
            status=AnalysisJobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            input=input_metadata,
        )
        try:
            self._repository.add(job)
        except Exception:
            self._input_storage.delete(job_id)
            raise
        return self._response(job)

    def get(self, job_id: str) -> AnalysisJobRecord | None:
        return self._repository.get(job_id)

    def response(self, job: AnalysisJobRecord) -> AnalysisJobResponse:
        return self._response(job)

    def mark_processing(self, job_id: str) -> bool:
        with self._lifecycle_lock:
            job = self._required(job_id)
            if job.status != AnalysisJobStatus.QUEUED:
                return False
            job.status = AnalysisJobStatus.PROCESSING
            job.result = None
            job.error = None
            self._touch(job)
            return True

    def complete(self, job_id: str, result: SharedTimeline) -> None:
        with self._lifecycle_lock:
            job = self._required(job_id)
            self._require_processing(job)
            job.status = AnalysisJobStatus.COMPLETED
            job.result = result
            job.error = None
            self._touch(job)

    def fail(self, job_id: str, code: str, message: str) -> None:
        with self._lifecycle_lock:
            job = self._required(job_id)
            self._require_processing(job)
            job.status = AnalysisJobStatus.FAILED
            job.result = None
            job.error = AnalysisJobError(code=code, message=message)
            self._touch(job)

    def _required(self, job_id: str) -> AnalysisJobRecord:
        job = self._repository.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def _touch(self, job: AnalysisJobRecord) -> None:
        job.updated_at = datetime.now(timezone.utc)
        self._repository.save(job)

    @staticmethod
    def _require_processing(job: AnalysisJobRecord) -> None:
        if job.status != AnalysisJobStatus.PROCESSING:
            raise ValueError(
                f"Job must be processing, not {job.status.value}."
            )

    def _response(self, job: AnalysisJobRecord) -> AnalysisJobResponse:
        return AnalysisJobResponse(
            job_id=job.job_id,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            error=job.error,
            result_available=(
                job.status == AnalysisJobStatus.COMPLETED and job.result is not None
            ),
        )
