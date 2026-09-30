"""Frozen BTC/Chordino consensus evidence.

Neither estimator is treated as ground truth. The helpers sample both outputs
on an unchanged beat grid and make every vocabulary simplification explicit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import fmean
from typing import Sequence

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import NO_CHORD_LABELS, normalize_chord_label


@dataclass(frozen=True)
class NormalizedEstimatorLabel:
    raw_label: str
    canonical_label: str
    simplifications: tuple[str, ...]


@dataclass(frozen=True)
class BeatEstimatorComparison:
    time: float
    btc_label: str
    chordino_label: str
    exact_match: bool
    root_match: bool
    quality_match: bool


@dataclass(frozen=True)
class EstimatorRegionComparison:
    start: float
    end: float
    beat_count: int
    btc_sequence: tuple[str, ...]
    chordino_sequence: tuple[str, ...]
    exact_agreement: float
    root_agreement: float
    quality_agreement: float
    disagreement_duration: float
    longest_disagreement_run_beats: int
    longest_disagreement_run_seconds: float
    mean_eight_beat_disagreement: float


def normalize_estimator_label(label: str) -> NormalizedEstimatorLabel:
    """Normalize to ChordSync's major/minor vocabulary with an audit trail."""
    raw = label.strip()
    if not raw or raw.upper() in NO_CHORD_LABELS:
        return NormalizedEstimatorLabel(raw, "N", ())

    root_part = raw.split("/", maxsplit=1)[0]
    match = re.match(r"^([A-Ga-g])([#b]?)(.*)$", root_part)
    simplifications = []
    if "/" in raw:
        simplifications.append("inversion removed")
    if match:
        quality = match.group(3).lower()
        direct_qualities = {"", "m", ":min", ":maj"}
        if quality not in direct_qualities:
            is_minor = (
                quality.startswith(":min")
                or quality.startswith("m") and not quality.startswith("maj")
            )
            target = "minor" if is_minor else "major"
            simplifications.append(f"extended quality collapsed to {target}")
    return NormalizedEstimatorLabel(
        raw_label=raw,
        canonical_label=normalize_chord_label(raw),
        simplifications=tuple(simplifications),
    )


def parse_vamp_simple_host_output(output: str) -> list[dict[str, object]]:
    """Parse vamp-simple-host's ``seconds: label`` output."""
    events = []
    for line in output.splitlines():
        match = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?):\s*(\S.*)$", line)
        if match:
            events.append(
                {"time": float(match.group(1)), "label": match.group(2).strip()}
            )
    return events


def sample_estimators_on_beats(
    btc_chords: Sequence[ChordSegment],
    chordino_chords: Sequence[ChordSegment],
    beats: Sequence[BeatEvent],
) -> list[BeatEstimatorComparison]:
    """Sample both canonical segment streams at identical beat timestamps."""
    btc_ordered = sorted(btc_chords, key=lambda chord: (chord.start, chord.end))
    chordino_ordered = sorted(
        chordino_chords, key=lambda chord: (chord.start, chord.end)
    )
    samples = []
    for beat in sorted(beats, key=lambda item: item.time):
        btc = _label_at(btc_ordered, float(beat.time))
        chordino = _label_at(chordino_ordered, float(beat.time))
        btc_root, btc_quality = _root_and_quality(btc)
        chordino_root, chordino_quality = _root_and_quality(chordino)
        samples.append(
            BeatEstimatorComparison(
                time=float(beat.time),
                btc_label=btc,
                chordino_label=chordino,
                exact_match=btc == chordino,
                root_match=btc_root == chordino_root,
                quality_match=btc_quality == chordino_quality,
            )
        )
    return samples


def summarize_estimator_region(
    samples: Sequence[BeatEstimatorComparison],
    *,
    start: float,
    end: float,
) -> EstimatorRegionComparison:
    """Summarize beat-sampled agreement and duration inside a fixed region."""
    if end <= start:
        raise ValueError("end must be greater than start")
    ordered = sorted(samples, key=lambda sample: sample.time)
    selected = [sample for sample in ordered if start <= sample.time < end]
    if not selected:
        raise ValueError("region contains no beat samples")

    duration = 0.0
    longest_seconds = 0.0
    current_seconds = 0.0
    longest_beats = 0
    current_beats = 0
    for index, sample in enumerate(ordered[:-1]):
        interval_start = max(start, sample.time)
        interval_end = min(end, ordered[index + 1].time)
        if interval_end <= interval_start:
            continue
        if sample.exact_match:
            current_seconds = 0.0
            current_beats = 0
        else:
            interval_duration = interval_end - interval_start
            duration += interval_duration
            current_seconds += interval_duration
            current_beats += 1
            longest_seconds = max(longest_seconds, current_seconds)
            longest_beats = max(longest_beats, current_beats)

    window_disagreements = []
    for index in range(0, len(selected), 8):
        window = selected[index : index + 8]
        if len(window) == 8:
            window_disagreements.append(
                sum(not sample.exact_match for sample in window) / 8
            )

    return EstimatorRegionComparison(
        start=start,
        end=end,
        beat_count=len(selected),
        btc_sequence=_compact(sample.btc_label for sample in selected),
        chordino_sequence=_compact(sample.chordino_label for sample in selected),
        exact_agreement=fmean(sample.exact_match for sample in selected),
        root_agreement=fmean(sample.root_match for sample in selected),
        quality_agreement=fmean(sample.quality_match for sample in selected),
        disagreement_duration=duration,
        longest_disagreement_run_beats=longest_beats,
        longest_disagreement_run_seconds=longest_seconds,
        mean_eight_beat_disagreement=(
            fmean(window_disagreements) if window_disagreements else 0.0
        ),
    )


def _label_at(chords, timestamp):
    for chord in chords:
        if chord.start <= timestamp < chord.end:
            return chord.normalized_label
    return "N"


def _root_and_quality(label):
    if label == "N":
        return "N", "N"
    return (label[:-1], "minor") if label.endswith("m") else (label, "major")


def _compact(labels):
    compacted = []
    for label in labels:
        if not compacted or compacted[-1] != label:
            compacted.append(label)
    return tuple(compacted)
