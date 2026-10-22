"""Guess a song's title and artist from a messy download file name.

Used only when the audio file has no usable title and artist tags. The guesses are
looked up and then checked against the provider's answer (exact title and artist,
and a matching duration), so a wrong guess is rejected, not trusted.
"""

from __future__ import annotations

import re
from pathlib import PurePath

# Words that sit in a file name but are not part of the song.
_SITE_NAMES = re.compile(
    r"\b(spotimate|spotifydown|spotdl|y2mate|ytmp3|mp3juices|savefrom|"
    r"spotify|youtube|www)\b(\.\w+)?",
    re.IGNORECASE,
)
_BRACKETED = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_UNDERSCORE_GROUP = re.compile(r"_([^_]*)_")
_NOISE_WORDS = re.compile(
    r"\b(official|lyrics?|lyric video|music video|audio|video|hd|hq|4k|"
    r"full song|mp3|free download)\b",
    re.IGNORECASE,
)
_FEATURING = re.compile(r"\b(feat|ft|featuring)\b\.?.*$", re.IGNORECASE)
_AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus", ".mp4"}


def identities_from_filename(name: str) -> list[tuple[str, str]]:
    """Return (title, artist) guesses, most likely first. Empty when none."""
    text = _strip_suffix(name)
    text = _SITE_NAMES.sub(" ", text)
    text = _BRACKETED.sub(" ", text)
    # Downloaders swap brackets and "&" for underscores: "_feat. X_", "A _ B".
    text = _UNDERSCORE_GROUP.sub(lambda m: " ", text) if _has_feat(text) else text
    text = text.replace("_", " ")
    text = _NOISE_WORDS.sub(" ", text)

    parts = [_tidy(part) for part in re.split(r"\s+[-–—]\s+", text)]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return []
    first, second = parts[0], parts[1]
    guesses = [(first, second), (second, first)]  # "Title - Artist", then reverse
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for title, artist in guesses:
        title = _FEATURING.sub("", title).strip()
        artist = _FEATURING.sub("", artist).strip()
        if title and artist and (title, artist) not in seen:
            seen.add((title, artist))
            result.append((title, artist))
    return result


def _has_feat(text: str) -> bool:
    return bool(re.search(r"_\s*(feat|ft|featuring)\b", text, re.IGNORECASE))


def _strip_suffix(name: str) -> str:
    path = PurePath(name)
    return path.stem if path.suffix.casefold() in _AUDIO_SUFFIXES else name


def _tidy(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -_.,")
