import copy
import unicodedata
from collections.abc import Mapping
from typing import Any

from anyascii import anyascii


_ENGLISH_LANGUAGE_CODES = frozenset({"en", "english"})


def romanize_whisperx_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return Latin-script display text without changing aligned timing data."""
    if not whisperx_needs_romanization(result):
        return result if isinstance(result, dict) else dict(result)

    romanized = copy.deepcopy(dict(result))
    for segment in romanized.get("segments", []):
        if not isinstance(segment, dict):
            continue
        _add_segment_word_timings(segment)
        segment["text"] = _romanize_text(segment.get("text"))
        for word in segment.get("words", []):
            if isinstance(word, dict):
                word["word"] = _romanize_text(word.get("word"))

    for word in romanized.get("word_segments", []):
        if isinstance(word, dict):
            word["word"] = _romanize_text(word.get("word"))

    return romanized


def add_approximate_word_timings(result: Mapping[str, Any]) -> dict[str, Any]:
    """Give sentence-timed segments per-word timings, keeping the native script.

    WhisperX `--no_align` output has segment times only; the rest of the pipeline
    needs words, so each segment's words share its time evenly.
    """
    timed = copy.deepcopy(dict(result))
    for segment in timed.get("segments", []):
        if isinstance(segment, dict):
            _add_segment_word_timings(segment)
    return timed


def _add_segment_word_timings(segment: dict[str, Any]) -> None:
    """Create approximate word timings for WhisperX --no_align output."""
    if segment.get("words"):
        return
    words = str(segment.get("text", "")).split()
    if not words:
        return
    try:
        start = float(segment["start"])
        end = float(segment["end"])
    except (KeyError, TypeError, ValueError):
        return
    if end <= start:
        return
    duration = (end - start) / len(words)
    segment["words"] = [
        {
            "word": word,
            "start": start + index * duration,
            "end": start + (index + 1) * duration,
        }
        for index, word in enumerate(words)
    ]


def whisperx_needs_romanization(result: Mapping[str, Any]) -> bool:
    """Handle WhisperX auto-detection results whose JSON language is mislabeled."""
    language = str(result.get("language", "")).strip().casefold()
    if language and language not in _ENGLISH_LANGUAGE_CODES | {"unknown"}:
        return True

    for segment in result.get("segments", []):
        if not isinstance(segment, Mapping):
            continue
        texts = [segment.get("text", "")]
        texts.extend(
            word.get("word", "")
            for word in segment.get("words", [])
            if isinstance(word, Mapping)
        )
        if any(_contains_non_ascii_letter(str(text)) for text in texts):
            return True
    return False


def _romanize_text(value: object) -> str:
    native_text = str(value or "")
    converted = anyascii(native_text)
    return converted or native_text


def _contains_non_ascii_letter(text: str) -> bool:
    return any(
        ord(character) > 127
        and unicodedata.category(character).startswith("L")
        for character in text
    )
