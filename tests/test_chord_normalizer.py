from analysis.chords.normalizer import normalize_chord_label


def test_major_chord():
    assert normalize_chord_label("C") == "C"


def test_minor_chord():
    assert normalize_chord_label("Bbm") == "Bbm"


def test_minor_seventh_chord():
    assert normalize_chord_label("Bbm7") == "Bbm"


def test_sixth_chord():
    assert normalize_chord_label("Ab6") == "Ab"


def test_slash_chord():
    assert normalize_chord_label("F#7/A#") == "F#"


def test_no_chord():
    assert normalize_chord_label("N") == "N"
