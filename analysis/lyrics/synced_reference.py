"""Build a lyric transcript from time-synced reference lyrics (LRC).

Speech recognition is weak for some languages (Whisper's small model writes
Sinhala as noisy Latin text and sometimes loops), and there is no forced aligner
for them. When the lyrics provider has synced lyrics, the text is already correct
and every line has a start time, so the transcript can be built from those lines
instead. Two details keep it honest:

* the provider's recording can differ from the user's file (a different intro), so
  the line times are shifted to best match where the singer is actually singing;
* word times inside a line are an even split by length, because only line times
  are known.
"""

from __future__ import annotations

import re
import wave
from dataclasses import dataclass
from typing import Any, Sequence

_STAMP = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_OFFSET_TAG = re.compile(r"^\[offset:\s*([+-]?\d+)\s*\]\s*$", re.IGNORECASE)

# Longest a line is allowed to last when the next line starts much later.
MAX_LINE_SECONDS = 12.0
_END_GAP_SECONDS = 0.05
_SECONDS_PER_CHARACTER = 0.15
MINIMUM_TIMED_LINES = 4


@dataclass(frozen=True)
class SyncedLine:
    start: float
    text: str


def parse_synced_lyrics(text: str | None) -> list[SyncedLine]:
    """Parse LRC text; empty lines are kept as markers that end the line before."""
    if not text:
        return []
    shift = 0.0
    lines: list[SyncedLine] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        offset = _OFFSET_TAG.match(raw)
        if offset:
            shift = int(offset.group(1)) / 1000.0
            continue
        stamps = list(_STAMP.finditer(raw))
        if not stamps:
            continue
        lyric = " ".join(raw[stamps[-1].end() :].split())
        for stamp in stamps:
            lines.append(SyncedLine(_seconds(stamp) - shift, lyric))
    lines.sort(key=lambda line: line.start)
    return [line for line in lines if line.start >= 0]


def _seconds(stamp: re.Match[str]) -> float:
    fraction = stamp.group(3)
    hundredths = int(fraction) / (10 ** len(fraction)) if fraction else 0.0
    return int(stamp.group(1)) * 60 + int(stamp.group(2)) + hundredths


def timed_line_count(lines: Sequence[SyncedLine]) -> int:
    return sum(1 for line in lines if line.text)


def line_spans(lines: Sequence[SyncedLine]) -> list[tuple[float, float, str]]:
    """Each lyric line with its end time; markers and later lines end a line."""
    spans: list[tuple[float, float, str]] = []
    for index, line in enumerate(lines):
        if not line.text:
            continue
        following = lines[index + 1].start if index + 1 < len(lines) else None
        natural = line.start + min(8.0, _SECONDS_PER_CHARACTER * len(line.text))
        end = natural if following is None else following - _END_GAP_SECONDS
        end = min(end, line.start + MAX_LINE_SECONDS)
        spans.append((line.start, max(end, line.start + 0.2), line.text))
    return spans


# --- finding where the singing really is -----------------------------------------


def vocal_activity(path: Any, hop_seconds: float = 0.05) -> list[float] | None:
    """Loudness of a 16-bit WAV per hop, or None if it cannot be read."""
    try:
        import audioop  # removed in Python 3.13; the worker runs 3.11

        with wave.open(str(path), "rb") as audio:
            width, channels = audio.getsampwidth(), audio.getnchannels()
            rate = audio.getframerate()
            frames_per_hop = max(1, int(rate * hop_seconds))
            levels: list[float] = []
            while True:
                chunk = audio.readframes(frames_per_hop)
                if not chunk:
                    break
                if channels > 1:
                    chunk = audioop.tomono(chunk, width, 0.5, 0.5)
                levels.append(float(audioop.rms(chunk, width)))
            return levels or None
    except (ImportError, OSError, EOFError, wave.Error, ValueError):
        return None


def estimate_offset(
    lines: Sequence[SyncedLine],
    levels: Sequence[float],
    hop_seconds: float = 0.05,
    max_shift_seconds: float = 10.0,
) -> float:
    """Seconds to add to the line times so they best overlap the singing."""
    spans = line_spans(lines)
    if len(levels) < 40 or len(spans) < MINIMUM_TIMED_LINES:
        return 0.0
    ordered = sorted(levels)
    loud = ordered[int(0.95 * (len(ordered) - 1))]
    if loud <= 0:
        return 0.0
    threshold = 0.12 * loud
    active = [1.0 if level >= threshold else 0.0 for level in levels]

    template: list[int] = []
    for start, end, _ in spans:
        first = int(start / hop_seconds)
        last = int(end / hop_seconds)
        template.extend(range(first, last))
    if not template:
        return 0.0

    limit = int(max_shift_seconds / hop_seconds)

    def score(shift: int) -> float:
        total = 0.0
        for index in template:
            position = index + shift
            if 0 <= position < len(active):
                total += active[position] - 0.5
            else:
                total -= 0.5
        return total

    baseline = score(0)
    best_shift, best_score = 0, baseline
    for shift in range(-limit, limit + 1):
        # A small pull towards no shift settles ties and near-ties.
        adjusted = score(shift) - 0.0005 * abs(shift)
        if adjusted > best_score:
            best_shift, best_score = shift, adjusted
    if best_score - baseline < 0.01 * len(template):
        return 0.0
    return best_shift * hop_seconds


# --- the transcript --------------------------------------------------------------


def build_transcript(
    lines: Sequence[SyncedLine],
    offset: float = 0.0,
    total_seconds: float | None = None,
    language: str = "synced",
) -> dict[str, Any]:
    """A WhisperX-shaped transcript, so the rest of the pipeline is unchanged."""
    segments: list[dict[str, Any]] = []
    flat: list[dict[str, Any]] = []
    for start, end, text in line_spans(lines):
        start, end = max(0.0, start + offset), max(0.0, end + offset)
        if total_seconds is not None:
            if start >= total_seconds:
                continue
            end = min(end, total_seconds)
        if end <= start:
            continue
        words = _split_words(text, start, end)
        if not words:
            continue
        segments.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": " " + text,
                "words": words,
                "avg_logprob": 0.0,
            }
        )
        flat.extend(words)
    return {"segments": segments, "word_segments": flat, "language": language}


def _split_words(text: str, start: float, end: float) -> list[dict[str, Any]]:
    tokens = text.split()
    if not tokens:
        return []
    weights = [max(1, len(token)) for token in tokens]
    scale = (end - start) / sum(weights)
    words: list[dict[str, Any]] = []
    cursor = start
    for token, weight in zip(tokens, weights):
        word_end = cursor + weight * scale
        words.append(
            {
                "word": token,
                "start": round(cursor, 3),
                "end": round(word_end, 3),
                "score": 1.0,
            }
        )
        cursor = word_end
    return words
