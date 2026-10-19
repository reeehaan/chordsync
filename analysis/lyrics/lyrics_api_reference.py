from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Mapping, Protocol

from analysis.lyrics.lyrics_reference import SongIdentity


class IdentityConfidence(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class SongIdentitySource(str, Enum):
    EMBEDDED_METADATA = "embedded_metadata"
    IMPORTED_METADATA = "imported_metadata"
    EXPLICIT = "explicit"
    FILENAME = "filename"
    ACOUSTIC_IDENTIFICATION = "acoustic_identification"


@dataclass(frozen=True)
class SongIdentityCandidate:
    identity: SongIdentity
    source: SongIdentitySource
    duration_seconds: float | None = None

    @property
    def confidence(self) -> IdentityConfidence:
        if (
            not self.identity.title.strip()
            or not self.identity.artist.strip()
            or self.source == SongIdentitySource.FILENAME
        ):
            return IdentityConfidence.LOW
        has_supporting_metadata = bool(
            (self.duration_seconds is not None and self.duration_seconds > 0)
            or self.identity.album
            or self.identity.version
        )
        if has_supporting_metadata:
            return IdentityConfidence.HIGH
        return IdentityConfidence.MEDIUM


@dataclass(frozen=True)
class IdentityMatchEvidence:
    title_match: bool
    artist_match: bool
    album_match: bool | None
    version_match: bool | None
    duration_delta_seconds: float | None


@dataclass(frozen=True)
class LyricsReferenceResult:
    song_identity: SongIdentity
    provider: str
    provider_track_id: str
    plain_lyrics: str
    synced_lyrics: str | None
    identity_confidence: IdentityConfidence
    match_evidence: IdentityMatchEvidence
    full_lyrics_storage_permitted: bool


class LyricsApiTransport(Protocol):
    def fetch(
        self,
        song_identity: SongIdentity,
        *,
        duration_seconds: float | None,
        credential: str | None,
    ) -> Mapping[str, object]: ...


class LyricsApiReferenceError(RuntimeError):
    pass


class LyricsApiUnavailableError(LyricsApiReferenceError):
    pass


class LyricsApiResponseRejectedError(LyricsApiReferenceError):
    pass


class LyricsApiReferenceSource:
    """Validate an ephemeral provider response before verification may use it."""

    def __init__(
        self,
        transport: LyricsApiTransport,
        *,
        provider: str,
        identity_candidate: SongIdentityCandidate,
        credential_environment_variable: str | None = None,
        minimum_confidence: IdentityConfidence = IdentityConfidence.MEDIUM,
        duration_tolerance_seconds: float = 3.0,
        exact_album_duration_tolerance_seconds: float = 10.0,
    ) -> None:
        self._transport = transport
        self._provider = provider
        self._candidate = identity_candidate
        self._credential_environment_variable = credential_environment_variable
        self._minimum_confidence = minimum_confidence
        self._duration_tolerance_seconds = duration_tolerance_seconds
        self._exact_album_duration_tolerance_seconds = max(
            exact_album_duration_tolerance_seconds, duration_tolerance_seconds
        )

    def get_lyrics(self, song_identity: SongIdentity) -> str:
        return self.get_reference(song_identity).plain_lyrics

    def get_reference(self, song_identity: SongIdentity) -> LyricsReferenceResult:
        if song_identity != self._candidate.identity:
            raise LyricsApiResponseRejectedError("Song identity changed during lookup.")
        if self._candidate.confidence < self._minimum_confidence:
            raise LyricsApiResponseRejectedError(
                "Song identity confidence is too low for reference lookup."
            )
        credential = None
        if self._credential_environment_variable is not None:
            credential = os.getenv(self._credential_environment_variable)
            if not credential:
                raise LyricsApiUnavailableError(
                    "Lyrics provider credentials are not configured."
                )
        try:
            response = self._transport.fetch(
                song_identity,
                duration_seconds=self._candidate.duration_seconds,
                credential=credential,
            )
        except LyricsApiReferenceError:
            raise
        except Exception as error:
            raise LyricsApiUnavailableError(
                "Lyrics provider lookup is unavailable."
            ) from error
        if not isinstance(response, Mapping):
            raise LyricsApiResponseRejectedError(
                "Lyrics provider response is malformed."
            )
        return self._validate_response(response)

    def get_reference_or_none(
        self,
        song_identity: SongIdentity,
    ) -> LyricsReferenceResult | None:
        try:
            return self.get_reference(song_identity)
        except LyricsApiReferenceError:
            return None

    def _validate_response(
        self,
        response: Mapping[str, object],
    ) -> LyricsReferenceResult:
        if bool(response.get("instrumental")):
            raise LyricsApiResponseRejectedError(
                "Provider identified the track as instrumental."
            )
        provider_track_id = _optional_text(response.get("provider_track_id")) or ""
        title = str(response.get("title", "")).strip()
        artist = str(response.get("artist", "")).strip()
        album = _optional_text(response.get("album"))
        version = _optional_text(response.get("version"))
        plain_lyrics = _optional_text(response.get("plain_lyrics")) or ""
        synced_lyrics = _optional_text(response.get("synced_lyrics"))
        if not provider_track_id:
            raise LyricsApiResponseRejectedError("Provider track ID is missing.")
        if not plain_lyrics:
            raise LyricsApiResponseRejectedError("Provider lyrics are empty.")
        if _lyrics_are_malformed_or_duplicated(plain_lyrics):
            raise LyricsApiResponseRejectedError(
                "Provider lyrics are malformed or duplicated."
            )

        requested = self._candidate.identity
        title_match = _identity_text(title) == _identity_text(requested.title)
        artist_match = _identity_text(artist) == _identity_text(requested.artist)
        album_match = _optional_match(album, requested.album)
        version_match = _version_matches(
            requested_title=requested.title,
            requested_version=requested.version,
            provider_title=title,
            provider_version=version,
        )
        duration_delta = _duration_delta(
            response.get("duration_seconds"),
            self._candidate.duration_seconds,
        )
        if not title_match or not artist_match:
            raise LyricsApiResponseRejectedError(
                "Provider title or artist does not match the requested song."
            )
        if album_match is False or version_match is False:
            raise LyricsApiResponseRejectedError(
                "Provider album or version does not match the requested song."
            )
        if (
            duration_delta is not None
            and duration_delta > self._duration_tolerance_seconds
        ):
            # A different cut of the same release (another intro or fade) can
            # differ by several seconds. Accept it only when the album is named
            # and matches too; the identity is then still exact.
            if not (
                album_match is True
                and duration_delta <= self._exact_album_duration_tolerance_seconds
            ):
                raise LyricsApiResponseRejectedError(
                    "Provider duration does not match the requested recording."
                )

        strong_match = (
            duration_delta is not None
            and duration_delta <= self._duration_tolerance_seconds
        ) or album_match is True or version_match is True
        confidence = (
            IdentityConfidence.HIGH if strong_match else IdentityConfidence.MEDIUM
        )
        return LyricsReferenceResult(
            song_identity=SongIdentity(title, artist, album, version),
            provider=self._provider,
            provider_track_id=provider_track_id,
            plain_lyrics=plain_lyrics,
            synced_lyrics=synced_lyrics,
            identity_confidence=confidence,
            match_evidence=IdentityMatchEvidence(
                title_match=title_match,
                artist_match=artist_match,
                album_match=album_match,
                version_match=version_match,
                duration_delta_seconds=duration_delta,
            ),
            full_lyrics_storage_permitted=bool(
                response.get("full_lyrics_storage_permitted", False)
            ),
        )


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _identity_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _optional_match(provider: str | None, requested: str | None) -> bool | None:
    if requested is None:
        return None
    if provider is None:
        return False
    return _identity_text(provider) == _identity_text(requested)


_VERSION_MARKERS = frozenset(
    {"acoustic", "demo", "edit", "live", "mix", "remaster", "remastered", "version"}
)


def _version_words(title: str, version: str | None) -> frozenset[str]:
    text = f"{title} {version or ''}".casefold()
    words = set(re.findall(r"[a-z0-9]+", text))
    return frozenset(words & _VERSION_MARKERS)


def _version_matches(
    *,
    requested_title: str,
    requested_version: str | None,
    provider_title: str,
    provider_version: str | None,
) -> bool | None:
    requested = _version_words(requested_title, requested_version)
    provider = _version_words(provider_title, provider_version)
    if not requested and not provider:
        return None
    return requested == provider


def _duration_delta(
    provider_value: object,
    requested_value: float | None,
) -> float | None:
    if provider_value is None or requested_value is None:
        return None
    try:
        provider_duration = float(provider_value)
    except (TypeError, ValueError) as error:
        raise LyricsApiResponseRejectedError(
            "Provider duration is malformed."
        ) from error
    if provider_duration <= 0 or requested_value <= 0:
        raise LyricsApiResponseRejectedError("Song duration must be positive.")
    return abs(provider_duration - requested_value)


def _lyrics_are_malformed_or_duplicated(text: str) -> bool:
    if not any(character.isalpha() for character in text):
        return True
    lines = [" ".join(line.split()).casefold() for line in text.splitlines()]
    lines = [line for line in lines if line]
    midpoint = len(lines) // 2
    return bool(
        midpoint >= 2
        and len(lines) % 2 == 0
        and lines[:midpoint] == lines[midpoint:]
    )
