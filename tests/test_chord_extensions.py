"""Chord extensions: a plain triad becomes 7, maj7, m7, sus2 or sus4 only where
BTC's large model and the sounding notes agree."""

import math
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from analysis.chords import extensions as ex
from analysis.chords.models import ChordSegment

C, D, E, G, A = 0, 2, 4, 7, 9


def profile(**notes: float) -> np.ndarray:
    """Note strengths measured from the root: root and fifth always sound."""
    names = {"root": 0, "b2": 1, "2": 2, "b3": 3, "3": 4, "4": 5, "b5": 6,
             "5": 7, "b6": 8, "6": 9, "b7": 10, "M7": 11}
    values = np.full(12, 0.05)
    values[0] = 1.0
    values[7] = 0.7
    for name, strength in notes.items():
        values[names[name]] = strength
    return values


# --- what the notes say ------------------------------------------------------


@pytest.mark.parametrize(
    "notes, triad, expected",
    [
        (dict(**{"3": 0.6}), "maj", "maj"),
        (dict(**{"b3": 0.6}), "min", "min"),
        (dict(**{"3": 0.6, "b7": 0.45}), "maj", "7"),
        (dict(**{"3": 0.6, "M7": 0.5}), "maj", "maj7"),
        (dict(**{"b3": 0.55, "b7": 0.3}), "min", "m7"),
        (dict(**{"4": 0.5}), "maj", "sus4"),
        (dict(**{"2": 0.55}), "min", "sus2"),
    ],
)
def test_note_check_names_the_chord_the_notes_describe(notes, triad, expected):
    assert ex.note_check(profile(**notes), triad) == expected


def test_faint_extra_notes_do_not_make_an_extension():
    # The levels seen on plain chords in real recordings: nothing is above the bars.
    assert ex.note_check(profile(**{"3": 0.6, "b7": 0.12, "M7": 0.2}), "maj") == "maj"
    assert ex.note_check(profile(**{"b3": 0.6, "b7": 0.11}), "min") == "min"
    # A strong third rules sus out, however loud the 2nd or 4th is.
    assert ex.note_check(profile(**{"3": 0.5, "4": 0.6, "2": 0.5}), "maj") == "maj"


def test_a_seventh_needs_the_right_third():
    # The seventh of a minor chord does not make a dominant 7.
    assert ex.note_check(profile(**{"b3": 0.6, "b7": 0.5}), "maj") == "maj"
    assert ex.note_check(profile(**{"3": 0.6, "b7": 0.5}), "min") == "min"


# --- reading labels -----------------------------------------------------------


def test_plain_labels_are_read_and_extended_ones_are_not():
    assert ex.parse_plain_label("F#m") == (6, "min")
    assert ex.parse_plain_label("A") == (9, "maj")
    for label in ("N", "Cmaj7", "Em7", "Dsus4", "", "H"):
        assert ex.parse_plain_label(label) is None


def test_large_labels_give_only_the_extensions_we_show():
    assert ex.parse_large_label("A:sus4") == (9, "sus4")
    assert ex.parse_large_label("E:min7") == (4, "m7")
    assert ex.parse_large_label("C:maj7") == (0, "maj7")
    assert ex.parse_large_label("G:7") == (7, "7")
    # Triads, rare types, "none" and "unknown" are not extensions we offer.
    for label in ("A", "A:min", "E:min6", "B:hdim7", "C:dim7", "C:aug", "N", "X", "H:sus4"):
        assert ex.parse_large_label(label) is None


# --- the two-vote rule --------------------------------------------------------


def chord(start, end, label):
    return ChordSegment(start=start, end=end, raw_label=label, normalized_label=label, source="btc")


def chroma_with(profile_values: np.ndarray, root: int, seconds=10.0) -> ex.Chroma:
    """A stand-in recording in which every moment has the given note strengths."""
    times = np.arange(0.0, seconds, 0.1)
    rolled = np.roll(profile_values, root)
    return ex.Chroma(values=np.tile(rolled[:, None], (1, len(times))), times=times)


def large(*segments):
    return [{"start": s, "end": e, "label": label} for s, e, label in segments]


def test_both_agreeing_upgrades_the_chord():
    notes = chroma_with(profile(**{"b3": 0.55, "b7": 0.3}), E)
    result = ex.extend_chords(
        [chord(0, 4, "Em")], large((0, 4, "E:min7")), notes
    )
    assert [c.normalized_label for c in result] == ["Em7"]
    # Everything else about the segment is untouched.
    assert (result[0].start, result[0].end, result[0].raw_label) == (0, 4, "Em")


@pytest.mark.parametrize(
    "why, notes, large_label, minutes",
    [
        ("the large model says nothing special", dict(**{"b3": 0.55, "b7": 0.3}), "E:min", 4),
        ("the notes say nothing special", dict(**{"b3": 0.55}), "E:min7", 4),
        ("they name different extensions", dict(**{"3": 0.6, "b7": 0.4}), "E:maj7", 4),
        ("the large model has another root", dict(**{"b3": 0.55, "b7": 0.3}), "G:min7", 4),
        ("the chord is too short to judge", dict(**{"b3": 0.55, "b7": 0.3}), "E:min7", 0.5),
    ],
)
def test_a_missing_vote_leaves_the_triad(why, notes, large_label, minutes):
    root = E
    chroma = chroma_with(profile(**notes), root)
    result = ex.extend_chords(
        [chord(0, minutes, "Em")], large((0, minutes, large_label)), chroma
    )
    assert result[0].normalized_label == "Em", why


def test_no_chord_and_already_extended_labels_are_left_alone():
    chroma = chroma_with(profile(**{"4": 0.6}), C)
    chords = [chord(0, 2, "N"), chord(2, 4, "Csus4")]
    result = ex.extend_chords(chords, large((0, 4, "C:sus4")), chroma)
    assert [c.normalized_label for c in result] == ["N", "Csus4"]


def test_each_chord_is_judged_on_its_own_stretch():
    chroma = chroma_with(profile(**{"3": 0.6, "b7": 0.45}), G)
    chords = [chord(0, 4, "G"), chord(4, 8, "G")]
    # The large model only hears a seventh in the first half.
    result = ex.extend_chords(chords, large((0, 4, "G:7"), (4, 8, "G")), chroma)
    assert [c.normalized_label for c in result] == ["G7", "G"]


# --- real audio ---------------------------------------------------------------


def _guitar_wav(path: Path, frets, capo=0, seconds=3.0, rate=22050):
    open_strings = [40, 45, 50, 55, 59, 64]
    t = np.arange(int(seconds * rate)) / rate
    mix = np.zeros_like(t)
    for strum in (0.0, 1.5):
        for string, fret in enumerate(frets):
            if fret < 0:
                continue
            frequency = 440.0 * 2 ** ((open_strings[string] + fret + capo - 69) / 12)
            onset = int((strum + string * 0.04) * rate)
            n = len(t) - onset
            tt = np.arange(n) / rate
            tone = sum(np.sin(2 * math.pi * frequency * h * tt) / h for h in range(1, 7))
            mix[onset:] += tone * np.exp(-tt * 1.6) * (1 - np.exp(-tt * 200))
    mix /= np.abs(mix).max()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(struct.pack("<h", int(v * 30000)) for v in mix))


@pytest.mark.parametrize(
    "frets, root, triad, expected",
    [
        ([-1, 3, 2, 0, 1, 0], C, "maj", "maj"),     # C
        ([-1, 3, 2, 0, 0, 0], C, "maj", "maj7"),    # Cmaj7
        ([3, 2, 0, 0, 0, 1], G, "maj", "7"),        # G7
        ([-1, -1, 0, 2, 3, 3], D, "maj", "sus4"),   # Dsus4
        ([-1, 0, 2, 2, 0, 0], A, "maj", "sus2"),    # Asus2
        ([0, 2, 2, 0, 0, 0], E, "min", "min"),      # Em
        ([0, 2, 0, 0, 0, 0], E, "min", "m7"),       # Em7
    ],
)
def test_note_check_hears_synthesized_guitar_chords(tmp_path, frets, root, triad, expected):
    pytest.importorskip("librosa")
    audio = tmp_path / "chord.wav"
    _guitar_wav(audio, frets)

    chroma = ex.chroma_from_audio(audio)
    measured = ex.segment_profile(chroma, 0.0, 3.0, root)

    assert ex.note_check(measured, triad) == expected
