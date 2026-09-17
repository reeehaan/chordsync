import math
from pathlib import Path

import mir_eval
import numpy as np

from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import normalize_chord_label


def to_mir_eval_label(label: str) -> str:
    normalized = normalize_chord_label(label)
    if normalized == "N":
        return "N"
    if normalized.endswith("m"):
        return f"{normalized[:-1]}:min"
    return normalized


def load_reference_lab(lab_path: Path) -> tuple[np.ndarray, list[str]]:
    if not lab_path.is_file():
        raise FileNotFoundError(f"Reference lab file not found: {lab_path}")

    intervals: list[list[float]] = []
    labels: list[str] = []
    for line_number, raw_line in enumerate(
        lab_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=2)
        if len(parts) != 3:
            raise ValueError(f"Reference annotation line {line_number} is malformed.")
        start_text, end_text, label = parts
        try:
            start = float(start_text)
            end = float(end_text)
        except ValueError as error:
            raise ValueError(
                f"Reference annotation line {line_number} is malformed."
            ) from error
        _validate_boundary(start, end, "Reference")
        if intervals and start < intervals[-1][1]:
            raise ValueError("Reference annotation intervals overlap.")
        intervals.append([start, end])
        labels.append(to_mir_eval_label(label))

    if not intervals:
        raise ValueError("Reference intervals cannot be empty.")
    return np.asarray(intervals, dtype=float), labels


def segments_to_intervals(
    segments: list[ChordSegment],
) -> tuple[np.ndarray, list[str]]:
    ordered = sorted(segments, key=lambda segment: (segment.start, segment.end))
    intervals: list[list[float]] = []
    labels: list[str] = []
    for segment in ordered:
        _validate_boundary(segment.start, segment.end, "Estimated")
        if intervals and segment.start < intervals[-1][1]:
            raise ValueError("Estimated chord intervals overlap.")
        intervals.append([segment.start, segment.end])
        labels.append(to_mir_eval_label(segment.raw_label))
    return np.asarray(intervals, dtype=float), labels


def evaluate_chords(
    reference_intervals: np.ndarray,
    reference_labels: list[str],
    estimated_intervals: np.ndarray,
    estimated_labels: list[str],
) -> dict:
    _validate_interval_array(reference_intervals, reference_labels, "Reference")
    _validate_interval_array(estimated_intervals, estimated_labels, "Estimated")

    evaluation_start = float(reference_intervals[0][0])
    evaluation_end = float(reference_intervals[-1][1])
    canonical_reference = [to_mir_eval_label(label) for label in reference_labels]
    canonical_estimated = [to_mir_eval_label(label) for label in estimated_labels]

    ref_intervals, ref_labels = mir_eval.util.adjust_intervals(
        reference_intervals,
        canonical_reference,
        t_min=evaluation_start,
        t_max=evaluation_end,
        start_label="N",
        end_label="N",
    )
    est_intervals, est_labels = mir_eval.util.adjust_intervals(
        estimated_intervals,
        canonical_estimated,
        t_min=evaluation_start,
        t_max=evaluation_end,
        start_label="N",
        end_label="N",
    )
    merged_intervals, merged_reference, merged_estimated = (
        mir_eval.util.merge_labeled_intervals(
            ref_intervals,
            ref_labels,
            est_intervals,
            est_labels,
        )
    )
    durations = mir_eval.util.intervals_to_durations(merged_intervals)

    return {
        "root_wcsr": _weighted_score(
            mir_eval.chord.root(merged_reference, merged_estimated), durations
        ),
        "majmin_wcsr": _weighted_score(
            mir_eval.chord.majmin(merged_reference, merged_estimated), durations
        ),
        "triad_wcsr": _weighted_score(
            mir_eval.chord.triads(merged_reference, merged_estimated), durations
        ),
        "no_chord": _no_chord_metrics(
            merged_reference, merged_estimated, durations
        ),
    }


def _weighted_score(comparisons: np.ndarray, durations: np.ndarray) -> float:
    return float(mir_eval.chord.weighted_accuracy(comparisons, durations))


def _no_chord_metrics(reference, estimated, durations) -> dict[str, float]:
    reference_duration = sum(
        float(duration)
        for label, duration in zip(reference, durations)
        if label == "N"
    )
    estimated_duration = sum(
        float(duration)
        for label, duration in zip(estimated, durations)
        if label == "N"
    )
    correct_duration = sum(
        float(duration)
        for ref_label, est_label, duration in zip(reference, estimated, durations)
        if ref_label == "N" and est_label == "N"
    )
    precision = (
        correct_duration / estimated_duration
        if estimated_duration
        else float(reference_duration == 0)
    )
    recall = (
        correct_duration / reference_duration
        if reference_duration
        else float(estimated_duration == 0)
    )
    return {
        "reference_duration": reference_duration,
        "estimated_duration": estimated_duration,
        "correct_duration": correct_duration,
        "precision": precision,
        "recall": recall,
    }


def _validate_interval_array(intervals, labels, name: str) -> None:
    if len(intervals) == 0:
        raise ValueError(f"{name} intervals cannot be empty.")
    if len(intervals) != len(labels):
        raise ValueError(f"{name} intervals and labels must have equal length.")
    previous_end = None
    for row in intervals:
        if len(row) != 2:
            raise ValueError(f"{name} interval is malformed.")
        start, end = float(row[0]), float(row[1])
        _validate_boundary(start, end, name)
        if previous_end is not None and start < previous_end:
            raise ValueError(f"{name} intervals overlap or are unsorted.")
        previous_end = end


def _validate_boundary(start: float, end: float, name: str) -> None:
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError(f"{name} interval has an invalid timestamp boundary.")
