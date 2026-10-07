from __future__ import annotations

from dataclasses import dataclass

from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactKeyFactory,
    ArtifactRole,
    ArtifactStorage,
)
from backend.api.app.services.cloud_job import CloudJobRecord, CloudJobStatus
from backend.api.app.services.cloud_job_repository import CloudJobRepository


class PublicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicationRequest:
    job_id: str
    playback_bytes: bytes
    playback_extension: str
    playback_content_type: str
    timeline_bytes: bytes


class AnalysisResultPublisher:
    def __init__(
        self,
        repository: CloudJobRepository,
        storage: ArtifactStorage,
        key_factory: ArtifactKeyFactory | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._keys = key_factory or ArtifactKeyFactory()

    def publish(self, request: PublicationRequest) -> CloudJobRecord:
        job = self._repository.get(request.job_id)
        if job is None:
            raise PublicationError("Job does not exist")
        if job.status is CloudJobStatus.COMPLETED:
            if self._required_artifacts_exist(job):
                return job
            raise PublicationError("Completed job is missing retained artifacts")
        if job.status is not CloudJobStatus.PROCESSING:
            raise PublicationError("Job is not processing")

        playback_key = self._keys.playback(
            job.job_id,
            request.playback_extension,
        )
        timeline_key = self._keys.timeline(job.job_id)
        self._storage.put_bytes(
            playback_key,
            request.playback_bytes,
            content_type=request.playback_content_type,
        )
        self._storage.put_bytes(
            timeline_key,
            request.timeline_bytes,
            content_type="application/json",
        )
        if not self._storage.exists(playback_key) or not self._storage.exists(
            timeline_key
        ):
            raise PublicationError("Required retained artifacts are unavailable")

        job.playback_object_key = playback_key.value
        job.timeline_object_key = timeline_key.value
        job.error_code = None
        job.error_message = None
        job.transition_to(CloudJobStatus.COMPLETED, stage="published")
        self._repository.save(job, expected_status=CloudJobStatus.PROCESSING)
        return job

    def _required_artifacts_exist(self, job: CloudJobRecord) -> bool:
        if not job.playback_object_key or not job.timeline_object_key:
            return False
        return self._storage.exists(
            ArtifactKey(
                role=ArtifactRole.PLAYBACK_AUDIO,
                value=job.playback_object_key,
            )
        ) and self._storage.exists(
            ArtifactKey(
                role=ArtifactRole.TIMELINE_RESULT,
                value=job.timeline_object_key,
            )
        )
