import pytest

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.evaluation.chord_reliability import build_reliability_windows


def _beats(count):
    return [
        BeatEvent(
            time=float(index),
            beat_number=index % 4 + 1,
            is_downbeat=index % 4 == 0,
            source="test",
        )
        for index in range(count)
    ]


def _chord(start, end, label):
    return ChordSegment(
        start=start,
        end=end,
        raw_label=label,
        normalized_label=label,
        source="btc",
    )


def test_builds_non_overlapping_eight_beat_windows():
    windows = build_reliability_windows([_chord(0, 16, "C")], _beats(17))

    assert [(window.start, window.end) for window in windows] == [
        (0.0, 8.0),
        (8.0, 16.0),
    ]


def test_measures_chord_runs_churn_and_repetition():
    windows = build_reliability_windows(
        [_chord(0, 2, "C"), _chord(2, 4, "G"), _chord(4, 8, "C")],
        _beats(9),
    )

    features = windows[0]
    assert features.chord_changes == 2
    assert features.unique_chords == 2
    assert features.average_run_duration == pytest.approx(8 / 3)
    assert features.shortest_run_duration == 2
    assert features.churn_per_beat == pytest.approx(2 / 8)
    assert features.repeat_consistency == 0.5


def test_detects_rapid_and_off_beat_boundaries():
    window = build_reliability_windows(
        [_chord(-2, 0.1, "C"), _chord(0.1, 0.4, "D"), _chord(0.4, 10, "C")],
        _beats(9),
    )[0]

    assert window.rapid_transition_count == 1
    assert window.shortest_run_duration == pytest.approx(0.3)
    assert window.beat_alignment_ratio == 0.5


def test_measures_no_chord_duration_without_assuming_unreliability():
    window = build_reliability_windows(
        [_chord(0, 4, "N"), _chord(4, 8, "C")],
        _beats(9),
    )[0]

    assert window.no_chord_ratio == 0.5
    assert window.rapid_transition_count == 0
