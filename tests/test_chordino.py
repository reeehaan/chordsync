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

    assert segments == [
        {
            "start": 0.0,
            "end": 1.5,
            "label": "N",
        },
        {
            "start": 1.5,
            "end": 3.0,
            "label": "C",
        },
        {
            "start": 3.0,
            "end": 5.0,
            "label": "G",
        },
    ]
