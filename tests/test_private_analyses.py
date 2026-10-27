"""A signed-in user's analyses are private; only catalogue songs are shared."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.app import auth
from backend.api.app.routers import analysis_jobs
from tests import auth_helpers
from tests.test_cognito_auth import NOW, SUB_A, SUB_B, make_token, verifier
from tests.test_hosted_upload import Env
from tests.test_shared_library_api import seed


@pytest.fixture(autouse=True)
def _reset():
    for provider in (analysis_jobs._runtime_config, analysis_jobs._cloud_application):
        provider.cache_clear()
    yield
    for provider in (analysis_jobs._runtime_config, analysis_jobs._cloud_application):
        provider.cache_clear()


@pytest.fixture
def env(tmp_path, monkeypatch) -> Env:
    environment = Env(tmp_path, monkeypatch)
    auth_helpers.install(
        monkeypatch,
        auth.RoutingVerifierProvider(
            demo=auth.StaticVerifierProvider(auth_helpers.verifier()),
            cognito=verifier(),
        ),
    )
    return environment


def _as(env: Env, sub: str) -> TestClient:
    return TestClient(
        env.client.app,
        raise_server_exceptions=False,
        headers={"Authorization": f"Bearer {make_token(sub)}"},
    )


def test_a_signed_in_user_sees_only_their_own_analysis(env):
    alice, bob = _as(env, SUB_A), _as(env, SUB_B)
    created = alice.post(
        "/analysis/jobs",
        json={"title": "Mine", "filename": "song.wav", "declared_size_bytes": 1000},
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["job_id"]
    assert env.repository.get(job_id).owner_id == f"cognito:{SUB_A}"

    assert alice.get(f"/analysis/jobs/{job_id}").status_code == 200
    missing = alice.get("/analysis/jobs/00000000-0000-4000-8000-000000000000")
    for other in (bob, env.client, env.client_b):  # another account, and demo testers
        response = other.get(f"/analysis/jobs/{job_id}")
        assert response.status_code == 404 and response.json() == missing.json()
        assert other.post(f"/analysis/jobs/{job_id}/confirm-upload").status_code == 404
        assert other.post(f"/analysis/jobs/{job_id}/cancel").status_code == 404


def test_private_analyses_never_appear_in_the_shared_library(env):
    seed(env, "catalogue-demo", title="Old demo song", owner="demo:tester-a")
    seed(env, "catalogue-none", title="Old ownerless song", owner=None)
    seed(env, "private", title="Alice only", owner=f"cognito:{SUB_A}")
    alice, bob = _as(env, SUB_A), _as(env, SUB_B)

    for client in (alice, bob, env.client):
        titles = {song["title"] for song in client.get("/analysis/library").json()["songs"]}
        assert titles == {"Old demo song", "Old ownerless song"}
        assert client.get("/analysis/library/catalogue-demo/result").status_code == 200
        assert client.get("/analysis/library/catalogue-demo/audio").status_code == 200
    # Not even Alice's own id works on the library routes, so the audio of a
    # private analysis cannot be fetched by anyone through the shared library.
    for client in (alice, bob, env.client):
        assert client.get("/analysis/library/private/result").status_code == 404
        assert client.get("/analysis/library/private/audio").status_code == 404


def test_a_bad_or_missing_token_is_still_401_and_the_same_body(env):
    expected = env.anonymous.get("/analysis/library")
    assert expected.status_code == 401
    for header in (
        f"Bearer {make_token(key='k2')}",
        f"Bearer {make_token(exp=int(NOW) - 5)}",
        f"Bearer {make_token(token_use='id')}",
    ):
        response = TestClient(env.client.app, raise_server_exceptions=False).get(
            "/analysis/library", headers={"Authorization": header}
        )
        assert response.status_code == 401 and response.json() == expected.json()
