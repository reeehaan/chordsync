"""Hosted presigned-upload lifecycle (S7-T03), against in-memory AWS fakes."""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import main as api_main
from backend.api.app.hosting import (
    ApiHostingConfig,
    HostingConfigurationError,
    HostingMode,
)
from backend.api.app.routers import analysis_jobs
from backend.api.app.services.analysis_application import (
    VALIDATION_LEASE_SECONDS,
    CloudAnalysisApplication,
)
from backend.api.app.services.analysis_input_storage import (
    MAX_AUDIO_SIZE_BYTES,
    LocalAnalysisInputStorage,
)
from backend.api.app.services.analysis_job_dispatcher import (
    DispatchReconciler,
    QueueBackedDispatcher,
)
from backend.api.app.services.analysis_job_queue import InMemoryAnalysisJobQueue
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
from backend.api.app.services.cloud_job_repository import InMemoryCloudJobRepository
from backend.api.app.services.cloud_runtime import CloudRuntimeConfig, RuntimeMode
from backend.api.app.services.source_upload_store import (
    InMemorySourceUploadStore,
    S3SourceUploadStore,
)
from tests import auth_helpers
from tests import media_samples as ms

HOSTED = ApiHostingConfig(
    HostingMode.LAMBDA,
    Path("/tmp/chordsync-api"),
    demo_token_parameter=auth_helpers.PARAMETER,
)
KEY_PATTERN = re.compile(
    r"^jobs/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}/source/input\.(wav|mp3|m4a)$"
)
TTL = 600


class CountingQueue(InMemoryAnalysisJobQueue):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[object] = []
        self.fail = False

    def enqueue(self, descriptor):
        if self.fail:
            raise CloudProviderError(
                CloudProviderErrorKind.TEMPORARY_UNAVAILABLE, "queue down"
            )
        self.sent.append(descriptor)
        super().enqueue(descriptor)


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Env:
    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        self.artifacts = LocalArtifactStorage(tmp_path / "objects")
        self.uploads = InMemorySourceUploadStore(mirror=self.artifacts)
        self.repository = InMemoryCloudJobRepository()
        self.queue = CountingQueue()
        self.clock = Clock()
        self.staging_root = tmp_path / "staging"
        self.application = CloudAnalysisApplication(
            self.repository,
            self.artifacts,
            QueueBackedDispatcher(self.repository, self.artifacts, self.queue),
            LocalAnalysisInputStorage(self.staging_root),
            source_uploads=self.uploads,
            upload_url_ttl_seconds=TTL,
            clock=self.clock,
            enforce_ownership=True,
        )
        auth_helpers.install(monkeypatch)
        monkeypatch.setattr(
            analysis_jobs,
            "_runtime_config",
            lambda: CloudRuntimeConfig(
                mode=RuntimeMode.AWS,
                storage_root=tmp_path,
                aws_region="ap-southeast-1",
                s3_bucket="bucket",
                dynamodb_job_table="jobs",
                sqs_analysis_queue_url="https://sqs.example/queue",
            ),
        )
        monkeypatch.setattr(
            analysis_jobs, "_cloud_application", lambda config, root: self.application
        )
        app = api_main.create_app(HOSTED)
        self.client = TestClient(
            app, raise_server_exceptions=False, headers=auth_helpers.HEADERS_A
        )
        self.client_b = TestClient(
            app, raise_server_exceptions=False, headers=auth_helpers.HEADERS_B
        )
        self.anonymous = TestClient(app, raise_server_exceptions=False)

    def create(self, filename="song.wav", size=1000, **extra):
        body = {"title": "Song", "filename": filename, "declared_size_bytes": size}
        body.update(extra)
        return self.client.post("/analysis/jobs", json=body)

    def create_and_upload(self, data: bytes, filename="song.wav", **upload):
        created = self.create(filename, len(data))
        assert created.status_code == 201, created.text
        body = created.json()
        self.uploads.client_upload(
            body["source_object_key"],
            data,
            **{"content_type": _type(filename), **upload},
        )
        return body["job_id"]

    def confirm(self, job_id):
        return self.client.post(f"/analysis/jobs/{job_id}/confirm-upload")

    def job(self, job_id):
        return self.repository.get(job_id)

    def staged_files(self):
        return [p for p in self.staging_root.rglob("*") if p.is_file()] if self.staging_root.exists() else []


def _type(filename: str) -> str:
    return {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4"}[filename.rsplit(".", 1)[-1]]


@pytest.fixture(autouse=True)
def _reset():
    for provider in (analysis_jobs._runtime_config, analysis_jobs._cloud_application):
        provider.cache_clear()
    yield
    for provider in (analysis_jobs._runtime_config, analysis_jobs._cloud_application):
        provider.cache_clear()


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


WAV = ms.wav_bytes(2.0)


# --- create ---------------------------------------------------------------------


def test_create_returns_a_signed_put_and_does_not_queue(env):
    response = env.create("song.wav", len(WAV), content_type="audio/wav")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "job_id", "status", "upload_url", "upload_method", "required_headers",
        "expires_at", "source_object_key",
    }
    assert body["status"] == "awaiting_upload"
    assert body["upload_method"] == "PUT"
    assert KEY_PATTERN.match(body["source_object_key"])
    assert body["source_object_key"] == f"jobs/{body['job_id']}/source/input.wav"
    assert body["required_headers"]["Content-Type"] == "audio/wav"
    assert body["required_headers"]["x-amz-server-side-encryption"] == "AES256"
    expires = datetime.fromisoformat(body["expires_at"])
    assert abs((expires - env.clock.now).total_seconds() - TTL) < 1
    assert env.job(body["job_id"]).status is CloudJobStatus.AWAITING_UPLOAD
    assert env.queue.sent == []


def test_the_client_cannot_choose_the_object_key(env):
    response = env.create(
        "song.wav", 1000,
        source_object_key="jobs/someone-else/source/input.wav",
        job_id="00000000-0000-4000-8000-000000000000",
        bucket="other",
    )

    body = response.json()
    assert response.status_code == 201
    assert body["source_object_key"] == f"jobs/{body['job_id']}/source/input.wav"
    assert body["job_id"] != "00000000-0000-4000-8000-000000000000"
    request = env.uploads.presign_requests[-1]
    assert request["key"] == body["source_object_key"]


@pytest.mark.parametrize(
    "filename",
    ["../../etc/passwd.wav", "..\\..\\x.wav", "a/b/c.wav", "/abs/path.wav", "x.wav\x00.exe.wav"],
)
def test_filenames_never_influence_the_key_beyond_the_extension(env, filename):
    response = env.create(filename, 1000)
    if response.status_code == 201:
        key = response.json()["source_object_key"]
        assert KEY_PATTERN.match(key) and ".." not in key
    else:
        assert response.status_code == 400


@pytest.mark.parametrize("filename", ["song.exe", "song", "song.mp3.exe", "song.flac", ".mp3x"])
def test_unsupported_extensions_are_a_400(env, filename):
    response = env.create(filename, 1000)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_audio_format"
    assert env.repository._jobs == {}


@pytest.mark.parametrize("size", [0, -1, -MAX_AUDIO_SIZE_BYTES])
def test_non_positive_declared_size_is_a_400(env, size):
    response = env.create("song.wav", size)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_declared_size_over_25_mb_is_a_413_and_exactly_25_mb_is_not(env):
    over = env.create("song.wav", MAX_AUDIO_SIZE_BYTES + 1)
    assert over.status_code == 413
    assert over.json()["error"]["code"] == "audio_too_large"
    assert env.create("song.wav", MAX_AUDIO_SIZE_BYTES).status_code == 201


def test_a_content_type_that_contradicts_the_extension_is_a_400(env):
    response = env.create("song.mp3", 1000, content_type="audio/wav")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_content_type"


@pytest.mark.parametrize("content_type", [None, "application/octet-stream", "audio/mpeg; x=y"])
def test_declared_content_type_is_only_a_hint(env, content_type):
    assert env.create("song.mp3", 1000, content_type=content_type).status_code == 201
    # The signed type is always the canonical one for the extension.
    assert env.uploads.presign_requests[-1]["content_type"] == "audio/mpeg"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": "x", "filename": "a.wav"},
        {"title": "x", "filename": "a.wav", "declared_size_bytes": "big"},
        {"title": " ", "filename": "a.wav", "declared_size_bytes": 5},
    ],
)
def test_malformed_create_bodies_are_a_400(env, body):
    response = env.client.post("/analysis/jobs", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_multipart_audio_is_not_accepted_by_the_hosted_api(env):
    response = env.client.post(
        "/analysis/jobs",
        data={"title": "x"},
        files={"audio": ("song.wav", WAV, "audio/wav")},
    )
    assert response.status_code == 400
    assert env.repository._jobs == {}


# --- confirm: success and idempotency ------------------------------------------------


def test_confirm_validates_queues_once_and_cleans_up(env):
    job_id = env.create_and_upload(WAV)

    response = env.confirm(job_id)

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert len(env.queue.sent) == 1
    sent = env.queue.sent[0]
    assert sent.job_id == job_id
    assert sent.source_artifact_key == f"jobs/{job_id}/source/input.wav"
    job = env.job(job_id)
    assert job.status is CloudJobStatus.QUEUED
    assert job.duration_seconds == pytest.approx(2.0)
    assert env.staged_files() == []
    assert env.uploads.deleted == []  # valid source is kept for the worker
    assert env.client.get(f"/analysis/jobs/{job_id}").json()["status"] == "queued"


def test_duplicate_confirm_sends_one_message(env):
    job_id = env.create_and_upload(WAV)

    first = env.confirm(job_id)
    second = env.confirm(job_id)
    third = env.confirm(job_id)

    assert first.status_code == 202
    assert second.status_code == third.status_code == 200
    assert second.json()["status"] == "queued"
    assert len(env.queue.sent) == 1


def test_confirm_after_the_worker_started_does_not_send_again(env):
    job_id = env.create_and_upload(WAV)
    env.confirm(job_id)
    job = env.job(job_id)
    job.transition_to(CloudJobStatus.PROCESSING)
    env.repository.save(job, expected_status=CloudJobStatus.QUEUED)

    response = env.confirm(job_id)

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert len(env.queue.sent) == 1


def test_concurrent_confirms_send_exactly_one_message(env):
    job_id = env.create_and_upload(WAV)
    original_head = env.uploads.head

    def slow_head(key):
        time.sleep(0.1)  # hold the claim long enough for the others to arrive
        return original_head(key)

    env.uploads.head = slow_head
    barrier = threading.Barrier(8)
    codes: list[int] = []

    def worker():
        barrier.wait()
        codes.append(env.confirm(job_id).status_code)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(env.queue.sent) == 1
    assert codes.count(202) == 1
    assert set(codes) <= {200, 202, 409}
    assert env.job(job_id).status is CloudJobStatus.QUEUED


def test_confirm_while_another_validation_is_running_is_a_409(env):
    job_id = env.create_and_upload(WAV)
    job = env.job(job_id)
    job.transition_to(CloudJobStatus.VALIDATING)
    env.repository.save(job, expected_status=CloudJobStatus.AWAITING_UPLOAD)

    response = env.confirm(job_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "validation_in_progress"
    assert env.queue.sent == []


def test_an_abandoned_validation_is_taken_over_after_the_lease(env):
    job_id = env.create_and_upload(WAV)
    job = env.job(job_id)
    job.transition_to(CloudJobStatus.VALIDATING)
    env.repository.save(job, expected_status=CloudJobStatus.AWAITING_UPLOAD)
    env.clock.advance(VALIDATION_LEASE_SECONDS + 1)

    response = env.confirm(job_id)

    assert response.status_code == 202
    assert len(env.queue.sent) == 1


def test_a_queue_outage_keeps_the_job_queued_and_reconcilable(env):
    job_id = env.create_and_upload(WAV)
    env.queue.fail = True

    first = env.confirm(job_id)

    assert first.status_code == 202
    job = env.job(job_id)
    assert job.status is CloudJobStatus.QUEUED and job.dispatch_pending
    assert env.queue.sent == []
    assert env.confirm(job_id).status_code == 200  # confirm never re-sends
    assert env.queue.sent == []

    env.queue.fail = False
    assert DispatchReconciler(env.repository, env.queue).reconcile() == 1
    assert len(env.queue.sent) == 1
    assert env.confirm(job_id).status_code == 200
    assert len(env.queue.sent) == 1


# --- confirm: missing, expired, tampered ----------------------------------------------


def test_unknown_job_is_a_404(env):
    response = env.confirm("00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


@pytest.mark.parametrize("job_id", ["..", ".", "not-a-job", "a%2Fb", "%2e%2e"])
def test_odd_job_ids_never_reach_storage(env, job_id):
    # Dot segments are normalised away by the HTTP client into a different route.
    assert env.confirm(job_id).status_code in {404, 405}
    assert env.uploads.deleted == []


def test_confirm_before_the_upload_is_recoverable(env):
    created = env.create("song.wav", len(WAV)).json()
    job_id = created["job_id"]

    early = env.confirm(job_id)
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "upload_not_received"
    assert env.job(job_id).status is CloudJobStatus.AWAITING_UPLOAD

    env.uploads.client_upload(created["source_object_key"], WAV, content_type="audio/wav")
    assert env.confirm(job_id).status_code == 202
    assert len(env.queue.sent) == 1


def test_an_expired_url_with_nothing_uploaded_expires_the_job(env):
    job_id = env.create("song.wav", len(WAV)).json()["job_id"]
    env.clock.advance(TTL + 1)

    response = env.confirm(job_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "upload_expired"
    job = env.job(job_id)
    assert job.status is CloudJobStatus.EXPIRED
    assert env.confirm(job_id).status_code == 409  # terminal: create a new job
    status = env.client.get(f"/analysis/jobs/{job_id}").json()
    assert status["status"] == "failed" and status["error"]["code"] == "upload_expired"
    assert env.queue.sent == []


def test_an_object_that_landed_before_expiry_is_accepted_late(env):
    job_id = env.create_and_upload(WAV)
    env.clock.advance(TTL * 3)
    assert env.confirm(job_id).status_code == 202


def test_a_job_pointing_at_another_jobs_key_cannot_be_confirmed(env):
    victim = env.create_and_upload(WAV)
    attacker = env.create("song.wav", len(WAV)).json()["job_id"]
    job = env.job(attacker)
    job.source_object_key = env.job(victim).source_object_key
    env.repository._jobs[attacker] = job
    heads: list[str] = []
    original = env.uploads.head
    env.uploads.head = lambda key: (heads.append(key.value), original(key))[1]

    response = env.confirm(attacker)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_job_state"
    assert heads == []  # the foreign key was never even inspected
    assert env.queue.sent == []
    assert env.uploads.deleted == []


# --- confirm: invalid uploads ----------------------------------------------------------


def _assert_rejected(env, job_id, response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    job = env.job(job_id)
    assert job.status is CloudJobStatus.FAILED
    assert job.error_code == code
    assert env.queue.sent == []
    assert env.uploads.deleted == [f"jobs/{job_id}/source/input.{job.file_type[1:]}"]
    assert env.uploads.objects == {}
    assert env.staged_files() == []
    # A rejected job is terminal and never dispatches.
    again = env.confirm(job_id)
    assert again.status_code == 409 and env.queue.sent == []


def test_malformed_media_is_a_422_and_the_object_is_deleted(env):
    job_id = env.create_and_upload(b"\x00" * 5000 + bytes(range(256)) * 20, "song.mp3")
    _assert_rejected(env, job_id, env.confirm(job_id), 422, "invalid_audio")


def test_extension_and_content_mismatch_is_a_422(env):
    job_id = env.create_and_upload(WAV, "song.mp3")  # WAV bytes behind an .mp3 name
    _assert_rejected(env, job_id, env.confirm(job_id), 422, "invalid_audio")


def test_audio_over_360_seconds_is_a_422(env):
    job_id = env.create_and_upload(ms.wav_bytes(361.0))
    _assert_rejected(env, job_id, env.confirm(job_id), 422, "audio_too_long")


def test_audio_of_exactly_360_seconds_is_accepted(env):
    job_id = env.create_and_upload(ms.wav_bytes(360.0))
    assert env.confirm(job_id).status_code == 202


def test_an_actual_object_over_25_mb_is_a_413_whatever_was_declared(env):
    created = env.create("song.wav", 1000).json()
    env.uploads.client_upload(
        created["source_object_key"], bytes(MAX_AUDIO_SIZE_BYTES + 1), content_type="audio/wav"
    )
    _assert_rejected(env, created["job_id"], env.confirm(created["job_id"]), 413, "audio_too_large")


def test_an_empty_object_is_a_422(env):
    created = env.create("song.wav", 10).json()
    env.uploads.client_upload(created["source_object_key"], b"", content_type="audio/wav")
    _assert_rejected(env, created["job_id"], env.confirm(created["job_id"]), 422, "empty_audio")


def test_an_object_whose_size_differs_from_the_declaration_is_a_422(env):
    created = env.create("song.wav", len(WAV) + 10).json()
    env.uploads.client_upload(created["source_object_key"], WAV, content_type="audio/wav")
    _assert_rejected(env, created["job_id"], env.confirm(created["job_id"]), 422, "invalid_upload")


def test_an_object_with_the_wrong_content_type_is_a_422(env):
    job_id = env.create_and_upload(WAV, content_type="text/html")
    _assert_rejected(env, job_id, env.confirm(job_id), 422, "invalid_upload")


def test_a_missing_content_type_is_tolerated(env):
    job_id = env.create_and_upload(WAV, content_type=None)
    assert env.confirm(job_id).status_code == 202


@pytest.mark.parametrize("encryption", [None, "", "none"])
def test_an_unencrypted_object_is_a_422(env, encryption):
    job_id = env.create_and_upload(WAV, server_side_encryption=encryption)
    _assert_rejected(env, job_id, env.confirm(job_id), 422, "invalid_upload")


def test_error_bodies_carry_no_internals(env):
    job_id = env.create_and_upload(b"garbage" * 1000, "song.mp3")
    text = env.confirm(job_id).text.casefold()
    for leaked in ("traceback", "bucket", "arn:", "amazonaws", "jobs/", "mutagen", "ffprobe"):
        assert leaked not in text


# --- confirm: transient failures -------------------------------------------------------


def test_a_transient_head_failure_is_a_503_and_retry_sends_one_message(env):
    job_id = env.create_and_upload(WAV)
    original = env.uploads.head
    calls = {"n": 0}

    def flaky(key):
        calls["n"] += 1
        if calls["n"] == 1:
            raise CloudProviderError(
                CloudProviderErrorKind.TEMPORARY_UNAVAILABLE, "private /account/123"
            )
        return original(key)

    env.uploads.head = flaky

    first = env.confirm(job_id)
    assert first.status_code == 503
    assert first.json()["error"]["code"] == "service_unavailable"
    assert "account/123" not in first.text
    assert env.job(job_id).status is CloudJobStatus.AWAITING_UPLOAD
    assert env.queue.sent == [] and env.uploads.deleted == []

    assert env.confirm(job_id).status_code == 202
    assert len(env.queue.sent) == 1


def test_a_transient_download_failure_cleans_up_and_is_retryable(env):
    job_id = env.create_and_upload(WAV)
    original = env.uploads.open
    calls = {"n": 0}

    def flaky(key):
        calls["n"] += 1
        if calls["n"] == 1:
            raise CloudProviderError(CloudProviderErrorKind.TEMPORARY_UNAVAILABLE, "down")
        return original(key)

    env.uploads.open = flaky

    assert env.confirm(job_id).status_code == 503
    assert env.staged_files() == []
    assert env.job(job_id).status is CloudJobStatus.AWAITING_UPLOAD
    assert env.confirm(job_id).status_code == 202
    assert len(env.queue.sent) == 1 and env.staged_files() == []


def test_stale_staging_from_a_previous_invocation_is_cleared(env):
    job_id = env.create_and_upload(WAV)
    leftover = env.staging_root / job_id
    leftover.mkdir(parents=True)
    (leftover / "input.wav").write_bytes(b"left over from a crashed invocation")

    assert env.confirm(job_id).status_code == 202
    assert env.staged_files() == []


# --- presigned URL scope ---------------------------------------------------------------


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_presigned_url(self, method, **kwargs):
        self.calls.append({"method": method, **kwargs})
        return "https://example.invalid/signed"


def test_the_presign_request_is_scoped_to_one_key_with_no_acl():
    client = RecordingClient()
    store = S3SourceUploadStore(client, "my-bucket")
    key = ArtifactKey(ArtifactRole.SOURCE_UPLOAD, "jobs/abc/source/input.mp3")

    store.presign_put(key, content_type="audio/mpeg", content_length=1234, expires_in=600)

    (call,) = client.calls
    assert call["method"] == "put_object"
    assert call["HttpMethod"] == "PUT"
    assert call["ExpiresIn"] == 600
    assert call["Params"] == {
        "Bucket": "my-bucket",
        "Key": "jobs/abc/source/input.mp3",
        "ContentType": "audio/mpeg",
        "ContentLength": 1234,
        "ServerSideEncryption": "AES256",
        "Tagging": "chordsync-upload=presigned",
    }
    assert not any("ACL" in name for name in call["Params"])


def test_a_real_sigv4_url_signs_length_type_and_encryption():
    boto3 = pytest.importorskip("boto3")
    from botocore.config import Config

    session = boto3.session.Session(
        aws_access_key_id="AKIAFAKEFAKEFAKEFAKE",
        aws_secret_access_key="fake-secret-do-not-leak",
        region_name="ap-southeast-1",
    )
    client = session.client("s3", config=Config(signature_version="s3v4"))
    store = S3SourceUploadStore(client, "my-bucket")
    key = ArtifactKey(ArtifactRole.SOURCE_UPLOAD, "jobs/abc/source/input.mp3")

    presigned = store.presign_put(
        key, content_type="audio/mpeg", content_length=1234, expires_in=600
    )

    from urllib.parse import parse_qs, unquote, urlparse

    parsed = urlparse(presigned.url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert "my-bucket" in (parsed.netloc + parsed.path)
    assert unquote(parsed.path).endswith("/jobs/abc/source/input.mp3")
    assert query["X-Amz-Expires"] == ["600"]
    signed = set(query["X-Amz-SignedHeaders"][0].split(";"))
    assert {"content-length", "content-type", "x-amz-server-side-encryption", "x-amz-tagging"} <= signed
    assert "x-amz-acl" not in signed
    assert "fake-secret-do-not-leak" not in presigned.url
    assert "acl" not in presigned.url.casefold()
    assert presigned.method == "PUT"


def test_the_hosted_response_never_contains_the_secret_key(tmp_path, monkeypatch):
    boto3 = pytest.importorskip("boto3")
    from botocore.config import Config

    env = Env(tmp_path, monkeypatch)
    client = boto3.session.Session(
        aws_access_key_id="AKIAFAKEFAKEFAKEFAKE",
        aws_secret_access_key="fake-secret-do-not-leak",
        region_name="ap-southeast-1",
    ).client("s3", config=Config(signature_version="s3v4"))
    env.application._uploads = S3SourceUploadStore(client, "my-bucket")

    response = env.create("song.mp3", 1000)

    assert response.status_code == 201
    assert "fake-secret-do-not-leak" not in response.text
    assert response.json()["upload_url"].startswith("https://")


def test_the_store_has_no_listing_or_prefix_operation():
    public = {name for name in dir(S3SourceUploadStore) if not name.startswith("_")}
    assert public == {"presign_put", "head", "open", "delete"}


# --- configuration ---------------------------------------------------------------------


def test_upload_ttl_defaults_to_ten_minutes_and_is_bounded():
    base = {
        "CHORDSYNC_API_HOSTING_MODE": "lambda",
        "CHORDSYNC_RUNTIME_MODE": "aws",
        "CHORDSYNC_DEMO_TOKEN_PARAMETER": auth_helpers.PARAMETER,
    }
    assert ApiHostingConfig.from_env(base).upload_url_ttl_seconds == 600
    assert (
        ApiHostingConfig.from_env({**base, "CHORDSYNC_UPLOAD_URL_TTL_SECONDS": "300"})
        .upload_url_ttl_seconds
        == 300
    )
    for bad in ("30", "7200", "abc", "-5"):
        with pytest.raises(HostingConfigurationError):
            ApiHostingConfig.from_env({**base, "CHORDSYNC_UPLOAD_URL_TTL_SECONDS": bad})


# --- local mode ------------------------------------------------------------------------


def test_local_mode_keeps_multipart_upload_and_has_no_confirm_route():
    local = api_main.create_app(ApiHostingConfig(HostingMode.LOCAL))
    paths = local.openapi()["paths"]
    assert "post" in paths["/analysis/jobs"]
    assert "/analysis/jobs/{job_id}/confirm-upload" not in paths
    body = local.openapi()["components"]["schemas"]
    assert any(name.startswith("Body_create_analysis_job") for name in body)
    assert "UploadInitiationRequest" not in body


class _AwsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__("private provider text")
        self.response = {"Error": {"Code": code, "Message": "private provider text"}}


class _HeadClient:
    def __init__(self, code: str) -> None:
        self.code = code

    def head_object(self, **_values):
        raise _AwsError(self.code)


KEY = ArtifactKey(ArtifactRole.SOURCE_UPLOAD, "jobs/abc/source/input.wav")


@pytest.mark.parametrize("code", ["404", "NoSuchKey", "NotFound"])
def test_only_a_definite_404_means_not_uploaded(code):
    assert S3SourceUploadStore(_HeadClient(code), "b").head(KEY) is None


@pytest.mark.parametrize("code", ["403", "AccessDenied", "Forbidden"])
def test_an_access_denied_head_is_a_configuration_fault_never_absence(code):
    with pytest.raises(CloudProviderError) as raised:
        S3SourceUploadStore(_HeadClient(code), "b").head(KEY)
    assert raised.value.kind is CloudProviderErrorKind.CONFIGURATION
    assert "private provider text" not in str(raised.value)


@pytest.mark.parametrize("code", ["500", "SlowDown", "InternalError"])
def test_other_head_failures_are_not_mistaken_for_absence(code):
    with pytest.raises(CloudProviderError):
        S3SourceUploadStore(_HeadClient(code), "b").head(KEY)


def test_a_permission_fault_on_confirm_is_a_503_not_upload_not_received(env):
    job_id = env.create_and_upload(WAV)

    def denied(_key):
        raise CloudProviderError(CloudProviderErrorKind.CONFIGURATION, "denied")

    env.uploads.head = denied

    response = env.confirm(job_id)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "upload_not_received" not in response.text
    job = env.job(job_id)
    assert job.status is CloudJobStatus.AWAITING_UPLOAD  # recoverable once fixed
    assert env.queue.sent == [] and env.uploads.deleted == []


def test_a_missing_object_is_still_upload_not_received(env):
    job_id = env.create("song.wav", len(WAV)).json()["job_id"]
    response = env.confirm(job_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "upload_not_received"


def test_every_presigned_upload_carries_the_lifecycle_tag(env):
    body = env.create("song.mp3", 1000).json()
    assert body["required_headers"]["x-amz-tagging"] == "chordsync-upload=presigned"


def test_the_signed_request_includes_the_tag_header():
    client = RecordingClient()
    S3SourceUploadStore(client, "b").presign_put(
        ArtifactKey(ArtifactRole.SOURCE_UPLOAD, "jobs/a/source/input.mp3"),
        content_type="audio/mpeg", content_length=5, expires_in=600,
    )
    assert client.calls[0]["Params"]["Tagging"] == "chordsync-upload=presigned"


# --- cancel ---------------------------------------------------------------------


def _move(env, job_id, status, expected):
    job = env.job(job_id)
    job.transition_to(status)
    env.repository.save(job, expected_status=expected)


def test_cancel_before_upload_stops_the_job_and_blocks_confirm(env):
    created = env.create().json()
    job_id = created["job_id"]

    response = env.client.post(f"/analysis/jobs/{job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert env.job(job_id).status is CloudJobStatus.CANCELLED
    confirm = env.confirm(job_id)
    assert confirm.status_code == 409
    assert confirm.json()["error"]["code"] == "invalid_job_state"
    assert env.queue.sent == []


def test_cancel_a_queued_job_reports_cancelled_and_has_no_result(env):
    job_id = env.create_and_upload(WAV)
    env.confirm(job_id)

    response = env.client.post(f"/analysis/jobs/{job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["result_available"] is False
    assert env.client.get(f"/analysis/jobs/{job_id}").json()["status"] == "cancelled"
    result = env.client.get(f"/analysis/jobs/{job_id}/result")
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "job_cancelled"


def test_cancel_a_processing_job(env):
    job_id = env.create_and_upload(WAV)
    env.confirm(job_id)
    _move(env, job_id, CloudJobStatus.PROCESSING, CloudJobStatus.QUEUED)

    response = env.client.post(f"/analysis/jobs/{job_id}/cancel")

    assert response.status_code == 200
    assert env.job(job_id).status is CloudJobStatus.CANCELLED


def test_cancel_while_validating(env):
    job_id = env.create().json()["job_id"]
    _move(env, job_id, CloudJobStatus.VALIDATING, CloudJobStatus.AWAITING_UPLOAD)

    assert env.client.post(f"/analysis/jobs/{job_id}/cancel").status_code == 200
    assert env.job(job_id).status is CloudJobStatus.CANCELLED


def test_cancelling_twice_is_harmless(env):
    job_id = env.create().json()["job_id"]

    first = env.client.post(f"/analysis/jobs/{job_id}/cancel")
    second = env.client.post(f"/analysis/jobs/{job_id}/cancel")

    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == "cancelled"


@pytest.mark.parametrize("final", [CloudJobStatus.COMPLETED, CloudJobStatus.FAILED])
def test_a_finished_job_cannot_be_cancelled(env, final):
    job_id = env.create_and_upload(WAV)
    env.confirm(job_id)
    _move(env, job_id, CloudJobStatus.PROCESSING, CloudJobStatus.QUEUED)
    _move(env, job_id, final, CloudJobStatus.PROCESSING)

    response = env.client.post(f"/analysis/jobs/{job_id}/cancel")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_job_state"
    assert env.job(job_id).status is final


def test_cancel_is_owner_only_and_hides_other_jobs(env):
    job_id = env.create().json()["job_id"]
    unknown = "00000000-0000-4000-8000-000000000000"

    other = env.client_b.post(f"/analysis/jobs/{job_id}/cancel")
    missing = env.client.post(f"/analysis/jobs/{unknown}/cancel")
    anonymous = env.anonymous.post(f"/analysis/jobs/{job_id}/cancel")

    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()
    assert anonymous.status_code == 401
    assert env.job(job_id).status is CloudJobStatus.AWAITING_UPLOAD


def test_local_mode_has_no_cancel_route():
    app = api_main.create_app(
        ApiHostingConfig(HostingMode.LOCAL, Path("/tmp/chordsync-api"))
    )
    client = TestClient(app, raise_server_exceptions=False)

    assert client.post("/analysis/jobs/anything/cancel").status_code in {404, 405}
