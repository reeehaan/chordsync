from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app.main import app
from backend.api.app.models.analysis_job import AnalysisJobCreateRequest
from backend.api.app.routers.analysis_jobs import (
    get_analysis_job_executor,
    get_analysis_job_service,
)
from backend.api.app.services.analysis_input_storage import (
    AnalysisInputStorageError,
    AudioTooLongError,
    InvalidAudioError,
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUDIO_SIZE_BYTES,
    LocalAnalysisInputStorage,
)
from backend.api.app.services.analysis_jobs import (
    AnalysisJobService,
    InMemoryAnalysisJobRepository,
)


@pytest.fixture
def repository():
    return InMemoryAnalysisJobRepository()


@pytest.fixture
def input_storage(tmp_path):
    return LocalAnalysisInputStorage(
        tmp_path / "uploads",
        duration_probe=lambda _: 1.0,
    )


@pytest.fixture
def job_service(repository, input_storage):
    service = AnalysisJobService(repository, input_storage)
    app.dependency_overrides[get_analysis_job_service] = lambda: service
    app.dependency_overrides[get_analysis_job_executor] = lambda: DeferredExecutor()
    yield service
    app.dependency_overrides.clear()


class DeferredExecutor:
    def submit(self, job_id: str) -> None:
        pass


@pytest.fixture
def client(job_service):
    return TestClient(app)


def upload_job(
    client: TestClient,
    *,
    filename: str = "synthetic.wav",
    content: bytes = b"RIFF publication-safe synthetic audio",
    content_type: str = "audio/wav",
    title: str = "Synthetic practice",
):
    return client.post(
        "/analysis/jobs",
        data={"title": title},
        files={"audio": (filename, content, content_type)},
    )


def test_synthetic_wav_upload_creates_queued_job_and_stores_input(
    client, job_service, input_storage
):
    response = upload_job(client)

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["result_available"] is False
    job = job_service.get(payload["job_id"])
    assert job is not None
    assert job.input is not None
    assert job.input.original_filename == "synthetic.wav"
    assert job.input.size_bytes == len(b"RIFF publication-safe synthetic audio")
    stored_path = input_storage.get_path(payload["job_id"])
    assert stored_path is not None
    assert stored_path.exists()
    assert stored_path.read_bytes() == b"RIFF publication-safe synthetic audio"
    assert stored_path.name == "input.wav"
    assert payload["job_id"] in stored_path.parts
    assert str(stored_path.resolve()) not in response.text


def test_existing_publication_safe_wav_fixture_can_be_uploaded(
    client, job_service, input_storage
):
    fixture = Path("mobile/assets/practice_audio/synthetic_practice.wav")

    response = upload_job(client, content=fixture.read_bytes())

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    stored_path = input_storage.get_path(job_id)
    assert stored_path is not None
    assert stored_path.stat().st_size == fixture.stat().st_size
    assert job_service.get(job_id) is not None


def test_real_ffprobe_duration_is_recorded_for_valid_audio(tmp_path):
    fixture = Path("mobile/assets/practice_audio/synthetic_practice.wav")
    storage = LocalAnalysisInputStorage(tmp_path / "uploads")

    metadata = storage.store(
        job_id="real-probe",
        original_filename="synthetic.wav",
        content_type="audio/wav",
        source=BytesIO(fixture.read_bytes()),
    )

    assert metadata.duration_seconds == pytest.approx(9.0, abs=0.1)


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("synthetic.mp3", "audio/mpeg"), ("synthetic.m4a", "audio/mp4")],
)
def test_supported_compressed_extensions_pass_contract_validation(
    client, input_storage, filename, content_type
):
    response = upload_job(
        client,
        filename=filename,
        content=b"synthetic contract bytes",
        content_type=content_type,
    )

    assert response.status_code == 202
    assert input_storage.get_path(response.json()["job_id"]).suffix == Path(
        filename
    ).suffix


def test_path_traversal_filename_cannot_control_destination(
    client, job_service, input_storage, tmp_path
):
    response = upload_job(client, filename="../../evil.wav")

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = job_service.get(job_id)
    assert job is not None
    assert job.input is not None
    assert job.input.original_filename == "evil.wav"
    stored_path = input_storage.get_path(job_id)
    assert stored_path == tmp_path / "uploads" / job_id / "input.wav"
    assert not (tmp_path / "evil.wav").exists()


def test_two_jobs_with_same_original_filename_do_not_collide(client, input_storage):
    first = upload_job(client, content=b"first")
    second = upload_job(client, content=b"second")

    assert first.status_code == 202
    assert second.status_code == 202
    first_id = first.json()["job_id"]
    second_id = second.json()["job_id"]
    assert first_id != second_id
    assert input_storage.get_path(first_id).read_bytes() == b"first"
    assert input_storage.get_path(second_id).read_bytes() == b"second"


@pytest.mark.parametrize(
    ("filename", "content", "expected_status", "expected_code"),
    [
        ("empty.wav", b"", 400, "empty_audio"),
        ("notes.txt", b"not audio", 415, "unsupported_audio_format"),
        ("huge.wav", b"x" * (MAX_AUDIO_SIZE_BYTES + 1), 413, "audio_too_large"),
    ],
    ids=["empty", "unsupported", "oversized"],
)
def test_invalid_upload_creates_no_job_and_retains_no_file(
    client,
    repository,
    input_storage,
    filename,
    content,
    expected_status,
    expected_code,
):
    response = upload_job(client, filename=filename, content=content)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert repository.count() == 0
    assert list(input_storage.root.rglob("*")) == []


def test_missing_audio_is_rejected_before_job_creation(client, repository, input_storage):
    response = client.post("/analysis/jobs", data={"title": "Missing audio"})

    assert response.status_code == 422
    assert repository.count() == 0
    assert list(input_storage.root.rglob("*")) == []


def test_storage_delete_support_removes_the_job_input(input_storage):
    metadata = input_storage.store(
        job_id="job-id",
        original_filename="synthetic.wav",
        content_type="audio/wav",
        source=BytesIO(b"audio"),
    )

    assert metadata.size_bytes == 5
    assert input_storage.get_path("job-id").exists()

    input_storage.delete("job-id")

    assert input_storage.get_path("job-id") is None


def test_audio_over_six_minutes_is_rejected_and_removed(tmp_path):
    storage = LocalAnalysisInputStorage(
        tmp_path / "uploads",
        duration_probe=lambda _: MAX_AUDIO_DURATION_SECONDS + 0.001,
    )

    with pytest.raises(AudioTooLongError):
        storage.store(
            job_id="too-long",
            original_filename="song.mp3",
            content_type="audio/mpeg",
            source=BytesIO(b"synthetic audio"),
        )

    assert list(storage.root.rglob("*")) == []


def test_audio_at_six_minutes_is_accepted(tmp_path):
    storage = LocalAnalysisInputStorage(
        tmp_path / "uploads",
        duration_probe=lambda _: MAX_AUDIO_DURATION_SECONDS,
    )

    metadata = storage.store(
        job_id="six-minutes",
        original_filename="song.m4a",
        content_type="audio/mp4",
        source=BytesIO(b"synthetic audio"),
    )

    assert metadata.size_bytes == len(b"synthetic audio")
    assert storage.get_path("six-minutes") is not None


def test_undecodable_audio_is_rejected_and_removed(tmp_path):
    def fail_probe(_: Path) -> float:
        raise RuntimeError("ffprobe rejected input")

    storage = LocalAnalysisInputStorage(
        tmp_path / "uploads",
        duration_probe=fail_probe,
    )

    with pytest.raises(InvalidAudioError):
        storage.store(
            job_id="invalid",
            original_filename="song.wav",
            content_type="audio/wav",
            source=BytesIO(b"not audio"),
        )

    assert list(storage.root.rglob("*")) == []


@pytest.mark.parametrize("duration", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_decoded_duration_is_rejected_and_removed(tmp_path, duration):
    storage = LocalAnalysisInputStorage(
        tmp_path / "uploads",
        duration_probe=lambda _: duration,
    )

    with pytest.raises(InvalidAudioError):
        storage.store(
            job_id="invalid-duration",
            original_filename="song.wav",
            content_type="audio/wav",
            source=BytesIO(b"synthetic audio"),
        )

    assert list(storage.root.rglob("*")) == []


def test_overlong_upload_returns_safe_api_error(client, repository, tmp_path):
    storage = LocalAnalysisInputStorage(
        tmp_path / "duration-limited-uploads",
        duration_probe=lambda _: MAX_AUDIO_DURATION_SECONDS + 1,
    )
    service = AnalysisJobService(repository, storage)
    app.dependency_overrides[get_analysis_job_service] = lambda: service

    response = upload_job(client, filename="long.mp3", content=b"synthetic audio")

    assert response.status_code == 413
    assert response.json() == {
        "error": {
            "code": "audio_too_long",
            "message": "Audio exceeds the 6-minute limit.",
        }
    }
    assert repository.count() == 0
    assert list(storage.root.rglob("*")) == []


def test_storage_failure_returns_safe_error_and_creates_no_job(client, repository):
    class FailingStorage:
        def store(self, **kwargs):
            raise AnalysisInputStorageError("private disk detail /Users/example")

        def get_path(self, job_id):
            return None

        def delete(self, job_id):
            raise AssertionError("Nothing was stored, so delete must not be called")

    service = AnalysisJobService(repository, FailingStorage())
    app.dependency_overrides[get_analysis_job_service] = lambda: service

    response = upload_job(client)

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "audio_storage_failed",
            "message": "Audio could not be stored.",
        }
    }
    assert repository.count() == 0
    assert "private disk detail" not in response.text
    assert "/Users/" not in response.text


def test_repository_failure_rolls_back_stored_input(input_storage):
    class FailingRepository(InMemoryAnalysisJobRepository):
        def add(self, job):
            raise RuntimeError("repository unavailable")

    service = AnalysisJobService(FailingRepository(), input_storage)

    with pytest.raises(RuntimeError, match="repository unavailable"):
        service.create(
            request=AnalysisJobCreateRequest(title="Synthetic practice"),
            original_filename="synthetic.wav",
            content_type="audio/wav",
            source=BytesIO(b"audio"),
        )

    assert list(input_storage.root.rglob("*")) == []


def test_openapi_describes_multipart_upload_without_storage_details(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/analysis/jobs"]["post"]
    request_body = operation["requestBody"]["content"]

    assert "multipart/form-data" in request_body
    multipart_schema = request_body["multipart/form-data"]["schema"]
    body_schema_name = multipart_schema["$ref"].split("/")[-1]
    body_schema = schema["components"]["schemas"][body_schema_name]
    assert set(body_schema["required"]) == {"title", "audio"}
    assert (
        body_schema["properties"]["audio"]["contentMediaType"]
        == "application/octet-stream"
    )
    serialized_schema = str(schema)
    assert "LocalAnalysisInputStorage" not in serialized_schema
    assert "stored_path" not in serialized_schema
    assert "/Users/" not in serialized_schema
    for status_code in ("400", "413", "415", "500"):
        response_schema = operation["responses"][status_code]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"].endswith("/AnalysisJobErrorResponse")
