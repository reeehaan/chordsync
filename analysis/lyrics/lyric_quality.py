"""Decide whether a transcript of a non-English song is trustworthy.

For some languages (Sinhala, with Whisper's small model) the transcript is not just
imperfect but unusable: the wrong script, one word repeated dozens of times, or a
single "word" lasting twenty seconds. Showing that is worse than showing nothing,
so such lyrics are dropped and the song is published with its chords only.
"""

from __future__ import annotations

import collections
import unicodedata
from typing import Any

_MINIMUM_WORDS = 12
_MIXED_SCRIPT_SHARE = 0.15
_REPEATED_WORD_SHARE = 0.15
_REPEATED_WORD_MINIMUM = 15
# Real songs repeat a lot (a good English song scores 0.34), so only extreme loops.
_LOW_VARIETY = 0.18
_LOW_VARIETY_MINIMUM_WORDS = 60
_LONG_LINE_SECONDS = 8.0
_LONG_LINE_MAX_WORDS = 2


def unreliable_reason(transcript: dict[str, Any]) -> str | None:
    """Why the transcript cannot be trusted, or None if it looks usable."""
    segments = [s for s in transcript.get("segments", []) if isinstance(s, dict)]
    words = [
        str(word.get("word", "")).strip()
        for segment in segments
        for word in segment.get("words", []) or []
        if isinstance(word, dict)
    ]
    words = [word for word in words if word]
    if len(words) < _MINIMUM_WORDS:
        return None

    scripts = collections.Counter(
        _script(character) for word in words for character in word if character.isalpha()
    )
    letters = sum(scripts.values())
    significant = [name for name, count in scripts.items() if count / letters >= _MIXED_SCRIPT_SHARE]
    if len(significant) >= 2:
        return "mixed scripts: " + ", ".join(sorted(significant))

    counts = collections.Counter(word.casefold() for word in words)
    word, times = counts.most_common(1)[0]
    if times >= _REPEATED_WORD_MINIMUM and times / len(words) >= _REPEATED_WORD_SHARE:
        return f"one word repeated {times} times"

    if len(words) >= _LOW_VARIETY_MINIMUM_WORDS and len(counts) / len(words) < _LOW_VARIETY:
        return "very little variety in the words"

    long_lines = [
        segment
        for segment in segments
        if len(segment.get("words", []) or []) <= _LONG_LINE_MAX_WORDS
        and float(segment.get("end", 0)) - float(segment.get("start", 0)) >= _LONG_LINE_SECONDS
    ]
    if len(long_lines) >= 2:
        return "several long lines with only one or two words"
    return None


def _script(character: str) -> str:
    name = unicodedata.name(character, "")
    return name.split(" ")[0] if name else "OTHER"


def without_lyrics(transcript: dict[str, Any]) -> dict[str, Any]:
    """The same transcript with no lyrics, marked so fusion publishes none."""
    return {
        "segments": [],
        "word_segments": [],
        "language": "unreliable",
        "original_language": transcript.get("language"),
    }
