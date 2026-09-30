import pytest

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.evaluation.acoustic_evidence import (
    chord_disagreement_rate,
    measure_acoustic_region,
)


def _chord(start, end, label):
    return ChordSegment(
        start=start,
        end=end,
        raw_label=label,
        normalized_label=label,
        source="test",
    )


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


def test_measures_clipped_region_without_changing_timestamps():
    evidence = measure_acoustic_region(
        [_chord(0, 4, "C"), _chord(4, 8, "G")],
        _beats(9),
        start=2,
        end=6,
    )

    assert evidence.sequence == ("C", "G")
    assert evidence.runs == ((2, 4.0, "C"), (4.0, 6, "G"))
    assert evidence.segment_count == 2
    assert evidence.unique_chord_count == 2
    assert evidence.average_run_duration == 2
    assert evidence.beat_alignment_ratio == 1


def test_disagreement_is_weighted_by_time_not_segment_count():
    left = [_chord(0, 8, "C")]
    right = [_chord(0, 2, "G"), _chord(2, 8, "C")]

    assert chord_disagreement_rate(left, right, start=0, end=8) == pytest.approx(0.25)


def test_rejects_invalid_regions():
    with pytest.raises(ValueError, match="end must be greater"):
        chord_disagreement_rate([], [], start=2, end=2)
