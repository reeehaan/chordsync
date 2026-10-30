"""What is published for a phone to play, kept apart from how it is made.

The API package never runs media tools; the worker supplies an encoder that
turns the upload into a smaller MP3 (see analysis/preprocessing). This default
publishes the uploaded file as it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlaybackAudio:
    content: bytes
    extension: str
    content_type: str


_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}


def original_playback(path: Path, content: bytes) -> PlaybackAudio:
    extension = path.suffix.casefold()
    return PlaybackAudio(content, extension, _CONTENT_TYPES[extension])
