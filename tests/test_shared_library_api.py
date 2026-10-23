"""Shared library: finished songs visible to every app token (hosted API)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.api.app.routers import analysis_jobs
from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactKeyFactory,
    ArtifactRole,
)
from backend.api.app.services.cloud_job import CloudJobStatus, new_cloud_job
from tests.test_hosted_upload import Env

TIMELINE = {
    "schema_version": 1,
    "bpm": 88,
    "beats_per_bar": 4,
    "beat_source": "test",
    "lyric_source": "test",
    "bars": [],
    "lyrics": [],
}


@pytest.fixture(autouse=True)
def _reset():
    for provider in (analysis_jobs._runtime_config, analysis_jobs._cloud_application):
        provider.cache_clear()
    yield
    for provider in (analysis_jobs._runtime_config, analysis_jobs._cloud_application):
        provider.cache_clear()


def seed(
    env: Env,
    job_id: str,
    *,
    title: str = "Song",
    owner: str = "demo:tester-a",
    age_minutes: int = 0,
    status: CloudJobStatus = CloudJobStatus.COMPLETED,
    with_audio: bool = True,
    with_timeline: bool = True,
) -> None:
    keys = ArtifactKeyFactory()
    job = new_cloud_job(job_id, title)
    job.owner_id = owner
    job.status = status
    job.duration_seconds = 215.5
    job.created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    if with_timeline:
        key = keys.timeline(job_id)
        env.artifacts.put_bytes(
            key, json.dumps(TIMELINE).encode(), content_type="application/json"
        )
        job.timeline_object_key = key.value
    if with_audio:
        key = keys.playback(job_id, ".mp3")
        env.artifacts.put_bytes(key, b"ID3 audio", content_type="audio/mpeg")
        job.playback_object_key = key.value
    env.repository.add(job)


@pytest.fixture
def env(tmp_path, monkeypatch) -> Env:
    return Env(tmp_path, monkeypatch)


def test_library_lists_every_tokens_finished_songs_newest_first(env):
    seed(env, "old", title="Older", owner="demo:tester-a", age_minutes=30)
    seed(env, "new", title="Newer", owner="demo:tester-b", age_minutes=1)

    for client in (env.client, env.client_b):
        response = client.get("/analysis/library")
        assert response.status_code == 200
        songs = response.json()["songs"]
        assert [song["job_id"] for song in songs] == ["new", "old"]
        assert songs[0]["title"] == "Newer"
        assert songs[0]["duration_seconds"] == 215.5


def test_library_leaves_out_unfinished_and_incomplete_jobs(env):
    seed(env, "done")
    seed(env, "queued", status=CloudJobStatus.QUEUED)
    seed(env, "no-audio", with_audio=False)
    seed(env, "no-timeline", with_timeline=False)

    songs = env.client.get("/analysis/library").json()["songs"]
    assert [song["job_id"] for song in songs] == ["done"]


def test_library_needs_a_token(env):
    seed(env, "done")
    for path in (
        "/analysis/library",
        "/analysis/library/done/result",
        "/analysis/library/done/audio",
    ):
        assert env.anonymous.get(path).status_code == 401


def test_another_token_can_fetch_a_songs_timeline(env):
    seed(env, "mine", owner="demo:tester-a")

    response = env.client_b.get("/analysis/library/mine/result")
    assert response.status_code == 200
    assert response.json()["bpm"] == 88
    # The per-job route still hides other owners' jobs.
    assert env.client_b.get("/analysis/jobs/mine/result").status_code == 404


def test_audio_link_is_short_lived_and_names_the_file_type(env):
    seed(env, "song")

    response = env.client_b.get("/analysis/library/song/audio")
    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("https://download.invalid/jobs/song/playback/")
    assert body["expires_in_seconds"] == 600
    assert body["file_type"] == "mp3"
    assert env.uploads.presign_requests[-1]["operation"] == "get"


def test_unknown_or_unfinished_song_is_not_found(env):
    seed(env, "queued", status=CloudJobStatus.QUEUED)
    for job_id in ("missing", "queued"):
        for suffix in ("result", "audio"):
            response = env.client.get(f"/analysis/library/{job_id}/{suffix}")
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "song_not_found"


def test_missing_timeline_object_is_reported_not_crashed(env):
    seed(env, "gone")
    env.artifacts.delete(ArtifactKey(ArtifactRole.TIMELINE_RESULT, f"jobs/gone/results/timeline.json"))

    response = env.client.get("/analysis/library/gone/result")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "result_artifact_missing"
