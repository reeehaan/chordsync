from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from analysis.fusion.models import SharedTimeline
from backend.api.app.main import app
from backend.api.app.routers.analysis_jobs import get_analysis_application_service
from backend.api.app.services.analysis_application import CloudAnalysisApplication
from backend.api.app.services.analysis_input_storage import LocalAnalysisInputStorage
from backend.api.app.services.analysis_job_dispatcher import (
    DispatchReconciler,
    QueueBackedDispatcher,
)
from backend.api.app.services.analysis_job_queue import InMemoryAnalysisJobQueue
from backend.api.app.services.analysis_worker_consumer import AnalysisWorkerConsumer
from backend.api.app.services.artifact_cleanup import ArtifactCleanup
from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactRole,
    LocalArtifactStorage,
)
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
)
from backend.api.app.services.cloud_job import CloudJobStatus
from backend.api.app.services.cloud_job_repository import (
    InMemoryCloudJobRepository,
    SqliteCloudJobRepository,
)
from backend.api.app.services.result_publication import AnalysisResultPublisher
from backend.api.app.services.source_materialization import SourceMaterializer


def _timeline() -> SharedTimeline:
    return SharedTimeline(
        schema_version=1,
        bpm=92,
        beats_per_bar=4,
        beat_source="fake-worker",
        lyric_source="fake-worker",
        bars=[],
        lyrics=[],
    )


class Processor:
    def process(self, path: Path) -> SharedTimeline:
        assert path.read_bytes() == b"RIFF cloud audio"
        return _timeline()


class FailingQueue(InMemoryAnalysisJobQueue):
    def __init__(self) -> None:
        super().__init__()
        self.fail = True

    def enqueue(self, descriptor):
        if self.fail:
            raise CloudProviderError(
                CloudProviderErrorKind.TEMPORARY_UNAVAILABLE,
                "Queue is temporarily unavailable",
            )
        super().enqueue(descriptor)


class FailingArtifactStorage(LocalArtifactStorage):
    def put_bytes(self, key, content, *, content_type):
        raise CloudProviderError(
            CloudProviderErrorKind.TEMPORARY_UNAVAILABLE,
            "private provider response /account/123",
        )


def _cloud_application(tmp_path, *, repository=None, queue=None, storage=None):
    repository = repository or InMemoryCloudJobRepository()
    queue = queue or InMemoryAnalysisJobQueue()
    storage = storage or LocalArtifactStorage(tmp_path / "objects")
    staging = LocalAnalysisInputStorage(
        tmp_path / "staging",
        duration_probe=lambda _: 12.5,
    )
    application = CloudAnalysisApplication(
        repository,
        storage,
        QueueBackedDispatcher(repository, storage, queue),
        staging,
    )
    return application, repository, storage, queue, staging


def _post(client):
    return client.post(
        "/analysis/jobs",
        data={"title": "Cloud song"},
        files={"audio": ("song.wav", b"RIFF cloud audio", "audio/wav")},
    )


def _consumer(tmp_path, repository, storage, queue):
    workspace = tmp_path / "worker"
    return AnalysisWorkerConsumer(
        queue,
        repository,
        storage,
        SourceMaterializer(storage, workspace),
        Processor(),
        AnalysisResultPublisher(repository, storage),
        ArtifactCleanup(workspace, storage),
    )


def test_cloud_api_fake_end_to_end_flow(tmp_path):
    application, repository, storage, queue, staging = _cloud_application(tmp_path)
    app.dependency_overrides[get_analysis_application_service] = lambda: application
    try:
        client = TestClient(app)
        created = _post(client)
        assert created.status_code == 202
        job_id = created.json()["job_id"]
        job = repository.get(job_id)
        assert job.status is CloudJobStatus.QUEUED
        assert job.dispatch_pending is False
        assert job.duration_seconds == 12.5
        assert job.source_object_key
        assert storage.exists(
            ArtifactKey(ArtifactRole.SOURCE_UPLOAD, job.source_object_key)
        )
        assert list(staging.root.rglob("*")) == []

        assert _consumer(tmp_path, repository, storage, queue).process_once().value == (
            "completed"
        )

        status = client.get(f"/analysis/jobs/{job_id}")
        result = client.get(f"/analysis/jobs/{job_id}/result")
        assert status.status_code == 200
        assert status.json()["status"] == "completed"
        assert status.json()["result_available"] is True
        assert "object_key" not in status.text
        assert result.status_code == 200
        assert result.json() == _timeline().model_dump(mode="json")
        completed = repository.get(job_id)
        assert completed.playback_object_key
        assert completed.timeline_object_key
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("filename", "content", "status_code", "error_code"),
    [
        ("song.txt", b"not audio", 415, "unsupported_audio_format"),
        ("song.wav", b"", 400, "empty_audio"),
    ],
)
def test_cloud_api_preserves_upload_validation(
    tmp_path, filename, content, status_code, error_code
):
    application, _, _, queue, staging = _cloud_application(tmp_path)
    app.dependency_overrides[get_analysis_application_service] = lambda: application
    try:
        response = TestClient(app).post(
            "/analysis/jobs",
            data={"title": "Invalid cloud upload"},
            files={"audio": (filename, content, "application/octet-stream")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == error_code
    assert queue.receive() is None
    assert list(staging.root.rglob("*")) == []


def test_cloud_source_storage_failure_is_safe_and_not_dispatched(tmp_path):
    storage = FailingArtifactStorage(tmp_path / "objects")
    application, _, _, queue, staging = _cloud_application(
        tmp_path, storage=storage
    )
    app.dependency_overrides[get_analysis_application_service] = lambda: application
    try:
        response = _post(TestClient(app))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "source_storage_failed"
    assert "private provider" not in response.text
    assert queue.receive() is None
    assert list(staging.root.rglob("*")) == []


def test_dispatch_failure_is_durable_and_reconcilable_without_upload(tmp_path):
    queue = FailingQueue()
    database = tmp_path / "state" / "jobs.sqlite3"
    first_repository = SqliteCloudJobRepository(database)
    application, repository, storage, _, staging = _cloud_application(
        tmp_path, queue=queue, repository=first_repository
    )
    app.dependency_overrides[get_analysis_application_service] = lambda: application
    try:
        response = _post(TestClient(app))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = repository.get(job_id)
    assert job.status is CloudJobStatus.QUEUED
    assert job.dispatch_pending is True
    assert job.source_object_key
    assert storage.exists(ArtifactKey(ArtifactRole.SOURCE_UPLOAD, job.source_object_key))
    assert list(staging.root.rglob("*")) == []

    repository = SqliteCloudJobRepository(database)
    queue.fail = False
    assert DispatchReconciler(repository, queue).reconcile() == 1
    assert repository.get(job_id).dispatch_pending is False
    assert DispatchReconciler(repository, queue).reconcile() == 0
    assert queue.receive().descriptor.job_id == job_id


def test_cloud_result_errors_are_safe(tmp_path):
    application, repository, storage, _, _ = _cloud_application(tmp_path)
    app.dependency_overrides[get_analysis_application_service] = lambda: application
    client = TestClient(app)
    try:
        created = _post(client).json()
        job = repository.get(created["job_id"])
        assert client.get(f"/analysis/jobs/{job.job_id}/result").status_code == 409

        job.transition_to(CloudJobStatus.PROCESSING)
        repository.save(job, expected_status=CloudJobStatus.QUEUED)
        job.transition_to(CloudJobStatus.FAILED)
        job.error_code = "analysis_failed"
        job.error_message = "Analysis could not be completed."
        repository.save(job, expected_status=CloudJobStatus.PROCESSING)
        failed = client.get(f"/analysis/jobs/{job.job_id}/result")
        assert failed.status_code == 409
        assert failed.json()["error"]["code"] == "analysis_failed"

        missing_job = repository.get(job.job_id)
        missing_job.status = CloudJobStatus.COMPLETED
        missing_job.timeline_object_key = "jobs/%s/results/timeline.json" % job.job_id
        repository.save(missing_job, expected_status=CloudJobStatus.FAILED)
        missing = client.get(f"/analysis/jobs/{job.job_id}/result")
        assert missing.status_code == 409
        assert missing.json()["error"]["code"] == "result_artifact_missing"

        storage.put_bytes(
            ArtifactKey(ArtifactRole.TIMELINE_RESULT, missing_job.timeline_object_key),
            b"not-json",
            content_type="application/json",
        )
        corrupt = client.get(f"/analysis/jobs/{job.job_id}/result")
        assert corrupt.status_code == 500
        assert corrupt.json()["error"]["code"] == "result_artifact_corrupt"
        assert "not-json" not in corrupt.text
    finally:
        app.dependency_overrides.clear()


def test_cloud_api_sqlite_and_artifact_result_survive_restart(tmp_path):
    database = tmp_path / "state" / "jobs.sqlite3"
    object_root = tmp_path / "objects"
    first_repo = SqliteCloudJobRepository(database)
    first_storage = LocalArtifactStorage(object_root)
    first, _, _, queue, _ = _cloud_application(
        tmp_path,
        repository=first_repo,
        storage=first_storage,
    )
    app.dependency_overrides[get_analysis_application_service] = lambda: first
    try:
        job_id = _post(TestClient(app)).json()["job_id"]
    finally:
        app.dependency_overrides.clear()
    _consumer(tmp_path, first_repo, first_storage, queue).process_once()

    second_repo = SqliteCloudJobRepository(database)
    second_storage = LocalArtifactStorage(object_root)
    second = CloudAnalysisApplication(
        second_repo,
        second_storage,
        QueueBackedDispatcher(second_repo, second_storage, InMemoryAnalysisJobQueue()),
        LocalAnalysisInputStorage(
            tmp_path / "second-staging", duration_probe=lambda _: 1.0
        ),
    )
    app.dependency_overrides[get_analysis_application_service] = lambda: second
    try:
        client = TestClient(app)
        assert client.get(f"/analysis/jobs/{job_id}").json()["status"] == "completed"
        result = client.get(f"/analysis/jobs/{job_id}/result")
        assert result.status_code == 200
        assert result.json() == _timeline().model_dump(mode="json")
    finally:
        app.dependency_overrides.clear()
