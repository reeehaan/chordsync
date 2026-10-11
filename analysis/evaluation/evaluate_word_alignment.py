import argparse
import csv
import json
import re
from pathlib import Path
from statistics import mean, median


MAX_MATCH_DISTANCE = 2.0


def normalize_word(word: str) -> str:
    return re.sub(
        r"[^a-z0-9']",
        "",
        word.lower().strip(),
    )


def load_reference_words(path: Path) -> list[dict]:
    words = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            words.append(
                {
                    "id": int(row["id"]),
                    "region": row["region"],
                    "word": normalize_word(
                        row["word"]
                    ),
                    "start": float(
                        row["start"]
                    ),
                    "end": float(
                        row["end"]
                    ),
                }
            )

    return words


def load_whisper_words(path: Path) -> list[dict]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    words = []

    for segment in data.get(
        "segments",
        [],
    ):
        for word in segment.get(
            "words",
            [],
        ):
            normalized = normalize_word(
                word["text"]
            )

            if not normalized:
                continue

            words.append(
                {
                    "word": normalized,
                    "start": float(
                        word["start"]
                    ),
                    "end": float(
                        word["end"]
                    ),
                }
            )

    return words


def load_whisperx_words(path: Path) -> list[dict]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    words = []

    for word in data.get(
        "word_segments",
        [],
    ):
        if (
            "start" not in word
            or "end" not in word
        ):
            continue

        normalized = normalize_word(
            word["word"]
        )

        if not normalized:
            continue

        words.append(
            {
                "word": normalized,
                "start": float(
                    word["start"]
                ),
                "end": float(
                    word["end"]
                ),
                "score": word.get(
                    "score"
                ),
            }
        )

    return words


def match_reference_to_model(
    reference_words: list[dict],
    model_words: list[dict],
) -> list[dict]:
    matches = []
    used_indices = set()

    for reference in reference_words:
        best_index = None
        best_distance = None

        for index, model_word in enumerate(
            model_words
        ):
            if index in used_indices:
                continue

            if (
                reference["word"]
                != model_word["word"]
            ):
                continue

            distance = abs(
                reference["start"]
                - model_word["start"]
            )

            if distance > MAX_MATCH_DISTANCE:
                continue

            if (
                best_distance is None
                or distance < best_distance
            ):
                best_distance = distance
                best_index = index

        if best_index is None:
            continue

        model_word = model_words[
            best_index
        ]

        used_indices.add(
            best_index
        )

        matches.append(
            {
                "id": reference["id"],
                "region": reference["region"],
                "word": reference["word"],
                "reference_start": reference[
                    "start"
                ],
                "reference_end": reference[
                    "end"
                ],
                "model_start": model_word[
                    "start"
                ],
                "model_end": model_word[
                    "end"
                ],
                "score": model_word.get(
                    "score"
                ),
            }
        )

    return matches


def calculate_metrics(
    matches: list[dict],
) -> dict:
    if not matches:
        raise ValueError(
            "No matched words found."
        )

    start_errors = [
        abs(
            match["reference_start"]
            - match["model_start"]
        )
        for match in matches
    ]

    end_errors = [
        abs(
            match["reference_end"]
            - match["model_end"]
        )
        for match in matches
    ]

    combined_errors = [
        (
            start_error
            + end_error
        )
        / 2
        for start_error, end_error in zip(
            start_errors,
            end_errors,
        )
    ]

    def within(
        values: list[float],
        threshold: float,
    ) -> float:
        return (
            sum(
                value <= threshold
                for value in values
            )
            / len(values)
        ) * 100

    return {
        "matched_words": len(
            matches
        ),
        "start_mae": mean(
            start_errors
        ),
        "start_median": median(
            start_errors
        ),
        "end_mae": mean(
            end_errors
        ),
        "end_median": median(
            end_errors
        ),
        "combined_mae": mean(
            combined_errors
        ),
        "combined_median": median(
            combined_errors
        ),
        "within_50ms": within(
            combined_errors,
            0.050,
        ),
        "within_100ms": within(
            combined_errors,
            0.100,
        ),
        "within_250ms": within(
            combined_errors,
            0.250,
        ),
    }


def print_metrics(
    name: str,
    metrics: dict,
):
    print()
    print(name)
    print("=" * 60)

    print(
        f"Matched words: "
        f"{metrics['matched_words']}"
    )

    print(
        f"Start MAE: "
        f"{metrics['start_mae'] * 1000:.2f} ms"
    )

    print(
        f"Start median: "
        f"{metrics['start_median'] * 1000:.2f} ms"
    )

    print(
        f"End MAE: "
        f"{metrics['end_mae'] * 1000:.2f} ms"
    )

    print(
        f"End median: "
        f"{metrics['end_median'] * 1000:.2f} ms"
    )

    print(
        f"Combined MAE: "
        f"{metrics['combined_mae'] * 1000:.2f} ms"
    )

    print(
        f"Combined median: "
        f"{metrics['combined_median'] * 1000:.2f} ms"
    )

    print(
        f"Within ±50 ms: "
        f"{metrics['within_50ms']:.2f}%"
    )

    print(
        f"Within ±100 ms: "
        f"{metrics['within_100ms']:.2f}%"
    )

    print(
        f"Within ±250 ms: "
        f"{metrics['within_250ms']:.2f}%"
    )


def print_sample_matches(
    name: str,
    matches: list[dict],
):
    print()
    print(
        f"{name} sample comparisons"
    )
    print("=" * 60)

    for match in matches[:10]:
        start_error = abs(
            match["reference_start"]
            - match["model_start"]
        )

        end_error = abs(
            match["reference_end"]
            - match["model_end"]
        )

        print(
            {
                "word": match["word"],
                "reference_start": round(
                    match[
                        "reference_start"
                    ],
                    3,
                ),
                "model_start": round(
                    match[
                        "model_start"
                    ],
                    3,
                ),
                "start_error_ms": round(
                    start_error * 1000,
                    2,
                ),
                "end_error_ms": round(
                    end_error * 1000,
                    2,
                ),
                "score": match.get(
                    "score"
                ),
            }
        )


def parse_arguments(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate word alignment against a supplied reference.",
    )
    parser.add_argument(
        "--reference",
        required=True,
        type=Path,
        help="Path to a reference word-timing CSV file.",
    )
    parser.add_argument(
        "--whisper",
        required=True,
        type=Path,
        help="Path to a Whisper transcript JSON file.",
    )
    parser.add_argument(
        "--whisperx",
        required=True,
        type=Path,
        help="Path to a WhisperX result JSON file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = parse_arguments(argv)
    reference_words = (
        load_reference_words(
            arguments.reference
        )
    )

    whisper_words = (
        load_whisper_words(
            arguments.whisper
        )
    )

    whisperx_words = (
        load_whisperx_words(
            arguments.whisperx
        )
    )

    whisper_matches = (
        match_reference_to_model(
            reference_words,
            whisper_words,
        )
    )

    whisperx_matches = (
        match_reference_to_model(
            reference_words,
            whisperx_words,
        )
    )

    whisper_metrics = (
        calculate_metrics(
            whisper_matches
        )
    )

    whisperx_metrics = (
        calculate_metrics(
            whisperx_matches
        )
    )

    print()
    print(
        "Word Alignment Evaluation"
    )
    print("=" * 60)

    print(
        f"Manual reference words: "
        f"{len(reference_words)}"
    )

    print_metrics(
        "OpenAI Whisper",
        whisper_metrics,
    )

    print_metrics(
        "WhisperX",
        whisperx_metrics,
    )

    print()
    print("Comparison")
    print("=" * 60)

    difference = (
        whisper_metrics[
            "combined_mae"
        ]
        - whisperx_metrics[
            "combined_mae"
        ]
    )

    print(
        "Combined MAE difference: "
        f"{difference * 1000:.2f} ms"
    )

    if difference > 0:
        print(
            "WhisperX has lower "
            "average timing error."
        )
    elif difference < 0:
        print(
            "Whisper has lower "
            "average timing error."
        )
    else:
        print(
            "Both have identical "
            "average timing error."
        )

    print_sample_matches(
        "Whisper",
        whisper_matches,
    )

    print_sample_matches(
        "WhisperX",
        whisperx_matches,
    )


if __name__ == "__main__":
    main()
