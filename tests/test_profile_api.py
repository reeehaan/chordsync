"""The signed-in user's own profile: private, validated, and kept by account."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.api.app.models.profile import GENRES, current_year
from backend.api.app.routers import analysis_jobs, profile
from backend.api.app.services.aws_errors import CloudProviderError, CloudProviderErrorKind
from backend.api.app.services.profile_store import (
    DynamoDbProfileStore,
    InMemoryProfileStore,
    StoredProfile,
)
from tests.test_cognito_auth import SUB_A, SUB_B
from tests.test_private_analyses import _as, _reset, env  # noqa: F401  (fixtures)

GOOD = {
    "name": "Kim Lee",
    "birth_year": 2000,
    "genres": ["Pop", "Jazz"],
    "experience": "intermediate",
}


@pytest.fixture
def store(env):  # noqa: F811
    memory = InMemoryProfileStore()
    env.client.app.dependency_overrides[profile.get_profile_store] = lambda: memory
    yield memory
    env.client.app.dependency_overrides.pop(profile.get_profile_store, None)


def test_a_person_saves_and_reads_back_their_own_profile(env, store):  # noqa: F811
    alice = _as(env, SUB_A)

    assert alice.get("/me/profile").status_code == 404
    saved = alice.put("/me/profile", json=GOOD)

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert {k: body[k] for k in GOOD} == GOOD
    assert datetime.fromisoformat(body["updated_at"]).tzinfo is not None
    assert alice.get("/me/profile").json() == body
    assert store.get(f"cognito:{SUB_A}").name == "Kim Lee"


def test_nobody_can_read_or_change_someone_elses_profile(env, store):  # noqa: F811
    alice, bob = _as(env, SUB_A), _as(env, SUB_B)
    alice.put("/me/profile", json=GOOD)

    assert bob.get("/me/profile").status_code == 404  # his own, which is empty
    bob.put("/me/profile", json={**GOOD, "name": "Bob"})
    assert alice.get("/me/profile").json()["name"] == "Kim Lee"
    assert bob.get("/me/profile").json()["name"] == "Bob"


def test_the_owner_comes_from_the_token_never_from_the_request(env, store):  # noqa: F811
    alice = _as(env, SUB_A)

    for extra in ({"owner_id": f"cognito:{SUB_B}"}, {"sub": SUB_B}, {"user": "x"}):
        assert alice.put("/me/profile", json={**GOOD, **extra}).status_code == 400
    assert store.get(f"cognito:{SUB_B}") is None


def test_saving_again_replaces_the_profile(env, store):  # noqa: F811
    alice = _as(env, SUB_A)
    first = alice.put("/me/profile", json=GOOD).json()

    second = alice.put(
        "/me/profile", json={**GOOD, "genres": ["Folk"], "experience": "advanced"}
    ).json()

    assert second["genres"] == ["Folk"] and second["experience"] == "advanced"
    assert second["updated_at"] >= first["updated_at"]


def test_demo_tokens_and_anonymous_callers_have_no_profile(env, store):  # noqa: F811
    assert env.client.get("/me/profile").status_code == 403
    assert env.client.put("/me/profile", json=GOOD).status_code == 403
    assert env.anonymous.get("/me/profile").status_code == 401
    assert env.anonymous.put("/me/profile", json=GOOD).status_code == 401


def test_the_name_is_tidied(env, store):  # noqa: F811
    saved = _as(env, SUB_A).put("/me/profile", json={**GOOD, "name": "  Kim   Lee \n"})

    assert saved.json()["name"] == "Kim Lee"


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 61},
        {"name": "Kim\x00Lee"},
        {"name": "Kim\u202ELee"},  # a right-to-left override
        {"name": "Kim​Lee"},  # a zero-width space
        {"name": 5},
        {"birth_year": current_year() - 12},  # too young
        {"birth_year": 1899},
        {"birth_year": "2000"},
        {"birth_year": 2000.5},
        {"birth_year": None},
        {"genres": ["Polka"]},
        {"genres": ["Pop", "Pop"]},
        {"genres": list(GENRES) + ["Pop"]},
        {"genres": "Pop"},
        {"genres": [["Pop"]]},
        {"experience": "expert"},
        {"experience": ""},
    ],
)
def test_a_bad_profile_is_refused_and_nothing_is_saved(env, store, change):  # noqa: F811
    response = _as(env, SUB_A).put("/me/profile", json={**GOOD, **change})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert store.get(f"cognito:{SUB_A}") is None


@pytest.mark.parametrize("missing", list(GOOD))
def test_every_field_is_required(env, store, missing):  # noqa: F811
    body = {k: v for k, v in GOOD.items() if k != missing}

    assert _as(env, SUB_A).put("/me/profile", json=body).status_code == 400


def test_the_youngest_allowed_birth_year_is_accepted_and_no_genre_is_fine(env, store):  # noqa: F811
    response = _as(env, SUB_A).put(
        "/me/profile", json={**GOOD, "birth_year": current_year() - 13, "genres": []}
    )

    assert response.status_code == 200


def test_every_listed_genre_is_accepted(env, store):  # noqa: F811
    assert _as(env, SUB_A).put("/me/profile", json={**GOOD, "genres": list(GENRES)}).status_code == 200


def test_the_server_genre_list_matches_what_the_app_offers():
    from pathlib import Path
    import re

    source = (Path(__file__).resolve().parents[1] / "mobile/lib/features/auth/data/user_profile.dart").read_text()
    block = re.search(r"const musicGenres = \[(.*?)\];", source, re.S).group(1)

    assert tuple(re.findall(r"'([^']+)'", block)) == GENRES


# --- the DynamoDB store ---


class _Table:
    def __init__(self, item=None, error=None):
        self.item, self.error = item, error
        self.updates, self.gets = [], []

    def get_item(self, **request):
        self.gets.append(request)
        if self.error:
            raise self.error
        return {"Item": self.item} if self.item else {}

    def update_item(self, **request):
        self.updates.append(request)
        if self.error:
            raise self.error


def _stored() -> StoredProfile:
    return StoredProfile("Kim Lee", 2000, ["Pop"], "beginner", datetime(2026, 10, 27, tzinfo=timezone.utc))


def test_dynamodb_writes_one_item_per_owner_and_keeps_the_first_created_time():
    table = _Table()

    DynamoDbProfileStore(table).put("cognito:abc", _stored())

    request = table.updates[0]
    assert request["Key"] == {"owner_id": "cognito:abc"}
    assert request["ExpressionAttributeNames"] == {"#name": "name"}  # "name" is reserved
    assert "created_at = if_not_exists(created_at, :updated)" in request["UpdateExpression"]
    assert request["ExpressionAttributeValues"][":name"] == "Kim Lee"
    assert request["ExpressionAttributeValues"][":year"] == 2000
    assert request["ExpressionAttributeValues"][":updated"].startswith("2026-10-27T00:00:00")
    assert all(name in request["UpdateExpression"] for name in request["ExpressionAttributeValues"])


def test_dynamodb_reads_a_profile_with_a_consistent_read():
    item = {"owner_id": "cognito:abc", "name": "Kim Lee", "birth_year": 2000,
            "genres": ["Pop"], "experience": "beginner", "updated_at": "2026-10-27T00:00:00+00:00"}
    table = _Table(item)

    result = DynamoDbProfileStore(table).get("cognito:abc")

    assert result == _stored()
    assert table.gets[0] == {"Key": {"owner_id": "cognito:abc"}, "ConsistentRead": True}
    assert DynamoDbProfileStore(_Table()).get("cognito:none") is None


def test_a_damaged_item_reads_as_no_profile_instead_of_an_error():
    assert DynamoDbProfileStore(_Table({"owner_id": "x", "name": "Kim"})).get("x") is None


def test_a_provider_failure_becomes_a_service_error():
    class Throttled(Exception):
        response = {"Error": {"Code": "ProvisionedThroughputExceededException"}}

    with pytest.raises(CloudProviderError) as caught:
        DynamoDbProfileStore(_Table(error=Throttled())).get("x")
    assert caught.value.kind is CloudProviderErrorKind.TEMPORARY_UNAVAILABLE


def test_without_a_table_name_the_store_is_not_built(monkeypatch):
    profile._profile_store.cache_clear()
    monkeypatch.delenv("CHORDSYNC_DYNAMODB_PROFILE_TABLE", raising=False)

    with pytest.raises(CloudProviderError):
        profile.get_profile_store()
    profile._profile_store.cache_clear()
