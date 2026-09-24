"""Offline chord-guidance reliability diagnostics.

This module is intentionally not imported by the production analysis pipeline.
It measures observable BTC label behavior in beat-aligned windows; its score is
exploratory and is not a model confidence value.
"""

from dataclasses import dataclass, replace
from statistics import median
from typing import Sequence

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment

_RAPID_RUN_SECONDS = 0.5
_BEAT_ALIGNMENT_TOLERANCE = 0.2


@dataclass(frozen=True)
class ChordReliabilityWindow:
    start: float
    end: float
    chord_changes: int
    unique_chords: int
    average_run_duration: float
    shortest_run_duration: float
    churn_per_beat: float
    repeat_consistency: float
    no_chord_ratio: float
    beat_alignment_ratio: float
    rapid_transition_count: int
    dominant_chord_ratio: float
    neighbor_label_similarity: float
    reliability_score: float
    sequence: tuple[str, ...]


@dataclass
class _Run:
    start: float
    end: float
    label: str
    original_duration: float
    left_clipped: bool
    right_clipped: bool

    @property
    def duration(self) -> float:
        return self.end - self.start


def build_reliability_windows(
    chords: Sequence[ChordSegment],
    beats: Sequence[BeatEvent],
    *,
    beats_per_window: int = 8,
) -> list[ChordReliabilityWindow]:
    """Measure non-overlapping beat windows without changing analysis output."""
    if beats_per_window <= 0:
        raise ValueError("beats_per_window must be positive")
    ordered_beats = sorted(beats, key=lambda beat: beat.time)
    ordered_chords = sorted(chords, key=lambda chord: (chord.start, chord.end))
    windows = []
    for index in range(0, len(ordered_beats) - beats_per_window, beats_per_window):
        window_beats = ordered_beats[index : index + beats_per_window + 1]
        windows.append(
            _measure_window(
                ordered_chords,
                window_beats,
                beats_per_window=beats_per_window,
            )
        )
    return _with_neighbor_context(windows)


def _measure_window(chords, beats, *, beats_per_window):
    start = float(beats[0].time)
    end = float(beats[-1].time)
    duration = end - start
    runs = _clip_runs(chords, start, end)
    run_durations = [run.duration for run in runs]
    chord_changes = max(0, len(runs) - 1)
    labels = tuple(run.label for run in runs)
    label_durations: dict[str, float] = {}
    for run in runs:
        label_durations[run.label] = label_durations.get(run.label, 0.0) + run.duration

    internal_runs = [
        run for run in runs if not run.left_clipped and not run.right_clipped
    ]
    diagnostic_durations = [run.original_duration for run in runs]
    rapid_count = sum(
        run.duration < _RAPID_RUN_SECONDS for run in internal_runs
    )
    boundaries = [run.start for run in runs[1:]]
    beat_times = [float(beat.time) for beat in beats]
    beat_interval = median(
        right - left for left, right in zip(beat_times, beat_times[1:])
    )
    aligned = sum(
        min(abs(boundary - beat) for beat in beat_times)
        <= beat_interval * _BEAT_ALIGNMENT_TOLERANCE
        for boundary in boundaries
    )
    alignment = aligned / len(boundaries) if boundaries else 1.0
    repeat_consistency = _repeat_consistency(chords, beat_times[:-1])
    no_chord_duration = label_durations.get("N", 0.0)
    dominant_duration = max(label_durations.values(), default=0.0)
    provisional = ChordReliabilityWindow(
        start=start,
        end=end,
        chord_changes=chord_changes,
        unique_chords=len(label_durations),
        average_run_duration=(sum(run_durations) / len(runs) if runs else 0.0),
        shortest_run_duration=min(diagnostic_durations, default=0.0),
        churn_per_beat=chord_changes / beats_per_window,
        repeat_consistency=repeat_consistency,
        no_chord_ratio=(no_chord_duration / duration if duration else 0.0),
        beat_alignment_ratio=alignment,
        rapid_transition_count=rapid_count,
        dominant_chord_ratio=(dominant_duration / duration if duration else 0.0),
        neighbor_label_similarity=1.0,
        reliability_score=0.0,
        sequence=labels,
    )
    return replace(provisional, reliability_score=_score(provisional))


def _clip_runs(chords, start, end):
    runs: list[_Run] = []
    for chord in chords:
        clipped_start = max(start, float(chord.start))
        clipped_end = min(end, float(chord.end))
        if clipped_end <= clipped_start:
            continue
        label = chord.normalized_label
        run = _Run(
            start=clipped_start,
            end=clipped_end,
            label=label,
            original_duration=float(chord.end) - float(chord.start),
            left_clipped=chord.start < start,
            right_clipped=chord.end > end,
        )
        if runs and runs[-1].label == label and runs[-1].end == run.start:
            runs[-1].end = run.end
            runs[-1].original_duration += run.original_duration
            runs[-1].right_clipped = run.right_clipped
        else:
            runs.append(run)
    return runs


def _repeat_consistency(chords, beat_times):
    if len(beat_times) < 2 or len(beat_times) % 2:
        return 0.0
    labels = [_label_at(chords, beat_time) for beat_time in beat_times]
    half = len(labels) // 2
    return sum(
        left == right for left, right in zip(labels[:half], labels[half:])
    ) / half


def _label_at(chords, timestamp):
    for chord in chords:
        if chord.start <= timestamp < chord.end:
            return chord.normalized_label
    return "N"


def _with_neighbor_context(windows):
    contextualized = []
    for index, window in enumerate(windows):
        neighbors = []
        if index > 0:
            neighbors.append(windows[index - 1])
        if index + 1 < len(windows):
            neighbors.append(windows[index + 1])
        similarities = [
            _label_similarity(window.sequence, neighbor.sequence)
            for neighbor in neighbors
        ]
        similarity = sum(similarities) / len(similarities) if similarities else 1.0
        with_context = replace(window, neighbor_label_similarity=similarity)
        contextualized.append(
            replace(with_context, reliability_score=_score(with_context))
        )
    return contextualized


def _label_similarity(left, right):
    left_labels = set(left) - {"N"}
    right_labels = set(right) - {"N"}
    if not left_labels and not right_labels:
        return 1.0
    union = left_labels | right_labels
    return len(left_labels & right_labels) / len(union)


def _score(window):
    change_count = max(1, window.chord_changes)
    rapid_pressure = min(1.0, window.rapid_transition_count / change_count)
    churn_pressure = min(1.0, max(0.0, (window.churn_per_beat - 0.5) / 0.5))
    off_beat_pressure = 1.0 - window.beat_alignment_ratio
    neighbor_pressure = 1.0 - window.neighbor_label_similarity
    repetition_pressure = 1.0 - window.repeat_consistency
    penalty = (
        0.35 * rapid_pressure
        + 0.25 * churn_pressure
        + 0.20 * off_beat_pressure
        + 0.10 * neighbor_pressure
        + 0.10 * repetition_pressure
    )
    return max(0.0, min(1.0, 1.0 - penalty))
