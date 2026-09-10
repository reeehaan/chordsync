import argparse
import json
from pathlib import Path

from analysis.lyrics.lyric_exporter import export_lyrics_json
from analysis.lyrics.whisperx_parser import parse_whisperx_result


def export_whisperx_lyrics(
    input_path: Path,
    output_path: Path,
):
    if not input_path.exists():
        raise FileNotFoundError(
            f"WhisperX input not found: {input_path}"
        )

    with input_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        raw_result = json.load(file)

    transcript = parse_whisperx_result(
        raw_result,
        source="whisperx-base",
    )

    export_lyrics_json(
        transcript,
        output_path,
    )

    return transcript


def parse_arguments(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a WhisperX result as ChordSync lyric JSON.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to a WhisperX result JSON file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path for the exported ChordSync lyric JSON file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = parse_arguments(argv)
    transcript = export_whisperx_lyrics(
        arguments.input,
        arguments.output,
    )

    total_words = sum(
        len(segment.words)
        for segment in transcript.segments
    )

    print("WhisperX lyric export complete")
    print("=" * 50)
    print(f"Language: {transcript.language}")
    print(f"Source: {transcript.source}")
    print(
        f"Segments: "
        f"{len(transcript.segments)}"
    )
    print(
        f"Words: "
        f"{total_words}"
    )
    print(
        f"Output: "
        f"{arguments.output}"
    )


if __name__ == "__main__":
    main()
