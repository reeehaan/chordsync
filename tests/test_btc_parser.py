from pathlib import Path

from analysis.chords.btc.btc_parser import parse_btc_lab


def test_parse_btc_lab(tmp_path: Path):
    lab_file = tmp_path / "test.lab"

    lab_file.write_text(
        """0.000 0.278 N
0.278 1.481 A#:min
1.481 2.870 G#
2.870 5.278 C#
"""
    )

    segments = parse_btc_lab(lab_file)

    assert len(segments) == 4

    assert segments[0].start == 0.0
    assert segments[0].end == 0.278
    assert segments[0].raw_label == "N"
    assert segments[0].normalized_label == "N"
    assert segments[0].source == "btc"

    assert segments[1].raw_label == "A#:min"
    assert segments[1].normalized_label == "A#m"

    assert segments[2].normalized_label == "G#"
    assert segments[3].normalized_label == "C#"
