"""Builds the splash screen's sound (assets/audio/splash_harmonics.wav).

It is a short fingerpicked tab of natural harmonics, the 5th/7th/12th-fret
"harp harmonics" technique, on a guitar in open C tuning (C G C G C E), which
spells C major:

    e|----------------12--------------|
    B|------------12------7-----------|
    G|--------12--------------7-------|
    D|----12----------------------7---|
    A|12------------------------------|
    E|--------------------------------|

Notes in order: G3, C4, G4, C5, E5 (12th fret), then G5, D5, G4 (7th fret).
The 6th string (C2) is not used: it is not in the recordings.

How a harmonic is made here: touching a string at 1/k of its length kills
every overtone that does not have a node there, so only the multiples of k of
the string's pitch ring. A comb filter does the same to a real recording of
the open string: it adds copies delayed by 1/k of the string's period, which
cancels the other overtones. The note keeps the string's own guitar tone but
gets the pure, quickly fading ring of a harmonic. A touch of high boost and a
short bright "tick" at the start add the sparkle of touch-and-pluck.

The recordings are the "guitar-acoustic" samples (University of Iowa Electronic
Music Studios) as packaged in https://github.com/nbrosowsky/tonejs-instruments,
under CC BY 3.0 -- see docs/licensing/splash-guitar-samples.md. Download G2, C3,
G3, C4 and E4 (.wav, 44.1 kHz mono) from samples/guitar-acoustic/ into a
folder, then:

    python3 tool/generate_splash_chord.py path/to/folder

The splash animation moves its three drawn strings at the same moments as these
notes (see chordsync_splash_screen.dart); keep PICK_STEP and the string order
there in step with this file. Pure Python, no extra packages.
"""

import math
import struct
import sys
import wave
from pathlib import Path

SAMPLE_RATE = 44100
DURATION = 3.6  # seconds
PICK_STEP = 0.16  # seconds between notes
FADE_OUT = 0.8  # seconds

HIGH_BOOST_HZ = 1600  # boost everything above this ...
HIGH_BOOST = 1.1  # ... by this much (1.0 doubles it)
TICK_SECONDS = 0.03  # the touch-and-pluck tick at the start of a note
TICK_LEVEL = 0.16

# Open-string recordings of a guitar in open C tuning (nominal pitch in Hz).
STRINGS = {"G2": 98.0, "C3": 130.81, "G3": 196.0, "C4": 261.63, "E4": 329.63}

# The tab, in the order picked: (open string, partial, decay seconds).
# Partial 2 is the 12th fret (an octave up), 3 the 7th fret (an octave and a
# fifth up).
TAB = [
    ("G2", 2, 1.1),  # 5th string, 12th fret: G3
    ("C3", 2, 1.1),  # 4th string, 12th fret: C4
    ("G3", 2, 1.0),  # 3rd string, 12th fret: G4
    ("C4", 2, 1.0),  # 2nd string, 12th fret: C5
    ("E4", 2, 0.9),  # 1st string, 12th fret: E5
    ("C4", 3, 0.8),  # 2nd string, 7th fret: G5
    ("G3", 3, 0.8),  # 3rd string, 7th fret: D5
    ("C3", 3, 0.8),  # 4th string, 7th fret: G4
]


def read_mono(path: Path) -> list[float]:
    with wave.open(str(path), "rb") as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        assert wav.getframerate() == SAMPLE_RATE, "samples must be 44.1 kHz"
        raw = wav.readframes(wav.getnframes())
    count = len(raw) // 2
    return [v / 32768 for v in struct.unpack(f"<{count}h", raw)]


def string_pitch(samples: list[float], nominal: float) -> float:
    """The recording's true pitch, from its autocorrelation near [nominal]."""
    start = int(0.15 * SAMPLE_RATE)
    segment = samples[start : start + 8192]

    def correlation(lag: int) -> float:
        return sum(
            segment[i] * segment[i + lag] for i in range(0, len(segment) - lag, 2)
        )

    low = int(SAMPLE_RATE / (nominal * 1.04))
    high = int(SAMPLE_RATE / (nominal * 0.96))
    best = max(range(low, high + 1), key=correlation)
    a, b, c = correlation(best - 1), correlation(best), correlation(best + 1)
    shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    return SAMPLE_RATE / (best + shift)


def harmonic(samples: list[float], period: float, partial: int) -> list[float]:
    """Keeps only the overtones that are multiples of [partial]."""
    spacing = period / partial
    out = [0.0] * len(samples)
    for copy in range(partial):
        delay = copy * spacing
        whole = int(delay)
        fraction = delay - whole
        for n in range(len(samples)):
            a = n - whole
            if a - 1 < 0:
                continue
            out[n] += samples[a] * (1 - fraction) + samples[a - 1] * fraction
    return out


def sparkle(note: list[float], source: list[float]) -> list[float]:
    """Boosts the highs and adds the short bright tick of touch-and-pluck."""
    coefficient = 1 - math.exp(-2 * math.pi * HIGH_BOOST_HZ / SAMPLE_RATE)
    low = 0.0
    bright = []
    for value in note:
        low += coefficient * (value - low)
        bright.append(value + HIGH_BOOST * (value - low))
    tick = int(TICK_SECONDS * SAMPLE_RATE)
    for n in range(min(tick, len(source))):
        step = source[n] - source[n - 1] if n else source[n]
        bright[n] += TICK_LEVEL * step * (1 - n / tick)
    return bright


def main(folder: Path) -> None:
    total = int(SAMPLE_RATE * DURATION)
    mix = [0.0] * total
    for index, (name, partial, decay) in enumerate(TAB):
        source = read_mono(folder / f"{name}.wav")[: int(SAMPLE_RATE * 3.0)]
        pitch = string_pitch(source, STRINGS[name])
        note = sparkle(harmonic(source, SAMPLE_RATE / pitch, partial), source)
        scale = max(abs(v) for v in note) or 1.0
        start = int(index * PICK_STEP * SAMPLE_RATE)
        for n in range(min(len(note), total - start)):
            mix[start + n] += note[n] / scale * math.exp(-(n / SAMPLE_RATE) / decay)
        print(f"{name} partial {partial}: {pitch * partial:.1f} Hz")

    peak = max(abs(s) for s in mix)
    fade = int(FADE_OUT * SAMPLE_RATE)
    frames = bytearray()
    for i, sample in enumerate(mix):
        value = sample / peak * 0.85
        if i >= total - fade:
            value *= (total - i) / fade
        frames += struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767))

    target = Path(__file__).resolve().parent.parent / "assets/audio/splash_harmonics.wav"
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))
    print(f"{target.name}: {target.stat().st_size // 1024} KB, {DURATION} s")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
