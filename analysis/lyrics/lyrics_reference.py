from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class LyricsReferenceError(RuntimeError):
    """Base error for unavailable or invalid reference lyrics."""


class LyricsReferenceNotFoundError(LyricsReferenceError):
    pass


@dataclass(frozen=True)
class SongIdentity:
    title: str
    artist: str
    album: str | None = None
    version: str | None = None

    @property
    def song_id(self) -> str:
        parts = [self.artist, self.title]
        if self.version:
            parts.append(self.version)
        text = "-".join(parts).casefold()
        return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


class LyricsReferenceSource(Protocol):
    def get_lyrics(self, song_identity: SongIdentity) -> str: ...


class LocalLyricsReferenceSource:
    """Read ignored, user-supplied reference lyrics from local text files."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def get_lyrics(self, song_identity: SongIdentity) -> str:
        path = self._root / f"{song_identity.song_id}.txt"
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as error:
            raise LyricsReferenceNotFoundError(
                f"No local lyrics reference exists for {song_identity.song_id}."
            ) from error
        except OSError as error:
            raise LyricsReferenceError(
                f"The local lyrics reference for {song_identity.song_id} "
                "could not be read."
            ) from error
        if not text:
            raise LyricsReferenceError(
                f"The local lyrics reference for {song_identity.song_id} is empty."
            )
        return text
