"""Word-level forced alignment of lyrics with Meta's MMS multilingual aligner.

Synced lyrics give correct text and a start time per line, but words inside a line
were only spread evenly by length, which is off by about 0.6 s on average (up to
nearly 2 s) because sung words are not evenly spaced. MMS can align text in over a
thousand languages (including Sinhala and Hindi) to the audio, so each line is
aligned inside a window around its synced time and the real word times replace the
estimate. Any line that cannot be aligned keeps its estimate.

Runs in the WhisperX environment (it needs torch, torchaudio and uroman):

    python -m analysis.lyrics.mms_alignment --audio vocals.wav \\
        --transcript in.json --output out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

# (start, end) in seconds for each word, or None for a word that could not be
# aligned (e.g. it has no letters after romanisation).
WordTimes = Sequence["tuple[float, float] | None"]
AlignLine = Callable[[float, float, "list[str]"], "WordTimes | None"]

WINDOW_PAD_SECONDS = 1.0
MINIMUM_WORD_SECONDS = 0.05
_LETTERS = re.compile(r"[^a-z']")


@dataclass(frozen=True)
class AlignmentReport:
    aligned_segments: int
    failed_segments: int


def refine_transcript(
    transcript: dict[str, Any],
    align_line: AlignLine,
    total_seconds: float,
    pad_seconds: float = WINDOW_PAD_SECONDS,
) -> AlignmentReport:
    """Replace word times by aligned ones, in place. Never raises for one line."""
    aligned = failed = 0
    previous_end = 0.0
    segments = [s for s in transcript.get("segments", []) if isinstance(s, dict)]
    for segment in segments:
        words = segment.get("words")
        if not isinstance(words, list) or not words:
            continue
        window_start = max(0.0, float(segment["start"]) - pad_seconds)
        window_end = min(total_seconds, float(segment["end"]) + pad_seconds)
        try:
            times = align_line(
                window_start, window_end, [str(word.get("word", "")) for word in words]
            )
        except Exception:  # one bad line must not lose the others
            times = None
        if not times or len(times) != len(words) or not any(times):
            failed += 1
            continue
        fitted = _fit(times, previous_end, window_end)
        if fitted is None:
            failed += 1
            continue
        for word, (start, end) in zip(words, fitted):
            word["start"], word["end"] = round(start, 3), round(end, 3)
        segment["start"], segment["end"] = fitted[0][0], fitted[-1][1]
        previous_end = fitted[-1][1]
        aligned += 1

    transcript["word_segments"] = [
        word for segment in segments for word in segment.get("words", []) or []
    ]
    return AlignmentReport(aligned, failed)


def _fit(
    times: WordTimes, not_before: float, not_after: float
) -> list[tuple[float, float]] | None:
    """Fill gaps, then make times ordered, non-overlapping and inside the window."""
    known = [index for index, value in enumerate(times) if value is not None]
    if not known:
        return None
    result: list[tuple[float, float]] = [(0.0, 0.0)] * len(times)
    for index, value in enumerate(times):
        if value is not None:
            result[index] = (float(value[0]), float(value[1]))
    # Words with no aligned time take the gap between their aligned neighbours.
    for index in range(len(times)):
        if times[index] is not None:
            continue
        left = max((i for i in known if i < index), default=None)
        right = min((i for i in known if i > index), default=None)
        low = result[left][1] if left is not None else result[right][0] - 0.3
        high = result[right][0] if right is not None else result[left][1] + 0.3
        slots = [i for i in range(len(times)) if left is None or i > left]
        slots = [i for i in slots if (right is None or i < right) and times[i] is None]
        position = slots.index(index)
        width = max(high - low, MINIMUM_WORD_SECONDS * len(slots)) / len(slots)
        result[index] = (low + position * width, low + (position + 1) * width)

    cursor = max(0.0, not_before)
    fitted: list[tuple[float, float]] = []
    for start, end in result:
        start = max(start, cursor)
        end = max(end, start + MINIMUM_WORD_SECONDS)
        fitted.append((start, end))
        cursor = end
    if fitted[-1][1] > not_after + 0.5:
        return None  # drifted far outside the line's window: do not trust it
    return fitted


# --- the model -------------------------------------------------------------------


def load_mono_16k(path: Path):
    """The audio as a (1, samples) float tensor at 16 kHz."""
    import numpy as np
    import torch
    import torchaudio

    with wave.open(str(path), "rb") as audio:
        rate, channels = audio.getframerate(), audio.getnchannels()
        data = np.frombuffer(audio.readframes(audio.getnframes()), dtype=np.int16)
    mono = data.reshape(-1, channels).mean(axis=1).astype(np.float32) / 32768.0
    waveform = torch.from_numpy(mono)[None, :]
    if rate != 16000:
        waveform = torchaudio.functional.resample(waveform, rate, 16000)
    return waveform


def romanize_word(romanizer: Any, word: str) -> str:
    return _LETTERS.sub("", romanizer.romanize_string(word).lower())


def build_aligner(audio_path: Path) -> tuple[AlignLine, float]:
    """An `align_line` backed by MMS_FA, and the audio length in seconds."""
    import torch
    import uroman
    from torchaudio.pipelines import MMS_FA

    waveform = load_mono_16k(audio_path)
    model = MMS_FA.get_model(with_star=False).eval()
    tokenizer, aligner = MMS_FA.get_tokenizer(), MMS_FA.get_aligner()
    romanizer = uroman.Uroman()
    rate = MMS_FA.sample_rate
    total = waveform.size(1) / rate

    def align_line(start: float, end: float, words: list[str]) -> WordTimes | None:
        romanized = [romanize_word(romanizer, word) for word in words]
        usable = [index for index, text in enumerate(romanized) if text]
        if not usable:
            return None
        clip = waveform[:, int(start * rate) : int(end * rate)]
        if clip.size(1) < rate // 10:
            return None
        with torch.inference_mode():
            emission, _ = model(clip)
        spans = aligner(emission[0], tokenizer([romanized[i] for i in usable]))
        seconds_per_frame = clip.size(1) / emission.size(1) / rate
        times: list[tuple[float, float] | None] = [None] * len(words)
        for index, word_spans in zip(usable, spans):
            times[index] = (
                start + word_spans[0].start * seconds_per_frame,
                start + word_spans[-1].end * seconds_per_frame,
            )
        return times

    return align_line, total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)

    transcript = json.loads(arguments.transcript.read_text(encoding="utf-8"))
    align_line, total = build_aligner(arguments.audio)
    report = refine_transcript(transcript, align_line, total)
    transcript["alignment"] = "mms_fa"
    arguments.output.write_text(
        json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"aligned {report.aligned_segments} lines, "
        f"{report.failed_segments} kept their estimate",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
