"""Cut Whisper repetition loops out of a WhisperX transcript.

On hard passages Whisper can get stuck repeating one phrase for the rest of a
segment (one cloud run produced 192 words with 12 distinct ones, the same
four-word phrase 30 times). Real lyrics repeat too, so only long, uninterrupted
runs count as loops, and the first few repeats are always kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

# Consecutive repeats needed before a run is treated as a loop.
_MIN_REPEATS_SINGLE_WORD = 10
_MIN_REPEATS_PHRASE = 6
_LONGEST_PHRASE_WORDS = 8
# How many repeats of a looping phrase are kept.
_KEPT_REPEATS = 3

_TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class RepetitionReport:
    removed_words: int
    loops: int


def remove_repetition_loops(transcript: dict[str, Any]) -> RepetitionReport:
    """Remove loop repeats from a WhisperX JSON payload, in place."""
    segments = transcript.get("segments")
    if not isinstance(segments, list):
        return RepetitionReport(0, 0)

    removed: list[dict[str, Any]] = []
    loops = 0
    kept_segments: list[Any] = []
    for segment in segments:
        words = segment.get("words") if isinstance(segment, dict) else None
        if not isinstance(words, list) or not words:
            kept_segments.append(segment)
            continue
        keep_flags, segment_loops = _loop_mask([_token(word) for word in words])
        loops += segment_loops
        if all(keep_flags):
            kept_segments.append(segment)
            continue
        removed.extend(word for word, keep in zip(words, keep_flags) if not keep)
        kept = [word for word, keep in zip(words, keep_flags) if keep]
        if kept:
            segment["words"] = kept
            segment["text"] = " " + " ".join(str(word.get("word", "")) for word in kept)
            _refit_times(segment, kept)
            kept_segments.append(segment)

    if removed:
        transcript["segments"] = kept_segments
        flat = transcript.get("word_segments")
        if isinstance(flat, list):
            gone = {_identity(word) for word in removed}
            transcript["word_segments"] = [
                word for word in flat if _identity(word) not in gone
            ]
    return RepetitionReport(len(removed), loops)


def _token(word: Any) -> str:
    text = str(word.get("word", "")) if isinstance(word, dict) else ""
    return " ".join(_TOKEN.findall(text.casefold()))


def _loop_mask(tokens: Sequence[str]) -> tuple[list[bool], int]:
    keep = [True] * len(tokens)
    loops = 0
    index = 0
    while index < len(tokens):
        best_size, best_repeats = 0, 0
        for size in range(1, _LONGEST_PHRASE_WORDS + 1):
            repeats = _repeats(tokens, index, size)
            needed = _MIN_REPEATS_SINGLE_WORD if size == 1 else _MIN_REPEATS_PHRASE
            if repeats >= needed and repeats * size > best_repeats * best_size:
                best_size, best_repeats = size, repeats
        if best_repeats == 0:
            index += 1
            continue
        loops += 1
        first_dropped = index + _KEPT_REPEATS * best_size
        for position in range(first_dropped, index + best_repeats * best_size):
            keep[position] = False
        index += best_repeats * best_size
    return keep, loops


def _repeats(tokens: Sequence[str], start: int, size: int) -> int:
    phrase = tokens[start : start + size]
    if len(phrase) < size or not any(phrase):
        return 0
    count = 1
    position = start + size
    while tokens[position : position + size] == phrase:
        count += 1
        position += size
    return count


def _identity(word: Any) -> tuple[Any, Any, Any]:
    if not isinstance(word, dict):
        return (None, None, None)
    return (word.get("word"), word.get("start"), word.get("end"))


def _refit_times(segment: dict[str, Any], words: list[dict[str, Any]]) -> None:
    starts = [w["start"] for w in words if isinstance(w.get("start"), (int, float))]
    ends = [w["end"] for w in words if isinstance(w.get("end"), (int, float))]
    if starts:
        segment["start"] = min(starts)
    if ends:
        segment["end"] = max(ends)
