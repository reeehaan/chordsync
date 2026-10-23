"""Makes the "extended chords" sample used to preview the beginner chord shapes:
a short, slow progression through the 7, maj7, m7, sus2 and sus4 chords, as a
synthesized guitar recording plus the timeline that describes it.

No recording or third-party material is involved. Standard library only:

    python3 tool/generate_chord_sample.py
"""

import json
import math
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "assets/practice_audio/extended_chords_sample.wav"
TIMELINE = ROOT / "assets/practice_timeline/extended_chords_sample.json"

RATE = 22050
BPM = 80.0
BEAT = 60.0 / BPM
OPEN_STRINGS = [40, 45, 50, 55, 59, 64]  # E2 A2 D3 G3 B3 E4, as MIDI notes

# The shapes the app draws for these chords (low E to high e, -1 = not played).
SHAPES = {
    "Em7": [0, 2, 0, 0, 0, 0], "G": [3, 2, 0, 0, 0, 3], "Cmaj7": [-1, 3, 2, 0, 0, 0],
    "Dsus4": [-1, -1, 0, 2, 3, 3], "A7": [-1, 0, 2, 0, 2, 0], "Dmaj7": [-1, -1, 0, 2, 2, 2],
    "Bm7": [-1, 2, 0, 2, 0, 2], "Asus2": [-1, 0, 2, 2, 0, 0], "Asus4": [-1, 0, 2, 2, 3, 0],
    "Gmaj7": [3, 2, 0, 0, 0, 2], "C7": [-1, 3, 2, 3, 1, 0], "Fmaj7": [-1, -1, 3, 2, 1, 0],
    "Dm7": [-1, -1, 0, 2, 1, 1], "G7": [3, 2, 0, 0, 0, 1], "Csus4": [-1, 3, 3, 0, 1, 1],
    "C": [-1, 3, 2, 0, 1, 0],
}
# Two chords a bar, two beats each.
PROGRESSION = [
    ("Em7", "G"), ("Cmaj7", "Dsus4"), ("Em7", "A7"), ("Dmaj7", "Bm7"),
    ("Asus2", "Asus4"), ("Gmaj7", "C7"), ("Fmaj7", "Dm7"), ("G7", "Csus4"),
]
WORDS = [("Strum", "along"), ("to", "every"), ("new", "shape"), ("you", "can"),
         ("play", "it"), ("slow", "then"), ("pick", "up"), ("speed", "now")]


def strum(samples, start, frets):
    for string, fret in enumerate(frets):
        if fret < 0:
            continue
        midi = OPEN_STRINGS[string] + fret
        frequency = 440.0 * 2 ** ((midi - 69) / 12)
        onset = int((start + string * 0.035) * RATE)
        length = int(2 * BEAT * RATE)
        for i in range(min(length, len(samples) - onset)):
            t = i / RATE
            tone = sum(math.sin(2 * math.pi * frequency * h * t) / h for h in range(1, 6))
            envelope = math.exp(-t * 1.7) * (1 - math.exp(-t * 250))
            samples[onset + i] += tone * envelope


def main():
    bars = len(PROGRESSION)
    seconds = bars * 4 * BEAT
    samples = [0.0] * int((seconds + 1.0) * RATE)
    timeline_bars = []
    for bar, pair in enumerate(PROGRESSION):
        beats = []
        for beat in range(4):
            chord = pair[beat // 2]
            time = (bar * 4 + beat) * BEAT
            beats.append({"time": round(time, 3), "beat_number": beat + 1,
                          "is_downbeat": beat == 0, "chord": chord})
            if beat % 2 == 0:
                strum(samples, time, SHAPES[chord])
        timeline_bars.append({"bar_number": bar + 1, "start_time": round(bar * 4 * BEAT, 3),
                              "end_time": round((bar + 1) * 4 * BEAT, 3), "beats": beats})
    lyrics = []
    for bar, pair in enumerate(WORDS):
        start = bar * 4 * BEAT
        words = [{"start": round(start + k * 2 * BEAT + 0.05, 3),
                  "end": round(start + (k + 1) * 2 * BEAT - 0.1, 3), "text": word}
                 for k, word in enumerate(pair)]
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
        "bars": timeline_bars, "lyrics": lyrics, "practice_regions": [],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{AUDIO.name}: {seconds:.1f} s, {AUDIO.stat().st_size / 1e6:.2f} MB; {TIMELINE.name}")


if __name__ == "__main__":
    main()
