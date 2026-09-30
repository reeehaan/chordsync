import pytest

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.evaluation.estimator_consensus import (
    normalize_estimator_label,
    sample_estimators_on_beats,
    summarize_estimator_region,
)


def _chord(start, end, label, source):
    return ChordSegment(
        start=start,
        end=end,
        raw_label=label,
        normalized_label=label,
        source=source,
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


def test_normalizes_flats_and_reports_quality_simplification():
    extended_minor = normalize_estimator_label("Bbm7")
    btc_extended_minor = normalize_estimator_label("B:min7")
    extended_major = normalize_estimator_label("Ab6")

    assert extended_minor.canonical_label == "A#m"
    assert extended_minor.simplifications == (
        "extended quality collapsed to minor",
    )
    assert btc_extended_minor.canonical_label == "Bm"
    assert btc_extended_minor.simplifications == (
        "extended quality collapsed to minor",
    )
    assert extended_major.canonical_label == "G#"
    assert extended_major.simplifications == (
        "extended quality collapsed to major",
    )


def test_samples_both_estimators_at_the_same_beats():
    btc = [_chord(0, 2, "C", "btc"), _chord(2, 4, "G", "btc")]
    chordino = [
        _chord(0, 1, "C", "chordino"),
        _chord(1, 4, "G", "chordino"),
    ]

    samples = sample_estimators_on_beats(btc, chordino, _beats(4))

    assert [(sample.btc_label, sample.chordino_label) for sample in samples] == [
        ("C", "C"),
        ("C", "G"),
        ("G", "G"),
        ("G", "G"),
    ]


def test_distinguishes_exact_root_and_quality_agreement():
    samples = sample_estimators_on_beats(
        [_chord(0, 4, "Cm", "btc")],
        [_chord(0, 2, "C", "chordino"), _chord(2, 4, "Cm", "chordino")],
        _beats(4),
    )
    result = summarize_estimator_region(samples, start=0, end=4)

    assert result.exact_agreement == 0.5
    assert result.root_agreement == 1.0
    assert result.quality_agreement == 0.5


def test_calculates_longest_disagreement_run_and_eight_beat_mean():
    btc = [_chord(0, 9, "C", "btc")]
    chordino = [
        _chord(0, 2, "C", "chordino"),
        _chord(2, 5, "G", "chordino"),
        _chord(5, 9, "C", "chordino"),
    ]
    samples = sample_estimators_on_beats(btc, chordino, _beats(9))

    result = summarize_estimator_region(samples, start=0, end=8)

    assert result.longest_disagreement_run_beats == 3
    assert result.longest_disagreement_run_seconds == 3.0
    assert result.disagreement_duration == 3.0
    assert result.mean_eight_beat_disagreement == pytest.approx(3 / 8)
