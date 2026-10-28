"""Pull the cover art out of the catalogue songs' audio files and store a small
copy next to each song.

    python -m scripts.extract_song_covers --bucket BUCKET            # dry run
    python -m scripts.extract_song_covers --bucket BUCKET --execute  # store them

For each finished song without a cover it downloads the stored audio, takes the
picture embedded in the file (if any), makes a 320x320 JPEG, stores it as
``jobs/<id>/playback/cover.jpg`` and sets ``cover_object_key`` on the song.
The audio is never changed. A song with no embedded picture is skipped and
listed. Running it twice does nothing the second time.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

COVER_SIZE = 320
MAX_COVER_BYTES = 300_000
MAX_AUDIO_BYTES = 60 * 1024 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,63}$")


class CoverError(Exception):
    pass


def cover_key(job_id: str) -> str:
    return f"jobs/{job_id}/playback/cover.jpg"


def extract_with_ffmpeg(audio: Path, out: Path) -> bool:
    """True if the file had a picture and ``out`` now holds the 320x320 JPEG."""
    command = [
        "ffmpeg", "-v", "error", "-y", "-protocol_whitelist", "file",
        "-i", str(audio), "-an", "-map", "0:v:0", "-frames:v", "1",
        "-vf", f"scale={COVER_SIZE}:{COVER_SIZE}:force_original_aspect_ratio=increase,"
        f"crop={COVER_SIZE}:{COVER_SIZE}",
        "-q:v", "4", str(out),
    ]
    result = subprocess.run(command, capture_output=True, timeout=120)
    return result.returncode == 0 and out.exists() and out.stat().st_size > 0


def process(
    item: dict,
    s3: Any,
    table: Any,
    bucket: str,
    workdir: Path,
    *,
    execute: bool,
    extract: Callable[[Path, Path], bool] = extract_with_ffmpeg,
) -> str:
    """One song. Returns what happened: "stored", "would store", "has cover", "no picture"."""
    job_id = str(item.get("job_id", ""))
    if not _SAFE_ID.match(job_id):
        raise CoverError(f"{job_id!r}: not a job id")
    if item.get("status") != "completed":
        raise CoverError(f"{job_id}: not a finished song")
    if item.get("cover_object_key"):
        return "has cover"
    playback = item.get("playback_object_key")
    if not isinstance(playback, str) or not playback.startswith(f"jobs/{job_id}/"):
        raise CoverError(f"{job_id}: no stored audio in its own folder")
    audio = workdir / f"{job_id}.audio"
    head = s3.head_object(Bucket=bucket, Key=playback)
    if int(head.get("ContentLength", 0)) > MAX_AUDIO_BYTES:
        raise CoverError(f"{job_id}: audio is unexpectedly large")
    s3.download_file(bucket, playback, str(audio))
    picture = workdir / f"{job_id}.jpg"
    try:
        found = extract(audio, picture)
        if not found:
            return "no picture"
        size = picture.stat().st_size
        if size > MAX_COVER_BYTES:
            raise CoverError(f"{job_id}: cover is {size} bytes, more than expected")
        if not execute:
            return "would store"
        key = cover_key(job_id)
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=picture.read_bytes(),
            ContentType="image/jpeg",
            CacheControl="private, max-age=86400",
            ServerSideEncryption="AES256",
        )
        table.update_item(
            Key={"PK": f"JOB#{job_id}"},
            UpdateExpression="SET cover_object_key = :k",
            ConditionExpression="attribute_exists(PK) AND #s = :completed",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":k": key, ":completed": "completed"},
        )
        return "stored"
    finally:
        audio.unlink(missing_ok=True)
        picture.unlink(missing_ok=True)


def completed_items(table: Any) -> list[dict]:
    items: list[dict] = []
    token = None
    while True:
        request: dict[str, Any] = {
            "FilterExpression": "#s = :c",
            "ExpressionAttributeNames": {"#s": "status"},
            "ExpressionAttributeValues": {":c": "completed"},
        }
        if token:
            request["ExclusiveStartKey"] = token
        page = table.scan(**request)
        items.extend(page.get("Items", []))
        token = page.get("LastEvaluatedKey")
        if not token:
            return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--table", default="chordsync-demo-jobs")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    import boto3

    session = boto3.session.Session(region_name="ap-southeast-1")
    table = session.resource("dynamodb").Table(args.table)
    s3 = session.client("s3")
    counts: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="chordsync-covers-") as tmp:
        for item in completed_items(table):
            outcome = process(item, s3, table, args.bucket, Path(tmp), execute=args.execute)
            counts[outcome] = counts.get(outcome, 0) + 1
            print(f"{outcome:12} {item.get('job_id')} {item.get('title')!r}")
    print(counts)
    if not args.execute:
        print("Dry run: nothing was stored. Add --execute to store the covers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
