"""Turn a saved song name into a title and, when there is one, an artist.

Saved names come from file names: "Tum Hi Ho - Arijit Singh - Spotimate.app",
"Wonderwall - Oasis", "Duvet", "Michael Jackson- Heal the World(Lyrics)". The
downloader writes brackets and quotes as underscores
("Love Me Not _feat. Rex Orange County_"), which are cut off here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SOURCE_SUFFIX = re.compile(r"\s*[-–]\s*spotimate\.app(?:\s*\d*)?\s*$", re.IGNORECASE)
_LYRICS_TAG = re.compile(r"\s*[\(\[]\s*(?:official\s+)?(?:lyrics?|lyric video|audio|video)\s*[\)\]]\s*", re.IGNORECASE)
_SEPARATOR = re.compile(r"\s+[-–]\s+|(?<=[A-Za-z0-9\)])[-–]\s+")
# Parts that are not part of a title or artist: "Take 1", "Live", "Remastered 2009".
_NOISE_PART = re.compile(
    r"^(?:take\s*\d+|live|remaster(?:ed)?(?:\s*\d{4})?|acoustic|demo|version)$", re.IGNORECASE
)


@dataclass(frozen=True)
class ParsedSong:
    title: str
    artist: str | None

    @property
    def key(self) -> str:
        """The same song written two ways ("Mata Rawana", "Mata Rawana - La Signore")
        has one key: the title, in a plain comparable form."""
        return normalize(self.title)


def normalize(text: str) -> str:
    """Lower case, no accents, no punctuation, single spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^0-9a-z]+", " ", text.casefold())
    return " ".join(text.split())


def _clean_part(part: str) -> str:
    # Cut at the first underscore: what follows is a bracketed note.
    part = part.split("_", 1)[0]
    return " ".join(part.split()).strip(" -–")


def parse_song_name(raw: str) -> ParsedSong:
    name = _SOURCE_SUFFIX.sub("", raw.strip())
    artist_first = bool(_LYRICS_TAG.search(name))  # YouTube style: "Artist - Title (Lyrics)"
    name = _LYRICS_TAG.sub(" ", name)
    parts = [_clean_part(p) for p in _SEPARATOR.split(name)]
    parts = [p for p in parts if p and not _NOISE_PART.match(p)]
    if not parts:
        return ParsedSong(title=" ".join(raw.split()) or raw, artist=None)
    if len(parts) == 1:
        return ParsedSong(title=parts[0], artist=None)
    if artist_first:
        return ParsedSong(title=" - ".join(parts[1:]), artist=parts[0])
    return ParsedSong(title=" - ".join(parts[:-1]), artist=parts[-1])
