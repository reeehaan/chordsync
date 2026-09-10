import argparse
from pathlib import Path

from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import normalize_chord_label
from analysis.evaluation.chord_evaluator import (
    evaluate_chords,
    load_reference_lab,
    segments_to_intervals,
)


DEFAULT_CHORDINO_PREDICTION = Path(
    "datasets/chord_eval/predictions/chordino/let_it_be.lab"
)
DEFAULT_BTC_PREDICTION = Path(
    "datasets/chord_eval/predictions/btc/let_it_be.lab"
)


def load_prediction_lab(
    lab_path: Path,
    source: str,
) -> list[ChordSegment]:
    segments = []

    with lab_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            parts = line.split(maxsplit=2)

            if len(parts) != 3:
                continue

            start_text, end_text, raw_label = parts

            try:
                start = float(start_text)
                end = float(end_text)
            except ValueError:
                continue

            segments.append(
                ChordSegment(
                    start=start,
                    end=end,
                    raw_label=raw_label,
                    normalized_label=normalize_chord_label(
                        raw_label
                    ),
                    source=source,
                )
            )

    return segments


def compare_estimators(
    reference_path: Path,
    chordino_path: Path = DEFAULT_CHORDINO_PREDICTION,
    btc_path: Path = DEFAULT_BTC_PREDICTION,
) -> dict[str, dict[str, float]]:
    reference_intervals, reference_labels = (
        load_reference_lab(reference_path)
    )

    chordino_segments = load_prediction_lab(
        chordino_path,
        source="chordino",
    )

    btc_segments = load_prediction_lab(
        btc_path,
        source="btc",
    )

    chordino_intervals, chordino_labels = (
        segments_to_intervals(chordino_segments)
    )

    btc_intervals, btc_labels = (
        segments_to_intervals(btc_segments)
    )

    chordino_result = evaluate_chords(
        reference_intervals,
        reference_labels,
        chordino_intervals,
        chordino_labels,
    )

    btc_result = evaluate_chords(
        reference_intervals,
        reference_labels,
        btc_intervals,
        btc_labels,
    )

    return {
        "chordino": chordino_result,
        "btc": btc_result,
    }


def parse_arguments(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare ChordSync chord estimator predictions.",
    )
    parser.add_argument(
        "--reference",
        required=True,
        type=Path,
        help="Path to a locally supplied reference chord .lab file.",
    )
    parser.add_argument(
        "--chordino-prediction",
        type=Path,
        default=DEFAULT_CHORDINO_PREDICTION,
        help="Path to the Chordino prediction .lab file.",
    )
    parser.add_argument(
        "--btc-prediction",
        type=Path,
        default=DEFAULT_BTC_PREDICTION,
        help="Path to the BTC prediction .lab file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = parse_arguments(argv)
    results = compare_estimators(
        reference_path=arguments.reference,
        chordino_path=arguments.chordino_prediction,
        btc_path=arguments.btc_prediction,
    )

    chordino_result = results["chordino"]
    btc_result = results["btc"]

    print()
    print("ChordSync — Chord Estimator Comparison")
    print("=" * 50)

    print(
        f"{'Model':<12}"
        f"{'Root WCSR':<15}"
        f"{'Maj/Min WCSR':<15}"
    )

    print("-" * 50)

    print(
        f"{'Chordino':<12}"
        f"{chordino_result['root_wcsr']:.4f}"
        f"{'':<9}"
        f"{chordino_result['majmin_wcsr']:.4f}"
    )

    print(
        f"{'BTC':<12}"
        f"{btc_result['root_wcsr']:.4f}"
        f"{'':<9}"
        f"{btc_result['majmin_wcsr']:.4f}"
    )

    print("=" * 50)


if __name__ == "__main__":
    main()
