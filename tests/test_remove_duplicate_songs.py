"""Removing duplicate copies for good: every safety check, and the order of deletes."""

from __future__ import annotations

import pytest

from scripts.remove_duplicate_songs import (
    SafetyError,
    build_target,
    remove,
    targets_from_proposal,
)

BUCKET = "bucket"
KEEP = "11111111-1111-4111-8111-111111111111"
DUPE = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


class FakeTable:
    def __init__(self, items):
        self.items = {f"JOB#{job_id}": item for job_id, item in items.items()}
        self.deleted: list[tuple[str, dict]] = []
        self.events: list[str] = []

    def get_item(self, Key, ConsistentRead=False):
        item = self.items.get(Key["PK"])
        return {"Item": item} if item else {}

    def delete_item(self, Key, **conditions):
        self.events.append(f"record:{Key['PK']}")
        self.deleted.append((Key["PK"], conditions))
        self.items.pop(Key["PK"], None)


class FakeS3:
    def __init__(self, objects, *, fail_delete=False, page_size=1000):
        self.objects = dict(objects)  # key -> size
        self.fail_delete, self.page_size = fail_delete, page_size
        self.events: list[str] = []

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {}

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None, MaxKeys=1000):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start : start + min(self.page_size, MaxKeys)]
        truncated = start + len(page) < len(keys)
        return {
            "Contents": [{"Key": k, "Size": self.objects[k]} for k in page],
            "IsTruncated": truncated,
            "NextContinuationToken": str(start + len(page)) if truncated else None,
        }

    def delete_objects(self, Bucket, Delete):
        self.events.append("files")
        if self.fail_delete:
            return {"Errors": [{"Key": Delete["Objects"][0]["Key"]}]}
        for obj in Delete["Objects"]:
            self.objects.pop(obj["Key"], None)
        return {}


def _item(job_id, **extra):
    return {
        "PK": f"JOB#{job_id}",
        "job_id": job_id,
        "title": "Song",
        "status": "completed",
        "owner_id": "demo:demo-owner",
        "source_object_key": f"jobs/{job_id}/source/input.mp3",
        "playback_object_key": f"jobs/{job_id}/playback/audio.mp3",
        "timeline_object_key": f"jobs/{job_id}/results/timeline.json",
        **extra,
    }


def _files(job_id):
    return {
        f"jobs/{job_id}/source/input.mp3": 100,
        f"jobs/{job_id}/playback/audio.mp3": 300,
        f"jobs/{job_id}/results/timeline.json": 5,
    }


@pytest.fixture
def world():
    table = FakeTable({KEEP: _item(KEEP), DUPE: _item(DUPE)})
    s3 = FakeS3({**_files(KEEP), **_files(DUPE), **_files(OTHER)})
    return table, s3


def test_a_copy_is_listed_with_its_files_and_size(world):
    table, s3 = world

    target = build_target(table, s3, BUCKET, DUPE, "Song", KEEP)

    assert sorted(target.keys) == sorted(_files(DUPE))
    assert target.size_bytes == 405 and target.keeper == KEEP


def test_removing_a_copy_deletes_its_files_then_its_record_and_nothing_else(world):
    table, s3 = world
    target = build_target(table, s3, BUCKET, DUPE, "Song", KEEP)
    order: list[str] = []
    s3.events, table.events = order, order

    remove(table, s3, BUCKET, target)

    assert order == ["files", f"record:JOB#{DUPE}"]  # files first, record last
    assert set(s3.objects) == set(_files(KEEP)) | set(_files(OTHER))
    assert f"JOB#{KEEP}" in table.items and f"JOB#{DUPE}" not in table.items
    key, conditions = table.deleted[0]
    assert key == f"JOB#{DUPE}"
    assert "attribute_exists(PK)" in conditions["ConditionExpression"]  # conditional delete


def test_a_failed_file_delete_leaves_the_record_so_the_run_can_be_repeated(world):
    table, s3 = world
    target = build_target(table, s3, BUCKET, DUPE, "Song", KEEP)
    s3.fail_delete = True

    with pytest.raises(SafetyError):
        remove(table, s3, BUCKET, target)

    assert f"JOB#{DUPE}" in table.items and table.deleted == []


def test_a_long_file_list_is_read_page_by_page():
    table = FakeTable({KEEP: _item(KEEP), DUPE: _item(DUPE)})
    objects = {**_files(KEEP), **{f"jobs/{DUPE}/results/part-{i}.json": 1 for i in range(7)}, **_files(DUPE)}
    s3 = FakeS3(objects, page_size=3)

    target = build_target(table, s3, BUCKET, DUPE, "Song", KEEP)

    assert len(target.keys) == 10


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda t, s: t.items.pop(f"JOB#{DUPE}"), "no such"),
        (lambda t, s: t.items[f"JOB#{DUPE}"].update(status="processing"), "not a finished"),
        (lambda t, s: t.items[f"JOB#{DUPE}"].update(owner_id="cognito:abc"), "belongs to an account"),
        (lambda t, s: t.items[f"JOB#{DUPE}"].update(playback_object_key=f"jobs/{KEEP}/playback/audio.mp3"), "outside its own folder"),
        (lambda t, s: t.items[f"JOB#{DUPE}"].update(timeline_object_key="results/timeline.json"), "outside its own folder"),
        (lambda t, s: t.items.pop(f"JOB#{KEEP}"), "not a finished"),
        (lambda t, s: t.items[f"JOB#{KEEP}"].update(status="failed"), "not a finished"),
        (lambda t, s: t.items[f"JOB#{KEEP}"].pop("timeline_object_key"), "timeline_object_key"),
        (lambda t, s: s.objects.pop(f"jobs/{KEEP}/playback/audio.mp3"), "KeyError"),
    ],
)
def test_nothing_is_deleted_unless_every_check_passes(world, mutate, reason):
    table, s3 = world
    mutate(table, s3)

    with pytest.raises((SafetyError, KeyError)) as caught:
        build_target(table, s3, BUCKET, DUPE, "Song", KEEP)

    assert reason in str(caught.value) or reason == "KeyError"
    assert table.deleted == []


@pytest.mark.parametrize("job_id", ["", "..", "../x", "a/b", "short", "x" * 100, "ok ok ok ok"])
def test_an_odd_job_id_is_refused_before_anything_is_looked_up(world, job_id):
    table, s3 = world

    with pytest.raises(SafetyError, match="not a job id"):
        build_target(table, s3, BUCKET, job_id, "Song", KEEP)


def test_a_copy_cannot_be_its_own_replacement(world):
    table, s3 = world

    with pytest.raises(SafetyError, match="itself"):
        build_target(table, s3, BUCKET, DUPE, "Song", DUPE)


def test_an_ownerless_old_song_is_allowed_like_a_demo_one():
    table = FakeTable({KEEP: _item(KEEP), DUPE: _item(DUPE, owner_id=None)})
    s3 = FakeS3({**_files(KEEP), **_files(DUPE)})

    assert build_target(table, s3, BUCKET, DUPE, "Song", KEEP).keys


def test_a_test_song_with_no_replacement_can_be_removed_whole():
    table = FakeTable({DUPE: _item(DUPE)})
    s3 = FakeS3(_files(DUPE))

    target = build_target(table, s3, BUCKET, DUPE, "Deploy smoke", None)
    remove(table, s3, BUCKET, target)

    assert s3.objects == {} and table.items == {}


def test_the_proposal_gives_every_extra_copy_and_the_test_song():
    groups = [
        {"title": "Dangalanna Be", "keep": KEEP, "hide": [DUPE, OTHER], "source": "ME"},
        {"title": "Wonderwall", "keep": "w" * 36, "hide": [], "source": "MB"},
        {"title": "Deploy smoke", "keep": "s" * 36, "hide": [], "source": "REMOVE"},
    ]

    assert targets_from_proposal(groups) == [
        (DUPE, "Dangalanna Be", KEEP),
        (OTHER, "Dangalanna Be", KEEP),
        ("s" * 36, "Deploy smoke", None),
    ]
