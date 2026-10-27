"""Map free-text tags ("alternative rock", "bollywood", "sinhala pop") onto the
fixed genre list."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from analysis.genre.genres import GENRES

# Specific phrases first. A matched phrase is removed from the tag, so "k-pop"
# gives K-Pop and not also Pop, and "hip hop" does not leave a stray "hop".
_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"sinhala|sinhalese|sri ?lanka(n)?", ("Sinhala",)),
    (r"bollywood|filmi|hindi|indian|punjabi", ("Bollywood",)),
    (r"k-?pop|korean pop", ("K-Pop",)),
    (r"hip[ -]?hop|rap\b|trap", ("Hip-Hop",)),
    (r"rhythm and blues|r&b|r ?n ?b|neo[ -]?soul", ("R&B",)),
    (r"heavy metal|metal(core)?|grindcore", ("Metal",)),
    (r"punk|hardcore", ("Punk",)),
    (r"singer[- ]songwriter|folk|bluegrass|acoustic", ("Folk",)),
    (r"country", ("Country",)),
    (r"blues", ("Blues",)),
    (r"jazz|bossa nova|swing", ("Jazz",)),
    (r"classical|orchestral|opera|baroque|symphon\w*|instrumental score", ("Classical",)),
    (r"reggae|ska\b|dub\b", ("Reggae",)),
    (r"soul|motown|funk", ("Soul",)),
    (r"electro\w*|edm|house|techno|trance|synth\w*|dance|ambient|downtempo|idm", ("Electronic",)),
    (r"latin|salsa|reggaeton|bachata|cumbia|samba|flamenco", ("Latin",)),
    (r"gospel|christian|worship|spiritual", ("Gospel",)),
    (r"britpop|post[- ]rock|alternative|indie", ("Indie",)),
    (r"rock\b|rock ?and ?roll|grunge|shoegaze", ("Rock",)),
    (r"j-?pop|city pop|pop\b|synth-?pop|dream pop|ballad|easy listening", ("Pop",)),
)
_COMPILED = tuple((re.compile(pattern), genres) for pattern, genres in _PATTERNS)

# "alternative rock" and "britpop" are both Rock and Indie to a listener.
_ALSO = {"britpop": ("Rock",), "alternative rock": ("Rock",), "indie rock": ("Rock",)}

MAX_GENRES = 3
# On a tie, a regional genre is the more telling one ("sinhala pop" is Sinhala first).
_REGIONAL = ("Sinhala", "Bollywood", "K-Pop")
# A genre must have at least this share of the strongest genre's votes.
MIN_SHARE = 0.25


def genres_for_tag(tag: str) -> list[str]:
    """Every ChordSync genre a single tag points at (empty for "seen live")."""
    text = tag.casefold().strip()
    found: list[str] = []
    for phrase, extra in _ALSO.items():
        if phrase in text:
            found.extend(extra)
    for pattern, genres in _COMPILED:
        if pattern.search(text):
            found.extend(genres)
            text = pattern.sub(" ", text)
    return list(dict.fromkeys(found))


def map_tags(tags: Iterable[tuple[str, int]]) -> list[str]:
    """The best genres for weighted tags ``(name, votes)``: strongest first, at
    most three, and never a genre far weaker than the best one."""
    score: dict[str, float] = defaultdict(float)
    for name, votes in tags:
        weight = max(float(votes), 1.0)
        for genre in genres_for_tag(name):
            score[genre] += weight
    if not score:
        return []
    best = max(score.values())
    ranked = sorted(score.items(), key=lambda item: (-item[1], item[0] not in _REGIONAL, GENRES.index(item[0])))
    return [genre for genre, value in ranked if value >= best * MIN_SHARE][:MAX_GENRES]
