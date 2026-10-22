from __future__ import annotations

from pathlib import Path
from typing import Mapping

from analysis.lyrics.filename_identity import identities_from_filename
from analysis.lyrics.lrclib_transport import LrclibTransport
from analysis.lyrics.lyrics_api_reference import (
    LyricsApiReferenceSource,
    LyricsReferenceResult,
    IdentityConfidence,
    SongIdentityCandidate,
    SongIdentitySource,
)
from analysis.lyrics.lyrics_reference import SongIdentity
from analysis.preprocessing.audio_preprocessor import get_audio_metadata


def identity_candidate_from_metadata(
    metadata: Mapping[str, object],
) -> SongIdentityCandidate:
    return SongIdentityCandidate(
        identity=SongIdentity(
            title=_text(metadata.get("title")) or "",
            artist=_text(metadata.get("artist")) or "",
            album=_text(metadata.get("album")),
            version=_text(metadata.get("version")),
        ),
        source=SongIdentitySource.EMBEDDED_METADATA,
        duration_seconds=_positive_float(metadata.get("duration")),
    )


def obtain_lrclib_reference(
    audio_path: Path,
    *,
    transport: LrclibTransport | None = None,
    source_title: str | None = None,
) -> LyricsReferenceResult | None:
    metadata = get_audio_metadata(audio_path)
    candidate = identity_candidate_from_metadata(metadata)
    transport = transport or LrclibTransport()
    if candidate.identity.title.strip() and candidate.identity.artist.strip():
        reference = LyricsApiReferenceSource(
            transport,
            provider="lrclib-development",
            identity_candidate=candidate,
        ).get_reference_or_none(candidate.identity)
        if reference is not None:
            return reference
    return _reference_from_filename(transport, metadata, source_title)


def _reference_from_filename(
    transport: LrclibTransport,
    metadata: Mapping[str, object],
    source_title: str | None,
) -> LyricsReferenceResult | None:
    """Try a title and artist guessed from the file name.

    Needs the recording's length: the provider's answer is only accepted when its
    title, artist and duration all agree, so a bad guess cannot attach wrong lyrics.
    """
    duration = _positive_float(metadata.get("duration"))
    if not source_title or duration is None:
        return None
    for title, artist in identities_from_filename(source_title):
        candidate = SongIdentityCandidate(
            identity=SongIdentity(title=title, artist=artist),
            source=SongIdentitySource.FILENAME,
            duration_seconds=duration,
        )
        reference = LyricsApiReferenceSource(
            transport,
            provider="lrclib-development",
            identity_candidate=candidate,
            minimum_confidence=IdentityConfidence.LOW,
        ).get_reference_or_none(candidate.identity)
        if reference is not None:
            return reference
    return None


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
