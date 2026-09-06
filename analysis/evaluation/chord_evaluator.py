from pathlib import Path

import mir_eval
import numpy as np

from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import normalize_chord_label


def to_mir_eval_label(label: str) -> str:
    """
    Convert the project's normalized chord label
    into mir_eval-compatible chord notation.

    Examples:
        C    -> C
        A#m  -> A#:min
        G#   -> G#
        N    -> N
    """

    if label == "N":
        return "N"

    if label.endswith("m"):
        return f"{label[:-1]}:min"

    return label


def load_reference_lab(
    lab_path: Path,
) -> tuple[np.ndarray, list[str]]:
    """
    Load a reference chord annotation file.

    Expected format:
        start end chord

    Example:
        0.000 1.500 C
        1.500 3.000 G
        3.000 5.000 A:min
    """

    if not lab_path.exists():
        raise FileNotFoundError(
            f"Reference lab file not found: {lab_path}"
        )

    intervals = []
    labels = []

    with lab_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            parts = line.split(maxsplit=2)

            if len(parts) != 3:
                continue

            start_text, end_text, label = parts

            try:
                start = float(start_text)
                end = float(end_text)
            except ValueError:
                continue

            normalized = normalize_chord_label(label)

            intervals.append([
                start,
                end,
            ])

            labels.append(
                to_mir_eval_label(normalized)
            )

    return np.asarray(
        intervals,
        dtype=float,
    ), labels


def segments_to_intervals(
    segments: list[ChordSegment],
) -> tuple[np.ndarray, list[str]]:
    """
    Convert ChordSegment objects into
    mir_eval interval and label arrays.
    """

    intervals = []
    labels = []

    for segment in segments:
        intervals.append([
            segment.start,
            segment.end,
        ])

        labels.append(
            to_mir_eval_label(
                segment.normalized_label
            )
        )

    return np.asarray(
        intervals,
        dtype=float,
    ), labels


def evaluate_chords(
    reference_intervals: np.ndarray,
    reference_labels: list[str],
    estimated_intervals: np.ndarray,
    estimated_labels: list[str],
) -> dict:
    """
    Evaluate estimated chords against reference annotations.

    Returns:
        root_wcsr:
            Weighted root accuracy.

        majmin_wcsr:
            Weighted major/minor chord accuracy.
    """

    if len(reference_intervals) == 0:
        raise ValueError(
            "Reference intervals cannot be empty."
        )

    if len(estimated_intervals) == 0:
        raise ValueError(
            "Estimated intervals cannot be empty."
        )

    evaluation_end = float(
        reference_intervals[-1][1]
    )

    ref_intervals, ref_labels = (
        mir_eval.util.adjust_intervals(
            reference_intervals,
            reference_labels,
            t_min=0.0,
            t_max=evaluation_end,
            start_label="N",
            end_label="N",
        )
    )

    est_intervals, est_labels = (
        mir_eval.util.adjust_intervals(
            estimated_intervals,
            estimated_labels,
            t_min=0.0,
            t_max=evaluation_end,
            start_label="N",
            end_label="N",
        )
    )

    (
        merged_intervals,
        merged_ref_labels,
        merged_est_labels,
    ) = mir_eval.util.merge_labeled_intervals(
        ref_intervals,
        ref_labels,
        est_intervals,
        est_labels,
    )

    durations = mir_eval.util.intervals_to_durations(
        merged_intervals
    )

    root_scores = mir_eval.chord.root(
        merged_ref_labels,
        merged_est_labels,
    )

    majmin_scores = mir_eval.chord.majmin(
        merged_ref_labels,
        merged_est_labels,
    )

    root_wcsr = mir_eval.chord.weighted_accuracy(
        root_scores,
        durations,
    )

    majmin_wcsr = mir_eval.chord.weighted_accuracy(
        majmin_scores,
        durations,
    )

    return {
        "root_wcsr": float(root_wcsr),
        "majmin_wcsr": float(majmin_wcsr),
    }
