"""Demo-token authentication and ownership (S7-T06)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import auth
from backend.api.app import main as api_main
from backend.api.app.hosting import (
    ApiHostingConfig,
    HostingConfigurationError,
    HostingMode,
)
from backend.api.app.routers import analysis_jobs
from backend.api.app.services.artifact_storage import ArtifactKey, ArtifactRole
from backend.api.app.services.cloud_job import CloudJobStatus, new_cloud_job
from tests import auth_helpers
from tests.auth_helpers import HEADERS_A, HEADERS_B, OWNER_A, OWNER_B, TOKEN_A, TOKEN_B
from tests.test_hosted_upload import WAV, Env

UNAUTHORIZED = {"error": {"code": "unauthorized", "message": "Authentication required."}}
UNAVAILABLE = {
    "error": {
        "code": "service_unavailable",
        "message": "Analysis service is temporarily unavailable.",
    }
}
JOB = "00000000-0000-4000-8000-000000000000"
PROTECTED = [
    ("POST", "/analysis/jobs"),
    ("POST", f"/analysis/jobs/{JOB}/confirm-upload"),
    ("GET", f"/analysis/jobs/{JOB}"),
    ("GET", f"/analysis/jobs/{JOB}/result"),
]
CREATE_BODY = {"title": "Song", "filename": "song.wav", "declared_size_bytes": 100}


@pytest.fixture(autouse=True)
def _reset():
    for provider in (
        analysis_jobs._runtime_config,
        analysis_jobs._cloud_application,
        analysis_jobs._auth_provider,
    ):
        provider.cache_clear()
    yield
    for provider in (
        analysis_jobs._runtime_config,
        analysis_jobs._cloud_application,
        analysis_jobs._auth_provider,
    ):
        provider.cache_clear()


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def _call(client, method, path):
    kwargs = {"json": CREATE_BODY} if method == "POST" and path == "/analysis/jobs" else {}
    return client.request(method, path, **kwargs)


# --- bearer header parsing -----------------------------------------------------------


def test_a_well_formed_bearer_header_yields_the_token():
    assert auth.bearer_token(f"Bearer {TOKEN_A}") == TOKEN_A
    assert auth.bearer_token(f"bearer {TOKEN_A}") == TOKEN_A  # the scheme is case-insensitive


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer",
        "Bearer ",
        f"Basic {TOKEN_A}",
        f"Token {TOKEN_A}",
        TOKEN_A,
        f"Bearer  {TOKEN_A}",
        f"Bearer {TOKEN_A} extra",
        f"Bearer {TOKEN_A}\n",
        "Bearer short",
        "Bearer " + "a" * 257,
        "Bearer tokén-0123456789abcdef",
        "Bearer tok en-0123456789abcdef",
    ],
)
def test_every_defective_header_is_the_same_error(header):
    with pytest.raises(auth.AuthenticationRequiredError):
        auth.bearer_token(header)


# --- the verifier ----------------------------------------------------------------------


def test_the_right_token_maps_to_its_principal_and_others_do_not():
    verifier = auth_helpers.verifier()
    assert verifier.verify(TOKEN_A) == auth.AuthenticatedPrincipal(OWNER_A)
    assert verifier.verify(TOKEN_B) == auth.AuthenticatedPrincipal(OWNER_B)
    assert verifier.verify(TOKEN_A + "x") is None
    assert verifier.verify(TOKEN_A[:-1]) is None
    assert verifier.verify("x" * 40) is None


def test_comparison_is_constant_time_and_visits_every_entry():
    import inspect

    source = inspect.getsource(auth.DemoTokenVerifier.verify)
    assert "hmac.compare_digest" in source and "break" not in source and "return" in source
    calls = []
    original = auth.hmac.compare_digest
    auth.hmac.compare_digest = lambda a, b: calls.append(1) or original(a, b)
    try:
        auth_helpers.verifier().verify(TOKEN_A)  # the first entry matches
    finally:
        auth.hmac.compare_digest = original
    assert len(calls) == 2  # still compared against the second entry


def test_the_document_holds_only_hashes_and_the_owner_id_is_not_the_token():
    document = json.dumps(
        {"version": 1, "tokens": [{"id": "tester-a", "sha256": auth.token_sha256(TOKEN_A)}]}
    )
    assert TOKEN_A not in document
    principal = auth.DemoTokenVerifier.from_document(document).verify(TOKEN_A)
    assert principal.principal_id == "demo:tester-a"
    assert TOKEN_A not in principal.principal_id and auth.token_sha256(TOKEN_A) not in principal.principal_id


GOOD = {"id": "a-1", "sha256": "a" * 64}


@pytest.mark.parametrize(
    "document",
    [
        "",
        "not json",
        "[]",
        "null",
        json.dumps({"version": 2, "tokens": [GOOD]}),
        json.dumps({"tokens": [GOOD]}),
        json.dumps({"version": 1}),
        json.dumps({"version": 1, "tokens": []}),
        json.dumps({"version": 1, "tokens": "x"}),
        json.dumps({"version": 1, "tokens": [GOOD, GOOD]}),
        json.dumps({"version": 1, "tokens": [{"id": "Bad Id", "sha256": "a" * 64}]}),
        json.dumps({"version": 1, "tokens": [{"id": "a", "sha256": "A" * 64}]}),
        json.dumps({"version": 1, "tokens": [{"id": "a", "sha256": "a" * 63}]}),
        json.dumps({"version": 1, "tokens": [{"id": "a"}]}),
        json.dumps({"version": 1, "tokens": ["a"]}),
        json.dumps({"version": 1, "tokens": [{"id": f"t{i}", "sha256": "a" * 64} for i in range(51)]}),
        " " * 9000,
    ],
)
def test_a_malformed_verifier_document_is_an_infrastructure_fault(document):
    with pytest.raises(auth.AuthUnavailableError) as raised:
        auth.DemoTokenVerifier.from_document(document)
    assert "a" * 20 not in str(raised.value)  # the document is never echoed


# --- caching and failure behaviour ----------------------------------------------------------


def _document(*pairs):
    return json.dumps(
        {"version": 1, "tokens": [{"id": label, "sha256": auth.token_sha256(t)} for label, t in pairs]}
    )


class Loader:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        outcome = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_verifier_is_loaded_once_per_cache_period_not_per_request():
    clock, loader = Clock(), Loader(_document(("a", TOKEN_A)))
    provider = auth.CachedVerifierProvider(loader, cache_seconds=300, clock=clock)
    for _ in range(50):
        provider.get()
    assert loader.calls == 1
    clock.now += 301
    provider.get()
    assert loader.calls == 2


def test_a_rotated_token_takes_effect_after_the_cache_period():
    clock = Clock()
    loader = Loader(_document(("a", TOKEN_A)), _document(("a", TOKEN_B)))
    provider = auth.CachedVerifierProvider(loader, cache_seconds=300, clock=clock)
    assert provider.get().verify(TOKEN_A) is not None
    clock.now += 301
    assert provider.get().verify(TOKEN_A) is None
    assert provider.get().verify(TOKEN_B) is not None


def test_an_initial_load_failure_is_unavailable_and_not_retried_every_request():
    clock, loader = Clock(), Loader(RuntimeError("ssm down"))
    provider = auth.CachedVerifierProvider(loader, failure_backoff_seconds=5, clock=clock)
    for _ in range(20):
        with pytest.raises(auth.AuthUnavailableError):
            provider.get()
    assert loader.calls == 1
    clock.now += 6
    with pytest.raises(auth.AuthUnavailableError):
        provider.get()
    assert loader.calls == 2


def test_recovery_after_an_initial_failure():
    clock = Clock()
    loader = Loader(RuntimeError("down"), _document(("a", TOKEN_A)))
    provider = auth.CachedVerifierProvider(loader, failure_backoff_seconds=5, clock=clock)
    with pytest.raises(auth.AuthUnavailableError):
        provider.get()
    clock.now += 6
    assert provider.get().verify(TOKEN_A) is not None


def test_a_failed_refresh_keeps_the_last_good_verifier():
    clock = Clock()
    loader = Loader(_document(("a", TOKEN_A)), RuntimeError("blip"))
    provider = auth.CachedVerifierProvider(loader, cache_seconds=300, clock=clock)
    provider.get()
    clock.now += 301
    assert provider.get().verify(TOKEN_A) is not None  # still serving


def test_a_malformed_stored_value_is_unavailable():
    provider = auth.CachedVerifierProvider(Loader("{not json"), clock=Clock())
    with pytest.raises(auth.AuthUnavailableError):
        provider.get()


def test_concurrent_requests_cause_one_load():
    loader = Loader(_document(("a", TOKEN_A)))
    original = loader.__call__

    def slow():
        import time

        time.sleep(0.05)
        return original()

    provider = auth.CachedVerifierProvider(slow)
    barrier = threading.Barrier(8)

    def run():
        barrier.wait()
        provider.get()

    threads = [threading.Thread(target=run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert loader.calls == 1


def test_the_ssm_request_matches_the_service_model_and_asks_for_decryption():
    boto3 = pytest.importorskip("boto3")
    from botocore.stub import Stubber

    client = boto3.session.Session(
        aws_access_key_id="x", aws_secret_access_key="x", region_name="ap-southeast-1"
    ).client("ssm")
    stubber = Stubber(client)
    stubber.add_response(
        "get_parameter",
        {"Parameter": {"Value": _document(("a", TOKEN_A))}},
        {"Name": auth_helpers.PARAMETER, "WithDecryption": True},
    )
    with stubber:
        value = auth.SsmDocumentLoader(client, auth_helpers.PARAMETER)()
        stubber.assert_no_pending_responses()
    assert auth.DemoTokenVerifier.from_document(value).verify(TOKEN_A) is not None


# --- hosting configuration ----------------------------------------------------------------


def test_hosted_mode_refuses_to_start_without_the_verifier_parameter():
    base = {"CHORDSYNC_API_HOSTING_MODE": "lambda", "CHORDSYNC_RUNTIME_MODE": "aws"}
    with pytest.raises(HostingConfigurationError, match="DEMO_TOKEN_PARAMETER"):
        ApiHostingConfig.from_env(base)
    with pytest.raises(HostingConfigurationError):
        ApiHostingConfig.from_env({**base, "CHORDSYNC_DEMO_TOKEN_PARAMETER": "  "})
    for bad in ("has space", "../x", "a//b", "x" * 1012):
        with pytest.raises(HostingConfigurationError):
            ApiHostingConfig.from_env({**base, "CHORDSYNC_DEMO_TOKEN_PARAMETER": bad})
    config = ApiHostingConfig.from_env({**base, "CHORDSYNC_DEMO_TOKEN_PARAMETER": auth_helpers.PARAMETER})
    assert config.auth_enabled and config.demo_token_parameter == auth_helpers.PARAMETER


def test_hosted_mode_ignores_an_inline_verifier():
    config = ApiHostingConfig.from_env(
        {
            "CHORDSYNC_API_HOSTING_MODE": "lambda",
            "CHORDSYNC_RUNTIME_MODE": "aws",
            "CHORDSYNC_DEMO_TOKEN_PARAMETER": auth_helpers.PARAMETER,
            "CHORDSYNC_DEMO_TOKEN_VERIFIER": _document(("a", TOKEN_A)),
        }
    )
    assert config.demo_token_verifier_document is None


def test_local_mode_has_auth_off_unless_configured():
    assert not ApiHostingConfig.from_env({}).auth_enabled
    assert ApiHostingConfig.from_env({"CHORDSYNC_DEMO_TOKEN_VERIFIER": "{}"}).auth_enabled
    assert ApiHostingConfig.from_env({"CHORDSYNC_DEMO_TOKEN_PARAMETER": "/x/y"}).auth_enabled


# --- the hosted API: authentication -------------------------------------------------------


@pytest.mark.parametrize("method,path", PROTECTED)
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": f"Basic {TOKEN_A}"},
        {"Authorization": TOKEN_A},
        {"Authorization": "Bearer " + "z" * 43},  # well formed, not a known token
        {"Authorization": f"Bearer {TOKEN_A}x"},
    ],
    ids=["missing", "empty", "no-token", "blank-token", "wrong-scheme", "no-scheme", "unknown", "near-miss"],
)
def test_every_protected_route_gives_the_same_401(env, method, path, headers):
    response = _call(env.anonymous, method, path) if not headers else env.anonymous.request(
        method, path, headers=headers, json=CREATE_BODY if path == "/analysis/jobs" else None
    )

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"
    assert env.queue.sent == [] and env.repository._jobs == {}


def test_unauthenticated_requests_learn_nothing_from_a_bad_body_or_job_id(env):
    assert env.anonymous.post("/analysis/jobs", json={"garbage": True}).status_code == 401
    assert env.anonymous.post("/analysis/jobs", content=b"not json").status_code == 401
    assert env.anonymous.get("/analysis/jobs/not-a-job").status_code == 401


def test_a_valid_token_succeeds_end_to_end_and_binds_the_owner(env):
    created = env.client.post(
        "/analysis/jobs",
        json={"title": "Song", "filename": "song.wav", "declared_size_bytes": len(WAV)},
    )
    assert created.status_code == 201
    body = created.json()
    assert env.job(body["job_id"]).owner_id == OWNER_A
    env.uploads.client_upload(body["source_object_key"], WAV, content_type="audio/wav")
    assert env.confirm(body["job_id"]).status_code == 202
    assert env.client.get(f"/analysis/jobs/{body['job_id']}").json()["status"] == "queued"
    assert len(env.queue.sent) == 1


def test_the_token_never_appears_in_responses_records_keys_or_urls(env):
    created = env.client.post("/analysis/jobs", json=CREATE_BODY)
    body = created.json()
    job = env.job(body["job_id"])
    haystack = json.dumps(
        [created.text, dict(created.headers), body["upload_url"], body["required_headers"],
         body["source_object_key"], job.to_dict(), env.uploads.presign_requests]
    )
    for secret in (TOKEN_A, TOKEN_B, auth.token_sha256(TOKEN_A)):
        assert secret not in haystack
    assert "authorization" not in json.dumps(body["required_headers"]).casefold()


def test_the_token_is_never_logged(env, caplog):
    caplog.set_level(logging.DEBUG)
    env.client.post("/analysis/jobs", json=CREATE_BODY)
    env.anonymous.get(f"/analysis/jobs/{JOB}", headers={"Authorization": f"Bearer {'q' * 43}"})
    env.anonymous.get(f"/analysis/jobs/{JOB}", headers={"Authorization": f"Bearer {TOKEN_B}x"})
    env.client_b.get(f"/analysis/jobs/{JOB}")
    for secret in (TOKEN_A, TOKEN_B, "q" * 43, auth.token_sha256(TOKEN_A)):
        assert secret not in caplog.text


def test_health_and_root_stay_public_and_inform_nothing_private(env):
    assert env.anonymous.get("/health").json() == {"status": "healthy"}
    root = env.anonymous.get("/")
    assert root.status_code == 200
    assert root.json() == {"name": "ChordSync API", "status": "running"}


def test_the_legacy_upload_route_does_not_exist_hosted(env):
    response = env.client.post("/api/v1/audio/upload", files={"file": ("a.wav", b"x", "audio/wav")})
    assert response.status_code == 404


# --- authentication backend failures are 503, never 401 ------------------------------------


class BrokenProvider:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def get(self):
        raise self.error


@pytest.mark.parametrize("method,path", PROTECTED)
def test_an_unavailable_verifier_is_a_503_even_for_valid_looking_requests(env, monkeypatch, method, path):
    auth_helpers.install(monkeypatch, BrokenProvider(auth.AuthUnavailableError("down")))
    response = _call(env.client, method, path)
    assert response.status_code == 503
    assert response.json() == UNAVAILABLE
    assert env.queue.sent == []


def test_a_malformed_stored_verifier_is_a_503(env, monkeypatch):
    auth_helpers.install(
        monkeypatch, auth.CachedVerifierProvider(Loader("{broken"), clock=Clock())
    )
    response = env.client.get(f"/analysis/jobs/{JOB}")
    assert response.status_code == 503 and response.json() == UNAVAILABLE


def test_a_ssm_failure_is_a_503_and_recovers(env, monkeypatch):
    clock = Clock()
    loader = Loader(RuntimeError("ThrottlingException"), _document(("tester-a", TOKEN_A)))
    auth_helpers.install(
        monkeypatch, auth.CachedVerifierProvider(loader, failure_backoff_seconds=5, clock=clock)
    )
    assert env.client.get(f"/analysis/jobs/{JOB}").status_code == 503
    clock.now += 6
    assert env.client.get(f"/analysis/jobs/{JOB}").status_code == 404  # authenticated now


def test_a_hosted_app_without_auth_configuration_never_runs_open(tmp_path, monkeypatch):
    unconfigured = ApiHostingConfig(HostingMode.LAMBDA, Path("/tmp/chordsync-api"))
    client = TestClient(api_main.create_app(unconfigured), raise_server_exceptions=False)
    response = client.get(f"/analysis/jobs/{JOB}", headers=HEADERS_A)
    assert response.status_code == 503 and response.json() == UNAVAILABLE


# --- ownership ---------------------------------------------------------------------------------


def _make_job(env, *, upload=True):
    created = env.client.post(
        "/analysis/jobs",
        json={"title": "Song", "filename": "song.wav", "declared_size_bytes": len(WAV)},
    ).json()
    if upload:
        env.uploads.client_upload(created["source_object_key"], WAV, content_type="audio/wav")
    return created["job_id"]


def test_another_principal_cannot_confirm_read_or_fetch_the_job(env):
    job_id = _make_job(env)
    not_found = env.client_b.get(f"/analysis/jobs/{JOB}")  # a job that never existed

    confirm = env.client_b.post(f"/analysis/jobs/{job_id}/confirm-upload")
    status = env.client_b.get(f"/analysis/jobs/{job_id}")
    result = env.client_b.get(f"/analysis/jobs/{job_id}/result")

    for response in (confirm, status, result):
        assert response.status_code == 404  # never 403
        assert response.json() == not_found.json()  # indistinguishable from "no such job"
    assert env.queue.sent == []
    assert env.job(job_id).status is CloudJobStatus.AWAITING_UPLOAD  # B changed nothing
    assert env.uploads.deleted == []


def test_the_owner_still_succeeds_after_a_cross_owner_attempt(env):
    job_id = _make_job(env)
    assert env.client_b.post(f"/analysis/jobs/{job_id}/confirm-upload").status_code == 404
    assert env.client.get(f"/analysis/jobs/{job_id}").status_code == 200
    assert env.confirm(job_id).status_code == 202
    assert len(env.queue.sent) == 1


def test_a_cross_owner_confirm_after_dispatch_still_sends_nothing_and_looks_missing(env):
    job_id = _make_job(env)
    assert env.confirm(job_id).status_code == 202
    again = env.client_b.post(f"/analysis/jobs/{job_id}/confirm-upload")
    assert again.status_code == 404  # not the idempotent 200 an owner would get
    assert len(env.queue.sent) == 1


def test_duplicate_confirm_by_the_owner_is_still_idempotent(env):
    job_id = _make_job(env)
    codes = [env.confirm(job_id).status_code for _ in range(3)]
    assert codes == [202, 200, 200]
    assert len(env.queue.sent) == 1


def test_interleaved_owners_send_exactly_one_message(env):
    job_id = _make_job(env)
    results = []
    barrier = threading.Barrier(6)

    def run(client):
        barrier.wait()
        results.append(client.post(f"/analysis/jobs/{job_id}/confirm-upload").status_code)

    threads = [threading.Thread(target=run, args=(c,)) for c in (env.client, env.client_b) * 3]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(env.queue.sent) == 1
    assert results.count(404) == 3  # all of B's, none of A's


def test_a_completed_result_is_not_readable_by_another_principal(env):
    job_id = _make_job(env)
    env.confirm(job_id)
    job = env.job(job_id)
    key = f"jobs/{job_id}/results/timeline.json"
    timeline = {
        "schema_version": 1, "bpm": 90, "beats_per_bar": 4, "beat_source": "x",
        "lyric_source": "x", "bars": [], "lyrics": [],
    }
    env.artifacts.put_bytes(
        ArtifactKey(ArtifactRole.TIMELINE_RESULT, key),
        json.dumps(timeline).encode(),
        content_type="application/json",
    )
    job.transition_to(CloudJobStatus.PROCESSING)
    env.repository.save(job, expected_status=CloudJobStatus.QUEUED)
    job = env.job(job_id)
    job.timeline_object_key = key
    job.playback_object_key = f"jobs/{job_id}/playback/audio.wav"
    job.transition_to(CloudJobStatus.COMPLETED)
    env.repository.save(job, expected_status=CloudJobStatus.PROCESSING)

    assert env.client.get(f"/analysis/jobs/{job_id}/result").status_code == 200
    other = env.client_b.get(f"/analysis/jobs/{job_id}/result")
    assert other.status_code == 404 and "schema_version" not in other.text


def test_a_job_without_an_owner_is_invisible_in_hosted_mode(env):
    legacy = new_cloud_job(JOB, "Legacy")
    legacy.transition_to(CloudJobStatus.AWAITING_UPLOAD)
    legacy.created_at = legacy.updated_at = datetime.now(timezone.utc)
    env.repository.add(legacy)
    for client in (env.client, env.client_b):
        assert client.get(f"/analysis/jobs/{JOB}").status_code == 404
        assert client.post(f"/analysis/jobs/{JOB}/confirm-upload").status_code == 404


def test_the_application_refuses_to_create_a_hosted_job_without_an_owner(env):
    from backend.api.app.models.analysis_job import UploadInitiationRequest

    with pytest.raises(auth.AuthenticationRequiredError):
        env.application.initiate_upload(UploadInitiationRequest(**CREATE_BODY), None)


def test_owner_ids_are_stable_non_secret_and_distinct_per_principal(env):
    first = env.job(env.client.post("/analysis/jobs", json=CREATE_BODY).json()["job_id"])
    second = env.job(env.client.post("/analysis/jobs", json=CREATE_BODY).json()["job_id"])
    other = env.job(env.client_b.post("/analysis/jobs", json=CREATE_BODY).json()["job_id"])
    assert first.owner_id == second.owner_id == OWNER_A
    assert other.owner_id == OWNER_B != OWNER_A
    assert first.owner_id.startswith("demo:")


# --- local mode ------------------------------------------------------------------------------


def test_local_mode_without_auth_configuration_is_unchanged():
    client = TestClient(api_main.create_app(ApiHostingConfig(HostingMode.LOCAL)))
    assert client.get(f"/analysis/jobs/{JOB}").status_code == 404  # no 401


def test_local_mode_can_opt_in_to_the_same_authentication():
    document = _document(("tester-a", TOKEN_A))
    app = api_main.create_app(
        ApiHostingConfig(HostingMode.LOCAL, demo_token_verifier_document=document)
    )
    client = TestClient(app)
    assert client.get(f"/analysis/jobs/{JOB}").status_code == 401
    assert client.get(f"/analysis/jobs/{JOB}", headers=HEADERS_A).status_code == 404
    assert client.get(f"/analysis/jobs/{JOB}", headers=HEADERS_B).status_code == 401
    assert client.get("/health").status_code == 200


# --- separation -----------------------------------------------------------------------------------


def test_the_dispatcher_has_no_user_authentication():
    source = "".join(
        p.read_text().casefold()
        for p in (Path(__file__).resolve().parents[1] / "backend/dispatcher").glob("*.py")
    )
    for word in ("bearer", "authorization", "demo_token", "principal", "backend.api"):
        assert word not in source


def test_routes_depend_on_the_principal_abstraction_not_the_demo_verifier():
    import inspect

    text = inspect.getsource(analysis_jobs)
    assert "DemoTokenVerifier" in text  # only inside the provider factory
    for handler in (
        analysis_jobs.create_upload,
        analysis_jobs.confirm_upload,
        analysis_jobs.get_analysis_job,
        analysis_jobs.get_analysis_job_result,
    ):
        source = inspect.getsource(handler)
        assert "principal" in source and "DemoTokenVerifier" not in source and "sha256" not in source


# --- token generator -------------------------------------------------------------------------


def test_the_generator_makes_strong_tokens_and_a_hash_only_document(capsys):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        import generate_demo_token
    finally:
        sys.path.pop(0)

    tokens, document = generate_demo_token.generate(["tester-1", "tester-2"])

    assert len(set(tokens.values())) == 2
    verifier = auth.DemoTokenVerifier.from_document(document)
    for label, token in tokens.items():
        assert len(token) >= 43 and token not in document
        assert auth.bearer_token(f"Bearer {token}") == token
        assert verifier.verify(token) == auth.AuthenticatedPrincipal(f"demo:{label}")
    generate_demo_token.main(["--id", "tester-1"])
    printed = capsys.readouterr()
    assert printed.out.count("sha256") == 1 and "token" not in printed.out.casefold().replace("tokens", "")


def test_a_hosted_app_serves_no_docs_or_schema_pages(env):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert env.anonymous.get(path).status_code == 404
        assert env.client.get(path).status_code == 404
    assert "/analysis/jobs" in api_main.create_app(auth_helpers_hosted()).openapi()["paths"]


def auth_helpers_hosted():
    return ApiHostingConfig(
        HostingMode.LAMBDA, Path("/tmp/chordsync-api"), demo_token_parameter=auth_helpers.PARAMETER
    )
