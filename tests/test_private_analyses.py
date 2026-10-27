"""A signed-in user's analyses are private; only catalogue songs are shared."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.app import auth
from backend.api.app.routers import analysis_jobs
from tests import auth_helpers
from tests.test_cognito_auth import NOW, SUB_A, SUB_B, make_token, verifier
from tests.test_hosted_upload import Env
from backend.api.app.services.cloud_job import CloudJobStatus
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


# --- "your songs": the caller's own analyses ---


def test_your_songs_lists_only_your_own_finished_analyses_newest_first(env):
    seed(env, "a-old", title="Alice old", owner=f"cognito:{SUB_A}", age_minutes=30)
    seed(env, "a-new", title="Alice new", owner=f"cognito:{SUB_A}", age_minutes=1)
    seed(env, "a-running", owner=f"cognito:{SUB_A}", status=CloudJobStatus.PROCESSING)
    seed(env, "b-song", title="Bob", owner=f"cognito:{SUB_B}")
    seed(env, "old-catalogue", title="Catalogue", owner="demo:tester-a")
    alice, bob = _as(env, SUB_A), _as(env, SUB_B)

    assert [s["title"] for s in alice.get("/analysis/mine").json()["songs"]] == [
        "Alice new",
        "Alice old",
    ]
    assert [s["title"] for s in bob.get("/analysis/mine").json()["songs"]] == ["Bob"]


def test_a_new_account_starts_with_an_empty_list_and_old_songs_are_nobodys(env):
    seed(env, "old-catalogue", title="Catalogue", owner="demo:tester-a")
    seed(env, "ownerless", title="Ownerless", owner=None)

    assert _as(env, SUB_A).get("/analysis/mine").json() == {"songs": []}
    # Even the demo-token holder who made the old songs does not get them as "your songs".
    assert env.client.get("/analysis/mine").json() == {"songs": []}
    assert env.client.get("/analysis/mine/old-catalogue/audio").status_code == 404


def test_you_can_play_your_own_audio_but_nobody_elses(env):
    seed(env, "alice-song", owner=f"cognito:{SUB_A}")
    alice, bob = _as(env, SUB_A), _as(env, SUB_B)

    assert alice.get("/analysis/mine/alice-song/audio").status_code == 200
    unknown = alice.get("/analysis/mine/nope/audio")
    for other in (bob, env.client):
        response = other.get("/analysis/mine/alice-song/audio")
        assert response.status_code == 404 and response.json() == unknown.json()


def test_your_songs_needs_a_sign_in(env):
    assert env.anonymous.get("/analysis/mine").status_code == 401
    assert env.anonymous.get("/analysis/mine/x/audio").status_code == 401


def test_a_flood_of_private_jobs_cannot_push_catalogue_songs_out_of_the_library(env):
    seed(env, "catalogue", title="Old song", owner="demo:tester-a", age_minutes=500)
    for number in range(12):
        seed(env, f"private-{number}", owner=f"cognito:{SUB_B}", age_minutes=number)

    titles = [s["title"] for s in env.client.get("/analysis/library").json()["songs"]]
    assert titles == ["Old song"]
    assert len(env.repository.list_completed(limit=5, catalogue_only=True)) == 1
    assert len(env.repository.list_completed(limit=5, owner_id=f"cognito:{SUB_B}")) == 5


def test_the_repository_refuses_an_owner_and_the_catalogue_together(env):
    with pytest.raises(ValueError):
        env.repository.list_completed(owner_id="cognito:x", catalogue_only=True)
    with pytest.raises(ValueError):
        env.repository.list_completed(owner_id="")


class _CapturingTable:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def scan(self, **request):
        self.requests.append(request)
        return {"Items": []}


@pytest.mark.parametrize(
    ("scope", "must_contain", "values"),
    [
        ({"owner_id": "cognito:abc"}, "#owner = :owner", {":owner": "cognito:abc"}),
        (
            {"catalogue_only": True},
            "begins_with(#owner, :demo)",
            {":null": "NULL", ":demo": "demo:"},
        ),
        ({}, None, {}),
    ],
)
def test_dynamodb_filters_by_owner_before_reading_the_results(scope, must_contain, values):
    from backend.api.app.services.dynamodb_cloud_job_repository import DynamoDbCloudJobRepository

    table = _CapturingTable()
    DynamoDbCloudJobRepository(table).list_completed(**scope)

    request = table.requests[0]
    assert request["FilterExpression"].startswith("#status = :completed")
    if must_contain:
        assert must_contain in request["FilterExpression"]
    else:
        assert "#owner" not in request["FilterExpression"]
    for name, value in values.items():
        assert request["ExpressionAttributeValues"][name] == value
    # Every placeholder used is defined, and every defined one is used.
    expression = request["FilterExpression"]
    assert all(name in expression for name in request["ExpressionAttributeNames"])
    assert all(name in expression for name in request["ExpressionAttributeValues"])


# --- genres, and duplicates that are hidden rather than deleted ---


def _tag(env, job_id, **fields):
    job = env.repository.get(job_id)
    for name, value in fields.items():
        setattr(job, name, value)
    env.repository.save(job, expected_status=job.status)


def test_the_library_shows_each_songs_artist_and_genres(env):
    seed(env, "tagged", title="Wonderwall - Oasis", owner="demo:tester-a")
    seed(env, "untagged", title="Duvet", owner="demo:tester-a", age_minutes=5)
    _tag(env, "tagged", artist="Oasis", genres=["Rock", "Indie"], genre_source="review")

    songs = {s["title"]: s for s in env.client.get("/analysis/library").json()["songs"]}

    assert songs["Wonderwall - Oasis"]["artist"] == "Oasis"
    assert songs["Wonderwall - Oasis"]["genres"] == ["Rock", "Indie"]
    assert songs["Duvet"]["artist"] is None and songs["Duvet"]["genres"] == []


def test_a_hidden_duplicate_leaves_every_list_but_nothing_is_deleted(env):
    seed(env, "keep", title="Dangalanna Be", owner="demo:tester-a")
    seed(env, "dupe", title="Dangalanna Be", owner="demo:tester-a", age_minutes=30)
    seed(env, "mine-keep", title="Mine", owner=f"cognito:{SUB_A}")
    seed(env, "mine-dupe", title="Mine", owner=f"cognito:{SUB_A}", age_minutes=30)
    _tag(env, "dupe", superseded_by="keep")
    _tag(env, "mine-dupe", superseded_by="mine-keep")

    library = [s["job_id"] for s in env.client.get("/analysis/library").json()["songs"]]
    mine = [s["job_id"] for s in _as(env, SUB_A).get("/analysis/mine").json()["songs"]]

    assert library == ["keep"] and mine == ["mine-keep"]
    assert env.client.get("/analysis/library/dupe/result").status_code == 404
    assert env.client.get("/analysis/library/dupe/audio").status_code == 404
    assert env.client.get("/analysis/library/keep/result").status_code == 200
    # Still stored, with its audio and timeline: only hidden.
    assert env.repository.get("dupe").superseded_by == "keep"
    assert env.repository.get("dupe").timeline_object_key is not None


def test_unmarking_a_duplicate_brings_it_back(env):
    seed(env, "keep", title="Song", owner="demo:tester-a")
    seed(env, "dupe", title="Song", owner="demo:tester-a", age_minutes=30)
    _tag(env, "dupe", superseded_by="keep")
    assert len(env.client.get("/analysis/library").json()["songs"]) == 1

    _tag(env, "dupe", superseded_by=None)

    assert len(env.client.get("/analysis/library").json()["songs"]) == 2


def test_stored_genres_outside_the_list_are_ignored_not_trusted():
    from backend.api.app.services.cloud_job import CloudJobRecord, new_cloud_job

    record = new_cloud_job("j1", "Song")
    payload = record.to_dict()
    for bad in ("Rock", None, 5, ["Polka", "Rock", 7, None, "Sinhala"], {"a": 1}):
        loaded = CloudJobRecord.from_dict({**payload, "genres": bad})
        assert loaded.genres in ([], ["Rock"], ["Sinhala"], ["Rock", "Sinhala"])
    assert CloudJobRecord.from_dict({**payload, "genres": ["Polka", "Rock", 7, "Sinhala"]}).genres == ["Rock", "Sinhala"]
    old = {k: v for k, v in payload.items() if k not in {"artist", "genres", "genre_source", "superseded_by"}}
    loaded = CloudJobRecord.from_dict(old)  # a song saved before these fields existed
    assert loaded.genres == [] and loaded.artist is None and loaded.superseded_by is None


def test_dynamodb_leaves_hidden_duplicates_out_of_every_list():
    from backend.api.app.services.dynamodb_cloud_job_repository import DynamoDbCloudJobRepository

    for scope in ({}, {"owner_id": "cognito:abc"}, {"catalogue_only": True}):
        table = _CapturingTable()
        DynamoDbCloudJobRepository(table).list_completed(**scope)
        request = table.requests[0]
        assert "attribute_not_exists(superseded_by)" in request["FilterExpression"]
        assert request["ExpressionAttributeValues"][":null"] == "NULL"
