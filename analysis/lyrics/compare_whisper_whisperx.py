import argparse
import json
import re
from pathlib import Path
from statistics import mean, median


MAX_TIME_DIFFERENCE = 2.0


def normalize_word(word: str) -> str:
    return re.sub(
        r"[^a-z0-9']",
        "",
        word.lower(),
    )


def load_whisper_words(path: Path) -> list[dict]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    words = []

    for segment in data.get("segments", []):
        for word in segment.get("words", []):
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


def match_words(
    whisper_words: list[dict],
    whisperx_words: list[dict],
) -> list[dict]:
    matches = []

    used_whisperx = set()

    for whisper_word in whisper_words:
        best_index = None
        best_difference = None

        for index, whisperx_word in enumerate(
            whisperx_words
        ):
            if index in used_whisperx:
                continue

            if (
                whisper_word["word"]
                != whisperx_word["word"]
            ):
                continue

            start_difference = abs(
                whisper_word["start"]
                - whisperx_word["start"]
            )

            if (
                start_difference
                > MAX_TIME_DIFFERENCE
            ):
                continue

            if (
                best_difference is None
                or start_difference
                < best_difference
            ):
                best_difference = (
                    start_difference
                )
                best_index = index

        if best_index is None:
            continue

        whisperx_word = whisperx_words[
            best_index
        ]

        used_whisperx.add(
            best_index
        )

        matches.append(
            {
                "word": whisper_word[
                    "word"
                ],
                "whisper_start": (
                    whisper_word["start"]
                ),
                "whisper_end": (
                    whisper_word["end"]
                ),
                "whisperx_start": (
                    whisperx_word["start"]
                ),
                "whisperx_end": (
                    whisperx_word["end"]
                ),
                "whisperx_score": (
                    whisperx_word.get(
                        "score"
                    )
                ),
            }
        )

    matches.sort(
        key=lambda item: item[
            "whisper_start"
        ]
    )

    return matches


def calculate_metrics(
    matches: list[dict],
) -> dict:
    if not matches:
        raise ValueError(
            "No matching words found."
        )

    start_differences = [
        abs(
            match["whisper_start"]
            - match["whisperx_start"]
        )
        for match in matches
    ]

    end_differences = [
        abs(
            match["whisper_end"]
            - match["whisperx_end"]
        )
        for match in matches
    ]

    combined_differences = [
        (
            start_difference
            + end_difference
        )
        / 2
        for (
            start_difference,
            end_difference,
        ) in zip(
            start_differences,
            end_differences,
        )
    ]

    def percentage_within(
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
            start_differences
        ),
        "start_median": median(
            start_differences
        ),
        "end_mae": mean(
            end_differences
        ),
        "end_median": median(
            end_differences
        ),
        "combined_mae": mean(
            combined_differences
        ),
        "combined_median": median(
            combined_differences
        ),
        "within_50ms": (
            percentage_within(
                combined_differences,
                0.050,
            )
        ),
        "within_100ms": (
            percentage_within(
                combined_differences,
                0.100,
            )
        ),
        "within_250ms": (
            percentage_within(
                combined_differences,
                0.250,
            )
        ),
    }


def calculate_high_confidence_metrics(
    matches: list[dict],
    minimum_score: float = 0.75,
):
    filtered = [
        match
        for match in matches
        if (
            match["whisperx_score"]
            is not None
            and match[
                "whisperx_score"
            ]
            >= minimum_score
        )
    ]

    if not filtered:
        return None

    return calculate_metrics(
        filtered
    )


def print_metrics(
    title: str,
    metrics: dict,
):
    print()
    print(title)
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


def parse_arguments(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Whisper and WhisperX word timings.",
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
    whisper_words = load_whisper_words(
        arguments.whisper
    )

    whisperx_words = load_whisperx_words(
        arguments.whisperx
    )

    matches = match_words(
        whisper_words,
        whisperx_words,
    )

    print()
    print(
        "Whisper vs WhisperX Timing Comparison"
    )
    print("=" * 60)

    print(
        f"Whisper words: "
        f"{len(whisper_words)}"
    )

    print(
        f"WhisperX words: "
        f"{len(whisperx_words)}"
    )

    metrics = calculate_metrics(
        matches
    )

    print_metrics(
        "All matched words",
        metrics,
    )

    high_confidence = (
        calculate_high_confidence_metrics(
            matches,
            minimum_score=0.75,
        )
    )

    if high_confidence is not None:
        print_metrics(
            "High-confidence WhisperX words "
            "(score >= 0.75)",
            high_confidence,
        )

    print()
    print("First 15 matched words")
    print("=" * 60)

    for match in matches[:15]:
        start_difference = abs(
            match["whisper_start"]
            - match["whisperx_start"]
        )

        end_difference = abs(
            match["whisper_end"]
            - match["whisperx_end"]
        )

        print(
            {
                "word": match["word"],
                "whisper_start": round(
                    match[
                        "whisper_start"
                    ],
                    3,
                ),
                "whisperx_start": round(
                    match[
                        "whisperx_start"
                    ],
                    3,
                ),
                "start_diff_ms": round(
                    start_difference
                    * 1000,
                    2,
                ),
                "end_diff_ms": round(
                    end_difference
                    * 1000,
                    2,
                ),
                "whisperx_score": (
                    match[
                        "whisperx_score"
                    ]
                ),
            }
        )


if __name__ == "__main__":
    main()
