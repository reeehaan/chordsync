from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import main as api_main
from backend.api.app.hosting import (
    DEFAULT_LAMBDA_STAGING_ROOT,
    ApiHostingConfig,
    HostingConfigurationError,
    HostingMode,
    lambda_staging_root,
)
from backend.api.app.routers import analysis_jobs
from backend.api.app.services.analysis_input_storage import AnalysisInputStorageError
from backend.api.app.services.cloud_job import CloudJobStatus
from backend.api.app.services.cloud_runtime import CloudRuntimeConfig, RuntimeMode
from backend.api.app.services.source_upload_store import InMemorySourceUploadStore
from tests import auth_helpers
from tests.test_cloud_analysis_api import _cloud_application, _consumer

LEGACY_UPLOAD = "/api/v1/audio/upload"
CLOUD_ROUTES = {
    "/analysis/jobs",
    "/analysis/jobs/{job_id}",
    "/analysis/jobs/{job_id}/result",
}
HOSTED_ROUTES = CLOUD_ROUTES | {"/analysis/jobs/{job_id}/confirm-upload"}
AUDIO = b"RIFF cloud audio"


def _hosted_application(tmp_path):
    from backend.api.app.services.artifact_storage import LocalArtifactStorage

    storage = LocalArtifactStorage(tmp_path / "objects")
    uploads = InMemorySourceUploadStore(mirror=storage)
    application, repository, storage, queue, staging = _cloud_application(
        tmp_path, storage=storage, uploads=uploads
    )
    application._enforce_ownership = True
    return application, repository, storage, queue, staging, uploads


def _create_and_upload(client, uploads, data=AUDIO):
    created = client.post(
        "/analysis/jobs",
        json={
            "title": "Cloud song",
            "filename": "song.wav",
            "declared_size_bytes": len(data),
            "content_type": "audio/wav",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    uploads.client_upload(body["source_object_key"], data, content_type="audio/wav")
    return body["job_id"]

HOSTED = ApiHostingConfig(
    HostingMode.LAMBDA,
    Path("/tmp/chordsync-api"),
    demo_token_parameter=auth_helpers.PARAMETER,
)


@pytest.fixture(autouse=True)
def _reset_cached_components():
    for provider in (
        analysis_jobs._runtime_config,
        analysis_jobs._hosting_config,
        analysis_jobs._cloud_application,
        analysis_jobs._local_job_executor,
        analysis_jobs._local_job_service,
        analysis_jobs._local_input_storage,
    ):
        provider.cache_clear()
    yield
    for provider in (
        analysis_jobs._runtime_config,
        analysis_jobs._hosting_config,
        analysis_jobs._cloud_application,
    ):
        provider.cache_clear()


# --- configuration ------------------------------------------------------------


def test_hosting_defaults_to_local():
    assert ApiHostingConfig.from_env({}).mode is HostingMode.LOCAL


def test_lambda_mode_uses_tmp_staging_root_by_default():
    config = ApiHostingConfig.from_env(
        {
            "CHORDSYNC_API_HOSTING_MODE": "lambda",
            "CHORDSYNC_RUNTIME_MODE": "aws",
            "CHORDSYNC_DEMO_TOKEN_PARAMETER": auth_helpers.PARAMETER,
        }
    )
    assert config.is_hosted
    assert config.staging_root == DEFAULT_LAMBDA_STAGING_ROOT
    assert config.staging_root.is_relative_to("/tmp")


def test_lambda_mode_refuses_the_local_in_process_runtime():
    with pytest.raises(HostingConfigurationError, match="RUNTIME_MODE=aws"):
        ApiHostingConfig.from_env({"CHORDSYNC_API_HOSTING_MODE": "lambda"})


def test_unknown_hosting_mode_is_rejected():
    with pytest.raises(HostingConfigurationError):
        ApiHostingConfig.from_env({"CHORDSYNC_API_HOSTING_MODE": "server"})


@pytest.mark.parametrize(
    "value",
    ["", "relative/dir", "/tmp", "/tmp/../etc", "/tmpfoo", "/var/tmp/x", "/app/storage"],
)
def test_staging_root_must_be_strictly_under_tmp(value):
    with pytest.raises(HostingConfigurationError):
        lambda_staging_root(value)


def test_custom_staging_root_under_tmp_is_accepted():
    assert lambda_staging_root("/tmp/custom-stage") == Path("/tmp/custom-stage")


# --- route registration -------------------------------------------------------


def _paths(application) -> set[str]:
    return set(application.openapi()["paths"])


def test_local_mode_keeps_the_legacy_upload_route():
    paths = _paths(api_main.create_app(ApiHostingConfig(HostingMode.LOCAL)))
    assert LEGACY_UPLOAD in paths
    assert CLOUD_ROUTES <= paths
    assert "/analysis/jobs/{job_id}/confirm-upload" not in paths


def test_hosted_mode_does_not_register_the_legacy_upload_route():
    application = api_main.create_app(HOSTED)

    paths = _paths(application)
    assert LEGACY_UPLOAD not in paths
    assert HOSTED_ROUTES | {"/", "/health"} <= paths
    response = TestClient(application).post(
        LEGACY_UPLOAD, files={"file": ("x.mp3", b"data", "audio/mpeg")}
    )
    assert response.status_code == 404


def test_hosted_health_endpoints_respond():
    client = TestClient(api_main.create_app(HOSTED))
    assert client.get("/").json()["status"] == "running"
    assert client.get("/health").json() == {"status": "healthy"}


# --- hosted cloud routes ------------------------------------------------------


def test_hosted_routes_use_cloud_provider_and_never_build_local_pipeline(
    tmp_path, monkeypatch
):
    application, repository, storage, queue, staging, uploads = _hosted_application(
        tmp_path
    )
    aws_config = CloudRuntimeConfig(
        mode=RuntimeMode.AWS,
        storage_root=tmp_path,
        aws_region="ap-southeast-1",
        s3_bucket="bucket",
        dynamodb_job_table="jobs",
        sqs_analysis_queue_url="https://sqs.example/queue",
    )
    monkeypatch.setattr(analysis_jobs, "_runtime_config", lambda: aws_config)
    monkeypatch.setattr(analysis_jobs, "_cloud_application", lambda config, root: application)
    auth_helpers.install(monkeypatch)
    client = TestClient(api_main.create_app(HOSTED), headers=auth_helpers.HEADERS_A)

    job_id = _create_and_upload(client, uploads)
    assert client.get(f"/analysis/jobs/{job_id}").json()["status"] == "awaiting_upload"
    assert client.post(f"/analysis/jobs/{job_id}/confirm-upload").status_code == 202
    assert client.get(f"/analysis/jobs/{job_id}").json()["status"] == "queued"
    assert client.get(f"/analysis/jobs/{job_id}/result").status_code == 409

    _consumer(tmp_path, repository, storage, queue).process_once()
    assert repository.get(job_id).status is CloudJobStatus.COMPLETED
    assert client.get(f"/analysis/jobs/{job_id}").json()["status"] == "completed"
    result = client.get(f"/analysis/jobs/{job_id}/result")
    assert result.status_code == 200
    assert result.json()["schema_version"] == 1

    assert analysis_jobs._local_job_executor.cache_info().currsize == 0
    assert analysis_jobs._local_job_service.cache_info().currsize == 0


def test_hosted_provider_stages_under_the_configured_tmp_root(monkeypatch):
    aws_config = CloudRuntimeConfig(
        mode=RuntimeMode.AWS,
        storage_root=Path("/var/task/storage"),
        aws_region="ap-southeast-1",
        s3_bucket="bucket",
        dynamodb_job_table="jobs",
        sqs_analysis_queue_url="https://sqs.example/queue",
    )
    roots = []
    monkeypatch.setattr(analysis_jobs, "_runtime_config", lambda: aws_config)
    monkeypatch.setattr(analysis_jobs, "_hosting_config", lambda: HOSTED)
    monkeypatch.setattr(
        analysis_jobs, "_cloud_application", lambda config, root: roots.append(root)
    )

    analysis_jobs.get_hosted_analysis_application()

    assert roots == [Path("/tmp/chordsync-api/cloud_api_staging")]


def test_hosted_provider_rejects_local_runtime(monkeypatch):
    monkeypatch.setattr(
        analysis_jobs,
        "_runtime_config",
        lambda: CloudRuntimeConfig(mode=RuntimeMode.LOCAL, storage_root=Path("/tmp")),
    )
    with pytest.raises(RuntimeError, match="AWS runtime"):
        analysis_jobs.get_hosted_analysis_application()


def test_staged_upload_is_removed_after_confirmation(tmp_path, monkeypatch):
    application, repository, storage, queue, staging, uploads = _hosted_application(
        tmp_path
    )
    monkeypatch.setattr(analysis_jobs, "_runtime_config", lambda: CloudRuntimeConfig(
        mode=RuntimeMode.AWS, storage_root=tmp_path, aws_region="r", s3_bucket="b",
        dynamodb_job_table="t", sqs_analysis_queue_url="https://q"))
    monkeypatch.setattr(analysis_jobs, "_cloud_application", lambda config, root: application)

    auth_helpers.install(monkeypatch)
    client = TestClient(api_main.create_app(HOSTED), headers=auth_helpers.HEADERS_A)
    job_id = _create_and_upload(client, uploads)
    confirmed = client.post(f"/analysis/jobs/{job_id}/confirm-upload")

    assert confirmed.status_code == 202
    assert not any(staging.root.rglob("*")), "staged upload was not cleaned up"


@pytest.mark.parametrize(
    "job_id",
    [
        "../escape",
        "..",
        ".",
        "a/b",
        "a/../../b",
        "../../etc/passwd",
        "..\\..\\windows",
        "/etc",
        "/tmp/chordsync-api/../escape",
        "a\\b",
        "",
    ],
)
def test_staging_rejects_path_traversal_job_ids(tmp_path, job_id):
    _, _, _, _, staging = _cloud_application(tmp_path)
    (tmp_path / "keep-me").write_text("parent directory content")
    with pytest.raises(AnalysisInputStorageError):
        staging.get_path(job_id)
    with pytest.raises(AnalysisInputStorageError):
        staging.delete(job_id)
    assert (tmp_path / "keep-me").exists()
