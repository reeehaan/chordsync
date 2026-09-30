import argparse
import json
import sys
from pathlib import Path


def run_btc_chord_analysis(
    input_path: Path,
    checkpoint_path: Path,
    source_path: Path,
):
    from analysis.chords.btc.btc_runner import run_btc

    return run_btc(input_path, checkpoint_path, source_path)

def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_preprocessing(input_path: Path, output_path: Path) -> None:
    from analysis.preprocessing.audio_preprocessor import preprocess_audio

    preprocess_audio(input_path, output_path)


def run_chord_analysis(input_path: Path, output_path: Path) -> None:
    from analysis.chords.chordino.chordino_runner import run_chordino

    chords = run_chordino(input_path)
    _write_json(output_path, [chord.model_dump() for chord in chords])


def run_btc_analysis(
    input_path: Path,
    output_path: Path,
    checkpoint_path: Path,
    source_path: Path,
    uncertainty_output_path: Path | None = None,
) -> None:
    if uncertainty_output_path is None:
        chords = run_btc_chord_analysis(input_path, checkpoint_path, source_path)
    else:
        from analysis.chords.btc.btc_runner import run_btc_with_diagnostics

        result = run_btc_with_diagnostics(input_path, checkpoint_path, source_path)
        chords = result.chords
    _write_json(output_path, [chord.model_dump() for chord in chords])
    if uncertainty_output_path is not None:
        try:
            _write_json(uncertainty_output_path, result.frame_diagnostics)
        except OSError:
            print(
                "BTC uncertainty diagnostics unavailable; preserving chord output",
                file=sys.stderr,
            )


def run_chordino_diagnostic_analysis(
    input_path: Path,
    output_path: Path,
    executable: Path,
) -> None:
    from analysis.chords.chordino.vamp_simple_host_runner import (
        run_chordino_diagnostic,
    )

    chords = run_chordino_diagnostic(input_path, executable=executable)
    _write_json(output_path, [chord.model_dump() for chord in chords])


def run_strumming_suitability_analysis(
    chord_path: Path,
    chordino_path: Path,
    beat_path: Path,
    uncertainty_path: Path,
    output_path: Path,
) -> None:
    from analysis.beats.models import BeatGrid
    from analysis.chords.models import ChordSegment
    from analysis.evaluation.btc_uncertainty import BtcFrameUncertainty
    from analysis.strumming.suitability import detect_music_only_regions

    btc_chords = [
        ChordSegment.model_validate(item)
        for item in json.loads(chord_path.read_text(encoding="utf-8"))
    ]
    chordino_chords = [
        ChordSegment.model_validate(item)
        for item in json.loads(chordino_path.read_text(encoding="utf-8"))
    ]
    beat_grid = BeatGrid.model_validate(
        json.loads(beat_path.read_text(encoding="utf-8"))
    )
    diagnostics = [
        BtcFrameUncertainty(**item)
        for item in json.loads(uncertainty_path.read_text(encoding="utf-8"))
    ]
    regions = detect_music_only_regions(
        btc_chords,
        chordino_chords,
        beat_grid,
        diagnostics,
    )
    _write_json(output_path, [region.model_dump(mode="json") for region in regions])


def run_beat_analysis(input_path: Path, output_path: Path) -> None:
    from analysis.beats.madmom_runner import build_beat_grid

    beat_grid = build_beat_grid(input_path)
    _write_json(output_path, beat_grid.model_dump())


def run_fusion(
    chord_path: Path,
    beat_path: Path,
    whisperx_path: Path,
    output_path: Path,
    lyric_source: str = "whisperx-base",
    practice_regions_path: Path | None = None,
) -> None:
    from analysis.beats.models import BeatGrid
    from analysis.chords.models import ChordSegment
    from analysis.fusion.timeline_exporter import export_shared_timeline
    from analysis.fusion.timeline_fusion import build_shared_timeline
    from analysis.fusion.models import PracticeRegion
    from analysis.lyrics.whisperx_parser import parse_whisperx_result
    from analysis.temporal.bar_grouper import group_into_bars
    from analysis.temporal.chord_beat_aligner import align_chords_to_beats

    chord_data = json.loads(chord_path.read_text(encoding="utf-8"))
    beat_data = json.loads(beat_path.read_text(encoding="utf-8"))
    whisperx_data = json.loads(whisperx_path.read_text(encoding="utf-8"))

    chords = [ChordSegment.model_validate(item) for item in chord_data]
    beat_grid = BeatGrid.model_validate(beat_data)
    lyrics = parse_whisperx_result(whisperx_data, source=lyric_source)
    practice_regions = (
        [
            PracticeRegion.model_validate(item)
            for item in json.loads(
                practice_regions_path.read_text(encoding="utf-8")
            )
        ]
        if practice_regions_path is not None
        else []
    )
    events = align_chords_to_beats(beat_grid.beats, chords)
    bars = group_into_bars(events)
    timeline = build_shared_timeline(
        beat_grid,
        bars,
        lyrics,
        practice_regions=practice_regions,
    )
    export_shared_timeline(timeline, output_path)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChordSync analysis stage runner")
    subparsers = parser.add_subparsers(dest="stage", required=True)

    for stage in ("preprocess", "chords", "beats"):
        stage_parser = subparsers.add_parser(stage)
        stage_parser.add_argument("--input", type=Path, required=True)
        stage_parser.add_argument("--output", type=Path, required=True)

    btc_parser = subparsers.add_parser("btc-chords")
    btc_parser.add_argument("--input", type=Path, required=True)
    btc_parser.add_argument("--output", type=Path, required=True)
    btc_parser.add_argument("--checkpoint", type=Path, required=True)
    btc_parser.add_argument("--source", type=Path, required=True)
    btc_parser.add_argument("--uncertainty-output", type=Path)

    chordino_diagnostic_parser = subparsers.add_parser("chordino-diagnostic")
    chordino_diagnostic_parser.add_argument("--input", type=Path, required=True)
    chordino_diagnostic_parser.add_argument("--output", type=Path, required=True)
    chordino_diagnostic_parser.add_argument("--executable", type=Path, required=True)

    suitability_parser = subparsers.add_parser("strumming-suitability")
    suitability_parser.add_argument("--chords", type=Path, required=True)
    suitability_parser.add_argument("--chordino", type=Path, required=True)
    suitability_parser.add_argument("--beats", type=Path, required=True)
    suitability_parser.add_argument("--uncertainty", type=Path, required=True)
    suitability_parser.add_argument("--output", type=Path, required=True)

    fusion_parser = subparsers.add_parser("fuse")
    fusion_parser.add_argument("--chords", type=Path, required=True)
    fusion_parser.add_argument("--beats", type=Path, required=True)
    fusion_parser.add_argument("--whisperx", type=Path, required=True)
    fusion_parser.add_argument("--lyric-source", default="whisperx-base")
    fusion_parser.add_argument("--output", type=Path, required=True)
    fusion_parser.add_argument("--practice-regions", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = parse_arguments(argv)
    if arguments.stage == "preprocess":
        run_preprocessing(arguments.input, arguments.output)
    elif arguments.stage == "chords":
        run_chord_analysis(arguments.input, arguments.output)
    elif arguments.stage == "btc-chords":
        run_btc_analysis(
            arguments.input,
            arguments.output,
            arguments.checkpoint,
            arguments.source,
            arguments.uncertainty_output,
        )
    elif arguments.stage == "chordino-diagnostic":
        run_chordino_diagnostic_analysis(
            arguments.input,
            arguments.output,
            arguments.executable,
        )
    elif arguments.stage == "strumming-suitability":
        run_strumming_suitability_analysis(
            arguments.chords,
            arguments.chordino,
            arguments.beats,
            arguments.uncertainty,
            arguments.output,
        )
    elif arguments.stage == "beats":
        run_beat_analysis(arguments.input, arguments.output)
    else:
        run_fusion(
            arguments.chords,
            arguments.beats,
            arguments.whisperx,
            arguments.output,
            arguments.lyric_source,
            arguments.practice_regions,
        )


if __name__ == "__main__":
    main()
