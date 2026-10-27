"""The catalogue review report: duplicates are grouped, the newest copy is kept."""

from __future__ import annotations

import json

from analysis.genre.musicbrainz import Lookup, MusicBrainzError
from scripts.genre_report import group_songs, load_jobs, lookup_all


def _job(job_id, title, created):
    return {"job_id": job_id, "title": title, "created_at": created}


def test_copies_of_one_song_become_one_group_and_the_newest_is_kept():
    groups = group_songs([
        _job("a1", "Dangalanna Be - Daddy - Spotimate.app", "2026-10-10T10:00:00Z"),
        _job("a2", "Dangalanna Be - Daddy - Spotimate.app", "2026-10-20T10:00:00Z"),
        _job("a3", "Dangalanna Be - Daddy - Spotimate.app", "2026-10-15T10:00:00Z"),
        _job("b1", "Wonderwall - Oasis", "2026-10-01T10:00:00Z"),
    ])

    by_title = {group["title"]: group for group in groups}
    daddy = by_title["Dangalanna Be"]
    assert daddy["keep"] == "a2" and sorted(daddy["hide"]) == ["a1", "a3"] and daddy["copies"] == 3
    assert daddy["artist"] == "Daddy"
    assert by_title["Wonderwall"]["keep"] == "b1" and by_title["Wonderwall"]["hide"] == []


def test_the_title_only_copy_joins_the_copy_with_an_artist():
    groups = group_songs([
        _job("t1", "Mata Rawana", "2026-10-10T10:00:00Z"),
        _job("t2", "Mata Rawana - La Signore - Spotimate.app", "2026-10-12T10:00:00Z"),
    ])

    assert len(groups) == 1
    assert groups[0]["artist"] == "La Signore" and groups[0]["keep"] == "t2" and groups[0]["hide"] == ["t1"]


def test_different_songs_are_never_merged_and_every_job_is_accounted_for():
    jobs = [_job(f"j{i}", name, f"2026-10-{10 + i:02d}T00:00:00Z")
            for i, name in enumerate(["Ghost", "Her", "Lemon", "Ghost", "Her"])]

    groups = group_songs(jobs)

    assert {group["title"] for group in groups} == {"Ghost", "Her", "Lemon"}
    kept_and_hidden = [g["keep"] for g in groups] + [h for g in groups for h in g["hide"]]
    assert sorted(kept_and_hidden) == sorted(job["job_id"] for job in jobs)


def test_a_job_is_either_kept_or_hidden_never_both():
    groups = group_songs([_job(f"j{i}", "Same - Band", f"2026-10-{10 + i:02d}T00:00:00Z") for i in range(5)])

    assert len(groups) == 1
    assert groups[0]["keep"] not in groups[0]["hide"] and len(groups[0]["hide"]) == 4


def test_the_job_list_is_read_from_a_dynamodb_scan(tmp_path):
    scan = {"Items": [
        {"job_id": {"S": "x1"}, "title": {"S": "Song"}, "created_at": {"S": "2026-10-01T00:00:00Z"}},
        {"job_id": {"S": "x2"}, "title": {"S": "Other"}},
        {"job_id": {"S": "x3"}},  # no title: skipped
    ]}
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(scan))

    assert [job["job_id"] for job in load_jobs(path)] == ["x1", "x2"]


class FakeClient:
    def __init__(self):
        self.asked = []

    def lookup(self, title, artist):
        self.asked.append((title, artist))
        if title == "Boom":
            raise MusicBrainzError("busy")
        return Lookup(found=True, genres=["Rock"], matched_title=title, matched_artist=artist, confidence="high")


def test_only_songs_with_an_artist_are_looked_up_and_answers_are_cached():
    groups = group_songs([_job("a", "Ghost", "2026-10-01T00:00:00Z"),
                          _job("b", "Wonderwall - Oasis", "2026-10-01T00:00:00Z"),
                          _job("c", "Boom - Band", "2026-10-01T00:00:00Z")])
    client, cache = FakeClient(), {}

    lookup_all(groups, client, cache, progress=lambda line: None)

    by_title = {group["title"]: group for group in groups}
    assert client.asked == [("Boom", "Band"), ("Wonderwall", "Oasis")]  # not Ghost
    assert by_title["Ghost"]["musicbrainz"]["found"] is False
    assert by_title["Wonderwall"]["musicbrainz"]["genres"] == ["Rock"]
    assert "lookup failed" in by_title["Boom"]["musicbrainz"]["note"]
    client.asked.clear()
    lookup_all(groups, client, cache, progress=lambda line: None)
    assert client.asked == []  # everything came from the cache
