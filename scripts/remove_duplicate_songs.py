"""Permanently remove duplicate copies of catalogue songs: the saved record and
every file stored for that copy. The copy that stays is checked first.

    python -m scripts.remove_duplicate_songs proposal.json            # dry run
    python -m scripts.remove_duplicate_songs proposal.json --execute  # really delete

``proposal.json`` is a list of groups ``{"title", "keep", "hide": [job ids]}`` as
made by scripts.genre_report. A group with ``"source": "REMOVE"`` and no ``keep``
is removed whole (a test song). Needs AWS credentials; take an on-demand backup of
the jobs table first. The stored files are not versioned, so deleting them cannot
be undone.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,63}$")


class SafetyError(Exception):
    """A copy did not pass its check, so nothing is deleted for it."""


@dataclass
class Target:
    job_id: str
    title: str
    keeper: str | None
    keys: list[str] = field(default_factory=list)
    size_bytes: int = 0


def _owner_ok(item: dict) -> bool:
    owner = item.get("owner_id")
    return owner is None or (isinstance(owner, str) and owner.startswith("demo:"))


def _prefix_of(job_id: str) -> str:
    return f"jobs/{job_id}/"


def _stored_keys(item: dict) -> list[str]:
    return [
        key
        for key in (item.get("source_object_key"), item.get("playback_object_key"), item.get("timeline_object_key"))
        if isinstance(key, str) and key
    ]


def check_keeper(table: Any, s3: Any, bucket: str, keeper_id: str) -> None:
    item = table.get_item(Key={"PK": f"JOB#{keeper_id}"}, ConsistentRead=True).get("Item")
    if not item or item.get("status") != "completed" or item.get("superseded_by"):
        raise SafetyError(f"the copy to keep ({keeper_id}) is not a finished song")
    for name in ("playback_object_key", "timeline_object_key"):
        key = item.get(name)
        if not key or not key.startswith(_prefix_of(keeper_id)):
            raise SafetyError(f"the copy to keep ({keeper_id}) has no {name}")
        s3.head_object(Bucket=bucket, Key=key)  # raises if the file is gone


def build_target(table: Any, s3: Any, bucket: str, job_id: str, title: str, keeper: str | None) -> Target:
    if not _SAFE_ID.match(job_id) or (keeper is not None and not _SAFE_ID.match(keeper)):
        raise SafetyError(f"{job_id}: not a job id")
    if keeper == job_id:
        raise SafetyError(f"{job_id}: a copy cannot replace itself")
    item = table.get_item(Key={"PK": f"JOB#{job_id}"}, ConsistentRead=True).get("Item")
    if not item:
        raise SafetyError(f"{job_id}: no such saved song")
    if item.get("status") != "completed":
        raise SafetyError(f"{job_id}: not a finished song")
    if not _owner_ok(item):
        raise SafetyError(f"{job_id}: belongs to an account, not the catalogue")
    prefix = _prefix_of(job_id)
    for key in _stored_keys(item):
        if not key.startswith(prefix):
            raise SafetyError(f"{job_id}: a stored file ({key}) is outside its own folder")
    if keeper is not None:
        check_keeper(table, s3, bucket, keeper)
    target = Target(job_id=job_id, title=str(item.get("title", "")), keeper=keeper)
    token = None
    while True:
        request = {"Bucket": bucket, "Prefix": prefix}
        if token:
            request["ContinuationToken"] = token
        page = s3.list_objects_v2(**request)
        for obj in page.get("Contents", []):
            if not obj["Key"].startswith(prefix):
                raise SafetyError(f"{job_id}: listing returned {obj['Key']}")
            target.keys.append(obj["Key"])
            target.size_bytes += int(obj.get("Size", 0))
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    return target


def remove(table: Any, s3: Any, bucket: str, target: Target) -> None:
    """Delete the files, check the folder is empty, then delete the record. The
    record goes last, so a stopped run leaves a song that can be tried again."""
    for start in range(0, len(target.keys), 1000):
        chunk = target.keys[start : start + 1000]
        result = s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True})
        if result.get("Errors"):
            raise SafetyError(f"{target.job_id}: could not delete {result['Errors'][0].get('Key')}")
    left = s3.list_objects_v2(Bucket=bucket, Prefix=_prefix_of(target.job_id), MaxKeys=1)
    if left.get("Contents"):
        raise SafetyError(f"{target.job_id}: files are still there after deleting")
    table.delete_item(
        Key={"PK": f"JOB#{target.job_id}"},
        ConditionExpression="attribute_exists(PK) AND #s = :completed",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":completed": "completed"},
    )


def targets_from_proposal(groups: list[dict]) -> list[tuple[str, str, str | None]]:
    wanted = []
    for group in groups:
        for job_id in group.get("hide", []):
            wanted.append((job_id, group["title"], group["keep"]))
        if group.get("source") == "REMOVE":
            wanted.append((group["keep"], group["title"], None))
    return wanted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--execute", action="store_true", help="really delete (the default is a dry run)")
    parser.add_argument("--table", default="chordsync-demo-jobs")
    parser.add_argument("--bucket", required=True)
    args = parser.parse_args(argv)

    import boto3

    session = boto3.session.Session(region_name="ap-southeast-1")
    table = session.resource("dynamodb").Table(args.table)
    s3 = session.client("s3")
    groups = json.loads(args.proposal.read_text())
    targets = []
    for job_id, title, keeper in targets_from_proposal(groups):
        targets.append(build_target(table, s3, args.bucket, job_id, title, keeper))  # any problem stops here, before any delete
    files = sum(len(target.keys) for target in targets)
    megabytes = sum(target.size_bytes for target in targets) / 1_048_576
    for target in targets:
        print(f"{'REMOVE' if args.execute else 'would remove'} {target.job_id} {target.title!r}: "
              f"{len(target.keys)} files, keeps {target.keeper or 'nothing (test song)'}")
    print(f"{len(targets)} saved songs, {files} files, {megabytes:.1f} MB")
    if not args.execute:
        print("Dry run: nothing was deleted. Add --execute to delete.")
        return 0
    for target in targets:
        remove(table, s3, args.bucket, target)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
