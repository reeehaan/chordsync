from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from analysis.lyrics.lyrics_api_reference import (
    LyricsApiResponseRejectedError,
    LyricsApiUnavailableError,
)
from analysis.lyrics.lyrics_reference import SongIdentity


LRCLIB_GET_URL = "https://lrclib.net/api/get"
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
# The exact lookup rejects a recording whose length differs by more than a couple
# of seconds; the search fallback picks the closest one within this many seconds.
SEARCH_DURATION_TOLERANCE_SECONDS = 10.0
# A different release of the same recording (single, album, compilation) has
# the same length; prefer such an entry when it has timed lyrics.
SAME_RECORDING_TOLERANCE_SECONDS = 3.0
# LRCLIB answers 5xx now and then, so a temporary failure is retried.
MAX_ATTEMPTS = 4
RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
DEFAULT_USER_AGENT = (
    "ChordSync/0.1 (academic development; contact: developer@localhost)"
)
DEFAULT_TIMEOUT_SECONDS = 10.0


class _TemporaryFailure(LyricsApiUnavailableError):
    """A failure worth trying again (server error, timeout, no connection)."""


@dataclass(frozen=True)
class LyricsApiRateLimitedError(LyricsApiUnavailableError):
    retry_after_seconds: float | None

    def __str__(self) -> str:
        return "Lyrics provider rate limit was reached."


class LrclibTransport:
    """Official LRCLIB API transport for development/academic validation."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Callable[..., object] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("LRCLIB User-Agent must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("LRCLIB timeout must be positive.")
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._opener = opener
        self._sleep = sleep

    def fetch(
        self,
        song_identity: SongIdentity,
        *,
        duration_seconds: float | None,
        credential: str | None,
    ) -> Mapping[str, object]:
        del credential
        parameters: dict[str, str] = {
            "track_name": song_identity.title,
            "artist_name": song_identity.artist,
        }
        if song_identity.album:
            parameters["album_name"] = song_identity.album
        if duration_seconds is not None and duration_seconds > 0:
            parameters["duration"] = str(round(duration_seconds, 3))
        try:
            exact = self._request_json(LRCLIB_GET_URL, parameters)
        except LyricsApiRateLimitedError:
            raise  # never send a second request while rate limited
        except LyricsApiUnavailableError as exact_failure:
            candidate = self._search(song_identity, duration_seconds, parameters)
            if candidate is None:
                raise exact_failure
            return _map_response(candidate)
        if exact.get("syncedLyrics"):
            return _map_response(exact)
        # The exact match only has plain lyrics. Another release of the same
        # recording may have timed lyrics, which are far more useful.
        better = self._search(
            song_identity, duration_seconds, parameters, require_synced=True
        )
        return _map_response(better if better is not None else exact)

    def _search(
        self,
        song_identity: SongIdentity,
        duration_seconds: float | None,
        parameters: Mapping[str, str],
        *,
        require_synced: bool = False,
    ) -> Mapping[str, object] | None:
        search = {
            key: value
            for key, value in parameters.items()
            if key in {"track_name", "artist_name"}
        }
        try:
            # One attempt: this is a fallback, so a failure must not add a wait.
            results = self._request_json(
                LRCLIB_SEARCH_URL, search, expect_list=True, attempts=1
            )
        except (LyricsApiUnavailableError, LyricsApiResponseRejectedError):
            return None
        wanted_title = _same_text(song_identity.title)
        wanted_artist = _same_text(song_identity.artist)
        wanted_album = _same_text(song_identity.album or "")
        best: tuple[tuple[int, float], Mapping[str, object]] | None = None
        for item in results:
            if not isinstance(item, dict) or item.get("instrumental"):
                continue
            if _same_text(str(item.get("trackName", ""))) != wanted_title:
                continue
            if _same_text(str(item.get("artistName", ""))) != wanted_artist:
                continue
            if not item.get("plainLyrics"):
                continue
            synced = bool(item.get("syncedLyrics"))
            if require_synced and not synced:
                continue
            delta = _duration_gap(item.get("duration"), duration_seconds)
            if delta is None:
                continue
            same_album = bool(wanted_album) and (
                _same_text(str(item.get("albumName", ""))) == wanted_album
            )
            limit = (
                SEARCH_DURATION_TOLERANCE_SECONDS
                if same_album
                else SAME_RECORDING_TOLERANCE_SECONDS
            )
            if delta > limit:
                continue
            rank = (0 if synced else 1, delta)  # timed lyrics first, then closest
            if best is None or rank < best[0]:
                best = (rank, item)
        return best[1] if best else None

    def _request_json(
        self,
        url: str,
        parameters: Mapping[str, str],
        *,
        expect_list: bool = False,
        attempts: int = MAX_ATTEMPTS,
    ):
        for attempt in range(attempts):
            try:
                return self._request_once(url, parameters, expect_list=expect_list)
            except _TemporaryFailure:
                if attempt == attempts - 1:
                    raise
                self._sleep(RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS) - 1)])
        raise AssertionError("unreachable")

    def _request_once(
        self,
        url: str,
        parameters: Mapping[str, str],
        *,
        expect_list: bool = False,
    ):
        request = Request(
            f"{url}?{urlencode(parameters)}",
            headers={"Accept": "application/json", "User-Agent": self._user_agent},
            method="GET",
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 404:
                raise LyricsApiUnavailableError(
                    "Lyrics provider found no matching recording."
                ) from error
            if error.code == 429:
                raise LyricsApiRateLimitedError(
                    _retry_after_seconds(error.headers)
                ) from error
            if 500 <= error.code < 600:
                raise _TemporaryFailure(
                    "Lyrics provider is temporarily unavailable."
                ) from error
            raise LyricsApiUnavailableError(
                "Lyrics provider request failed."
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            raise _TemporaryFailure(
                "Lyrics provider lookup is unavailable."
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LyricsApiResponseRejectedError(
                "Lyrics provider response is malformed."
            ) from error
        if not isinstance(payload, list if expect_list else dict):
            raise LyricsApiResponseRejectedError(
                "Lyrics provider response is malformed."
            )
        return payload


def _same_text(value: str) -> str:
    from analysis.lyrics.lyrics_api_reference import _identity_text

    return _identity_text(value)


def _duration_gap(provider_value: object, requested: float | None) -> float | None:
    try:
        provider = float(provider_value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if requested is None or requested <= 0 or provider <= 0:
        return None
    return abs(provider - requested)


def _map_response(payload: Mapping[str, object]) -> Mapping[str, object]:
    return {
        "provider_track_id": payload.get("id"),
        "title": payload.get("trackName"),
        "artist": payload.get("artistName"),
        "album": payload.get("albumName"),
        "version": None,
        "duration_seconds": payload.get("duration"),
        "instrumental": payload.get("instrumental", False),
        "plain_lyrics": payload.get("plainLyrics"),
        "synced_lyrics": payload.get("syncedLyrics"),
        "full_lyrics_storage_permitted": False,
    }


def _retry_after_seconds(headers: Message | Mapping[str, str] | None) -> float | None:
    if headers is None:
        return None
    value = headers.get("Retry-After")
    try:
        seconds = float(value) if value is not None else None
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
    return seconds if seconds is not None and seconds >= 0 else None
