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


# --- a different cut of the same release ----------------------------------------


def _routing_opener(get_result, search_results):
    """Answer /api/get with `get_result` (an HTTPError is raised) and /api/search."""
    calls = []

    def opener(request, *, timeout):
        calls.append(request.full_url)
        if "/api/search" in request.full_url:
            return FakeResponse(search_results)
        if isinstance(get_result, Exception):
            raise get_result
        return FakeResponse(get_result)

    opener.calls = calls
    return opener


def test_exact_miss_falls_back_to_the_closest_search_result():
    opener = _routing_opener(
        _http_error(404),
        [
            _payload(id=1, duration=131.0),
            _payload(id=2, duration=124.0),  # closest to the 120 s file
            _payload(id=3, artistName="Someone Else", duration=120.0),
        ],
    )

    result = _source(opener).get_reference(IDENTITY)

    assert result.provider_track_id == "2"
    assert any("/api/search" in url for url in opener.calls)
    assert result.match_evidence.duration_delta_seconds == pytest.approx(4.0)


def test_a_server_error_on_the_exact_lookup_also_tries_search():
    opener = _routing_opener(_http_error(503), [_payload(duration=121.0)])

    assert _source(opener).get_reference(IDENTITY).provider_track_id == "42"


def test_rate_limiting_never_triggers_a_second_request():
    opener = _routing_opener(_http_error(429), [_payload()])

    with pytest.raises(LyricsApiRateLimitedError):
        _source(opener).get_reference(IDENTITY)

    assert not any("/api/search" in url for url in opener.calls)


def test_search_results_for_other_songs_or_far_durations_are_ignored():
    opener = _routing_opener(
        _http_error(404),
        [
            _payload(id=1, trackName="Different Song", duration=120.0),
            _payload(id=2, duration=140.0),  # too far from 120 s
            _payload(id=3, plainLyrics=""),
            _payload(id=4, instrumental=True),
        ],
    )

    assert _source(opener).get_reference_or_none(IDENTITY) is None


def test_the_album_must_match_to_accept_a_duration_off_by_several_seconds():
    far = _payload(duration=127.0)  # 7 s away: beyond the 3 s strict limit
    assert _source(lambda r, *, timeout: FakeResponse(far)).get_reference(
        IDENTITY
    ).identity_confidence is IdentityConfidence.HIGH

    other_album = _payload(duration=127.0, albumName="Another Album")
    with pytest.raises(LyricsApiResponseRejectedError):
        _source(lambda r, *, timeout: FakeResponse(other_album)).get_reference(
            IDENTITY
        )

    no_album_candidate = SongIdentityCandidate(
        SongIdentity("Tagged Song", "Tagged Artist"),
        SongIdentitySource.EMBEDDED_METADATA,
        duration_seconds=120.0,
    )
    source = LyricsApiReferenceSource(
        LrclibTransport(opener=lambda r, *, timeout: FakeResponse(far)),
        provider="lrclib-development",
        identity_candidate=no_album_candidate,
    )
    with pytest.raises(LyricsApiResponseRejectedError):
        source.get_reference(SongIdentity("Tagged Song", "Tagged Artist"))


def test_a_duration_beyond_ten_seconds_is_rejected_even_with_the_album():
    far = _payload(duration=135.0)

    with pytest.raises(LyricsApiResponseRejectedError):
        _source(lambda r, *, timeout: FakeResponse(far)).get_reference(IDENTITY)
