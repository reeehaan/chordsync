"""Offline comparison helpers for full-mix and accompaniment chord evidence.

This module is diagnostic-only. It is not imported by the production pipeline.
"""

from dataclasses import dataclass
from statistics import median
from typing import Sequence

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.evaluation.chord_reliability import build_reliability_windows

_RAPID_RUN_SECONDS = 0.5
_BEAT_ALIGNMENT_TOLERANCE = 0.2


@dataclass(frozen=True)
class AcousticRegionEvidence:
    start: float
    end: float
    runs: tuple[tuple[float, float, str], ...]
    sequence: tuple[str, ...]
    segment_count: int
    unique_chord_count: int
    average_run_duration: float
    rapid_transition_count: int
    beat_alignment_ratio: float
    reliability_average: float
    reliability_minimum: float


def measure_acoustic_region(
    chords: Sequence[ChordSegment],
    beats: Sequence[BeatEvent],
    *,
    start: float,
    end: float,
) -> AcousticRegionEvidence:
    """Summarize one unchanged timestamp region of an estimator result."""
    if end <= start:
        raise ValueError("end must be greater than start")

    runs = _clip_and_merge(chords, start, end)
    durations = [run.end - run.start for run in runs]
    boundaries = [run.start for run in runs[1:]]
    beat_times = [float(beat.time) for beat in sorted(beats, key=lambda beat: beat.time)]
    beat_intervals = [
        right - left
        for left, right in zip(beat_times, beat_times[1:])
        if right > left
    ]
    tolerance = (
        median(beat_intervals) * _BEAT_ALIGNMENT_TOLERANCE
        if beat_intervals
        else 0.0
    )
    aligned = sum(
        bool(beat_times)
        and min(abs(boundary - beat) for beat in beat_times) <= tolerance
        for boundary in boundaries
    )

    reliability = [
        window
        for window in build_reliability_windows(chords, beats)
        if window.end > start and window.start < end
    ]
    scores = [window.reliability_score for window in reliability]
    return AcousticRegionEvidence(
        start=start,
        end=end,
        runs=tuple(
            (run.start, run.end, run.normalized_label) for run in runs
        ),
        sequence=tuple(run.normalized_label for run in runs),
        segment_count=len(runs),
        unique_chord_count=len({run.normalized_label for run in runs}),
        average_run_duration=(sum(durations) / len(durations) if durations else 0.0),
        rapid_transition_count=sum(duration < _RAPID_RUN_SECONDS for duration in durations),
        beat_alignment_ratio=(aligned / len(boundaries) if boundaries else 1.0),
        reliability_average=(sum(scores) / len(scores) if scores else 0.0),
        reliability_minimum=min(scores, default=0.0),
    )


def chord_disagreement_rate(
    left: Sequence[ChordSegment],
    right: Sequence[ChordSegment],
    *,
    start: float,
    end: float,
) -> float:
    """Return the time-weighted label disagreement inside a fixed region."""
    if end <= start:
        raise ValueError("end must be greater than start")
    boundaries = {start, end}
    for chord in (*left, *right):
        if start < chord.start < end:
            boundaries.add(float(chord.start))
        if start < chord.end < end:
            boundaries.add(float(chord.end))
    ordered = sorted(boundaries)
    disagreement = 0.0
    for interval_start, interval_end in zip(ordered, ordered[1:]):
        midpoint = (interval_start + interval_end) / 2
        if _label_at(left, midpoint) != _label_at(right, midpoint):
            disagreement += interval_end - interval_start
    return disagreement / (end - start)


def _clip_and_merge(chords, start, end):
    runs: list[ChordSegment] = []
    for chord in sorted(chords, key=lambda item: (item.start, item.end)):
        clipped_start = max(start, float(chord.start))
        clipped_end = min(end, float(chord.end))
        if clipped_end <= clipped_start:
            continue
        clipped = chord.model_copy(update={"start": clipped_start, "end": clipped_end})
        if (
            runs
            and runs[-1].normalized_label == clipped.normalized_label
            and runs[-1].end == clipped.start
        ):
            runs[-1] = runs[-1].model_copy(update={"end": clipped.end})
        else:
            runs.append(clipped)
    return runs


def _label_at(chords, timestamp):
    for chord in chords:
        if chord.start <= timestamp < chord.end:
            return chord.normalized_label
    return "N"
