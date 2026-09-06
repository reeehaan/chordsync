from analysis.chords.normalizer import normalize_chord_label


def test_major_chord():
    assert normalize_chord_label("C") == "C"


def test_minor_chord():
    assert normalize_chord_label("Bbm") == "A#m"


def test_minor_seventh_chord():
    assert normalize_chord_label("Bbm7") == "A#m"


def test_sixth_chord():
    assert normalize_chord_label("Ab6") == "G#"


def test_slash_chord():
    assert normalize_chord_label("F#7/A#") == "F#"


def test_no_chord():
    assert normalize_chord_label("N") == "N"


def test_btc_minor():
    assert normalize_chord_label("A#:min") == "A#m"


def test_flat_to_sharp_major():
    assert normalize_chord_label("Ab") == "G#"


def test_flat_to_sharp_minor():
    assert normalize_chord_label("Bbm") == "A#m"


def test_enharmonic_equivalence():
    assert normalize_chord_label("Bbm") == normalize_chord_label("A#:min")
