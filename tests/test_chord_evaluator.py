import numpy as np

from analysis.evaluation.chord_evaluator import (
    evaluate_chords,
)


def test_perfect_chord_evaluation():
    reference_intervals = np.array([
        [0.0, 1.0],
        [1.0, 2.0],
        [2.0, 3.0],
    ])

    reference_labels = [
        "C",
        "G",
        "A:min",
    ]

    estimated_intervals = np.array([
        [0.0, 1.0],
        [1.0, 2.0],
        [2.0, 3.0],
    ])

    estimated_labels = [
        "C",
        "G",
        "A:min",
    ]

    result = evaluate_chords(
        reference_intervals,
        reference_labels,
        estimated_intervals,
        estimated_labels,
    )

    assert result["root_wcsr"] == 1.0
    assert result["majmin_wcsr"] == 1.0
