import json
import socket
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from analysis.lyrics.lrclib_transport import LyricsApiRateLimitedError, LrclibTransport
from analysis.lyrics.lyrics_api_reference import (
    IdentityConfidence,
    LyricsApiReferenceSource,
    LyricsApiResponseRejectedError,
    SongIdentityCandidate,
    SongIdentitySource,
)
from analysis.lyrics.lyrics_reference import SongIdentity
from analysis.lyrics.production_reference import identity_candidate_from_metadata


IDENTITY = SongIdentity("Tagged Song", "Tagged Artist", "Tagged Album")
LYRIC_MARKER = "private provider lyric marker"


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self._body


def _payload(**updates):
    payload = {
        "id": 42,
        "trackName": "Tagged Song",
        "artistName": "Tagged Artist",
        "albumName": "Tagged Album",
        "duration": 120.5,
        "instrumental": False,
        "plainLyrics": LYRIC_MARKER,
        "syncedLyrics": None,
    }
    payload.update(updates)
    return payload


def _source(opener):
    candidate = SongIdentityCandidate(
        IDENTITY,
        SongIdentitySource.EMBEDDED_METADATA,
        duration_seconds=120.0,
    )
    return LyricsApiReferenceSource(
        LrclibTransport(
            user_agent="ChordSync-tests/1.0 (contact: test@example.invalid)",
            timeout_seconds=3,
            opener=opener,
        ),
        provider="lrclib-development",
        identity_candidate=candidate,
    )


def test_identity_mapping_high_medium_and_low():
    high = identity_candidate_from_metadata(
        {"title": "Tagged Song", "artist": "Tagged Artist", "album": "Tagged Album", "duration": 120}
    )
    medium = identity_candidate_from_metadata(
        {"title": "Tagged Song", "artist": "Tagged Artist"}
    )
    high_from_album = identity_candidate_from_metadata(
        {"title": "Tagged Song", "artist": "Tagged Artist", "album": "Album"}
    )
    low = identity_candidate_from_metadata(
        {"title": "Tagged Song", "artist": None, "duration": 120}
    )

    assert high.confidence is IdentityConfidence.HIGH
    assert high_from_album.confidence is IdentityConfidence.HIGH
    assert medium.confidence is IdentityConfidence.MEDIUM
    assert low.confidence is IdentityConfidence.LOW
    assert low.identity.artist == ""


def test_successful_lrclib_request_uses_identity_and_user_agent():
    observed = {}

    def opener(request, *, timeout):
        observed["request"] = request
        observed["timeout"] = timeout
        return FakeResponse(_payload())

    result = _source(opener).get_reference(IDENTITY)
    query = parse_qs(urlparse(observed["request"].full_url).query)

    assert query == {
        "track_name": ["Tagged Song"],
        "artist_name": ["Tagged Artist"],
        "album_name": ["Tagged Album"],
        "duration": ["120.0"],
    }
    assert observed["request"].get_header("User-agent").startswith("ChordSync-tests")
    assert observed["timeout"] == 3
    assert result.plain_lyrics == LYRIC_MARKER
    assert result.full_lyrics_storage_permitted is False


def _http_error(code, *, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("https://lrclib.net/api/get", code, "error", headers, BytesIO())


@pytest.mark.parametrize("code", [404, 500, 503])
def test_no_match_or_server_failure_is_unavailable(code):
    def opener(request, *, timeout):
        raise _http_error(code)

    assert _source(opener).get_reference_or_none(IDENTITY) is None


def test_rate_limit_retains_retry_after_without_retrying():
    calls = 0

    def opener(request, *, timeout):
        nonlocal calls
        calls += 1
        raise _http_error(429, retry_after="12")

    with pytest.raises(LyricsApiRateLimitedError) as captured:
        _source(opener).get_reference(IDENTITY)
    assert captured.value.retry_after_seconds == 12
    assert calls == 1


def test_rate_limit_parses_http_date_retry_after():
    def opener(request, *, timeout):
        raise _http_error(429, retry_after="Fri, 01 Jan 2099 00:00:00 GMT")

    with pytest.raises(LyricsApiRateLimitedError) as captured:
        _source(opener).get_reference(IDENTITY)

    assert captured.value.retry_after_seconds is not None
    assert captured.value.retry_after_seconds > 0


def test_timeout_falls_back():
    def opener(request, *, timeout):
        raise socket.timeout()

    assert _source(opener).get_reference_or_none(IDENTITY) is None


def test_malformed_json_is_rejected():
    class MalformedResponse(FakeResponse):
        def read(self):
            return b"not-json"

    with pytest.raises(LyricsApiResponseRejectedError):
        _source(lambda request, timeout: MalformedResponse({})).get_reference(IDENTITY)


@pytest.mark.parametrize(
    "updates",
    [
        {"instrumental": True, "plainLyrics": None},
        {"plainLyrics": None},
        {"trackName": "Other Song"},
        {"artistName": "Other Artist"},
        {"duration": 140},
    ],
)
def test_provider_validation_rejects_unsafe_match(updates):
    with pytest.raises(LyricsApiResponseRejectedError):
        _source(lambda request, timeout: FakeResponse(_payload(**updates))).get_reference(IDENTITY)


def test_transport_never_logs_provider_payload(caplog):
    result = _source(lambda request, timeout: FakeResponse(_payload())).get_reference(IDENTITY)

    assert result.plain_lyrics == LYRIC_MARKER
    assert LYRIC_MARKER not in caplog.text
