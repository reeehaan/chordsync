from pathlib import Path

from analysis.chords.chordino.chordino_runner import run_chordino


audio_path = Path("storage/processed/abc123.wav")

segments = run_chordino(audio_path)

print(f"Detected {len(segments)} chord segments\n")

for segment in segments[:20]:
    print(segment.model_dump())
