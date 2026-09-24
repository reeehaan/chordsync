import sys

import pytest

from analysis.chords.btc.btc_inference import (
    _frames_to_segments,
    _smooth_frame_labels,
    _stabilize_segments,
)


@pytest.fixture(autouse=True, scope="module")
def _cleanup_btc_inference_import():
    # Importing this module for its pure-Python helpers otherwise leaks it
    # into sys.modules for the rest of the pytest session, tripping the
    # guard in test_real_analysis_processor.py that checks the lightweight
    # API path never pulls in the heavy BTC module.
    yield
    sys.modules.pop("analysis.chords.btc.btc_inference", None)


def test_smoothing_removes_single_frame_flicker():
    # A single stray frame in the middle of a long run of the same label.
    labels = [0] * 5 + [7] + [0] * 5

    smoothed = _smooth_frame_labels(labels, window=5)

    assert smoothed == [0] * 11


def test_smoothing_preserves_a_genuine_multi_frame_change():
    labels = [0] * 5 + [3] * 5 + [0] * 5

    smoothed = _smooth_frame_labels(labels, window=3)

    assert smoothed[5:10] == [3] * 5


def test_smoothing_is_a_no_op_below_the_window_size():
    labels = [1, 2, 1]

    assert _smooth_frame_labels(labels, window=7) == labels


def test_frames_to_segments_ignores_flicker_after_smoothing():
    vocabulary = {0: "C", 1: "G", 7: "D#"}
    # Without smoothing this single frame would create a spurious D# segment.
    raw_labels = [0] * 5 + [7] + [0] * 5

    smoothed = _smooth_frame_labels(raw_labels, window=5)
    segments = _frames_to_segments(
        smoothed, time_unit=0.1, song_length=1.1, vocabulary=vocabulary
    )

    assert len(segments) == 1
    assert segments[0]["label"] == "C"


def _segment(start, end, label):
    return {"start": start, "end": end, "label": label}


def test_stability_merges_a_short_a_b_a_interruption():
    segments = [
        _segment(0.0, 1.0, "D"),
        _segment(1.0, 1.3, "F#"),
        _segment(1.3, 2.0, "D"),
    ]

    assert _stabilize_segments(segments, max_interruption_seconds=0.4) == [
        _segment(0.0, 2.0, "D")
    ]


def test_stability_preserves_a_long_a_b_a_middle_segment():
    segments = [
        _segment(0.0, 1.0, "D"),
        _segment(1.0, 1.6, "F#"),
        _segment(1.6, 2.4, "D"),
    ]

    assert _stabilize_segments(segments, max_interruption_seconds=0.4) == segments


def test_stability_does_not_blindly_remove_short_a_b_c_transition():
    segments = [
        _segment(0.0, 1.0, "D"),
        _segment(1.0, 1.2, "F#"),
        _segment(1.2, 2.0, "A"),
    ]

    assert _stabilize_segments(segments, max_interruption_seconds=0.4) == segments


def test_stability_can_merge_short_n_between_the_same_chord():
    segments = [
        _segment(0.0, 1.0, "D"),
        _segment(1.0, 1.2, "N"),
        _segment(1.2, 2.0, "D"),
    ]

    assert _stabilize_segments(segments, max_interruption_seconds=0.4) == [
        _segment(0.0, 2.0, "D")
    ]


def test_stability_keeps_output_contiguous_after_merge():
    segments = [
        _segment(0.0, 0.6, "G"),
        _segment(0.6, 0.9, "C"),
        _segment(0.9, 1.5, "G"),
        _segment(1.5, 2.0, "D"),
    ]

    cleaned = _stabilize_segments(segments, max_interruption_seconds=0.4)

    assert cleaned == [_segment(0.0, 1.5, "G"), _segment(1.5, 2.0, "D")]
    assert all(left["end"] == right["start"] for left, right in zip(cleaned, cleaned[1:]))
