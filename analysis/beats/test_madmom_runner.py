from pathlib import Path

from analysis.beats.madmom_runner import (
    detect_beats,
    detect_downbeats,
    build_beat_grid,
)

audio_path = Path(
    "datasets/chord_eval/audio/let_it_be.wav"
)

beats = detect_beats(audio_path)
downbeats = detect_downbeats(audio_path)

print()
print("Beat tracking")
print("=" * 40)
print(f"Detected beats: {len(beats)}")
print("First 10 beats:")

for beat in beats[:10]:
    print(beat)

print()
print("Downbeat tracking")
print("=" * 40)
print(f"Detected beat positions: {len(downbeats)}")
print("First 12 positions:")

for item in downbeats[:12]:
    print(item)

grid = build_beat_grid(audio_path)

print()
print("Beat grid")
print("=" * 40)
print(f"BPM: {grid.bpm}")
print(f"Beats per bar: {grid.beats_per_bar}")
print(f"Total beat positions: {len(grid.beats)}")
print(f"Source: {grid.source}")
