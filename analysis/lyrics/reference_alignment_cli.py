from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.lyrics.forced_alignment import (
    ReferenceAlignmentSegment,
    WhisperXReferenceAligner,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    request = json.loads(arguments.request.read_text(encoding="utf-8"))
    segments = [
        ReferenceAlignmentSegment(
            text=item["text"],
            start=float(item["start"]),
            end=float(item["end"]),
        )
        for item in request["segments"]
    ]
    result = WhisperXReferenceAligner(
        language_code=request["language_code"],
        device=request["device"],
    ).align(Path(request["audio_path"]), segments)
    arguments.output.write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
