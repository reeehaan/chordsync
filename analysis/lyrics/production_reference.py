from __future__ import annotations

from pathlib import Path
from typing import Mapping

from analysis.lyrics.lrclib_transport import LrclibTransport
from analysis.lyrics.lyrics_api_reference import (
    LyricsApiReferenceSource,
    LyricsReferenceResult,
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
) -> LyricsReferenceResult | None:
    candidate = identity_candidate_from_metadata(get_audio_metadata(audio_path))
    source = LyricsApiReferenceSource(
        transport or LrclibTransport(),
        provider="lrclib-development",
        identity_candidate=candidate,
    )
    return source.get_reference_or_none(candidate.identity)


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
