from pathlib import Path

from analysis.beats.madmom_runner import build_beat_grid
from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import normalize_chord_label
from analysis.temporal.bar_grouper import group_into_bars
from analysis.temporal.chord_beat_aligner import (
    align_chords_to_beats,
)
from analysis.temporal.timeline_exporter import (
    export_timeline_json,
)


def load_lab(path: Path) -> list[ChordSegment]:
    segments = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            start, end, label = line.split(maxsplit=2)

            segments.append(
                ChordSegment(
                    start=float(start),
                    end=float(end),
                    raw_label=label,
                    normalized_label=normalize_chord_label(
                        label
                    ),
                    source="btc",
                )
            )

    return segments


audio_path = Path(
    "datasets/chord_eval/audio/let_it_be.wav"
)

chord_path = Path(
    "datasets/chord_eval/predictions/btc/let_it_be.lab"
)

output_path = Path(
    "storage/analysis/let_it_be_timeline.json"
)


# Build beat/downbeat grid
grid = build_beat_grid(audio_path)

# Load BTC chord predictions
chords = load_lab(chord_path)

# Align chords to beat positions
aligned = align_chords_to_beats(
    grid.beats,
    chords,
)

# Group beat-level events into bars
bars = group_into_bars(aligned)

# Export timeline to JSON
export_timeline_json(
    output_path,
    grid,
    bars,
)


print()
print("Chord → Beat Alignment")
print("=" * 50)

for item in aligned[:20]:
    print(item)


print()
print("Bars")
print("=" * 50)

for bar in bars[:8]:
    chord_sequence = [
        event.chord
        for event in bar.beats
    ]

    print(
        f"Bar {bar.bar_number}: "
        f"{chord_sequence} "
        f"({bar.start_time:.2f}s - "
        f"{bar.end_time:.2f}s)"
    )


print()
print("Summary")
print("=" * 50)

print(f"BPM: {grid.bpm}")
print(f"Beats per bar: {grid.beats_per_bar}")
print(f"Total beat events: {len(aligned)}")
print(f"Total bars: {len(bars)}")
print(f"Timeline exported to: {output_path}")
