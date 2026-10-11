from __future__ import annotations

import logging
import time

import pytest

from backend.api.app.services.analysis_job_queue import (
    AnalysisJobDescriptor,
    InMemoryAnalysisJobQueue,
    QueueDelivery,
)
from backend.api.app.services.analysis_worker_consumer import (
    AnalysisWorkerConsumer,
    NonRetryableWorkerError,
    WorkerOutcome,
)
from backend.api.app.services.artifact_cleanup import ArtifactCleanup
from backend.api.app.services.cloud_job import CloudJobStatus
from backend.api.app.services.result_publication import AnalysisResultPublisher
from backend.api.app.services.source_materialization import SourceMaterializer
from backend.api.app.services.visibility_heartbeat import (
    DEFAULT_VISIBILITY_POLICY,
    VisibilityHeartbeat,
    VisibilityPolicy,
)
from tests.test_cloud_worker_dispatch import FakeProcessor, _setup


def _delivery() -> QueueDelivery:
    descriptor = AnalysisJobDescriptor(
        job_id="job-one",
        source_artifact_key="jobs/job-one/source/input.mp3",
        title="Song",
    )
    return QueueDelivery(descriptor, "receipt-1")


class RecordingQueue:
    def __init__(self, fail_extensions: bool = False) -> None:
        self.extensions: list[int] = []
        self.fail_extensions = fail_extensions
        self.acknowledged = False

    def extend_visibility(self, delivery, *, visibility_timeout_seconds):
        if self.fail_extensions:
            raise RuntimeError("throttled")
        self.extensions.append(visibility_timeout_seconds)

    def acknowledge(self, delivery):
        self.acknowledged = True


def test_default_policy_documents_first_test_values():
    policy = DEFAULT_VISIBILITY_POLICY
    assert policy.initial_timeout_seconds == 1800
    assert policy.heartbeat_interval_seconds == 300
    assert policy.extension_seconds == 1800
    assert policy.max_processing_seconds == 3600


def test_policy_rejects_interval_not_shorter_than_extension():
    with pytest.raises(ValueError):
        VisibilityPolicy(heartbeat_interval_seconds=600, extension_seconds=600)


def test_heartbeat_extends_periodically_and_stops():
    queue = RecordingQueue()
    policy = VisibilityPolicy(heartbeat_interval_seconds=0.01, extension_seconds=60)

    with VisibilityHeartbeat(queue, _delivery(), policy) as heartbeat:
        deadline = time.monotonic() + 2
        while heartbeat.extensions < 2 and time.monotonic() < deadline:
            time.sleep(0.01)

    count = len(queue.extensions)
    assert count >= 2
    assert set(queue.extensions) == {60}
    time.sleep(0.05)
    assert len(queue.extensions) == count


def test_heartbeat_stops_extending_after_processing_cap():
    now = [0.0]
    queue = RecordingQueue()
    heartbeat = VisibilityHeartbeat(
        queue,
        _delivery(),
        VisibilityPolicy(max_processing_seconds=100),
        clock=lambda: now[0],
    )

    assert heartbeat.tick() is True
    now[0] = 100.0
    assert heartbeat.tick() is False
    assert queue.extensions == [1800]


def test_extension_failure_is_logged_and_never_acknowledges(caplog):
    queue = RecordingQueue(fail_extensions=True)
    heartbeat = VisibilityHeartbeat(queue, _delivery())

    with caplog.at_level(logging.WARNING):
        assert heartbeat.tick() is True

    assert "visibility extension failed (RuntimeError)" in caplog.text
    assert "receipt-1" not in caplog.text
    assert not queue.acknowledged


# --- consumer integration ---------------------------------------------------


class OrderedQueue(InMemoryAnalysisJobQueue):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def acknowledge(self, delivery):
        self.events.append("acknowledge")
        super().acknowledge(delivery)

    def release(self, delivery, *, visibility_timeout_seconds=0):
        self.events.append("release")
        super().release(delivery, visibility_timeout_seconds=visibility_timeout_seconds)


class RecordingHeartbeat:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self):
        self.events.append("heartbeat-start")
        return self

    def __exit__(self, *exc_info):
        self.events.append("heartbeat-stop")


def _consumer(tmp_path, processor=None, max_attempts=3):
    repository, storage, original_queue, processor, _ = _setup(
        tmp_path, processor=processor, max_attempts=max_attempts
    )
    events: list[str] = []
    queue = OrderedQueue(events)
    queue._available = original_queue._available
    workspaces = tmp_path / "workspaces"
    consumer = AnalysisWorkerConsumer(
        queue,
        repository,
        storage,
        SourceMaterializer(storage, workspaces),
        processor,
        AnalysisResultPublisher(repository, storage),
        ArtifactCleanup(workspaces, storage),
        heartbeat_factory=lambda delivery: RecordingHeartbeat(events),
    )
    return consumer, repository, queue, events


def test_heartbeat_stops_before_acknowledging_completed_job(tmp_path):
    consumer, repository, queue, events = _consumer(tmp_path)

    assert consumer.process_once() is WorkerOutcome.COMPLETED
    assert events == ["heartbeat-start", "heartbeat-stop", "acknowledge"]
    assert repository.get("job-one").status is CloudJobStatus.COMPLETED


def test_heartbeat_stops_before_releasing_retryable_failure(tmp_path):
    consumer, repository, queue, events = _consumer(
        tmp_path, processor=FakeProcessor(error=RuntimeError("stage failed"))
    )

    assert consumer.process_once() is WorkerOutcome.RETRY_SCHEDULED
    assert events == ["heartbeat-start", "heartbeat-stop", "release"]
    assert repository.get("job-one").status is CloudJobStatus.QUEUED


def test_heartbeat_stops_before_acknowledging_permanent_failure(tmp_path):
    consumer, repository, queue, events = _consumer(
        tmp_path, processor=FakeProcessor(error=NonRetryableWorkerError("bad input"))
    )

    assert consumer.process_once() is WorkerOutcome.FAILED_PERMANENTLY
    assert events == ["heartbeat-start", "heartbeat-stop", "acknowledge"]
    assert repository.get("job-one").status is CloudJobStatus.FAILED


def test_duplicate_of_processing_job_never_starts_heartbeat(tmp_path):
    consumer, repository, queue, events = _consumer(tmp_path)
    job = repository.get("job-one")
    job.transition_to(CloudJobStatus.PROCESSING, stage="materializing")
    repository.save(job, expected_status=CloudJobStatus.QUEUED)

    assert consumer.process_once() is WorkerOutcome.RELEASED_BUSY
    assert events == ["release"]


def test_real_heartbeat_with_failing_extensions_still_completes_once(tmp_path):
    repository, storage, queue, processor, _ = _setup(tmp_path)

    class FailingExtensionQueue:
        def __getattr__(self, name):
            return getattr(queue, name)

        def extend_visibility(self, delivery, *, visibility_timeout_seconds):
            raise RuntimeError("throttled")

    workspaces = tmp_path / "workspaces"
    policy = VisibilityPolicy(heartbeat_interval_seconds=0.001, extension_seconds=60)

    class SlowProcessor(FakeProcessor):
        def process(self, path):
            time.sleep(0.02)
            return super().process(path)

    consumer = AnalysisWorkerConsumer(
        queue,
        repository,
        storage,
        SourceMaterializer(storage, workspaces),
        SlowProcessor(),
        AnalysisResultPublisher(repository, storage),
        ArtifactCleanup(workspaces, storage),
        heartbeat_factory=lambda delivery: VisibilityHeartbeat(
            FailingExtensionQueue(), delivery, policy
        ),
    )

    assert consumer.process_once() is WorkerOutcome.COMPLETED
    assert repository.get("job-one").status is CloudJobStatus.COMPLETED
    assert queue.receive() is None
