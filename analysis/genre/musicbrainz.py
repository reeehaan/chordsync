"""Ask MusicBrainz, the open music database, what genre a song is.

Only text is sent (the title and artist), never audio. The request is https
only, follows no redirects, reads at most one megabyte, and waits between
calls, as MusicBrainz asks (one request a second, and a User-Agent that says
who is asking). When the server says it is busy the call is retried slowly.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable

from analysis.genre.genre_mapping import map_tags
from analysis.genre.title_parser import normalize

BASE_URL = "https://musicbrainz.org/ws/2"
USER_AGENT = "ChordSync/1.0 (chordsync.app@gmail.com)"
MIN_SECONDS_BETWEEN_REQUESTS = 1.1
MAX_RESPONSE_BYTES = 1_000_000
TIMEOUT_SECONDS = 15
RETRY_WAITS = (3.0, 8.0, 20.0)
MIN_TITLE_SIMILARITY = 0.88
MIN_ARTIST_SIMILARITY = 0.7
MIN_SEARCH_SCORE = 90

Fetcher = Callable[[str], tuple[int, bytes]]


class MusicBrainzError(Exception):
    """The service could not be asked (network, or busy for too long)."""


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # type: ignore[override]
        return None


def fetch_https(url: str) -> tuple[int, bytes]:
    if not url.startswith("https://"):
        raise MusicBrainzError("not https")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirects)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - https only
            return response.status, response.read(MAX_RESPONSE_BYTES + 1)[:MAX_RESPONSE_BYTES]
    except urllib.error.HTTPError as error:
        return error.code, b""
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise MusicBrainzError(type(error).__name__) from error


@dataclass
class Lookup:
    """What was found for one song."""

    found: bool
    genres: list[str] = field(default_factory=list)
    matched_title: str | None = None
    matched_artist: str | None = None
    # "high": the title and the artist both match. "low": a title-only guess,
    # which is often a different song with the same name.
    confidence: str = "none"
    tags: list[tuple[str, int]] = field(default_factory=list)
    note: str = ""


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


class MusicBrainz:
    def __init__(
        self,
        fetch: Fetcher = fetch_https,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._sleep = sleep
        self._clock = clock
        self._last_request = float("-inf")

    def _get(self, path: str, params: dict[str, str]) -> dict:
        url = f"{BASE_URL}/{path}?" + urllib.parse.urlencode({**params, "fmt": "json"})
        for attempt in range(len(RETRY_WAITS) + 1):
            wait = MIN_SECONDS_BETWEEN_REQUESTS - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
            self._last_request = self._clock()
            status, body = self._fetch(url)
            if status == 200:
                try:
                    data = json.loads(body)
                except (ValueError, RecursionError) as error:
                    raise MusicBrainzError("answer was not JSON") from error
                if not isinstance(data, dict):
                    raise MusicBrainzError("answer was not an object")
                return data
            if status in (429, 503) and attempt < len(RETRY_WAITS):
                self._sleep(RETRY_WAITS[attempt])
                continue
            raise MusicBrainzError(f"status {status}")
        raise MusicBrainzError("busy")  # pragma: no cover - the loop always returns or raises

    def lookup(self, title: str, artist: str | None) -> Lookup:
        query = f'recording:"{_quote(title)}"'
        if artist:
            query += f' AND artist:"{_quote(artist)}"'
        data = self._get("recording", {"query": query, "limit": "8"})
        best = self._best_match(title, artist, data.get("recordings", []))
        if best is None:
            return Lookup(found=False, note="no matching recording")
        recording, credit_name, artist_id = best
        tags = _tags(recording)
        note = ""
        if artist_id:
            try:
                detail = self._get(f"artist/{artist_id}", {"inc": "genres+tags"})
                tags += _tags(detail, weight=1)
            except MusicBrainzError as error:
                note = f"artist tags unavailable ({error})"
        return Lookup(
            found=True,
            genres=map_tags(tags),
            matched_title=str(recording.get("title", "")),
            matched_artist=credit_name,
            confidence="high" if artist else "low",
            tags=tags,
            note=note,
        )

    @staticmethod
    def _best_match(title: str, artist: str | None, recordings: list) -> tuple[dict, str, str | None] | None:
        scored: list[tuple[float, dict, str, str | None]] = []
        for recording in recordings:
            if not isinstance(recording, dict) or int(recording.get("score", 0)) < MIN_SEARCH_SCORE:
                continue
            title_match = similarity(title, str(recording.get("title", "")))
            if title_match < MIN_TITLE_SIMILARITY:
                continue
            credits = [c for c in recording.get("artist-credit", []) if isinstance(c, dict)]
            names = [str(c.get("name", "")) for c in credits]
            first = credits[0] if credits else {}
            artist_id = (first.get("artist") or {}).get("id") if isinstance(first.get("artist"), dict) else None
            if artist:
                artist_match = max((similarity(artist, name) for name in names), default=0.0)
                if artist_match < MIN_ARTIST_SIMILARITY:
                    continue
            else:
                artist_match = 0.0
            scored.append((title_match + artist_match, recording, ", ".join(names), artist_id))
        if not scored:
            return None
        scored.sort(key=lambda item: -item[0])
        _, recording, names, artist_id = scored[0]
        return recording, names, artist_id


def _quote(text: str) -> str:
    return text.replace("\\", " ").replace('"', " ")


def _tags(entity: dict, weight: int = 2) -> list[tuple[str, int]]:
    """Tag and genre names with their votes, counted ``weight`` times. A tag on
    the recording itself says more about the song than one on the artist."""
    found: list[tuple[str, int]] = []
    for key in ("genres", "tags"):
        for item in entity.get(key, []) or []:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                votes = item.get("count", 1)
                found.append((item["name"], (votes if isinstance(votes, int) else 1) * weight))
    return found
