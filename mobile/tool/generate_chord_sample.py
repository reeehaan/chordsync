"""Makes the chord-shapes sample used to preview every chord diagram the app can
draw: all 12 major, all 12 minor and the 60 beginner 7, maj7, m7, sus2 and sus4
shapes, one after another, as a synthesized guitar recording plus the timeline
that describes it.

The shapes are read from the app's own table (chord_diagram.dart), so what you
hear and what you see can never disagree. No recording or third-party material
is involved. Standard library only:

    python3 tool/generate_chord_sample.py
"""

import json
import math
import re
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMS = ROOT / "lib/features/practice_timeline/presentation/chord_diagram.dart"
AUDIO = ROOT / "assets/practice_audio/extended_chords_sample.wav"
TIMELINE = ROOT / "assets/practice_timeline/extended_chords_sample.json"

RATE = 11025  # plenty for a guitar chord, and keeps the file small
BPM = 100.0
BEAT = 60.0 / BPM
BEATS_PER_CHORD = 2
OPEN_STRINGS = [40, 45, 50, 55, 59, 64]  # E2 A2 D3 G3 B3 E4, as MIDI notes
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# In the order they are played: the plain chords, then each new type.
SUFFIXES = ["", "m", "7", "maj7", "m7", "sus2", "sus4"]


def shapes_from_app():
    """chord name -> frets (low E to high e, -1 = not played), as the app draws it."""
    text = DIAGRAMS.read_text(encoding="utf-8")
    table = {}
    for name, frets in re.findall(r"'([A-G]#?[a-z0-9]*)': _ChordVoicing\(\[([^\]]*)\]", text):
        table[name] = [int(f) for f in frets.split(",")]
    return table


def strum(samples, start, frets):
    length = int(BEATS_PER_CHORD * BEAT * RATE)
    for string, fret in enumerate(frets):
        if fret < 0:
            continue
        midi = OPEN_STRINGS[string] + fret
        frequency = 440.0 * 2 ** ((midi - 69) / 12)
        onset = int((start + string * 0.03) * RATE)
        for i in range(min(length, len(samples) - onset)):
            t = i / RATE
            tone = sum(math.sin(2 * math.pi * frequency * h * t) / h for h in range(1, 5))
            samples[onset + i] += tone * math.exp(-t * 2.2) * (1 - math.exp(-t * 250))


def main():
    shapes = shapes_from_app()
    chords = [f"{root}{suffix}" for suffix in SUFFIXES for root in NAMES]
    missing = [chord for chord in chords if chord not in shapes]
    assert not missing, f"no shape in the app for: {missing}"

    per_bar = 4 // BEATS_PER_CHORD
    bars_count = math.ceil(len(chords) / per_bar)
    seconds = bars_count * 4 * BEAT
    samples = [0.0] * int((seconds + 1.0) * RATE)
    bars, lyrics = [], []
    for bar in range(bars_count):
        pair = chords[bar * per_bar:(bar + 1) * per_bar]
        beats = []
        for beat in range(4):
            chord = pair[min(beat // BEATS_PER_CHORD, len(pair) - 1)]
            time = (bar * 4 + beat) * BEAT
            beats.append({"time": round(time, 3), "beat_number": beat + 1,
                          "is_downbeat": beat == 0, "chord": chord})
            if beat % BEATS_PER_CHORD == 0 and beat // BEATS_PER_CHORD < len(pair):
                strum(samples, time, shapes[chord])
        bars.append({"bar_number": bar + 1, "start_time": round(bar * 4 * BEAT, 3),
                     "end_time": round((bar + 1) * 4 * BEAT, 3), "beats": beats})
        start = bar * 4 * BEAT
        words = [{"start": round(start + k * BEATS_PER_CHORD * BEAT + 0.05, 3),
                  "end": round(start + (k + 1) * BEATS_PER_CHORD * BEAT - 0.1, 3), "text": chord}
                 for k, chord in enumerate(pair)]
        lyrics.append({"start": words[0]["start"], "end": words[-1]["end"],
                       "text": " ".join(pair), "words": words})
    peak = max(abs(v) for v in samples) or 1.0
    AUDIO.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(AUDIO), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(b"".join(struct.pack("<h", int(v / peak * 28000)) for v in samples))
    TIMELINE.write_text(json.dumps({
        "schema_version": 1, "bpm": BPM, "beats_per_bar": 4,
        "beat_source": "sample", "lyric_source": "sample",
        "bars": bars, "lyrics": lyrics, "practice_regions": [],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{len(chords)} chords, {bars_count} bars, {seconds:.0f} s, "
          f"{AUDIO.stat().st_size / 1e6:.2f} MB, {TIMELINE.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
