"""Storing covers: only finished songs, only inside their own folder, once."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from scripts.extract_song_covers import (
    CoverError,
    completed_items,
    cover_key,
    extract_with_ffmpeg,
    process,
)

JOB = "11111111-1111-4111-8111-111111111111"


class FakeS3:
    def __init__(self, size=1000):
        self.size, self.puts, self.downloads = size, [], []

    def head_object(self, Bucket, Key):
        return {"ContentLength": self.size}

    def download_file(self, bucket, key, dest):
        self.downloads.append(key)
        open(dest, "wb").write(b"audio")

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


class FakeTable:
    def __init__(self, pages=None):
        self.updates, self.pages = [], pages or []

    def update_item(self, **kwargs):
        self.updates.append(kwargs)

    def scan(self, **kwargs):
        return self.pages.pop(0)


def _item(**extra):
    return {"job_id": JOB, "status": "completed", "playback_object_key": f"jobs/{JOB}/playback/audio.mp3", **extra}


def _picture(size=2000, found=True):
    def extract(audio, out):
        if found:
            out.write_bytes(b"x" * size)
        return found

    return extract


def test_a_cover_is_stored_in_the_songs_own_folder_and_recorded(tmp_path):
    s3, table = FakeS3(), FakeTable()

    result = process(_item(), s3, table, "bucket", tmp_path, execute=True, extract=_picture())

    assert result == "stored"
    put = s3.puts[0]
    assert put["Key"] == f"jobs/{JOB}/playback/cover.jpg" == cover_key(JOB)
    assert put["ContentType"] == "image/jpeg" and put["ServerSideEncryption"] == "AES256"
    update = table.updates[0]
    assert update["UpdateExpression"] == "SET cover_object_key = :k"  # only that field
    assert update["ConditionExpression"] == "attribute_exists(PK) AND #s = :completed"
    assert update["ExpressionAttributeValues"][":k"] == put["Key"]
    assert list(tmp_path.iterdir()) == []  # the working files are removed


def test_a_dry_run_stores_and_changes_nothing(tmp_path):
    s3, table = FakeS3(), FakeTable()

    assert process(_item(), s3, table, "bucket", tmp_path, execute=False, extract=_picture()) == "would store"
    assert s3.puts == [] and table.updates == []


def test_a_song_with_a_cover_is_left_alone(tmp_path):
    s3, table = FakeS3(), FakeTable()

    result = process(_item(cover_object_key="jobs/x/playback/cover.jpg"), s3, table, "b", tmp_path, execute=True, extract=_picture())

    assert result == "has cover" and s3.downloads == []  # not even downloaded


def test_a_file_with_no_picture_is_skipped(tmp_path):
    s3, table = FakeS3(), FakeTable()

    assert process(_item(), s3, table, "b", tmp_path, execute=True, extract=_picture(found=False)) == "no picture"
    assert s3.puts == [] and table.updates == []


@pytest.mark.parametrize(
    "item",
    [
        _item(status="processing"),
        _item(playback_object_key="jobs/other-folder/playback/audio.mp3"),
        _item(playback_object_key=None),
        {**_item(), "job_id": "../x"},
        {**_item(), "job_id": ""},
    ],
)
def test_nothing_is_stored_for_an_unsafe_song(tmp_path, item):
    s3, table = FakeS3(), FakeTable()

    with pytest.raises(CoverError):
        process(item, s3, table, "b", tmp_path, execute=True, extract=_picture())
    assert s3.puts == [] and table.updates == []


def test_an_oversized_audio_file_or_cover_is_refused(tmp_path):
    with pytest.raises(CoverError):
        process(_item(), FakeS3(size=10**9), FakeTable(), "b", tmp_path, execute=True, extract=_picture())
    s3, table = FakeS3(), FakeTable()
    with pytest.raises(CoverError):
        process(_item(), s3, table, "b", tmp_path, execute=True, extract=_picture(size=400_000))
    assert s3.puts == []


def test_every_finished_song_is_listed_across_pages():
    table = FakeTable(pages=[{"Items": [{"a": 1}], "LastEvaluatedKey": {"PK": "x"}}, {"Items": [{"a": 2}]}])

    assert completed_items(table) == [{"a": 1}, {"a": 2}]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_ffmpeg_makes_a_square_320_jpeg_from_a_picture_in_an_mp3(tmp_path):
    cover = tmp_path / "art.png"
    audio = tmp_path / "song.mp3"
    out = tmp_path / "cover.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=640x480", "-frames:v", "1", str(cover)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-i", str(cover),
                    "-map", "0:a", "-map", "1:v", "-c:a", "libmp3lame", "-c:v", "copy", "-id3v2_version", "3", str(audio)], check=True)

    assert extract_with_ffmpeg(audio, out)

    size = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                          capture_output=True, text=True).stdout.strip()
    assert size == "320,320"
    plain = tmp_path / "plain.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(plain)], check=True)
    assert not extract_with_ffmpeg(plain, tmp_path / "none.jpg")  # no picture, no file
