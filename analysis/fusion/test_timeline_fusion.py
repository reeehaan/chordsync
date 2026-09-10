import json
from pathlib import Path

from analysis.beats.models import (
    BeatEvent,
    BeatGrid,
)
from analysis.fusion.timeline_exporter import (
    export_shared_timeline,
)
from analysis.fusion.timeline_fusion import (
    build_shared_timeline,
)
from analysis.lyrics.models import LyricTranscript
from analysis.temporal.models import Bar


beat_timeline_path = Path(
    "storage/analysis/let_it_be_timeline.json"
)

lyrics_path = Path(
    "storage/analysis/let_it_be_lyrics.json"
)

output_path = Path(
    "storage/analysis/let_it_be_shared_timeline.json"
)


# Load beat/chord timeline JSON
with beat_timeline_path.open(
    "r",
    encoding="utf-8",
) as file:
    beat_data = json.load(file)


# Load lyrics JSON
with lyrics_path.open(
    "r",
    encoding="utf-8",
) as file:
    lyric_data = json.load(file)


# Rebuild Bar models
bars = [
    Bar.model_validate(bar)
    for bar in beat_data["bars"]
]


# Convert TimelineEvent objects back into BeatEvent objects
beat_events = []

for bar in bars:
    for event in bar.beats:
        beat_events.append(
            BeatEvent(
                time=event.time,
                beat_number=event.beat_number,
                is_downbeat=event.is_downbeat,
                source=beat_data["source"],
            )
        )


# Rebuild BeatGrid
beat_grid = BeatGrid(
    bpm=beat_data["bpm"],
    beats_per_bar=beat_data["beats_per_bar"],
    beats=beat_events,
    source=beat_data["source"],
)


# Rebuild lyric transcript
lyrics = LyricTranscript.model_validate(
    lyric_data
)


# Build shared timeline
timeline = build_shared_timeline(
    beat_grid,
    bars,
    lyrics,
)


# Export final shared timeline
export_shared_timeline(
    timeline,
    output_path,
)


print()
print("Shared Timeline")
print("=" * 50)

print(
    f"Schema version: "
    f"{timeline.schema_version}"
)

print(
    f"BPM: "
    f"{timeline.bpm}"
)

print(
    f"Beats per bar: "
    f"{timeline.beats_per_bar}"
)

print(
    f"Beat source: "
    f"{timeline.beat_source}"
)

print(
    f"Lyric source: "
    f"{timeline.lyric_source}"
)

print(
    f"Bars: "
    f"{len(timeline.bars)}"
)

total_beats = sum(
    len(bar.beats)
    for bar in timeline.bars
)

print(
    f"Beat events: "
    f"{total_beats}"
)

print(
    f"Lyric segments: "
    f"{len(timeline.lyrics)}"
)

total_words = sum(
    len(segment.words)
    for segment in timeline.lyrics
)

print(
    f"Lyric words: "
    f"{total_words}"
)

print(
    f"Output: "
    f"{output_path}"
)
