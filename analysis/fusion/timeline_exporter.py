import json
from pathlib import Path

from analysis.fusion.models import SharedTimeline


def export_shared_timeline(
    timeline: SharedTimeline,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            timeline.model_dump(),
            file,
            indent=2,
            ensure_ascii=False,
        )
