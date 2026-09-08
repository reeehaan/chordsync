import json
from pathlib import Path

from analysis.beats.models import BeatGrid
from analysis.temporal.models import Bar


def export_timeline_json(
    output_path: Path,
    beat_grid: BeatGrid,
    bars: list[Bar],
) -> None:
    data = {
        "bpm": beat_grid.bpm,
        "beats_per_bar": beat_grid.beats_per_bar,
        "source": beat_grid.source,
        "bars": [
            {
                "bar_number": bar.bar_number,
                "start_time": bar.start_time,
                "end_time": bar.end_time,
                "beats": [
                    {
                        "time": beat.time,
                        "beat_number": beat.beat_number,
                        "is_downbeat": beat.is_downbeat,
                        "chord": beat.chord,
                    }
                    for beat in bar.beats
                ],
            }
            for bar in bars
        ],
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
        )
