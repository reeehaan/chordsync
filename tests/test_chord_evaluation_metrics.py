from pathlib import Path

import numpy as np
import pytest

from analysis.chords.models import ChordSegment
from analysis.evaluation.chord_evaluator import (
    evaluate_chords,
    load_reference_lab,
    segments_to_intervals,
)


def intervals(*rows):
    return np.asarray(rows, dtype=float)


def evaluate(reference_intervals, reference_labels, estimated_intervals, labels):
    return evaluate_chords(
        intervals(*reference_intervals),
        list(reference_labels),
        intervals(*estimated_intervals),
        list(labels),
    )


def test_perfect_prediction_has_perfect_duration_weighted_scores():
    result = evaluate(
        [(0, 1), (1, 2), (2, 3)],
        ["C", "A:min", "N"],
        [(0, 1), (1, 2), (2, 3)],
        ["C:maj", "Am", "N"],
    )

    assert result["root_wcsr"] == 1.0
    assert result["majmin_wcsr"] == 1.0
    assert result["triad_wcsr"] == 1.0
    assert result["no_chord"] == {
        "reference_duration": 1.0,
        "estimated_duration": 1.0,
        "correct_duration": 1.0,
        "precision": 1.0,
        "recall": 1.0,
    }


def test_completely_wrong_roots_score_zero():
    result = evaluate([(0, 2)], ["C"], [(0, 2)], ["F#:min"])

    assert result["root_wcsr"] == 0.0
    assert result["majmin_wcsr"] == 0.0
    assert result["triad_wcsr"] == 0.0


def test_major_minor_mismatch_preserves_root_but_not_quality():
    result = evaluate([(0, 2)], ["C"], [(0, 2)], ["C:min"])

    assert result["root_wcsr"] == 1.0
    assert result["majmin_wcsr"] == 0.0
    assert result["triad_wcsr"] == 0.0


def test_no_chord_statistics_are_duration_weighted():
    result = evaluate(
        [(0, 1), (1, 2)],
        ["N", "C"],
        [(0, 0.5), (0.5, 2)],
        ["N", "C"],
    )

    assert result["no_chord"] == {
        "reference_duration": 1.0,
        "estimated_duration": 0.5,
        "correct_duration": 0.5,
        "precision": 1.0,
        "recall": 0.5,
    }


def test_different_boundaries_are_aligned_by_duration():
    result = evaluate(
        [(0, 2), (2, 4)],
        ["C", "G"],
        [(0, 1), (1, 4)],
        ["C", "G"],
    )

    assert result["root_wcsr"] == 0.75


def test_prediction_shorter_than_reference_is_filled_with_no_chord():
    result = evaluate([(0, 2)], ["C"], [(0, 1)], ["C"])

    assert result["root_wcsr"] == 0.5


def test_prediction_longer_than_reference_is_clipped():
    result = evaluate([(0, 1)], ["C"], [(0, 2)], ["C"])

    assert result["root_wcsr"] == 1.0


def test_adjacent_identical_labels_do_not_change_score():
    result = evaluate([(0, 2)], ["C"], [(0, 1), (1, 2)], ["C", "C"])

    assert result["triad_wcsr"] == 1.0


@pytest.mark.parametrize(
    "contents, message",
    [
        ("not a valid row\n", "malformed"),
        ("0 2 C\n1 3 G\n", "overlap"),
        ("-1 1 C\n", "timestamp"),
        ("0 0 C\n", "timestamp"),
    ],
)
def test_invalid_reference_annotations_are_rejected(tmp_path, contents, message):
    reference = tmp_path / "reference.lab"
    reference.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_reference_lab(reference)


def test_estimator_segment_order_does_not_change_score():
    segments = [
        ChordSegment(
            start=1,
            end=2,
            raw_label="G:maj",
            normalized_label="wrong",
            source="btc",
        ),
        ChordSegment(
            start=0,
            end=1,
            raw_label="C:maj",
            normalized_label="wrong",
            source="btc",
        ),
    ]

    estimated_intervals, labels = segments_to_intervals(segments)
    result = evaluate_chords(
        intervals((0, 1), (1, 2)),
        ["C", "G"],
        estimated_intervals,
        labels,
    )

    assert result["root_wcsr"] == 1.0
    assert labels == ["C", "G"]
