from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from analysis.fusion.models import SharedTimeline
from analysis.lyrics.models import LyricSegment, LyricWord
from analysis.temporal.models import Bar, TimelineEvent
from backend.api.app.main import app
from backend.api.app.routers.analysis_jobs import (
    get_analysis_job_executor,
    get_analysis_job_service,
)
from backend.api.app.services.analysis_jobs import (
    AnalysisJobService,
    InMemoryAnalysisJobRepository,
)
from backend.api.app.services.analysis_input_storage import LocalAnalysisInputStorage


@pytest.fixture
def job_service(tmp_path):
    service = AnalysisJobService(
        InMemoryAnalysisJobRepository(),
        LocalAnalysisInputStorage(tmp_path / "uploads"),
    )
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


def synthetic_timeline() -> SharedTimeline:
    return SharedTimeline(
        schema_version=1,
        bpm=120.0,
        beats_per_bar=4,
        beat_source="synthetic-grid",
        lyric_source="synthetic-words",
        bars=[
            Bar(
                bar_number=1,
                start_time=0.0,
                end_time=2.0,
                beats=[
                    TimelineEvent(
                        time=0.0,
                        beat_number=1,
                        is_downbeat=True,
                        chord="C",
                    )
                ],
            )
        ],
        lyrics=[
            LyricSegment(
                start=0.25,
                end=0.75,
                text="steady",
                words=[LyricWord(start=0.25, end=0.75, text="steady")],
            )
        ],
    )


def create_job(client: TestClient, title: str = "Synthetic practice") -> dict:
    response = client.post(
        "/analysis/jobs",
        data={"title": title},
        files={"audio": ("synthetic.wav", b"RIFF synthetic audio", "audio/wav")},
    )
    assert response.status_code == 202
    return response.json()


def test_create_job_returns_queued_contract_with_aware_timestamp(client):
    payload = create_job(client)

    assert payload["status"] == "queued"
    assert payload["error"] is None
    assert payload["result_available"] is False
    assert UUID(payload["job_id"])
    created_at = datetime.fromisoformat(payload["created_at"])
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() is not None


def test_two_jobs_have_distinct_stable_ids_and_can_be_retrieved(client):
    first = create_job(client, "First synthetic job")
    second = create_job(client, "Second synthetic job")

    assert first["job_id"] != second["job_id"]
    response = client.get(f"/analysis/jobs/{first['job_id']}")
    assert response.status_code == 200
    assert response.json()["job_id"] == first["job_id"]
    assert response.json()["created_at"] == first["created_at"]
    assert datetime.fromisoformat(response.json()["updated_at"]).tzinfo is not None


def test_unknown_job_uses_safe_404_error_contract(client):
    response = client.get("/analysis/jobs/00000000-0000-0000-0000-000000000000")
    result_response = client.get(
        "/analysis/jobs/00000000-0000-0000-0000-000000000000/result"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "job_not_found",
            "message": "Analysis job was not found.",
        }
    }
    assert result_response.status_code == 404
    assert result_response.json() == response.json()


@pytest.mark.parametrize("status", ["queued", "processing"])
def test_result_is_not_ready_for_active_jobs(client, job_service, status):
    job = create_job(client)
    if status == "processing":
        job_service.mark_processing(job["job_id"])

    response = client.get(f"/analysis/jobs/{job['job_id']}/result")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "result_not_ready",
            "message": "Analysis result is not ready.",
        }
    }


def test_completed_job_returns_shared_timeline_contract(client, job_service):
    job = create_job(client)
    timeline = synthetic_timeline()
    job_service.mark_processing(job["job_id"])
    job_service.complete(job["job_id"], timeline)

    status_response = client.get(f"/analysis/jobs/{job['job_id']}")
    result_response = client.get(f"/analysis/jobs/{job['job_id']}/result")

    assert status_response.json()["status"] == "completed"
    assert status_response.json()["result_available"] is True
    assert result_response.status_code == 200
    assert result_response.json() == timeline.model_dump(mode="json")


def test_failed_job_exposes_only_safe_error(client, job_service):
    job = create_job(client)
    job_service.mark_processing(job["job_id"])
    job_service.fail(
        job["job_id"],
        code="analysis_failed",
        message="Analysis could not be completed.",
    )

    status_response = client.get(f"/analysis/jobs/{job['job_id']}")
    result_response = client.get(f"/analysis/jobs/{job['job_id']}/result")

    expected_error = {
        "code": "analysis_failed",
        "message": "Analysis could not be completed.",
    }
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "failed"
    assert status_response.json()["error"] == expected_error
    assert result_response.status_code == 409
    assert result_response.json() == {"error": expected_error}
    serialized = str(result_response.json()).lower()
    assert "traceback" not in serialized
    assert "/users/" not in serialized


def test_lifecycle_values_serialize_exactly(client, job_service):
    job = create_job(client)
    assert client.get(f"/analysis/jobs/{job['job_id']}").json()["status"] == "queued"

    job_service.mark_processing(job["job_id"])
    assert (
        client.get(f"/analysis/jobs/{job['job_id']}").json()["status"]
        == "processing"
    )

    job_service.complete(job["job_id"], synthetic_timeline())
    assert (
        client.get(f"/analysis/jobs/{job['job_id']}").json()["status"]
        == "completed"
    )

    failed = create_job(client, "Failure lifecycle")
    job_service.mark_processing(failed["job_id"])
    job_service.fail(failed["job_id"], "analysis_failed", "Safe failure.")
    assert (
        client.get(f"/analysis/jobs/{failed['job_id']}").json()["status"]
        == "failed"
    )


@pytest.mark.parametrize("title", [None, "", "   "])
def test_invalid_create_request_returns_422(client, title):
    data = {} if title is None else {"title": title}
    response = client.post(
        "/analysis/jobs",
        data=data,
        files={"audio": ("synthetic.wav", b"RIFF synthetic audio", "audio/wav")},
    )

    assert response.status_code == 422


def test_openapi_exposes_only_public_typed_contract(client):
    schema = client.get("/openapi.json").json()

    assert "/analysis/jobs" in schema["paths"]
    assert "/analysis/jobs/{job_id}" in schema["paths"]
    assert "/analysis/jobs/{job_id}/result" in schema["paths"]
    schemas = schema["components"]["schemas"]
    assert schemas["AnalysisJobStatus"]["enum"] == [
        "queued",
        "processing",
        "completed",
        "failed",
    ]
    assert "AnalysisJobResponse" in schemas
    assert "AnalysisJobErrorResponse" in schemas
    assert "SharedTimeline" in schemas
    assert "InMemoryAnalysisJobRepository" not in schemas
    assert "AnalysisJobRecord" not in schemas
