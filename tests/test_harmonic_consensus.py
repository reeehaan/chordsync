import pytest

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.evaluation.harmonic_consensus import (
    build_harmonic_windows,
    compare_harmonic_windows,
    find_repeated_families,
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


def _window(labels):
    chords = [_chord(index, index + 1, label) for index, label in enumerate(labels)]
    return build_harmonic_windows(
        chords,
        _beats(len(labels) + 1),
        bars_per_window=1,
        beats_per_bar=len(labels),
    )[0]


def test_normalizes_roots_relative_to_first_pitched_chord():
    window = _window(["D", "G", "Bm", "A"])

    assert window.root_intervals == (0, 5, 9, 7)
    assert window.qualities == ("major", "major", "minor", "major")


def test_transposition_invariant_comparison_recognizes_same_progression():
    left = _window(["D", "G", "Bm", "A"])
    right = _window(["E", "A", "C#m", "B"])
    similarity = compare_harmonic_windows(left, right)

    assert similarity.exact_agreement == 0.0
    assert similarity.transposition_invariant_agreement == 1.0
    assert similarity.change_position_agreement == 1.0
    assert similarity.repeated_progression_similarity == pytest.approx(0.85)


def test_major_minor_quality_is_not_discarded():
    major = _window(["C", "F", "G", "C"])
    minor = _window(["Cm", "Fm", "Gm", "Cm"])

    similarity = compare_harmonic_windows(major, minor)

    assert similarity.transposition_invariant_agreement == 0.0
    assert similarity.repeated_progression_similarity < 0.5


def test_detects_repeated_family_and_leaves_unique_section_unclassified():
    repeated = _window(["C", "F", "Am", "G"])
    transposed = _window(["D", "G", "Bm", "A"])
    unique = _window(["C", "C", "C", "C"])

    families = find_repeated_families([repeated, transposed, unique])

    assert [family.member_indexes for family in families] == [(0, 1)]
