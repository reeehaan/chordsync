import json
from pathlib import Path

from analysis.lyrics.models import LyricTranscript


def export_lyrics_json(
    transcript: LyricTranscript,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = transcript.model_dump()

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )
