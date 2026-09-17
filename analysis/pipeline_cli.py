import argparse
import json
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
) -> None:
    chords = run_btc_chord_analysis(input_path, checkpoint_path, source_path)
    _write_json(output_path, [chord.model_dump() for chord in chords])


def run_beat_analysis(input_path: Path, output_path: Path) -> None:
    from analysis.beats.madmom_runner import build_beat_grid

    beat_grid = build_beat_grid(input_path)
    _write_json(output_path, beat_grid.model_dump())


def run_fusion(
    chord_path: Path,
    beat_path: Path,
    whisperx_path: Path,
    output_path: Path,
) -> None:
    from analysis.beats.models import BeatGrid
    from analysis.chords.models import ChordSegment
    from analysis.fusion.timeline_exporter import export_shared_timeline
    from analysis.fusion.timeline_fusion import build_shared_timeline
    from analysis.lyrics.whisperx_parser import parse_whisperx_result
    from analysis.temporal.bar_grouper import group_into_bars
    from analysis.temporal.chord_beat_aligner import align_chords_to_beats

    chord_data = json.loads(chord_path.read_text(encoding="utf-8"))
    beat_data = json.loads(beat_path.read_text(encoding="utf-8"))
    whisperx_data = json.loads(whisperx_path.read_text(encoding="utf-8"))

    chords = [ChordSegment.model_validate(item) for item in chord_data]
    beat_grid = BeatGrid.model_validate(beat_data)
    lyrics = parse_whisperx_result(whisperx_data, source="whisperx-base")
    events = align_chords_to_beats(beat_grid.beats, chords)
    bars = group_into_bars(events)
    timeline = build_shared_timeline(beat_grid, bars, lyrics)
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

    fusion_parser = subparsers.add_parser("fuse")
    fusion_parser.add_argument("--chords", type=Path, required=True)
    fusion_parser.add_argument("--beats", type=Path, required=True)
    fusion_parser.add_argument("--whisperx", type=Path, required=True)
    fusion_parser.add_argument("--output", type=Path, required=True)
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
        )
    elif arguments.stage == "beats":
        run_beat_analysis(arguments.input, arguments.output)
    else:
        run_fusion(
            arguments.chords,
            arguments.beats,
            arguments.whisperx,
            arguments.output,
        )


if __name__ == "__main__":
    main()
