"""Decide which lyrics to publish: the transcript, the reference, or none.

After WhisperX transcribes the vocals, the transcript is compared word by word with
the LRCLIB reference. A few wrong words are fixed elsewhere and the transcript is
kept. This module handles the other cases:

* the transcript disagrees with the reference on many words -> use the reference
  (only when it has timed lines, otherwise there is nothing to follow);
* there is no reference and the speech recogniser itself was unsure -> no lyrics.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

# Songs in the project's own logs: good transcripts scored 0.14 to 0.22, a bad one
# scored 0.74. Between 0.22 and 0.74 the transcript is half right at best.
WER_USE_REFERENCE = 0.35
# Too few compared words and the error rate means little.
MINIMUM_COMPARED_WORDS = 30
# Mean WhisperX word score below which, with no reference to check against, the
# transcript is not trusted. A starting value: the score is logged for every song.
MINIMUM_MEAN_WORD_SCORE = 0.45
MINIMUM_SCORED_WORDS = 20


class LyricsPath(str, enum.Enum):
    TRANSCRIPT = "transcript"
    REFERENCE = "reference"
    NONE = "none"


@dataclass(frozen=True)
class LyricsDecision:
    path: LyricsPath
    reason: str


def decide_with_reference(
    *,
    error_rate: float,
    compared_words: int,
    reference_is_timed: bool,
) -> LyricsDecision:
    """Pick the lyrics when a reference was found and compared."""
    if compared_words < MINIMUM_COMPARED_WORDS or error_rate <= WER_USE_REFERENCE:
        return LyricsDecision(LyricsPath.TRANSCRIPT, "transcript agrees with reference")
    if reference_is_timed:
        return LyricsDecision(
            LyricsPath.REFERENCE,
            f"transcript differs from the reference (error rate {error_rate:.2f})",
        )
    return LyricsDecision(
        LyricsPath.NONE,
        f"transcript differs from the reference (error rate {error_rate:.2f}) "
        "and the reference has no timing",
    )


def mean_word_score(transcript: dict[str, Any]) -> tuple[float | None, int]:
    """Average WhisperX word confidence and how many words carried one."""
    scores = [
        float(word["score"])
        for segment in transcript.get("segments", [])
        if isinstance(segment, dict)
        for word in segment.get("words", []) or []
        if isinstance(word, dict) and isinstance(word.get("score"), (int, float))
    ]
    if not scores:
        return None, 0
    return sum(scores) / len(scores), len(scores)


def low_confidence_reason(transcript: dict[str, Any]) -> str | None:
    """Why a transcript with no reference to check it is not trusted, if so."""
    mean, count = mean_word_score(transcript)
    if mean is None or count < MINIMUM_SCORED_WORDS:
        return None
    if mean < MINIMUM_MEAN_WORD_SCORE:
        return f"speech recognition was unsure (mean word score {mean:.2f})"
    return None


def non_english_without_timed_lyrics_reason(
    transcript: dict[str, Any],
    *,
    reference_plain_lyrics: str | None,
) -> str | None:
    """Why a non-English song gets no lyrics, or None when it may keep the transcript.

    Speech recognition cannot be trusted on a song that is not in English: it
    labels Sinhala as Hindi or Korean and writes invented words. For those songs
    the lyrics come only from the reference with timed lines, and this runs after
    that was tried, so any transcript still here has no timed reference behind it.
    English songs are left to the vocabulary and agreement checks.
    """
    from analysis.lyrics.language_hint import looks_english

    language = str(transcript.get("language", "")).casefold()
    if language in {"synced", "unreliable"}:
        return None
    if reference_plain_lyrics is not None:
        if language == "en" or looks_english(reference_plain_lyrics):
            return None
        return "non-English song and the reference has no timed lyrics"
    text = " ".join(
        str(segment.get("text", ""))
        for segment in transcript.get("segments", [])
        if isinstance(segment, dict)
    )
    # The words' script says more than the label does: text written in Hangul,
    # Devanagari or Sinhala letters is not English whatever it was labelled.
    if _mostly_non_latin(text):
        return (
            f"non-English song (written in {_dominant_script(text)}, labelled "
            f"{language or 'unknown'}) with no lyrics reference"
        )
    if language == "en" or looks_english(text):
        return None  # an English song, or one the recogniser labelled otherwise
    return f"non-English song (detected {language or 'unknown'}) with no lyrics reference"


def _letters(text: str) -> list[str]:
    return [character for character in text if character.isalpha()]


def _mostly_non_latin(text: str) -> bool:
    letters = _letters(text)
    if len(letters) < 10:
        return False
    outside = sum(1 for character in letters if ord(character) > 0x024F)
    return outside / len(letters) >= 0.5


def _dominant_script(text: str) -> str:
    import collections
    import unicodedata

    counts = collections.Counter(
        unicodedata.name(character, "UNKNOWN").split()[0].title()
        for character in _letters(text)
        if ord(character) > 0x024F
    )
    return counts.most_common(1)[0][0] if counts else "another script"
