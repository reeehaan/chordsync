import json
from pathlib import Path

from analysis.beats.models import BeatEvent, BeatGrid
from analysis.chords.models import ChordSegment
from analysis.temporal.bar_grouper import group_into_bars
from analysis.temporal.chord_beat_aligner import (
    align_chords_to_beats,
    chord_at_time,
)
from analysis.temporal.models import TimelineEvent
from analysis.temporal.timeline_exporter import (
    export_timeline_json,
)


def test_chord_at_time_returns_matching_chord():
    chords = [
        ChordSegment(
            start=0.0,
            end=1.0,
            raw_label="C",
            normalized_label="C",
            source="test",
        ),
        ChordSegment(
            start=1.0,
            end=2.0,
            raw_label="G",
            normalized_label="G",
            source="test",
        ),
    ]

    result = chord_at_time(1.5, chords)

    assert result is not None
    assert result.normalized_label == "G"


def test_align_chords_to_beats():
    beats = [
        BeatEvent(
            time=0.25,
            beat_number=1,
            is_downbeat=True,
            source="test",
        ),
        BeatEvent(
            time=1.25,
            beat_number=2,
            is_downbeat=False,
            source="test",
        ),
    ]

    chords = [
        ChordSegment(
            start=0.0,
            end=1.0,
            raw_label="C",
            normalized_label="C",
            source="test",
        ),
        ChordSegment(
            start=1.0,
            end=2.0,
            raw_label="G",
            normalized_label="G",
            source="test",
        ),
    ]

    aligned = align_chords_to_beats(
        beats,
        chords,
    )

    assert len(aligned) == 2
    assert aligned[0].chord == "C"
    assert aligned[1].chord == "G"


def test_align_chords_to_beats_snaps_onset_to_nearest_beat():
    # Chord estimator says G starts at 1.05s, but the nearest beat is 1.0s
    # (the estimator overshot slightly); the beat two beats later is 2.0s.
    beats = [
        BeatEvent(time=0.0, beat_number=1, is_downbeat=True, source="test"),
        BeatEvent(time=1.0, beat_number=2, is_downbeat=False, source="test"),
        BeatEvent(time=2.0, beat_number=3, is_downbeat=False, source="test"),
    ]

    chords = [
        ChordSegment(
            start=0.0, end=1.05, raw_label="C", normalized_label="C", source="test"
        ),
        ChordSegment(
            start=1.05, end=3.0, raw_label="G", normalized_label="G", source="test"
        ),
    ]

    aligned = align_chords_to_beats(beats, chords)

    # Without snapping, the beat at 1.0s still falls inside the C segment
    # (0.0-1.05) and G would only appear a full beat later, at 2.0s.
    assert [event.chord for event in aligned] == ["C", "G", "G"]


def test_align_chords_to_beats_does_not_snap_a_distant_off_beat_change():
    beats = [
        BeatEvent(time=0.0, beat_number=1, is_downbeat=True, source="test"),
        BeatEvent(time=1.0, beat_number=2, is_downbeat=False, source="test"),
        BeatEvent(time=2.0, beat_number=3, is_downbeat=False, source="test"),
    ]
    chords = [
        ChordSegment(
            start=0.0, end=1.4, raw_label="C", normalized_label="C", source="test"
        ),
        ChordSegment(
            start=1.4, end=3.0, raw_label="G", normalized_label="G", source="test"
        ),
    ]

    aligned = align_chords_to_beats(beats, chords)

    assert [event.chord for event in aligned] == ["C", "C", "G"]


def test_align_chords_to_beats_does_not_collapse_adjacent_changes():
    beats = [
        BeatEvent(time=0.0, beat_number=1, is_downbeat=True, source="test"),
        BeatEvent(time=1.0, beat_number=2, is_downbeat=False, source="test"),
        BeatEvent(time=2.0, beat_number=3, is_downbeat=False, source="test"),
    ]
    chords = [
        ChordSegment(
            start=0.0, end=0.95, raw_label="C", normalized_label="C", source="test"
        ),
        ChordSegment(
            start=0.95, end=1.05, raw_label="G", normalized_label="G", source="test"
        ),
        ChordSegment(
            start=1.05, end=3.0, raw_label="Am", normalized_label="Am", source="test"
        ),
    ]

    aligned = align_chords_to_beats(beats, chords)

    assert [event.chord for event in aligned] == ["C", "G", "Am"]


def test_group_into_bars():
    events = [
        TimelineEvent(
            time=0.0,
            beat_number=1,
            is_downbeat=True,
            chord="C",
        ),
        TimelineEvent(
            time=1.0,
            beat_number=2,
            is_downbeat=False,
            chord="C",
        ),
        TimelineEvent(
            time=2.0,
            beat_number=3,
            is_downbeat=False,
            chord="G",
        ),
        TimelineEvent(
            time=3.0,
            beat_number=4,
            is_downbeat=False,
            chord="G",
        ),
        TimelineEvent(
            time=4.0,
            beat_number=1,
            is_downbeat=True,
            chord="Am",
        ),
        TimelineEvent(
            time=5.0,
            beat_number=2,
            is_downbeat=False,
            chord="Am",
        ),
    ]

    bars = group_into_bars(events)

    assert len(bars) == 2

    assert bars[0].bar_number == 1
    assert len(bars[0].beats) == 4
    assert bars[0].start_time == 0.0
    assert bars[0].end_time == 4.0

    assert bars[1].bar_number == 2
    assert len(bars[1].beats) == 2


def test_export_timeline_json(tmp_path: Path):
    grid = BeatGrid(
        bpm=70.59,
        beats_per_bar=4,
        beats=[
            BeatEvent(
                time=0.0,
                beat_number=1,
                is_downbeat=True,
                source="test",
            )
        ],
        source="test",
    )

    events = [
        TimelineEvent(
            time=0.0,
            beat_number=1,
            is_downbeat=True,
            chord="C",
        ),
        TimelineEvent(
            time=1.0,
            beat_number=2,
            is_downbeat=False,
            chord="C",
        ),
    ]

    bars = group_into_bars(events)

    output_path = tmp_path / "timeline.json"

    export_timeline_json(
        output_path,
        grid,
        bars,
    )

    assert output_path.exists()

    data = json.loads(
        output_path.read_text(
            encoding="utf-8"
        )
    )

    assert data["bpm"] == 70.59
    assert data["beats_per_bar"] == 4
    assert data["source"] == "test"

    assert len(data["bars"]) == 1

    first_bar = data["bars"][0]

    assert first_bar["bar_number"] == 1
    assert first_bar["beats"][0]["chord"] == "C"
    assert first_bar["beats"][0]["is_downbeat"] is True
