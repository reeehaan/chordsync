"""Write reviewed genres and artists onto catalogue songs.

    python -m scripts.apply_song_genres proposal.json                 # dry run
    python -m scripts.apply_song_genres proposal.json --execute       # write

Only the fields ``artist``, ``genres`` and ``genre_source`` are set, on a song
that exists and is finished; nothing else on the record is touched, and nothing
is created. Running it twice gives the same result. Undo it by removing those
three fields. Take an on-demand backup of the jobs table first.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from analysis.genre.genres import GENRES

MAX_GENRES = 3
MAX_ARTIST_CHARACTERS = 100
SOURCE = "review"  # the owner looked at every one of them
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,63}$")


class InvalidGenres(ValueError):
    pass


def check(group: dict) -> tuple[str, list[str], str | None]:
    """The song to tag, its genres and its artist, or an error saying what is wrong."""
    job_id = group.get("keep")
    if not isinstance(job_id, str) or not _SAFE_ID.match(job_id):
        raise InvalidGenres(f"{group.get('title')!r}: not a job id")
    genres = group.get("genres")
    if not isinstance(genres, list) or not 1 <= len(genres) <= MAX_GENRES:
        raise InvalidGenres(f"{group.get('title')!r}: needs 1 to {MAX_GENRES} genres")
    if len(set(genres)) != len(genres) or any(genre not in GENRES for genre in genres):
        raise InvalidGenres(f"{group.get('title')!r}: genres must be unique and on the list: {genres}")
    artist = group.get("artist")
    if artist is not None:
        if not isinstance(artist, str) or not artist.strip() or len(artist) > MAX_ARTIST_CHARACTERS:
            raise InvalidGenres(f"{group.get('title')!r}: bad artist")
        artist = " ".join(artist.split())
    return job_id, list(genres), artist


def write(table: Any, job_id: str, genres: list[str], artist: str | None) -> None:
    names = {"#s": "status", "#g": "genres", "#src": "genre_source"}
    values: dict[str, Any] = {":completed": "completed", ":g": genres, ":src": SOURCE}
    expression = "SET #g = :g, #src = :src"
    if artist is not None:
        names["#a"] = "artist"
        values[":a"] = artist
        expression += ", #a = :a"
    table.update_item(
        Key={"PK": f"JOB#{job_id}"},
        UpdateExpression=expression,
        ConditionExpression="attribute_exists(PK) AND #s = :completed",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--table", default="chordsync-demo-jobs")
    args = parser.parse_args(argv)

    groups = [g for g in json.loads(args.proposal.read_text()) if g.get("source") != "REMOVE"]
    work = [(g["title"], *check(g)) for g in groups]  # every row is checked before any write
    for title, job_id, genres, artist in work:
        print(f"{'WRITE' if args.execute else 'would write'} {title!r}: {', '.join(genres)} | {artist}")
    print(f"{len(work)} songs")
    if not args.execute:
        print("Dry run: nothing was written. Add --execute to write.")
        return 0
    import boto3

    table = boto3.session.Session(region_name="ap-southeast-1").resource("dynamodb").Table(args.table)
    for _, job_id, genres, artist in work:
        write(table, job_id, genres, artist)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
