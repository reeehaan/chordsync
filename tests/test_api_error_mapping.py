from __future__ import annotations

import random
from pathlib import Path

import pytest
from botocore.exceptions import (
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    ReadTimeoutError,
)
from fastapi.testclient import TestClient

from backend.api.app import main as api_main
from backend.api.app.hosting import ApiHostingConfig, HostingMode
from tests import auth_helpers
from backend.api.app.routers import analysis_jobs
from backend.api.app.services.analysis_application import CloudAnalysisApplication
from backend.api.app.services.analysis_input_storage import LocalAnalysisInputStorage
from backend.api.app.services.analysis_job_dispatcher import QueueBackedDispatcher
from backend.api.app.services.analysis_job_queue import InMemoryAnalysisJobQueue
from backend.api.app.services.artifact_storage import LocalArtifactStorage
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
    translate_provider_error,
)
from backend.api.app.services.cloud_job import CloudJobStatus, new_cloud_job
from backend.api.app.services.cloud_job_repository import InMemoryCloudJobRepository
from backend.api.app.services.cloud_runtime import CloudRuntimeConfig, RuntimeMode
from backend.api.app.services.dynamodb_cloud_job_repository import (
    DynamoDbCloudJobRepository,
)

HOSTED = ApiHostingConfig(
    HostingMode.LAMBDA,
    Path("/tmp/chordsync-api"),
    demo_token_parameter=auth_helpers.PARAMETER,
)
JOB = "00000000-0000-4000-8000-000000000000"
SECRET_DETAIL = (
    "private provider response /account/123 "
    "https://dynamodb.ap-southeast-1.amazonaws.com arn:aws:dynamodb:ap-southeast-1:123456789012:table/jobs"
)
UNAVAILABLE_BODY = {
    "error": {
        "code": "service_unavailable",
        "message": "Analysis service is temporarily unavailable.",
    }
}


@pytest.fixture(autouse=True)
def _reset_cached_components():
    for provider in (
        analysis_jobs._runtime_config,
        analysis_jobs._hosting_config,
        analysis_jobs._cloud_application,
    ):
        provider.cache_clear()
    yield
    for provider in (
        analysis_jobs._runtime_config,
        analysis_jobs._hosting_config,
        analysis_jobs._cloud_application,
    ):
        provider.cache_clear()


def _hosted_client(monkeypatch, application, *, raise_server_exceptions=True) -> TestClient:
    monkeypatch.setattr(
        analysis_jobs,
        "_runtime_config",
        lambda: CloudRuntimeConfig(
            mode=RuntimeMode.AWS,
            storage_root=Path("/tmp"),
            aws_region="ap-southeast-1",
            s3_bucket="bucket",
            dynamodb_job_table="jobs",
            sqs_analysis_queue_url="https://sqs.example/queue",
        ),
    )
    monkeypatch.setattr(analysis_jobs, "_cloud_application", lambda config, root: application)
    auth_helpers.install(monkeypatch)
    return TestClient(
        api_main.create_app(HOSTED),
        raise_server_exceptions=raise_server_exceptions,
        headers=auth_helpers.HEADERS_A,
    )


class FailingApplication:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def create(self, **_kwargs):
        raise self._error

    def status(self, _job_id: str, _owner_id=None):
        raise self._error

    def result(self, _job_id: str, _owner_id=None):
        raise self._error


def _provider_error(kind: CloudProviderErrorKind) -> CloudProviderError:
    return CloudProviderError(kind, SECRET_DETAIL)


def _working_application(tmp_path, *, repository=None, storage=None):
    repository = repository or InMemoryCloudJobRepository()
    storage = storage or LocalArtifactStorage(tmp_path / "objects")
    staging = LocalAnalysisInputStorage(tmp_path / "staging")  # real validator
    application = CloudAnalysisApplication(
        repository,
        storage,
        QueueBackedDispatcher(repository, storage, InMemoryAnalysisJobQueue()),
        staging,
    )
    return application, repository


# --- transient dependency failures -> 503 ------------------------------------


@pytest.mark.parametrize("path", [f"/analysis/jobs/{JOB}", f"/analysis/jobs/{JOB}/result"])
def test_transient_dependency_failure_returns_clean_503(monkeypatch, path):
    client = _hosted_client(
        monkeypatch,
        FailingApplication(_provider_error(CloudProviderErrorKind.TEMPORARY_UNAVAILABLE)),
    )

    response = client.get(path)

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE_BODY
    assert response.headers["content-type"] == "application/json"


def test_503_body_exposes_no_internal_details(monkeypatch):
    client = _hosted_client(
        monkeypatch,
        FailingApplication(_provider_error(CloudProviderErrorKind.TEMPORARY_UNAVAILABLE)),
    )

    text = client.get(f"/analysis/jobs/{JOB}").text.casefold()

    for leaked in ("account/123", "amazonaws", "arn:", "dynamodb", "traceback", "private provider"):
        assert leaked not in text


def test_a_botocore_connection_failure_through_the_real_adapter_is_a_503(tmp_path, monkeypatch):
    class UnreachableTable:
        def get_item(self, **_kwargs):
            raise EndpointConnectionError(endpoint_url="https://secret-endpoint.internal:9999")

    repository = DynamoDbCloudJobRepository(UnreachableTable())
    application, _ = _working_application(tmp_path, repository=repository)
    client = _hosted_client(monkeypatch, application)

    for path in (f"/analysis/jobs/{JOB}", f"/analysis/jobs/{JOB}/result"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json() == UNAVAILABLE_BODY
        assert "secret-endpoint" not in response.text


@pytest.mark.parametrize(
    "error",
    [
        EndpointConnectionError(endpoint_url="https://secret.example"),
        ConnectTimeoutError(endpoint_url="https://secret.example"),
        ReadTimeoutError(endpoint_url="https://secret.example"),
        ConnectionClosedError(endpoint_url="https://secret.example"),
    ],
    ids=lambda e: type(e).__name__,
)
def test_network_errors_are_classified_as_transient_without_leaking(error):
    translated = translate_provider_error(error)

    assert translated.kind is CloudProviderErrorKind.TEMPORARY_UNAVAILABLE
    assert "secret.example" not in str(translated)


def test_missing_credentials_are_not_treated_as_transient():
    assert translate_provider_error(NoCredentialsError()).kind is (
        CloudProviderErrorKind.UNEXPECTED
    )


# --- genuine application responses are preserved -----------------------------


def test_unknown_job_is_still_404(tmp_path, monkeypatch):
    application, _ = _working_application(tmp_path)
    response = _hosted_client(monkeypatch, application).get(f"/analysis/jobs/{JOB}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


def test_result_before_completion_is_still_409(tmp_path, monkeypatch):
    application, repository = _working_application(tmp_path)
    job = new_cloud_job(JOB, "Song")
    job.transition_to(CloudJobStatus.AWAITING_UPLOAD)
    repository.add(job)

    response = _hosted_client(monkeypatch, application).get(f"/analysis/jobs/{JOB}/result")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "result_not_ready"


def test_hosted_api_does_not_accept_multipart_audio(tmp_path, monkeypatch):
    application, _ = _working_application(tmp_path)
    client = _hosted_client(monkeypatch, application)

    response = client.post(
        "/analysis/jobs",
        data={"title": "Song"},
        files={"audio": ("song.mp3", random.Random(9).randbytes(20_000), "audio/mpeg")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_storage_read_outage_keeps_its_own_503_code(tmp_path, monkeypatch):
    class UnreadableStorage(LocalArtifactStorage):
        def exists(self, key):
            return True

        def read_bytes(self, key):
            raise CloudProviderError(
                CloudProviderErrorKind.TEMPORARY_UNAVAILABLE, SECRET_DETAIL
            )

    repository = InMemoryCloudJobRepository()
    application, _ = _working_application(
        tmp_path, repository=repository, storage=UnreadableStorage(tmp_path / "objects")
    )
    job = new_cloud_job(JOB, "Song")
    job.timeline_object_key = f"jobs/{JOB}/results/timeline.json"
    job.transition_to(CloudJobStatus.AWAITING_UPLOAD)
    job.transition_to(CloudJobStatus.QUEUED)
    job.transition_to(CloudJobStatus.PROCESSING)
    job.transition_to(CloudJobStatus.COMPLETED)
    repository.add(job)

    response = _hosted_client(monkeypatch, application).get(f"/analysis/jobs/{JOB}/result")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "result_temporarily_unavailable"
    assert "account/123" not in response.text


# --- the mapping is narrow ----------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        CloudProviderErrorKind.CONFIGURATION,
        CloudProviderErrorKind.UNEXPECTED,
        CloudProviderErrorKind.CONDITIONAL_CONFLICT,
    ],
)
def test_non_transient_provider_errors_are_not_converted_to_503(monkeypatch, kind):
    client = _hosted_client(
        monkeypatch, FailingApplication(_provider_error(kind)), raise_server_exceptions=False
    )

    response = client.get(f"/analysis/jobs/{JOB}")

    assert response.status_code == 500
    assert "service_unavailable" not in response.text
    assert "account/123" not in response.text


def test_local_mode_does_not_register_the_503_mapping():
    local = api_main.create_app(ApiHostingConfig(HostingMode.LOCAL))
    hosted = api_main.create_app(HOSTED)

    assert CloudProviderError not in local.exception_handlers
    assert CloudProviderError in hosted.exception_handlers
