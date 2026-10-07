from __future__ import annotations

import json
from typing import BinaryIO, Protocol
from uuid import uuid4

from pydantic import ValidationError

from analysis.fusion.models import SharedTimeline
from backend.api.app.models.analysis_job import (
    AnalysisJobCreateRequest,
    AnalysisJobError,
    AnalysisJobResponse,
    AnalysisJobStatus,
)
from backend.api.app.services.analysis_input_storage import AnalysisInputStorage
from backend.api.app.services.analysis_job_dispatcher import AnalysisJobDispatcher
from backend.api.app.services.analysis_job_executor import AnalysisJobExecutor
from backend.api.app.services.analysis_jobs import AnalysisJobService
from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactKeyFactory,
    ArtifactRole,
    ArtifactStorage,
)
from backend.api.app.services.aws_errors import CloudProviderError
from backend.api.app.services.aws_errors import CloudProviderErrorKind
from backend.api.app.services.cloud_job import (
    CloudJobRecord,
    CloudJobStatus,
    new_cloud_job,
)
from backend.api.app.services.cloud_job_repository import CloudJobRepository


class JobNotFoundError(LookupError):
    pass


class ResultNotReadyError(RuntimeError):
    pass


class AnalysisFailedError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ResultArtifactMissingError(RuntimeError):
    pass


class ResultArtifactCorruptError(RuntimeError):
    pass


class ResultArtifactUnavailableError(RuntimeError):
    pass


class SourceArtifactStorageError(RuntimeError):
    pass


class AnalysisApplication(Protocol):
    def create(
        self,
        request: AnalysisJobCreateRequest,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> AnalysisJobResponse: ...

    def status(self, job_id: str) -> AnalysisJobResponse | None: ...

    def result(self, job_id: str) -> SharedTimeline: ...


class LocalAnalysisApplication:
    def __init__(
        self,
        jobs: AnalysisJobService,
        executor: AnalysisJobExecutor,
    ) -> None:
        self._jobs = jobs
        self._executor = executor

    def create(
        self,
        request: AnalysisJobCreateRequest,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> AnalysisJobResponse:
        response = self._jobs.create(
            request,
            original_filename,
            content_type,
            source,
        )
        self._executor.submit(response.job_id)
        return response

    def status(self, job_id: str) -> AnalysisJobResponse | None:
        job = self._jobs.get(job_id)
        return self._jobs.response(job) if job else None

    def result(self, job_id: str) -> SharedTimeline:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job.status in {AnalysisJobStatus.QUEUED, AnalysisJobStatus.PROCESSING}:
            raise ResultNotReadyError
        if job.status is AnalysisJobStatus.FAILED:
            error = job.error or AnalysisJobError(
                code="analysis_failed",
                message="Analysis could not be completed.",
            )
            raise AnalysisFailedError(error.code, error.message)
        if job.result is None:
            raise ResultNotReadyError
        return job.result


class CloudAnalysisApplication:
    def __init__(
        self,
        repository: CloudJobRepository,
        artifact_storage: ArtifactStorage,
        dispatcher: AnalysisJobDispatcher,
        staging_storage: AnalysisInputStorage,
    ) -> None:
        self._repository = repository
        self._artifacts = artifact_storage
        self._dispatcher = dispatcher
        self._staging = staging_storage

    def create(
        self,
        request: AnalysisJobCreateRequest,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> AnalysisJobResponse:
        job_id = str(uuid4())
        metadata = self._staging.store(
            job_id,
            original_filename,
            content_type,
            source,
        )
        local_path = self._staging.get_path(job_id)
        if local_path is None:
            self._staging.delete(job_id)
            raise SourceArtifactStorageError

        job = new_cloud_job(job_id, request.title)
        source_key = ArtifactKeyFactory().source(job_id, metadata.extension)
        try:
            self._repository.add(job)
            self._artifacts.put_bytes(
                source_key,
                local_path.read_bytes(),
                content_type=metadata.content_type or _content_type(metadata.extension),
            )
            job.source_object_key = source_key.value
            job.duration_seconds = metadata.duration_seconds
            job.file_type = metadata.extension
            job.transition_to(CloudJobStatus.AWAITING_UPLOAD, stage="source_stored")
            self._repository.save(job, expected_status=CloudJobStatus.CREATED)
        except (CloudProviderError, OSError) as error:
            raise SourceArtifactStorageError from error
        finally:
            self._staging.delete(job_id)

        try:
            self._dispatcher.dispatch(job_id)
        except CloudProviderError:
            # QUEUED + dispatch_pending is durable and can be reconciled without
            # another upload. Return the existing compatible queued response.
            pass
        current = self._repository.get(job_id)
        if current is None:
            raise JobNotFoundError(job_id)
        return _cloud_response(current)

    def status(self, job_id: str) -> AnalysisJobResponse | None:
        job = self._repository.get(job_id)
        return _cloud_response(job) if job else None

    def result(self, job_id: str) -> SharedTimeline:
        job = self._repository.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job.status is CloudJobStatus.FAILED:
            raise AnalysisFailedError(
                job.error_code or "analysis_failed",
                job.error_message or "Analysis could not be completed.",
            )
        if job.status is not CloudJobStatus.COMPLETED:
            raise ResultNotReadyError
        if not job.timeline_object_key:
            raise ResultArtifactMissingError
        key = ArtifactKey(ArtifactRole.TIMELINE_RESULT, job.timeline_object_key)
        try:
            if not self._artifacts.exists(key):
                raise ResultArtifactMissingError
            raw = self._artifacts.read_bytes(key).decode("utf-8")
            payload = json.loads(raw)
            return SharedTimeline.model_validate(payload)
        except CloudProviderError as error:
            if error.kind is CloudProviderErrorKind.NOT_FOUND:
                raise ResultArtifactMissingError from error
            raise ResultArtifactUnavailableError from error
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError) as error:
            raise ResultArtifactCorruptError from error


def _cloud_response(job: CloudJobRecord) -> AnalysisJobResponse:
    if job.status in {
        CloudJobStatus.CREATED,
        CloudJobStatus.AWAITING_UPLOAD,
        CloudJobStatus.QUEUED,
    }:
        status = AnalysisJobStatus.QUEUED
    elif job.status is CloudJobStatus.PROCESSING:
        status = AnalysisJobStatus.PROCESSING
    elif job.status is CloudJobStatus.COMPLETED:
        status = AnalysisJobStatus.COMPLETED
    else:
        status = AnalysisJobStatus.FAILED
    error = None
    if status is AnalysisJobStatus.FAILED:
        error = AnalysisJobError(
            code=job.error_code or "analysis_failed",
            message=job.error_message or "Analysis could not be completed.",
        )
    return AnalysisJobResponse(
        job_id=job.job_id,
        status=status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=error,
        result_available=(
            job.status is CloudJobStatus.COMPLETED
            and job.timeline_object_key is not None
        ),
    )


def _content_type(extension: str) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
    }[extension]
