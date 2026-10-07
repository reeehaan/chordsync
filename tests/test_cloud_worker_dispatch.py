from __future__ import annotations

from pathlib import Path

import pytest

from analysis.fusion.models import SharedTimeline
from backend.api.app.services.analysis_job_dispatcher import (
    LocalInProcessDispatcher,
    QueueBackedDispatcher,
)
from backend.api.app.services.analysis_job_queue import (
    AnalysisJobDescriptor,
    InMemoryAnalysisJobQueue,
)
from backend.api.app.services.analysis_worker_consumer import (
    AnalysisWorkerConsumer,
    NonRetryableWorkerError,
    WorkerOutcome,
)
from backend.api.app.services.artifact_cleanup import ArtifactCleanup
from backend.api.app.services.artifact_storage import (
    ArtifactKeyFactory,
    ArtifactRole,
    LocalArtifactStorage,
)
from backend.api.app.services.cloud_job import CloudJobStatus, new_cloud_job
from backend.api.app.services.cloud_job_repository import InMemoryCloudJobRepository
from backend.api.app.services.result_publication import AnalysisResultPublisher
from backend.api.app.services.source_materialization import SourceMaterializer


def _timeline() -> SharedTimeline:
    return SharedTimeline(
        schema_version=1,
        bpm=120,
        beats_per_bar=4,
        beat_source="test",
        lyric_source="test",
        bars=[],
        lyrics=[],
    )


class FakeExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, job_id):
        self.submitted.append(job_id)


class FakeProcessor:
    def __init__(self, error=None):
        self.error = error
        self.paths: list[Path] = []

    def process(self, path):
        self.paths.append(path)
        if self.error:
            raise self.error
        return _timeline()


class FailTimelineOnceStorage(LocalArtifactStorage):
    def __init__(self, root):
        super().__init__(root)
        self.failed = False

    def put_bytes(self, key, content, *, content_type):
        if key.role is ArtifactRole.TIMELINE_RESULT and not self.failed:
            self.failed = True
            raise OSError("temporary publication outage")
        return super().put_bytes(key, content, content_type=content_type)


def _setup(tmp_path, *, processor=None, max_attempts=3, storage=None):
    repository = InMemoryCloudJobRepository()
    storage = storage or LocalArtifactStorage(tmp_path / "objects")
    queue = InMemoryAnalysisJobQueue()
    keys = ArtifactKeyFactory()
    source_key = keys.source("job-one", ".mp3")
    storage.put_bytes(source_key, b"exact source bytes", content_type="audio/mpeg")
    job = new_cloud_job("job-one", "Song")
    job.max_attempts = max_attempts
    job.source_object_key = source_key.value
    job.transition_to(CloudJobStatus.AWAITING_UPLOAD)
    repository.add(job)
    QueueBackedDispatcher(repository, storage, queue).dispatch(job.job_id)
    workspaces = tmp_path / "workspaces"
    processor = processor or FakeProcessor()
    consumer = AnalysisWorkerConsumer(
        queue,
        repository,
        storage,
        SourceMaterializer(storage, workspaces),
        processor,
        AnalysisResultPublisher(repository, storage),
        ArtifactCleanup(workspaces, storage),
    )
    return repository, storage, queue, processor, consumer


def test_local_dispatcher_preserves_executor_semantics():
    executor = FakeExecutor()
    LocalInProcessDispatcher(executor).dispatch("job-one")
    assert executor.submitted == ["job-one"]


def test_queue_dispatch_requires_source_before_marking_queued(tmp_path):
    repository = InMemoryCloudJobRepository()
    storage = LocalArtifactStorage(tmp_path / "objects")
    queue = InMemoryAnalysisJobQueue()
    job = new_cloud_job("job-one", "Song")
    job.source_object_key = "jobs/job-one/source/input.mp3"
    job.transition_to(CloudJobStatus.AWAITING_UPLOAD)
    repository.add(job)

    with pytest.raises(ValueError, match="source"):
        QueueBackedDispatcher(repository, storage, queue).dispatch(job.job_id)
    assert repository.get(job.job_id).status is CloudJobStatus.AWAITING_UPLOAD
    assert queue.receive() is None


def test_worker_claims_processes_publishes_cleans_and_acknowledges(tmp_path):
    repository, storage, queue, processor, consumer = _setup(tmp_path)

    outcome = consumer.process_once()

    job = repository.get("job-one")
    assert outcome is WorkerOutcome.COMPLETED
    assert job.status is CloudJobStatus.COMPLETED
    assert job.attempt_count == 1
    assert processor.paths[0].name == "input.mp3"
    assert not (tmp_path / "workspaces" / "job-one").exists()
    playback = ArtifactKeyFactory().playback("job-one", ".mp3")
    assert storage.read_bytes(playback) == b"exact source bytes"
    assert queue.receive() is None


def test_completed_duplicate_with_artifacts_is_acknowledged(tmp_path):
    repository, _, queue, processor, consumer = _setup(tmp_path)
    assert consumer.process_once() is WorkerOutcome.COMPLETED
    job = repository.get("job-one")
    queue.enqueue(
        AnalysisJobDescriptor(
            job_id=job.job_id,
            source_artifact_key=job.source_object_key,
            title=job.title,
        )
    )

    assert consumer.process_once() is WorkerOutcome.ACKNOWLEDGED_STALE
    assert len(processor.paths) == 1


def test_processing_duplicate_is_released_without_execution(tmp_path):
    repository, _, queue, processor, consumer = _setup(tmp_path)
    job = repository.get("job-one")
    job.transition_to(CloudJobStatus.PROCESSING)
    repository.save(job, expected_status=CloudJobStatus.QUEUED)

    assert consumer.process_once() is WorkerOutcome.RELEASED_BUSY
    assert processor.paths == []
    assert queue.receive().receive_count == 2


def test_cancelled_before_claim_is_acknowledged(tmp_path):
    repository, _, queue, processor, consumer = _setup(tmp_path)
    job = repository.get("job-one")
    job.transition_to(CloudJobStatus.CANCELLED)
    repository.save(job, expected_status=CloudJobStatus.QUEUED)

    assert consumer.process_once() is WorkerOutcome.ACKNOWLEDGED_STALE
    assert processor.paths == []
    assert queue.receive() is None


def test_retryable_failure_requeues_until_attempt_limit(tmp_path):
    processor = FakeProcessor(RuntimeError("temporary infrastructure failure"))
    repository, _, queue, _, consumer = _setup(
        tmp_path, processor=processor, max_attempts=2
    )

    assert consumer.process_once() is WorkerOutcome.RETRY_SCHEDULED
    assert repository.get("job-one").status is CloudJobStatus.QUEUED
    assert consumer.process_once() is WorkerOutcome.FAILED_PERMANENTLY
    job = repository.get("job-one")
    assert job.status is CloudJobStatus.FAILED
    assert job.attempt_count == 2
    assert job.error_message == "Analysis could not be completed."
    assert queue.receive() is None


def test_nonretryable_failure_is_acknowledged(tmp_path):
    processor = FakeProcessor(NonRetryableWorkerError("corrupt audio"))
    repository, _, queue, _, consumer = _setup(tmp_path, processor=processor)

    assert consumer.process_once() is WorkerOutcome.FAILED_PERMANENTLY
    assert repository.get("job-one").status is CloudJobStatus.FAILED
    assert queue.receive() is None


def test_partial_publication_retries_with_deterministic_keys(tmp_path):
    storage = FailTimelineOnceStorage(tmp_path / "objects")
    repository, storage, _, processor, consumer = _setup(
        tmp_path, storage=storage
    )

    assert consumer.process_once() is WorkerOutcome.RETRY_SCHEDULED
    playback = ArtifactKeyFactory().playback("job-one", ".mp3")
    assert storage.read_bytes(playback) == b"exact source bytes"
    assert consumer.process_once() is WorkerOutcome.COMPLETED
    assert repository.get("job-one").status is CloudJobStatus.COMPLETED
    assert len(processor.paths) == 2


def test_source_materialization_preserves_bytes_and_uses_safe_job_path(tmp_path):
    storage = LocalArtifactStorage(tmp_path / "objects")
    key = ArtifactKeyFactory().source("job-one", ".m4a")
    storage.put_bytes(key, b"source", content_type="audio/mp4")

    result = SourceMaterializer(storage, tmp_path / "work").materialize(
        "job-one", key.value
    )

    assert result.content == b"source"
    assert result.path == tmp_path / "work" / "job-one" / "input.m4a"
    assert result.path.read_bytes() == b"source"
    with pytest.raises(ValueError):
        SourceMaterializer(storage, tmp_path / "work").materialize("../bad", key.value)
