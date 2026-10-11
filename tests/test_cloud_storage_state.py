from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.api.app.services.artifact_cleanup import ArtifactCleanup
from backend.api.app.services.artifact_storage import (
    ArtifactKeyFactory,
    ArtifactRole,
    LocalArtifactStorage,
)
from backend.api.app.services.cloud_job import (
    CloudJobRecord,
    CloudJobStatus,
    new_cloud_job,
)
from backend.api.app.services.cloud_job_repository import (
    InMemoryCloudJobRepository,
    JobWriteConflictError,
    SqliteCloudJobRepository,
)
from backend.api.app.services.result_publication import (
    AnalysisResultPublisher,
    PublicationRequest,
)


def _processing_job(job_id: str = "job-one") -> CloudJobRecord:
    now = datetime.now(timezone.utc)
    return CloudJobRecord(
        job_id=job_id,
        title="Synthetic song",
        created_at=now,
        updated_at=now,
        status=CloudJobStatus.PROCESSING,
        source_object_key=f"jobs/{job_id}/source/input.mp3",
        duration_seconds=120.0,
        file_type=".mp3",
        attempt_count=1,
        last_attempt_at=now,
    )


def test_cloud_job_serialization_round_trip_contains_only_metadata():
    job = _processing_job()
    job.stage = "whisperx"
    job.owner_id = None

    payload = job.to_dict()
    restored = CloudJobRecord.from_dict(payload)

    assert restored == job
    assert set(payload) == {
        "job_id",
        "title",
        "created_at",
        "updated_at",
        "status",
        "stage",
        "source_object_key",
        "playback_object_key",
        "timeline_object_key",
        "error_code",
        "error_message",
        "attempt_count",
        "max_attempts",
        "duration_seconds",
        "file_type",
        "owner_id",
        "last_attempt_at",
        "dispatch_pending",
        "version",
    }
    assert "timeline" not in payload
    assert "audio" not in payload


def test_allowed_state_path_and_attempt_metadata():
    job = new_cloud_job("job-one", "Synthetic song")

    job.transition_to(CloudJobStatus.AWAITING_UPLOAD)
    job.transition_to(CloudJobStatus.QUEUED)
    job.transition_to(CloudJobStatus.PROCESSING, stage="preprocess")
    job.transition_to(CloudJobStatus.COMPLETED, stage="published")

    assert job.status is CloudJobStatus.COMPLETED
    assert job.attempt_count == 1
    assert job.last_attempt_at is not None


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        (CloudJobStatus.CREATED, CloudJobStatus.COMPLETED),
        (CloudJobStatus.QUEUED, CloudJobStatus.COMPLETED),
        (CloudJobStatus.COMPLETED, CloudJobStatus.PROCESSING),
        (CloudJobStatus.EXPIRED, CloudJobStatus.QUEUED),
    ],
)
def test_invalid_state_transitions_are_rejected(initial, target):
    job = new_cloud_job("job-one", "Synthetic song")
    job.status = initial

    with pytest.raises(ValueError, match="Invalid job transition"):
        job.transition_to(target)


def test_in_memory_repository_uses_conditional_updates():
    repository = InMemoryCloudJobRepository()
    job = new_cloud_job("job-one", "Synthetic song")
    repository.add(job)
    loaded = repository.get(job.job_id)
    loaded.transition_to(CloudJobStatus.AWAITING_UPLOAD)

    repository.save(loaded, expected_status=CloudJobStatus.CREATED)

    assert repository.get(job.job_id).status is CloudJobStatus.AWAITING_UPLOAD
    with pytest.raises(JobWriteConflictError):
        repository.save(loaded, expected_status=CloudJobStatus.CREATED)


def test_sqlite_repository_survives_restart_with_artifact_references(tmp_path):
    database = tmp_path / "state" / "jobs.sqlite3"
    first = SqliteCloudJobRepository(database)
    job = _processing_job()
    job.playback_object_key = "jobs/job-one/playback/audio.mp3"
    job.timeline_object_key = "jobs/job-one/results/timeline.json"
    first.add(job)
    job.error_code = "analysis_failed"
    job.error_message = "Safe failure"
    job.transition_to(CloudJobStatus.FAILED, stage="failed")
    first.save(job, expected_status=CloudJobStatus.PROCESSING)

    second = SqliteCloudJobRepository(database)
    restored = second.get("job-one")

    assert restored == job
    assert restored.status is CloudJobStatus.FAILED
    assert not restored.playback_object_key.startswith("/")
    assert not restored.timeline_object_key.startswith("/")


def test_job_record_rejects_absolute_artifact_references():
    job = _processing_job()
    job.source_object_key = "/Users/developer/song.mp3"

    with pytest.raises(ValueError, match="logical object keys"):
        job.to_dict()


def test_artifact_keys_are_deterministic_and_ignore_raw_filename():
    factory = ArtifactKeyFactory()

    assert factory.source("job-one", ".MP3").value == (
        "jobs/job-one/source/input.mp3"
    )
    assert factory.playback("job-one", ".mp3").value == (
        "jobs/job-one/playback/audio.mp3"
    )
    assert factory.timeline("job-one").value == (
        "jobs/job-one/results/timeline.json"
    )
    assert ArtifactKeyFactory("student-1").timeline("job-one").value == (
        "users/student-1/jobs/job-one/results/timeline.json"
    )
    with pytest.raises(ValueError):
        factory.source("../unsafe", ".mp3")


def test_local_artifact_storage_put_read_exists_and_delete(tmp_path):
    storage = LocalArtifactStorage(tmp_path / "cloud-local")
    key = ArtifactKeyFactory().source("job-one", ".wav")

    metadata = storage.put_bytes(key, b"exact source", content_type="audio/wav")

    assert metadata.key.role is ArtifactRole.SOURCE_UPLOAD
    assert metadata.size_bytes == len(b"exact source")
    assert storage.exists(key)
    assert storage.read_bytes(key) == b"exact source"
    storage.delete(key)
    assert not storage.exists(key)


class RecordingStorage(LocalArtifactStorage):
    def __init__(self, root: Path, events: list[str], fail_timeline=False):
        super().__init__(root)
        self.events = events
        self.fail_timeline = fail_timeline

    def put_bytes(self, key, content, *, content_type):
        self.events.append(f"put:{key.role.value}")
        if self.fail_timeline and key.role is ArtifactRole.TIMELINE_RESULT:
            raise OSError("simulated timeline publication failure")
        return super().put_bytes(key, content, content_type=content_type)


class RecordingRepository(InMemoryCloudJobRepository):
    def __init__(self, events: list[str]):
        super().__init__()
        self.events = events

    def save(self, job, *, expected_status):
        self.events.append(f"save:{job.status.value}")
        return super().save(job, expected_status=expected_status)


def _request() -> PublicationRequest:
    return PublicationRequest(
        job_id="job-one",
        playback_bytes=b"exact analyzed recording",
        playback_extension=".mp3",
        playback_content_type="audio/mpeg",
        timeline_bytes=b'{"schema_version":1}',
    )


def test_publication_orders_playback_timeline_then_completed(tmp_path):
    events = []
    repository = RecordingRepository(events)
    repository.add(_processing_job())
    storage = RecordingStorage(tmp_path / "objects", events)

    completed = AnalysisResultPublisher(repository, storage).publish(_request())

    assert events == [
        "put:playback_audio",
        "put:timeline_result",
        "save:completed",
    ]
    assert completed.status is CloudJobStatus.COMPLETED
    assert storage.read_bytes(ArtifactKeyFactory().playback("job-one", ".mp3")) == (
        b"exact analyzed recording"
    )


def test_duplicate_completed_publication_is_idempotent(tmp_path):
    events = []
    repository = RecordingRepository(events)
    repository.add(_processing_job())
    storage = RecordingStorage(tmp_path / "objects", events)
    publisher = AnalysisResultPublisher(repository, storage)
    first = publisher.publish(_request())
    event_count = len(events)

    second = publisher.publish(_request())

    assert second.status is CloudJobStatus.COMPLETED
    assert second.version == first.version
    assert len(events) == event_count


def test_failed_publication_does_not_mark_job_completed(tmp_path):
    events = []
    repository = RecordingRepository(events)
    repository.add(_processing_job())
    storage = RecordingStorage(tmp_path / "objects", events, fail_timeline=True)

    with pytest.raises(OSError, match="timeline publication failure"):
        AnalysisResultPublisher(repository, storage).publish(_request())

    assert repository.get("job-one").status is CloudJobStatus.PROCESSING
    assert "save:completed" not in events


def test_cleanup_removes_only_workspace_and_transient_source(tmp_path):
    object_storage = LocalArtifactStorage(tmp_path / "objects")
    keys = ArtifactKeyFactory()
    source = keys.source("job-one", ".mp3")
    playback = keys.playback("job-one", ".mp3")
    timeline = keys.timeline("job-one")
    for key in (source, playback, timeline):
        object_storage.put_bytes(key, b"data", content_type="application/octet-stream")
    job = _processing_job()
    job.playback_object_key = playback.value
    job.timeline_object_key = timeline.value
    workspace = tmp_path / "workspaces" / job.job_id
    workspace.mkdir(parents=True)
    (workspace / "normalized.wav").write_bytes(b"temporary")
    cleanup = ArtifactCleanup(tmp_path / "workspaces", object_storage)

    cleanup.delete_workspace(job.job_id)
    cleanup.delete_transient_source(job)

    assert not workspace.exists()
    assert not object_storage.exists(source)
    assert object_storage.exists(playback)
    assert object_storage.exists(timeline)
