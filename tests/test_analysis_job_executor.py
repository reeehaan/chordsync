from io import BytesIO
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from analysis.fusion.models import SharedTimeline
from analysis.lyrics.models import LyricSegment, LyricWord
from analysis.temporal.models import Bar, TimelineEvent
from backend.api.app.main import app
from backend.api.app.models.analysis_job import AnalysisJobCreateRequest
from backend.api.app.routers.analysis_jobs import (
    get_analysis_job_executor,
    get_analysis_job_service,
)
from backend.api.app.services.analysis_input_storage import LocalAnalysisInputStorage
from backend.api.app.services.analysis_job_executor import InProcessAnalysisJobExecutor
from backend.api.app.services.analysis_jobs import (
    AnalysisJobService,
    InMemoryAnalysisJobRepository,
)


def synthetic_timeline(chord: str = "C") -> SharedTimeline:
    return SharedTimeline(
        schema_version=1,
        bpm=120.0,
        beats_per_bar=4,
        beat_source="synthetic-executor",
        lyric_source="synthetic-executor",
        bars=[
            Bar(
                bar_number=1,
                start_time=0.0,
                end_time=1.0,
                beats=[
                    TimelineEvent(
                        time=0.0,
                        beat_number=1,
                        is_downbeat=True,
                        chord=chord,
                    )
                ],
            )
        ],
        lyrics=[
            LyricSegment(
                start=0.1,
                end=0.5,
                text="steady",
                words=[LyricWord(start=0.1, end=0.5, text="steady")],
            )
        ],
    )


class DeterministicProcessor:
    def __init__(self, result: SharedTimeline | None = None) -> None:
        self.result = result or synthetic_timeline()
        self.received_paths: list[Path] = []

    def process(self, input_path: Path) -> SharedTimeline:
        assert input_path.exists()
        self.received_paths.append(input_path)
        return self.result


class FailingProcessor:
    def process(self, input_path: Path) -> SharedTimeline:
        raise RuntimeError(f"secret processor failure at {input_path}")


class BlockingProcessor(DeterministicProcessor):
    def __init__(self, result: SharedTimeline | None = None) -> None:
        super().__init__(result)
        self.started = Event()
        self.release = Event()

    def process(self, input_path: Path) -> SharedTimeline:
        self.received_paths.append(input_path)
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test did not release processor")
        return self.result


@pytest.fixture
def executor_context(tmp_path):
    repository = InMemoryAnalysisJobRepository()
    storage = LocalAnalysisInputStorage(
        tmp_path / "uploads",
        duration_probe=lambda _: 1.0,
    )
    service = AnalysisJobService(repository, storage)
    return service, storage


def create_job(service: AnalysisJobService, title: str = "Executor test"):
    return service.create(
        request=AnalysisJobCreateRequest(title=title),
        original_filename="synthetic.wav",
        content_type="audio/wav",
        source=BytesIO(b"RIFF synthetic executor audio"),
    )


def test_queued_job_transitions_to_completed_with_shared_timeline(executor_context):
    service, storage = executor_context
    job = create_job(service)
    processor = DeterministicProcessor()
    executor = InProcessAnalysisJobExecutor(service, storage, processor)

    assert executor.run(job.job_id) is True

    record = service.get(job.job_id)
    assert record is not None
    assert record.status.value == "completed"
    assert record.result == processor.result
    assert service.response(record).result_available is True
    assert processor.received_paths == [storage.get_path(job.job_id)]
    assert storage.get_path(job.job_id).exists()


def test_processing_transition_is_observable_and_duplicate_start_is_blocked(
    executor_context,
):
    service, storage = executor_context
    job = create_job(service)
    processor = BlockingProcessor()
    executor = InProcessAnalysisJobExecutor(service, storage, processor)

    executor.submit(job.job_id)
    assert processor.started.wait(timeout=2)
    assert service.get(job.job_id).status.value == "processing"
    assert executor.run(job.job_id) is False
    assert len(processor.received_paths) == 1

    processor.release.set()
    executor.drain()
    assert service.get(job.job_id).status.value == "completed"
    executor.shutdown()


def test_processor_failure_is_safe_and_failed_job_cannot_rerun(executor_context):
    service, storage = executor_context
    job = create_job(service)
    executor = InProcessAnalysisJobExecutor(service, storage, FailingProcessor())

    assert executor.run(job.job_id) is True

    record = service.get(job.job_id)
    assert record.status.value == "failed"
    assert record.result is None
    assert service.response(record).result_available is False
    assert record.error.model_dump() == {
        "code": "analysis_failed",
        "message": "Analysis could not be completed.",
    }
    assert "secret" not in str(service.response(record).model_dump())
    assert executor.run(job.job_id) is False


def test_missing_stored_input_fails_safely(executor_context):
    service, storage = executor_context
    job = create_job(service)
    storage.delete(job.job_id)
    processor = DeterministicProcessor()
    executor = InProcessAnalysisJobExecutor(service, storage, processor)

    assert executor.run(job.job_id) is True

    record = service.get(job.job_id)
    assert record.status.value == "failed"
    assert record.error.code == "analysis_failed"
    assert processor.received_paths == []


def test_completed_job_cannot_be_rerun(executor_context):
    service, storage = executor_context
    job = create_job(service)
    processor = DeterministicProcessor()
    executor = InProcessAnalysisJobExecutor(service, storage, processor)

    assert executor.run(job.job_id) is True
    assert executor.run(job.job_id) is False
    assert len(processor.received_paths) == 1

    with pytest.raises(ValueError, match="must be processing"):
        service.fail(job.job_id, "analysis_failed", "Must not replace completion.")


def test_failed_job_cannot_be_completed_or_restarted(executor_context):
    service, storage = executor_context
    job = create_job(service)
    executor = InProcessAnalysisJobExecutor(service, storage, FailingProcessor())
    executor.run(job.job_id)

    assert executor.run(job.job_id) is False
    with pytest.raises(ValueError, match="must be processing"):
        service.complete(job.job_id, synthetic_timeline())


def test_two_jobs_execute_without_result_crossover(executor_context):
    service, storage = executor_context
    first = create_job(service, "First")
    second = create_job(service, "Second")
    first_processor = DeterministicProcessor(synthetic_timeline("C"))
    second_processor = DeterministicProcessor(synthetic_timeline("G"))

    assert InProcessAnalysisJobExecutor(service, storage, first_processor).run(
        first.job_id
    )
    assert InProcessAnalysisJobExecutor(service, storage, second_processor).run(
        second.job_id
    )

    assert service.get(first.job_id).result.bars[0].beats[0].chord == "C"
    assert service.get(second.job_id).result.bars[0].beats[0].chord == "G"


def test_upload_returns_before_processing_finishes_then_result_is_available(
    executor_context,
):
    service, storage = executor_context
    processor = BlockingProcessor()
    executor = InProcessAnalysisJobExecutor(service, storage, processor)
    app.dependency_overrides[get_analysis_job_service] = lambda: service
    app.dependency_overrides[get_analysis_job_executor] = lambda: executor

    try:
        with TestClient(app) as client:
            response = client.post(
                "/analysis/jobs",
                data={"title": "Asynchronous synthetic job"},
                files={"audio": ("synthetic.wav", b"RIFF synthetic", "audio/wav")},
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]
            assert processor.started.wait(timeout=2)
            assert client.get(f"/analysis/jobs/{job_id}").json()["status"] == "processing"
            pending = client.get(f"/analysis/jobs/{job_id}/result")
            assert pending.status_code == 409
            assert pending.json()["error"]["code"] == "result_not_ready"

            processor.release.set()
            executor.drain()

            status_response = client.get(f"/analysis/jobs/{job_id}")
            result_response = client.get(f"/analysis/jobs/{job_id}/result")
            assert status_response.json()["status"] == "completed"
            assert status_response.json()["result_available"] is True
            assert result_response.status_code == 200
            assert result_response.json() == processor.result.model_dump(mode="json")
    finally:
        processor.release.set()
        executor.shutdown()
        app.dependency_overrides.clear()


def test_failed_execution_remains_safe_through_result_endpoint(executor_context):
    service, storage = executor_context
    job = create_job(service)
    executor = InProcessAnalysisJobExecutor(service, storage, FailingProcessor())
    executor.run(job.job_id)
    app.dependency_overrides[get_analysis_job_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.get(f"/analysis/jobs/{job.job_id}/result")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "analysis_failed",
            "message": "Analysis could not be completed.",
        }
    }
    assert "secret processor failure" not in response.text
    assert str(storage.root) not in response.text


def test_openapi_does_not_expose_executor_or_processor_details():
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    serialized = str(schema)
    for internal_name in (
        "AnalysisJobExecutor",
        "InProcessAnalysisJobExecutor",
        "AnalysisProcessor",
        "UnavailableAnalysisProcessor",
        "processor_type",
        "executable_path",
        "python_environment",
    ):
        assert internal_name not in serialized
