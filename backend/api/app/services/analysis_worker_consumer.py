from __future__ import annotations

import json
from enum import Enum

from backend.api.app.services.analysis_job_queue import (
    AnalysisJobQueue,
    QueueDelivery,
)
from backend.api.app.services.analysis_processor import AnalysisProcessor
from backend.api.app.services.artifact_cleanup import ArtifactCleanup
from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactRole,
    ArtifactStorage,
)
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
)
from backend.api.app.services.cloud_job import CloudJobRecord, CloudJobStatus
from backend.api.app.services.cloud_job_repository import (
    CloudJobRepository,
    JobWriteConflictError,
)
from backend.api.app.services.result_publication import (
    AnalysisResultPublisher,
    PublicationRequest,
)
from backend.api.app.services.source_materialization import SourceMaterializer


class WorkerOutcome(str, Enum):
    EMPTY = "empty"
    COMPLETED = "completed"
    ACKNOWLEDGED_STALE = "acknowledged_stale"
    RELEASED_BUSY = "released_busy"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED_PERMANENTLY = "failed_permanently"


class NonRetryableWorkerError(RuntimeError):
    pass


class AnalysisWorkerConsumer:
    def __init__(
        self,
        queue: AnalysisJobQueue,
        repository: CloudJobRepository,
        storage: ArtifactStorage,
        materializer: SourceMaterializer,
        processor: AnalysisProcessor,
        publisher: AnalysisResultPublisher,
        cleanup: ArtifactCleanup,
    ) -> None:
        self._queue = queue
        self._repository = repository
        self._storage = storage
        self._materializer = materializer
        self._processor = processor
        self._publisher = publisher
        self._cleanup = cleanup

    def process_once(self) -> WorkerOutcome:
        delivery = self._queue.receive()
        if delivery is None:
            return WorkerOutcome.EMPTY
        job = self._repository.get(delivery.descriptor.job_id)
        if job is None:
            self._queue.acknowledge(delivery)
            return WorkerOutcome.ACKNOWLEDGED_STALE
        if delivery.descriptor.source_artifact_key != job.source_object_key:
            self._queue.acknowledge(delivery)
            return WorkerOutcome.ACKNOWLEDGED_STALE
        if job.status is CloudJobStatus.COMPLETED:
            if self._retained_artifacts_exist(job):
                self._queue.acknowledge(delivery)
                return WorkerOutcome.ACKNOWLEDGED_STALE
            self._queue.release(delivery)
            return WorkerOutcome.RELEASED_BUSY
        if job.status in {
            CloudJobStatus.CANCELLED,
            CloudJobStatus.EXPIRED,
        }:
            self._queue.acknowledge(delivery)
            return WorkerOutcome.ACKNOWLEDGED_STALE
        if job.status is CloudJobStatus.PROCESSING:
            self._queue.release(delivery, visibility_timeout_seconds=60)
            return WorkerOutcome.RELEASED_BUSY
        if job.status is not CloudJobStatus.QUEUED:
            self._queue.acknowledge(delivery)
            return WorkerOutcome.ACKNOWLEDGED_STALE

        try:
            job.dispatch_pending = False
            job.transition_to(CloudJobStatus.PROCESSING, stage="materializing")
            self._repository.save(job, expected_status=CloudJobStatus.QUEUED)
        except JobWriteConflictError:
            self._queue.release(delivery, visibility_timeout_seconds=60)
            return WorkerOutcome.RELEASED_BUSY

        return self._process_claimed(delivery, job)

    def _process_claimed(
        self,
        delivery: QueueDelivery,
        job: CloudJobRecord,
    ) -> WorkerOutcome:
        try:
            source = self._materializer.materialize(
                job.job_id,
                delivery.descriptor.source_artifact_key,
            )
            timeline = self._processor.process(source.path)
            latest = self._repository.get(job.job_id)
            if latest is None or latest.status is CloudJobStatus.CANCELLED:
                self._queue.acknowledge(delivery)
                return WorkerOutcome.ACKNOWLEDGED_STALE
            if latest.status is not CloudJobStatus.PROCESSING:
                self._queue.release(delivery, visibility_timeout_seconds=60)
                return WorkerOutcome.RELEASED_BUSY
            self._publisher.publish(
                PublicationRequest(
                    job_id=job.job_id,
                    playback_bytes=source.content,
                    playback_extension=source.path.suffix,
                    playback_content_type=_content_type(source.path.suffix),
                    timeline_bytes=json.dumps(
                        timeline.model_dump(mode="json"),
                        separators=(",", ":"),
                    ).encode("utf-8"),
                )
            )
            self._queue.acknowledge(delivery)
            return WorkerOutcome.COMPLETED
        except Exception as error:
            return self._handle_failure(delivery, job, error)
        finally:
            self._cleanup.delete_workspace(job.job_id)

    def _handle_failure(
        self,
        delivery: QueueDelivery,
        claimed_job: CloudJobRecord,
        error: Exception,
    ) -> WorkerOutcome:
        retryable = _is_retryable(error)
        latest = self._repository.get(claimed_job.job_id)
        if latest is None or latest.status is CloudJobStatus.CANCELLED:
            self._queue.acknowledge(delivery)
            return WorkerOutcome.ACKNOWLEDGED_STALE
        if latest.status is CloudJobStatus.COMPLETED:
            self._queue.acknowledge(delivery)
            return WorkerOutcome.ACKNOWLEDGED_STALE
        if latest.status is not CloudJobStatus.PROCESSING:
            self._queue.release(delivery, visibility_timeout_seconds=60)
            return WorkerOutcome.RELEASED_BUSY

        latest.error_code = "analysis_failed"
        latest.error_message = "Analysis could not be completed."
        latest.transition_to(CloudJobStatus.FAILED, stage="failed")
        self._repository.save(
            latest,
            expected_status=CloudJobStatus.PROCESSING,
        )
        if retryable and latest.attempt_count < latest.max_attempts:
            latest.transition_to(CloudJobStatus.QUEUED, stage="retry_queued")
            self._repository.save(latest, expected_status=CloudJobStatus.FAILED)
            self._queue.release(delivery)
            return WorkerOutcome.RETRY_SCHEDULED
        self._queue.acknowledge(delivery)
        return WorkerOutcome.FAILED_PERMANENTLY

    def _retained_artifacts_exist(self, job: CloudJobRecord) -> bool:
        if not job.playback_object_key or not job.timeline_object_key:
            return False
        return self._storage.exists(
            ArtifactKey(ArtifactRole.PLAYBACK_AUDIO, job.playback_object_key)
        ) and self._storage.exists(
            ArtifactKey(ArtifactRole.TIMELINE_RESULT, job.timeline_object_key)
        )


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, NonRetryableWorkerError):
        return False
    if isinstance(error, (ValueError, FileNotFoundError)):
        return False
    if isinstance(error, CloudProviderError):
        return error.kind in {
            CloudProviderErrorKind.TEMPORARY_UNAVAILABLE,
            CloudProviderErrorKind.UNEXPECTED,
        }
    return True


def _content_type(extension: str) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
    }[extension.casefold()]
