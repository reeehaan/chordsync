"""Build a review report of the catalogue's songs: which copies are duplicates,
and what genre MusicBrainz suggests for each song. Read-only: it reads a saved
copy of the job list and writes a JSON file; it never touches AWS.

    aws dynamodb scan --table-name chordsync-demo-jobs \\
        --filter-expression '#s = :c' --expression-attribute-names '{"#s":"status"}' \\
        --expression-attribute-values '{":c":{"S":"completed"}}' --output json > jobs.json
    python -m scripts.genre_report jobs.json report.json [--cache cache.json]

Songs with no artist in their name are not looked up: a title alone often
matches a different song with the same name.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from analysis.genre.musicbrainz import Lookup, MusicBrainz, MusicBrainzError
from analysis.genre.title_parser import parse_song_name


def _text(item: dict, name: str) -> str | None:
    value = item.get(name)
    if isinstance(value, dict):
        return value.get("S")
    return None


def load_jobs(path: Path) -> list[dict]:
    items = json.loads(path.read_text()).get("Items", [])
    jobs = []
    for item in items:
        title = _text(item, "title")
        job_id = _text(item, "job_id")
        if title and job_id:
            jobs.append({"job_id": job_id, "title": title, "created_at": _text(item, "created_at") or ""})
    return jobs


def group_songs(jobs: list[dict]) -> list[dict]:
    """One group per song. The newest copy is the one to keep."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for job in jobs:
        parsed = parse_song_name(job["title"])
        groups[parsed.key].append({**job, "title_clean": parsed.title, "artist": parsed.artist})
    result = []
    for key, copies in groups.items():
        copies.sort(key=lambda copy: copy["created_at"], reverse=True)
        artists = Counter(copy["artist"] for copy in copies if copy["artist"])
        result.append(
            {
                "key": key,
                "title": copies[0]["title_clean"],
                "artist": artists.most_common(1)[0][0] if artists else None,
                "keep": copies[0]["job_id"],
                "hide": [copy["job_id"] for copy in copies[1:]],
                "names": sorted({copy["title"] for copy in copies}),
                "copies": len(copies),
            }
        )
    result.sort(key=lambda group: group["key"])
    return result


def lookup_all(groups: list[dict], client: MusicBrainz, cache: dict, progress=print) -> None:
    for number, group in enumerate(groups, 1):
        if not group["artist"]:
            group["musicbrainz"] = {"found": False, "note": "no artist in the name, not looked up"}
            continue
        cache_key = f'{group["title"]}|{group["artist"]}'
        if cache_key not in cache:
            try:
                result = client.lookup(group["title"], group["artist"])
                cache[cache_key] = _as_dict(result)
            except MusicBrainzError as error:
                cache[cache_key] = {"found": False, "note": f"lookup failed: {error}"}
        group["musicbrainz"] = cache[cache_key]
        progress(f'[{number}/{len(groups)}] {group["title"]} / {group["artist"]}: {group["musicbrainz"].get("genres")}')


def _as_dict(result: Lookup) -> dict:
    return {
        "found": result.found,
        "genres": result.genres,
        "matched_title": result.matched_title,
        "matched_artist": result.matched_artist,
        "confidence": result.confidence,
        "note": result.note,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("jobs", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args(argv)

    jobs = load_jobs(args.jobs)
    groups = group_songs(jobs)
    cache = json.loads(args.cache.read_text()) if args.cache and args.cache.exists() else {}
    try:
        lookup_all(groups, MusicBrainz(), cache)
    finally:
        if args.cache:
            args.cache.write_text(json.dumps(cache, indent=1))
    args.report.write_text(json.dumps({"songs": len(groups), "jobs": len(jobs), "groups": groups}, indent=1))
    print(f"{len(jobs)} saved songs are {len(groups)} different songs; report written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
