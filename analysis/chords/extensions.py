"""Beginner-friendly chord extensions on top of BTC's plain major/minor chords.

BTC's standard model only knows major, minor and "no chord". This module adds
the few extensions a beginner can play: 7, maj7, m7, sus2 and sus4. It never
trusts a single source. A chord is only upgraded where two independent
opinions name the same extension on the same stretch of the song:

1. BTC's large-vocabulary model, which labels the same audio with 170 chords.
2. A note check: which notes are actually sounding in the instrumental
   (vocals removed) audio, measured against the chord's root.

Wherever they disagree the chord stays a plain triad. A missing extension costs
a beginner nothing (the triad is easier to play); a wrong one is a harder chord
that is not in the song, so the rule favours being right over finding more.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from analysis.chords.models import ChordSegment

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NOTE_INDEX = {name: index for index, name in enumerate(NOTE_NAMES)}

# The extensions that can be shown, and how each is written after the root.
EXTENSION_SUFFIX: Mapping[str, str] = {
    "7": "7",
    "maj7": "maj7",
    "m7": "m7",
    "sus2": "sus2",
    "sus4": "sus4",
}

# BTC large-vocabulary chord types that correspond to one of those extensions.
_LARGE_TO_EXTENSION: Mapping[str, str] = {
    "7": "7",
    "maj7": "maj7",
    "min7": "m7",
    "sus2": "sus2",
    "sus4": "sus4",
}

# How strong a note must be, as a fraction of the chord's strongest note, to
# count as sounding. Extension notes are quieter than the root and fifth, but
# on plain chords they sit near zero, so these bars are low.
SEVENTH = 0.20
MAJOR_SEVENTH = 0.30
SUS4_NOTE = 0.25
SUS2_NOTE = 0.30
THIRD_PRESENT = 0.30
THIRD_ABSENT = 0.30

# Shorter chords are too brief to judge.
MINIMUM_SECONDS = 0.8

_SAMPLE_RATE = 22050
_HOP_LENGTH = 2048  # about 93 ms, the step BTC itself uses


@dataclass(frozen=True)
class Chroma:
    """How much of each of the 12 notes sounds, frame by frame."""

    values: np.ndarray  # shape (12, frames)
    times: np.ndarray  # seconds, one per frame


def chroma_from_audio(audio_path: Path) -> Chroma:
    """Harmonic-only chroma of an audio file (drums and noise are filtered out)."""
    import librosa  # imported here: only the analysis worker has it installed

    samples, _ = librosa.load(str(audio_path), sr=_SAMPLE_RATE, mono=True)
    harmonic = librosa.effects.harmonic(samples, margin=3.0)
    tuning = librosa.estimate_tuning(y=harmonic, sr=_SAMPLE_RATE)
    values = librosa.feature.chroma_cqt(
        y=harmonic,
        sr=_SAMPLE_RATE,
        hop_length=_HOP_LENGTH,
        tuning=tuning,
        n_chroma=12,
    )
    times = librosa.frames_to_time(
        np.arange(values.shape[1]), sr=_SAMPLE_RATE, hop_length=_HOP_LENGTH
    )
    return Chroma(values=values, times=times)


def segment_profile(
    chroma: Chroma, start: float, end: float, root: int
) -> np.ndarray | None:
    """The notes sounding in [start, end), measured from the root upward.

    Index 0 is the root, 3 the minor third, 4 the major third, 10 the minor
    seventh and so on, scaled so the strongest note is 1. The pick attack at the
    start is skipped, and the median ignores a passing melody note.
    """
    attack = min(0.15, (end - start) * 0.2)
    mask = (chroma.times >= start + attack) & (chroma.times < end)
    if int(mask.sum()) < 2:
        return None
    frames = chroma.values[:, mask]
    frames = frames / (frames.max(axis=0, keepdims=True) + 1e-9)
    profile = np.roll(np.median(frames, axis=1), -root)
    return profile / (profile.max() + 1e-9)


def note_check(profile: np.ndarray, triad: str) -> str:
    """What the sounding notes say this chord is: its triad or an extension.

    [triad] is "maj" or "min", as BTC labelled it.
    """
    third = max(profile[3], profile[4])
    if third < THIRD_ABSENT:
        # The third is missing and the 2nd or 4th takes its place: a sus chord.
        if profile[5] >= SUS4_NOTE and profile[5] >= profile[2]:
            return "sus4"
        if profile[2] >= SUS2_NOTE:
            return "sus2"
        return triad
    if triad == "maj" and profile[4] >= THIRD_PRESENT:
        if profile[10] >= SEVENTH and profile[10] > profile[11]:
            return "7"
        if profile[11] >= MAJOR_SEVENTH and profile[11] > profile[10]:
            return "maj7"
    if (
        triad == "min"
        and profile[3] >= THIRD_PRESENT
        and profile[10] >= SEVENTH
        and profile[10] > profile[11]
    ):
        return "m7"
    return triad


def parse_plain_label(label: str) -> tuple[int, str] | None:
    """(root, "maj" or "min") of a plain normalized label such as "F#m", else None."""
    if label.endswith("m") and label[:-1] in _NOTE_INDEX:
        return _NOTE_INDEX[label[:-1]], "min"
    if label in _NOTE_INDEX:
        return _NOTE_INDEX[label], "maj"
    return None


def parse_large_label(label: str) -> tuple[int, str] | None:
    """(root, extension) of a large-vocabulary label, or None when it has none.

    "A:sus4" gives (9, "sus4"); "E:min7" gives (4, "m7"). Triads, "N" and "X"
    give None: only the five extensions are of interest here.
    """
    root, separator, quality = label.partition(":")
    if not separator or root not in _NOTE_INDEX:
        return None
    extension = _LARGE_TO_EXTENSION.get(quality)
    return (_NOTE_INDEX[root], extension) if extension else None


def _label_at(predictions: Sequence[Mapping[str, object]], moment: float) -> str:
    for prediction in predictions:
        if float(prediction["start"]) <= moment < float(prediction["end"]):
            return str(prediction["label"])
    return "N"


def extend_chords(
    chords: Sequence[ChordSegment],
    large_predictions: Sequence[Mapping[str, object]],
    chroma: Chroma,
) -> list[ChordSegment]:
    """Chords with an extension wherever the large model and the notes agree."""
    result: list[ChordSegment] = []
    for chord in chords:
        extended = _extended(chord, large_predictions, chroma)
        result.append(extended if extended is not None else chord)
    return result


def _extended(
    chord: ChordSegment,
    large_predictions: Sequence[Mapping[str, object]],
    chroma: Chroma,
) -> ChordSegment | None:
    plain = parse_plain_label(chord.normalized_label)
    if plain is None or chord.end - chord.start < MINIMUM_SECONDS:
        return None
    root, triad = plain

    middle = (chord.start + chord.end) / 2
    from_large = parse_large_label(_label_at(large_predictions, middle))
    if from_large is None or from_large[0] != root:
        return None

    profile = segment_profile(chroma, chord.start, chord.end, root)
    if profile is None or note_check(profile, triad) != from_large[1]:
        return None

    return chord.model_copy(
        update={
            "normalized_label": f"{NOTE_NAMES[root]}{EXTENSION_SUFFIX[from_large[1]]}"
        }
    )
