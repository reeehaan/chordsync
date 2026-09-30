"""Frozen section-level harmonic-consensus evidence.

Uniqueness is never treated as proof that a chord sequence is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment


_ROOT_TO_PITCH = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}


@dataclass(frozen=True)
class HarmonicWindow:
    start: float
    end: float
    labels: tuple[str, ...]
    root_intervals: tuple[int | None, ...]
    qualities: tuple[str, ...]
    change_positions: tuple[bool, ...]


@dataclass(frozen=True)
class HarmonicSimilarity:
    exact_agreement: float
    transposition_invariant_agreement: float
    change_position_agreement: float
    repeated_progression_similarity: float


@dataclass(frozen=True)
class HarmonicFamily:
    member_indexes: tuple[int, ...]


def build_harmonic_windows(
    chords: Sequence[ChordSegment],
    beats: Sequence[BeatEvent],
    *,
    bars_per_window: int = 4,
    beats_per_bar: int = 4,
    align_to_downbeat: bool = True,
) -> list[HarmonicWindow]:
    """Sample chord labels at beats in non-overlapping downbeat-aligned windows."""
    if bars_per_window <= 0 or beats_per_bar <= 0:
        raise ValueError("window dimensions must be positive")
    ordered_beats = sorted(beats, key=lambda beat: beat.time)
    ordered_chords = sorted(chords, key=lambda chord: (chord.start, chord.end))
    first_downbeat = 0
    if align_to_downbeat:
        first_downbeat = next(
            (
                index
                for index, beat in enumerate(ordered_beats)
                if beat.is_downbeat or beat.beat_number == 1
            ),
            0,
        )
    beats_per_window = bars_per_window * beats_per_bar
    windows = []
    for index in range(
        first_downbeat,
        len(ordered_beats) - beats_per_window,
        beats_per_window,
    ):
        window_beats = ordered_beats[index : index + beats_per_window + 1]
        labels = tuple(
            _label_at(ordered_chords, float(beat.time))
            for beat in window_beats[:-1]
        )
        roots_and_qualities = tuple(_parse_label(label) for label in labels)
        anchor = next(
            (root for root, _ in roots_and_qualities if root is not None),
            None,
        )
        intervals = tuple(
            ((root - anchor) % 12 if root is not None and anchor is not None else None)
            for root, _ in roots_and_qualities
        )
        windows.append(
            HarmonicWindow(
                start=float(window_beats[0].time),
                end=float(window_beats[-1].time),
                labels=labels,
                root_intervals=intervals,
                qualities=tuple(quality for _, quality in roots_and_qualities),
                change_positions=tuple(
                    left != right for left, right in zip(labels, labels[1:])
                ),
            )
        )
    return windows


def compare_harmonic_windows(
    left: HarmonicWindow,
    right: HarmonicWindow,
) -> HarmonicSimilarity:
    """Compare equal-length beat sequences while preserving chord quality."""
    if len(left.labels) != len(right.labels):
        raise ValueError("windows must have equal beat counts")
    exact = _agreement(left.labels, right.labels)
    transposition_invariant = _agreement(
        tuple(zip(left.root_intervals, left.qualities)),
        tuple(zip(right.root_intervals, right.qualities)),
    )
    change_positions = _agreement(left.change_positions, right.change_positions)
    composite = (
        0.15 * exact + 0.55 * transposition_invariant + 0.30 * change_positions
    )
    return HarmonicSimilarity(
        exact_agreement=exact,
        transposition_invariant_agreement=transposition_invariant,
        change_position_agreement=change_positions,
        repeated_progression_similarity=composite,
    )


def find_repeated_families(
    windows: Sequence[HarmonicWindow],
    *,
    similarity_threshold: float = 0.75,
) -> list[HarmonicFamily]:
    """Group windows around a representative using a diagnostic threshold."""
    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between zero and one")
    unassigned = set(range(len(windows)))
    families = []
    while unassigned:
        seed = min(unassigned)
        members = tuple(
            index
            for index in sorted(unassigned)
            if compare_harmonic_windows(windows[seed], windows[index])
            .repeated_progression_similarity
            >= similarity_threshold
        )
        unassigned.difference_update(members)
        if len(members) >= 2:
            families.append(HarmonicFamily(member_indexes=members))
    return families


def nearest_window(
    windows: Sequence[HarmonicWindow],
    target_index: int,
) -> tuple[int, HarmonicSimilarity]:
    """Return the target's most similar distinct window."""
    if not 0 <= target_index < len(windows):
        raise IndexError("target_index is outside the window collection")
    candidates = [index for index in range(len(windows)) if index != target_index]
    if not candidates:
        raise ValueError("at least two windows are required")
    comparisons = [
        (index, compare_harmonic_windows(windows[target_index], windows[index]))
        for index in candidates
    ]
    return max(
        comparisons,
        key=lambda item: (
            item[1].repeated_progression_similarity,
            item[1].transposition_invariant_agreement,
            -item[0],
        ),
    )


def _parse_label(label: str) -> tuple[int | None, str]:
    if label == "N":
        return None, "N"
    quality = "minor" if label.endswith("m") else "major"
    root = label[:-1] if quality == "minor" else label
    if root not in _ROOT_TO_PITCH:
        raise ValueError(f"unsupported normalized chord label: {label}")
    return _ROOT_TO_PITCH[root], quality


def _label_at(chords, timestamp):
    for chord in chords:
        if chord.start <= timestamp < chord.end:
            return chord.normalized_label
    return "N"


def _agreement(left, right):
    if len(left) != len(right):
        raise ValueError("sequences must have equal lengths")
    if not left:
        return 1.0
    matches = sum(
        left_item == right_item for left_item, right_item in zip(left, right)
    )
    return matches / len(left)
