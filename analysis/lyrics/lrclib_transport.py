from __future__ import annotations

import json
import socket
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
DEFAULT_USER_AGENT = (
    "ChordSync/0.1 (academic development; contact: developer@localhost)"
)
DEFAULT_TIMEOUT_SECONDS = 10.0


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
    ) -> None:
        if not user_agent.strip():
            raise ValueError("LRCLIB User-Agent must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("LRCLIB timeout must be positive.")
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._opener = opener

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
        request = Request(
            f"{LRCLIB_GET_URL}?{urlencode(parameters)}",
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
                raise LyricsApiUnavailableError(
                    "Lyrics provider is temporarily unavailable."
                ) from error
            raise LyricsApiUnavailableError(
                "Lyrics provider request failed."
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            raise LyricsApiUnavailableError(
                "Lyrics provider lookup is unavailable."
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LyricsApiResponseRejectedError(
                "Lyrics provider response is malformed."
            ) from error
        if not isinstance(payload, dict):
            raise LyricsApiResponseRejectedError(
                "Lyrics provider response is malformed."
            )
        return _map_response(payload)


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
