import json
from pathlib import Path

import pytest

from analysis.lyrics.compare_whisper_whisperx import (
    parse_arguments as parse_comparison_arguments,
)
from analysis.lyrics.evaluate_word_alignment import (
    calculate_metrics,
    parse_arguments as parse_evaluation_arguments,
)
from analysis.lyrics.export_whisperx_lyrics import (
    export_whisperx_lyrics,
)


def test_comparison_cli_requires_explicit_input_paths() -> None:
    arguments = parse_comparison_arguments([
        "--whisper",
        "whisper.json",
        "--whisperx",
        "whisperx.json",
    ])

    assert arguments.whisper == Path("whisper.json")
    assert arguments.whisperx == Path("whisperx.json")


def test_evaluation_cli_requires_explicit_input_paths() -> None:
    arguments = parse_evaluation_arguments([
        "--reference",
        "reference.csv",
        "--whisper",
        "whisper.json",
        "--whisperx",
        "whisperx.json",
    ])

    assert arguments.reference == Path("reference.csv")
    assert arguments.whisper == Path("whisper.json")
    assert arguments.whisperx == Path("whisperx.json")


def test_alignment_metrics_use_synthetic_timing_errors() -> None:
    metrics = calculate_metrics([
        {
            "reference_start": 1.0,
            "reference_end": 1.5,
            "model_start": 1.1,
            "model_end": 1.7,
        },
        {
            "reference_start": 2.0,
            "reference_end": 2.5,
            "model_start": 2.0,
            "model_end": 2.5,
        },
    ])

    assert metrics["start_mae"] == pytest.approx(0.05)
    assert metrics["end_mae"] == pytest.approx(0.1)
    assert metrics["combined_mae"] == pytest.approx(0.075)
    assert metrics["within_250ms"] == 100.0


def test_export_whisperx_lyrics_uses_explicit_paths(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text(
        json.dumps({
            "language": "en",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "Count in",
                    "words": [
                        {
                            "word": "Count",
                            "start": 0.0,
                            "end": 0.4,
                            "score": 0.9,
                        }
                    ],
                }
            ],
        }),
        encoding="utf-8",
    )

    transcript = export_whisperx_lyrics(
        input_path,
        output_path,
    )

    assert output_path.exists()
    assert transcript.segments[0].words[0].text == "Count"
