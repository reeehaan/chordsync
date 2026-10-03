from dataclasses import replace

import pytest

from analysis.lyrics.forced_alignment import select_forced_alignment_context
from analysis.lyrics.lyrics_api_reference import (
    IdentityConfidence,
    LyricsApiReferenceSource,
    LyricsApiResponseRejectedError,
    SongIdentityCandidate,
    SongIdentitySource,
)
from analysis.lyrics.lyrics_reference import SongIdentity
from analysis.lyrics.lyrics_verification import (
    TimedAsrWord,
    VerificationState,
    align_words,
    classify_alignment,
    tokenize_reference,
)


IDENTITY = SongIdentity(
    title="Paper Moons",
    artist="Example Ensemble",
    album="Synthetic Sessions",
)


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.response = response or _response()
        self.error = error
        self.calls = []

    def fetch(self, song_identity, *, duration_seconds, credential):
        self.calls.append((song_identity, duration_seconds, credential))
        if self.error:
            raise self.error
        return self.response


def _response(**updates):
    response = {
        "provider_track_id": "synthetic-42",
        "title": "Paper Moons",
        "artist": "Example Ensemble",
        "album": "Synthetic Sessions",
        "version": None,
        "duration_seconds": 120.5,
        "instrumental": False,
        "plain_lyrics": "silver birds cross quiet skies",
        "synced_lyrics": None,
        "full_lyrics_storage_permitted": False,
    }
    response.update(updates)
    return response


def _source(transport, *, candidate=None, credential_environment_variable=None):
    return LyricsApiReferenceSource(
        transport,
        provider="synthetic-provider",
        identity_candidate=candidate
        or SongIdentityCandidate(
            IDENTITY,
            SongIdentitySource.EMBEDDED_METADATA,
            duration_seconds=120.0,
        ),
        credential_environment_variable=credential_environment_variable,
    )


def test_trusted_identity_returns_validated_reference_result():
    transport = FakeTransport()

    result = _source(transport).get_reference(IDENTITY)

    assert result.provider == "synthetic-provider"
    assert result.provider_track_id == "synthetic-42"
    assert result.identity_confidence is IdentityConfidence.HIGH
    assert result.match_evidence.title_match is True
    assert result.match_evidence.artist_match is True
    assert result.match_evidence.duration_delta_seconds == pytest.approx(0.5)
    assert result.full_lyrics_storage_permitted is False


def test_low_confidence_filename_identity_falls_back_without_api_call():
    transport = FakeTransport()
    candidate = SongIdentityCandidate(
        IDENTITY,
        SongIdentitySource.FILENAME,
        duration_seconds=120.0,
    )

    assert _source(transport, candidate=candidate).get_reference_or_none(IDENTITY) is None
    assert transport.calls == []


def test_api_unavailable_falls_back_to_whisperx_only():
    source = _source(FakeTransport(error=TimeoutError("offline")))

    assert source.get_reference_or_none(IDENTITY) is None


@pytest.mark.parametrize(
    "response",
    [
        _response(title="Different Song"),
        _response(artist="Different Artist"),
        _response(plain_lyrics=""),
        _response(plain_lyrics="---"),
        _response(
            plain_lyrics="silver birds\ncross skies\nsilver birds\ncross skies"
        ),
    ],
)
def test_invalid_provider_response_is_rejected(response):
    with pytest.raises(LyricsApiResponseRejectedError):
        _source(FakeTransport(response)).get_reference(IDENTITY)


def test_version_mismatch_is_rejected():
    identity = replace(IDENTITY, version="Acoustic Version")
    candidate = SongIdentityCandidate(
        identity,
        SongIdentitySource.EXPLICIT,
        duration_seconds=120.0,
    )

    with pytest.raises(LyricsApiResponseRejectedError, match="version"):
        _source(
            FakeTransport(_response(version="Live Version")),
            candidate=candidate,
        ).get_reference(identity)


@pytest.mark.parametrize(
    "response",
    [
        _response(instrumental=True, plain_lyrics=""),
        _response(duration_seconds=140.0),
    ],
)
def test_instrumental_or_wrong_duration_response_is_rejected(response):
    with pytest.raises(LyricsApiResponseRejectedError):
        _source(FakeTransport(response)).get_reference(IDENTITY)


def test_no_credentials_falls_back_without_transport_call(monkeypatch):
    monkeypatch.delenv("SYNTHETIC_LYRICS_API_KEY", raising=False)
    transport = FakeTransport()
    source = _source(
        transport,
        credential_environment_variable="SYNTHETIC_LYRICS_API_KEY",
    )

    assert source.get_reference_or_none(IDENTITY) is None
    assert transport.calls == []


def _alignment(reference_text, asr_words):
    timed = [
        TimedAsrWord(word, index * 0.5, index * 0.5 + 0.4)
        for index, word in enumerate(asr_words)
    ]
    aligned = align_words(timed, tokenize_reference(reference_text))
    return aligned, classify_alignment(aligned)


def test_automatic_context_selection_uses_nearest_stable_matches():
    aligned, verified = _alignment(
        "silver birds cross quiet skies",
        ["silver", "birds", "crest", "quiet", "skies"],
    )

    context = select_forced_alignment_context(aligned, verified, 2)

    assert context is not None
    assert context.candidate_offset == 2
    assert context.segment.start == 0.0
    assert context.segment.end == 2.4
    assert context.segment.text == "silver birds cross quiet skies"


def test_repeated_section_ambiguity_refuses_context():
    aligned, verified = _alignment(
        "silver birds cross quiet skies silver birds cross quiet skies",
        [
            "silver",
            "birds",
            "crest",
            "quiet",
            "skies",
            "silver",
            "birds",
            "cross",
            "quiet",
            "skies",
        ],
    )
    verified[2] = replace(
        verified[2],
        verification=VerificationState.VERIFIED_REFERENCE,
    )

    assert select_forced_alignment_context(aligned, verified, 2) is None


def test_unsafe_mismatch_block_refuses_context():
    aligned, verified = _alignment(
        "silver birds cross quiet skies",
        ["silver", "birds", "turn", "softly", "skies"],
    )

    assert select_forced_alignment_context(aligned, verified, 2) is None
