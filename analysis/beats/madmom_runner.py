from pathlib import Path
from statistics import median

from analysis.beats.models import BeatEvent, BeatGrid
from analysis.beats.madmom_compat import apply_madmom_compatibility

apply_madmom_compatibility()

from madmom.features.beats import (
    RNNBeatProcessor,
    DBNBeatTrackingProcessor,
)
from madmom.features.downbeats import (
    RNNDownBeatProcessor,
    DBNDownBeatTrackingProcessor,
)


def detect_beats(audio_path: Path) -> list[BeatEvent]:
    if not audio_path.exists():
        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    activations = RNNBeatProcessor()(str(audio_path))

    beats = DBNBeatTrackingProcessor(
        fps=100,
    )(activations)

    return [
        BeatEvent(
            time=round(float(time), 6),
            source="madmom",
        )
        for time in beats
    ]


def detect_downbeats(
    audio_path: Path,
) -> list[BeatEvent]:
    if not audio_path.exists():
        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    activations = RNNDownBeatProcessor()(
        str(audio_path)
    )

    downbeat_data = DBNDownBeatTrackingProcessor(
        beats_per_bar=[3, 4],
        fps=100,
    )(activations)

    return [
        BeatEvent(
            time=round(float(time), 6),
            beat_number=int(beat_number),
            is_downbeat=int(beat_number) == 1,
            source="madmom",
        )
        for time, beat_number in downbeat_data
    ]

def estimate_tempo(beats: list[BeatEvent]) -> float:
    if len(beats) < 2:
        raise ValueError("At least two beats are required")

    intervals = [
        beats[index + 1].time - beats[index].time
        for index in range(len(beats) - 1)
    ]

    valid_intervals = [
        interval
        for interval in intervals
        if interval > 0
    ]

    if not valid_intervals:
        raise ValueError("No valid beat intervals found")

    median_interval = median(valid_intervals)

    bpm = 60.0 / median_interval

    return round(bpm, 2)


def build_beat_grid(
    audio_path: Path,
) -> BeatGrid:
    beat_positions = detect_downbeats(audio_path)

    if not beat_positions:
        raise ValueError("No beats detected")

    bpm = estimate_tempo(beat_positions)

    beat_numbers = [
        beat.beat_number
        for beat in beat_positions
        if beat.beat_number is not None
    ]

    beats_per_bar = max(beat_numbers)

    return BeatGrid(
        bpm=bpm,
        beats_per_bar=beats_per_bar,
        beats=beat_positions,
        source="madmom",
    )
