"""Generate the publication-safe C-Am-F-G BTC smoke-test fixture."""

import math
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 22_050
CHORD_SECONDS = 3.0
SEQUENCE = (
    ("C", (261.63, 329.63, 392.00)),
    ("Am", (220.00, 261.63, 329.63)),
    ("F", (174.61, 220.00, 261.63)),
    ("G", (196.00, 246.94, 293.66)),
)


def generate(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames_per_chord = round(SAMPLE_RATE * CHORD_SECONDS)
    fade_frames = round(SAMPLE_RATE * 0.02)
    with wave.open(str(output_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        for _, frequencies in SEQUENCE:
            for frame in range(frames_per_chord):
                envelope = min(
                    1.0,
                    frame / fade_frames,
                    (frames_per_chord - frame - 1) / fade_frames,
                )
                sample = sum(
                    math.sin(2 * math.pi * frequency * frame / SAMPLE_RATE)
                    for frequency in frequencies
                ) / len(frequencies)
                audio.writeframesraw(
                    struct.pack("<h", round(sample * envelope * 0.65 * 32767))
                )


if __name__ == "__main__":
    generate(
        Path(__file__).resolve().parents[3]
        / "tests/fixtures/audio/synthetic_c_am_f_g.wav"
    )
