import math

import pytest

from analysis.beats.models import BeatEvent
from analysis.evaluation.btc_uncertainty import (
    aggregate_uncertainty_windows,
    measure_frame_uncertainty,
)


def _beat(time):
    return BeatEvent(time=time, beat_number=1, is_downbeat=True, source="test")


def test_measures_top_scores_margin_and_predicted_label():
    frame = measure_frame_uncertainty(
        [0.1, 0.7, 0.2], time=1.5, labels=["C", "G", "Am"]
    )

    assert frame.time == 1.5
    assert frame.predicted_index == 1
    assert frame.predicted_label == "G"
    assert frame.top1_score == pytest.approx(0.7)
    assert frame.top2_score == pytest.approx(0.2)
    assert frame.margin == pytest.approx(0.5)


def test_entropy_is_normalized_and_handles_ties_and_one_class():
    tied = measure_frame_uncertainty([0.5, 0.5])
    certain = measure_frame_uncertainty([1.0, 0.0])
    single = measure_frame_uncertainty([1.0])

    assert tied.margin == 0.0
    assert tied.normalized_entropy == pytest.approx(1.0)
    assert certain.normalized_entropy == 0.0
    assert single.top2_score == 0.0
    assert single.margin == 1.0
    assert single.normalized_entropy == 0.0


def test_entropy_uses_normalized_scores_without_assuming_exact_sum():
    frame = measure_frame_uncertainty([2.0, 1.0, 1.0])
    expected = -(0.5 * math.log(0.5) + 2 * 0.25 * math.log(0.25)) / math.log(3)

    assert frame.normalized_entropy == pytest.approx(expected)


def test_aggregates_frames_over_non_overlapping_eight_beat_windows():
    probabilities = ([0.9, 0.1], [0.55, 0.45], [0.8, 0.2], [0.4, 0.6])
    frames = [
        measure_frame_uncertainty(scores, time=time)
        for time, scores in zip((0.5, 4.5, 8.5, 12.5), probabilities)
    ]
    windows = aggregate_uncertainty_windows(
        frames,
        [_beat(float(time)) for time in range(17)],
        low_margin_threshold=0.15,
        high_entropy_threshold=0.9,
    )

    assert [(window.start, window.end) for window in windows] == [
        (0.0, 8.0),
        (8.0, 16.0),
    ]
    assert windows[0].frame_count == 2
    assert windows[0].mean_margin == pytest.approx(0.45)
    assert windows[0].minimum_margin == pytest.approx(0.1)
    assert windows[0].low_margin_ratio == 0.5
    assert windows[0].label_change_frequency == 0.0
    assert windows[1].label_change_frequency == 1.0


def test_rejects_invalid_probability_vectors():
    with pytest.raises(ValueError, match="at least one"):
        measure_frame_uncertainty([])
    with pytest.raises(ValueError, match="non-negative"):
        measure_frame_uncertainty([1.1, -0.1])
    with pytest.raises(ValueError, match="positive sum"):
        measure_frame_uncertainty([0.0, 0.0])
