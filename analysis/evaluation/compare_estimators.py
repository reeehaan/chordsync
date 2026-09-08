from pathlib import Path

from analysis.chords.btc.btc_parser import parse_btc_lab
from analysis.chords.chordino.chordino_runner import (
    parse_chordino_csv,
)
from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import normalize_chord_label
from analysis.evaluation.chord_evaluator import (
    evaluate_chords,
    load_reference_lab,
    segments_to_intervals,
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


def main():
    reference_path = Path(
        "datasets/chord_eval/annotations/let_it_be.lab"
    )

    chordino_path = Path(
        "datasets/chord_eval/predictions/chordino/let_it_be.lab"
    )

    btc_path = Path(
        "datasets/chord_eval/predictions/btc/let_it_be.lab"
    )

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
