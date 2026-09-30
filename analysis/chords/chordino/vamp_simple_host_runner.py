import subprocess
import wave
from pathlib import Path

from analysis.chords.models import ChordSegment
from analysis.evaluation.estimator_consensus import (
    normalize_estimator_label,
    parse_vamp_simple_host_output,
)


def run_chordino_diagnostic(
    audio_path: Path,
    *,
    executable: Path,
) -> list[ChordSegment]:
    """Run secondary Chordino evidence without replacing the primary estimator."""
    completed = subprocess.run(
        [
            str(executable),
            "nnls-chroma:chordino:simplechord",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    events = parse_vamp_simple_host_output(completed.stdout)
    if not events:
        raise RuntimeError("Chordino diagnostic produced no chord events")
    duration = _wav_duration(audio_path)
    chords = []
    for index, event in enumerate(events):
        start = float(event["time"])
        end = (
            float(events[index + 1]["time"])
            if index + 1 < len(events)
            else duration
        )
        if end <= start:
            continue
        raw_label = str(event["label"])
        chords.append(
            ChordSegment(
                start=round(start, 6),
                end=round(end, 6),
                raw_label=raw_label,
                normalized_label=normalize_estimator_label(
                    raw_label
                ).canonical_label,
                source="chordino-diagnostic",
            )
        )
    if not chords:
        raise RuntimeError("Chordino diagnostic produced no usable chord segments")
    return chords


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()
