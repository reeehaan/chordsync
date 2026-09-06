from analysis.chords.chordino.chordino_runner import (
    parse_chordino_csv,
    events_to_segments,
)


def test_parse_chordino_csv():
    csv_data = """test.wav,0.000000000,N
test.wav,1.500000000,C
test.wav,3.000000000,G
"""

    events = parse_chordino_csv(csv_data)

    assert len(events) == 3
    assert events[0]["label"] == "N"
    assert events[1]["label"] == "C"
    assert events[2]["time"] == 3.0


def test_events_to_segments():
    events = [
        {"time": 0.0, "label": "N"},
        {"time": 1.5, "label": "C"},
        {"time": 3.0, "label": "G"},
    ]

    segments = events_to_segments(
        events,
        duration=5.0,
    )

    assert len(segments) == 3

    assert segments[0].start == 0.0
    assert segments[0].end == 1.5
    assert segments[0].raw_label == "N"
    assert segments[0].normalized_label == "N"
    assert segments[0].source == "chordino"

    assert segments[1].start == 1.5
    assert segments[1].end == 3.0
    assert segments[1].raw_label == "C"
    assert segments[1].normalized_label == "C"
    assert segments[1].source == "chordino"

    assert segments[2].start == 3.0
    assert segments[2].end == 5.0
    assert segments[2].raw_label == "G"
    assert segments[2].normalized_label == "G"
    assert segments[2].source == "chordino"
